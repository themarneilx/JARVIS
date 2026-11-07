"""Bounded public place/route lookups; geometry stays out of native prompts."""
import asyncio
from collections import OrderedDict
import json
import secrets
import time
from pydantic import BaseModel, ConfigDict, Field
from .information import clean, number


class MapSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    receipt: str = Field(pattern=r'^map-[a-f0-9]{24}$')
    destination: int = Field(ge=0, le=4)
    origin: int = Field(default=0, ge=0, le=4)


class Maps:
    def __init__(self, information):
        self.info = information
        self.views = OrderedDict()
        self.geocodes = OrderedDict()
        self.lock = asyncio.Lock()
        self.last_search = 0

    def check(self, generation):
        self.info.permission()
        if generation != self.info.generation:
            raise ValueError('Information settings changed. Repeat the map request.')

    async def places(self, query):
        query = clean(query, 200)
        if len(query) < 2:
            raise ValueError('Name a place to locate on the map.')
        generation = self.info.generation
        async with self.lock:
            self.check(generation)
            cached = self.geocodes.get(query.casefold())
            if cached and cached[0] > time.monotonic():
                return cached[1]
            await asyncio.sleep(max(0, 1.1 - (time.monotonic() - self.last_search)))
            self.check(generation)
            self.last_search = time.monotonic()
            data = json.loads(await self.info.fetch('map_search', params={
                'q': query, 'format': 'jsonv2', 'limit': 5, 'addressdetails': 0,
            }))
            if not isinstance(data, list):
                raise ValueError('The map provider returned an invalid result.')
            results = []
            for item in data[:5]:
                try:
                    lat, lon = float(item['lat']), float(item['lon'])
                    if not (-90 <= number(lat) <= 90 and -180 <= number(lon) <= 180):
                        continue
                    results.append({'label': clean(item['display_name'], 220), 'lat': lat, 'lon': lon})
                except (KeyError, TypeError, ValueError):
                    continue
            if not results:
                raise ValueError('No matching place was found. Add the city or country and try again.')
            self.geocodes[query.casefold()] = (time.monotonic() + 86400, results)
            while len(self.geocodes) > 128:
                self.geocodes.popitem(last=False)
            return results

    def store(self, view, generation):
        self.check(generation)
        receipt = 'map-' + secrets.token_hex(12)
        view = {**view, 'receipt': receipt, 'attribution': '© OpenStreetMap contributors',
                'generation': generation, 'expires': time.time() + 1800}
        self.views[receipt] = view
        while len(self.views) > 32:
            self.views.popitem(last=False)
        return view

    def get(self, receipt):
        self.info.permission()
        view = self.views.get(receipt)
        if not view or view['expires'] < time.time():
            raise ValueError('Map result expired. Ask Jarvis to locate the place again.')
        self.check(view['generation'])
        return view

    async def lookup(self, request):
        generation = self.info.generation
        self.check(generation)
        saved = self.info.config.location
        if request.kind == 'map' and not request.query.strip() and saved:
            destinations = [{'label': saved.name + ', ' + saved.country + ' (saved city, not GPS)',
                             'lat': saved.latitude, 'lon': saved.longitude}]
        else:
            destinations = await self.places(request.query)
        origins = []
        needs_origin_confirmation = False
        if request.kind == 'directions':
            if request.origin.strip():
                origins = await self.places(request.origin)
            elif saved:
                origins = [{'label': saved.name + ', ' + saved.country + ' (city centre, not GPS)',
                            'lat': saved.latitude, 'lon': saved.longitude}]
                needs_origin_confirmation = True
        view = self.store({'kind': request.kind, 'destinations': destinations, 'origins': origins,
                           'route': None, 'selected_destination': None, 'selected_origin': None,
                           'confirm_origin': needs_origin_confirmation}, generation)
        if request.kind == 'directions' and len(destinations) == len(origins) == 1 and not needs_origin_confirmation:
            view = await self.select(MapSelection(receipt=view['receipt'], destination=0, origin=0))
        elif request.kind == 'map' and len(destinations) == 1:
            view['selected_destination'] = 0
        if view['route']:
            route = view['route']
            summary = f"Driving route: {route['distance_m']/1000:.1f} km, approximately {route['duration_s']/60:.0f} minutes. OSRM estimate, without live traffic. The route is displayed on the map."
        elif request.kind == 'directions':
            summary = 'Choose the destination and confirm the starting point in the map panel. The saved city is not your GPS position.'
            if not origins:
                summary = 'Please specify a starting place and destination for directions. No GPS position is available.'
        else:
            summary = f"Located {destinations[0]['label']}. The map is open." if len(destinations) == 1 else 'Several places match. Select the intended place in the map panel before zooming in.'
        return {'source': 'jarvis_online/v1', 'covered': [request.kind],
                'provider': 'OpenStreetMap / OSRM', 'url': 'https://www.openstreetmap.org/copyright',
                'verified_summary': summary, 'map_receipt': view['receipt']}

    async def select(self, selection):
        original = self.get(selection.receipt)
        generation = original['generation']
        if selection.destination >= len(original['destinations']):
            raise ValueError('Choose one of the returned destinations.')
        view = {**original, 'selected_destination': selection.destination}
        if view['kind'] == 'directions':
            if selection.origin >= len(view['origins']):
                raise ValueError('Specify the starting place before requesting a route.')
            start, end = view['origins'][selection.origin], view['destinations'][selection.destination]
            coordinates = f"{start['lon']:.6f},{start['lat']:.6f};{end['lon']:.6f},{end['lat']:.6f}"
            data = json.loads(await self.info.fetch('route', coordinates, {
                'overview': 'simplified', 'geometries': 'geojson', 'steps': 'false', 'alternatives': 'false',
            }))
            if data.get('code') != 'Ok' or not data.get('routes'):
                raise ValueError('No driving route was returned for those places.')
            route = data['routes'][0]
            geometry = route.get('geometry', {}).get('coordinates', [])
            if not 2 <= len(geometry) <= 12000:
                raise ValueError('The route geometry is missing or too large.')
            points = []
            for point in geometry:
                if not isinstance(point, list) or len(point) != 2 or not -180 <= number(point[0]) <= 180 or not -90 <= number(point[1]) <= 90:
                    raise ValueError('The provider returned invalid route coordinates.')
                points.append(point)
            distance, duration = number(route['distance']), number(route['duration'])
            if distance < 0 or duration < 0:
                raise ValueError('The provider returned invalid route measurements.')
            view.update(selected_origin=selection.origin, confirm_origin=False,
                        route={'coordinates': points, 'distance_m': distance, 'duration_s': duration})
        return self.store(view, generation)
