import asyncio
import json
import time
import httpx
import pytest
from app.information import Information, Lookup, OnlineSettings
from app.maps import Maps, MapSelection
from app.hermes import online_kinds


def test_map_intents_do_not_replace_saved_location():
    assert online_kinds('Where is Mactan Airport?') == {'map'}
    assert online_kinds('Show Mandaue on the map') == {'map'}
    assert online_kinds('Give me directions to Mactan Airport') == {'directions'}
    assert online_kinds("What's my location?") == {'location'}
    assert online_kinds('Where is the setting to change your voice?') == set()
    assert online_kinds('locate cebu') == {'map'}
    assert online_kinds('where is bohol') == {'map'}
    assert online_kinds('where is manila') == {'map'}
    assert online_kinds('where is my file') == set()
    assert online_kinds('locate ~/Downloads/report.txt') == set()


def test_map_choices_routes_consent_and_expiry(tmp_path):
    async def run():
        calls = []
        def handler(request):
            calls.append(request)
            assert 'authorization' not in request.headers
            if request.url.host == 'nominatim.openstreetmap.org':
                return httpx.Response(200, json=[
                    {'lat': '10.3', 'lon': '123.9', 'display_name': 'Airport, Cebu'},
                    {'lat': '10.4', 'lon': '124.0', 'display_name': 'Airport, other place'},
                ])
            assert request.url.host == 'router.project-osrm.org'
            assert request.url.path == '/route/v1/driving/123.900000,10.300000;123.900000,10.300000'
            return httpx.Response(200, json={'code': 'Ok', 'routes': [{'distance': 1200, 'duration': 180,
                'geometry': {'coordinates': [[123.9, 10.3], [123.91, 10.31]]}}]})
        info = Information(tmp_path, transport=httpx.MockTransport(handler))
        maps = Maps(info)
        try:
            with pytest.raises(ValueError, match='disabled'):
                await maps.lookup(Lookup(kind='map', query='Airport'))
            assert not calls
            info.save(OnlineSettings(enabled=True, location={'id': 1, 'name': 'Mandaue', 'country': 'Philippines', 'country_code': 'PH', 'latitude': 10.3, 'longitude': 123.9, 'timezone': 'Asia/Manila'}))
            receipt = await maps.lookup(Lookup(kind='directions', query='Airport'))
            assert 'coordinates' not in json.dumps(receipt)
            view = maps.get(receipt['map_receipt'])
            assert view['route'] is None and view['confirm_origin'] is True
            assert len(calls) == 1
            await maps.lookup(Lookup(kind='map', query='Airport'))
            assert len(calls) == 1  # Geocoding cache applies to repeated user/tool calls.
            with pytest.raises(ValueError, match='destinations'):
                await maps.select(MapSelection(receipt=view['receipt'], destination=4))
            selected = await maps.select(MapSelection(receipt=view['receipt'], destination=0))
            assert selected['route']['distance_m'] == 1200 and len(calls) == 2
            assert selected['receipt'] != view['receipt']
            maps.views[selected['receipt']]['expires'] = time.time() - 1
            with pytest.raises(ValueError, match='expired'): maps.get(selected['receipt'])
            info.save(OnlineSettings(enabled=False))
            with pytest.raises(ValueError, match='disabled'): maps.get(view['receipt'])
            info.save(OnlineSettings(enabled=True))
            with pytest.raises(ValueError, match='changed'): maps.get(view['receipt'])
        finally: await info.close()
    asyncio.run(run())


def test_bad_place_coordinates_and_untrusted_route_paths(tmp_path):
    async def run():
        info = Information(tmp_path, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[{'lat': 'nan', 'lon': '1800', 'display_name': 'Invalid'}])))
        info.save(OnlineSettings(enabled=True))
        try:
            with pytest.raises(ValueError, match='No matching'):
                await Maps(info).lookup(Lookup(kind='map', query='Place'))
            for path in ['http://127.0.0.1', '../secret', '1,2;3,4?url=localhost']:
                with pytest.raises(ValueError, match='Unsupported'): await info.fetch('route', path)
        finally: await info.close()
    asyncio.run(run())


def test_map_receipts_only_come_from_current_successful_native_tools():
    from app.hermes import map_receipt
    receipt = 'map-' + 'a' * 24
    row = {'role': 'tool', 'tool_name': 'jarvis_online', 'content': json.dumps({'source': 'jarvis_online/v1', 'covered': ['map'], 'map_receipt': receipt})}
    assert map_receipt([{'role': 'user', 'content': 'Locate the airport'}, row]) == receipt
    assert map_receipt([row, {'role': 'user', 'content': 'Another question'}]) is None
    assert map_receipt([{'role': 'user'}, {**row, 'role': 'assistant'}]) is None
    assert map_receipt([{'role': 'user'}, {**row, 'tool_name': 'jarvis_telemetry'}]) is None
