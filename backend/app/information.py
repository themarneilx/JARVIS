import asyncio
from collections import OrderedDict
from datetime import datetime,date
import html,json,math,os,re,secrets,time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
import httpx
from pydantic import BaseModel,ConfigDict,Field,field_validator,model_validator


class Place(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:int
    name:str=Field(min_length=1,max_length=100)
    country:str=Field(max_length=100)
    country_code:str=Field(pattern=r'^[A-Z]{2}$')
    latitude:float=Field(ge=-90,le=90,allow_inf_nan=False)
    longitude:float=Field(ge=-180,le=180,allow_inf_nan=False)
    timezone:str=Field(max_length=80)

    @field_validator('timezone')
    @classmethod
    def zone(cls,value):
        try:ZoneInfo(value)
        except (ZoneInfoNotFoundError,ValueError):raise ValueError('Choose a valid IANA timezone, such as Asia/Manila')
        return value


class OnlineSettings(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:Literal[1]=1
    enabled:bool=False
    timezone:str=Field(default='Asia/Manila',max_length=80)
    location:Place|None=None
    _zone=field_validator('timezone')(Place.zone.__func__)


class Lookup(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:Literal['search','news','weather','stocks','exchange_rates','time','location','map','directions']
    query:str=Field(default='',max_length=500)
    origin:str=Field(default='',max_length=200)
    symbol:str=Field(default='',max_length=20,pattern=r'^[A-Za-z0-9.^=-]*$')
    base:str=Field(default='USD',pattern=r'^[A-Z]{3}$')
    quote:str=Field(default='PHP',pattern=r'^[A-Z]{3}$')
    amount:float=Field(default=1,gt=0,le=1e12,allow_inf_nan=False)

    @model_validator(mode='after')
    def different_currencies(self):
        if self.kind=='exchange_rates' and self.base==self.quote:
            raise ValueError('Choose two different currencies. The default pair is USD/PHP, which reports both directions.')
        return self


def clean(value,limit=400):
    return ' '.join(re.sub(r'<[^>]*>|[\x00-\x1f\x7f]',' ',html.unescape(str(value or ''))).split())[:limit]


def safe_link(value):
    value=str(value or '')
    if re.search(r'[\s\x00-\x1f\x7f<>\\]',value):return ''
    parsed=urlparse(value)
    return value if parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password and len(value)<2000 else ''


def number(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError('The provider did not return a valid measurement')
    return value


class Information:
    def __init__(self,state,transport=None):
        self.path=state/'online-settings.json'
        self.config=OnlineSettings.model_validate_json(self.path.read_text()) if self.path.exists() else OnlineSettings()
        self.client=httpx.AsyncClient(timeout=httpx.Timeout(7,connect=3),trust_env=False,follow_redirects=False,transport=transport,headers={'User-Agent':'Jarvis-local-personal-assistant/1.0','Accept':'application/json, application/rss+xml'})
        self.cache=OrderedDict()
        self.presentations=OrderedDict()
        self.generation=0
        self.slots=asyncio.Semaphore(3)

    async def close(self):await self.client.aclose()

    def save(self,config):
        if self.path.is_symlink():raise ValueError('Online settings must be a private regular file')
        temporary=self.path.with_name('.online-'+secrets.token_hex(8))
        try:
            with os.fdopen(os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'w') as file:file.write(config.model_dump_json())
            os.replace(temporary,self.path)
        finally:temporary.unlink(missing_ok=True)
        self.config=config
        self.generation+=1
        self.cache.clear()
        self.presentations.clear()
        return config.model_dump()

    def permission(self):
        if not self.config.enabled:raise ValueError('Internet lookups are disabled. Enable them in Settings.')
        return {'enabled':True}

    async def fetch(self,provider,path='',params=None):
        self.permission()
        generation=self.generation
        hosts={'weather':'https://api.open-meteo.com/v1/forecast','geocode':'https://geocoding-api.open-meteo.com/v1/search','fx':'https://api.frankfurter.dev/v2/rate/','stocks':'https://query1.finance.yahoo.com/v8/finance/chart/','news':'https://news.google.com/rss/search','map_search':'https://nominatim.openstreetmap.org/search','route':'https://router.project-osrm.org/route/v1/driving/'}
        valid_path = re.fullmatch(r'-?\d{1,3}\.\d{6},-?\d{1,2}\.\d{6};-?\d{1,3}\.\d{6},-?\d{1,2}\.\d{6}',path) if provider=='route' else (not path or re.fullmatch(r'[A-Za-z0-9.^=/\-]{1,30}',path))
        if provider not in hosts or not valid_path or '..' in path:
            raise ValueError('Unsupported provider request')
        try:
            async with self.slots:
                self.permission()
                if generation!=self.generation:raise ValueError('Information settings changed; retry with the current defaults')
                async with asyncio.timeout(9):
                    async with self.client.stream('GET',hosts[provider]+path,params=params) as response:
                        response.raise_for_status()
                        body=bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body)>1048576:raise ValueError('Provider response exceeded its size limit')
                        if generation!=self.generation:raise ValueError('Information settings changed; retry with the current defaults')
                        return bytes(body)
        except (httpx.HTTPError,TimeoutError) as exc:
            raise ValueError('The information provider is unavailable or refused the lookup. Try again later.') from exc

    async def cities(self,query):
        query=clean(query,100)
        if len(query)<2:raise ValueError('Enter a city or town name')
        body=json.loads(await self.fetch('geocode',params={'name':query,'count':8,'language':'en','format':'json'}))
        places=[]
        for item in body.get('results',[])[:8]:
            try:places.append(Place(**{key:item.get(key) for key in Place.model_fields}).model_dump())
            except ValueError:continue
        return places

    def presentation(self,receipt):
        self.permission()
        item=self.presentations.get(receipt)
        if not item or item['expires']<time.time() or item['generation']!=self.generation:
            raise ValueError('This information view expired. Request a fresh report.')
        return item

    async def lookup(self,request):
        try:
            result=await self._lookup(request)
            if request.kind in ('news','stocks'):
                receipt='info-'+secrets.token_hex(12)
                self.presentations[receipt]={**result,'kind':request.kind,'receipt':receipt,'expires':time.time()+1800,'generation':self.generation}
                while len(self.presentations)>32:self.presentations.popitem(last=False)
                result={key:value for key,value in result.items() if key!='history'}
                if 'results' in result:result['results']=result['results'][:3]
                result['information_receipt']=receipt
            return result
        except (KeyError,IndexError,TypeError,ET.ParseError,OverflowError) as exc:
            raise ValueError('The provider returned incomplete or unsupported information. No result was invented.') from exc

    async def _lookup(self,request):
        kind=request.kind;zone=self.config.timezone
        now=datetime.now(ZoneInfo(zone))
        result={'source':'jarvis_online/v1','covered':[kind],'fetched_at':now.isoformat(),'cached':False}
        if kind=='time':return {**result,'verified_summary':f"It is {now.strftime('%I:%M %p, %A %d %B %Y')} in {zone}, according to this computer's clock.",'timezone':zone}
        place=self.config.location
        if kind=='location':
            summary=f'Your saved location is {clean(place.name)}, {clean(place.country)}; timezone {zone}. This is your configured city, not GPS tracking.' if place else 'No city is saved yet. Which city or town should I use for weather? You can set it in Settings.'
            return {**result,'verified_summary':summary,'location':place.model_dump() if place else None,'timezone':zone}
        self.permission()
        generation=self.generation
        key=(generation,request.model_dump_json())
        cached=self.cache.get(key)
        if cached and cached[0]>time.monotonic():return {**cached[1],'cached':True}
        if kind=='weather':
            if not place:raise ValueError('Set your city or town in Settings before requesting weather')
            data=json.loads(await self.fetch('weather',params={'latitude':place.latitude,'longitude':place.longitude,'current':'temperature_2m,apparent_temperature,weather_code,wind_speed_10m','daily':'temperature_2m_max,temperature_2m_min,precipitation_probability_max','timezone':zone,'forecast_days':3}))
            current=data['current'];daily=data['daily'];temperature=number(current.get('temperature_2m'))
            code=current.get('weather_code');condition={0:'clear',1:'mainly clear',2:'partly cloudy',3:'overcast',45:'foggy',48:'foggy',51:'light drizzle',53:'drizzle',55:'dense drizzle',61:'light rain',63:'rain',65:'heavy rain',80:'rain showers',81:'rain showers',82:'heavy showers',95:'thunderstorms',96:'thunderstorms with hail',99:'thunderstorms with hail'}.get(code,'conditions code '+str(code))
            forecast=[]
            for i,day in enumerate(daily.get('time',[])[:3]):
                low=number(daily['temperature_2m_min'][i]);high=number(daily['temperature_2m_max'][i]);rain=daily['precipitation_probability_max'][i]
                forecast.append({'date':day,'low_c':low,'high_c':high,'rain_probability_percent':rain})
            today=forecast[0] if forecast else None
            summary=f"{clean(place.name)}: {temperature:g}°C, {condition}."
            if today:
                summary+=f" Today {today['low_c']:g}–{today['high_c']:g}°C"
                if isinstance(today['rain_probability_percent'],(int,float)):summary+=f", rain probability {number(today['rain_probability_percent']):g}%"
                summary+='.'
            summary+=f" Open-Meteo model estimate as of {clean(current['time'],40)} ({zone})."
            result.update(provider='Open-Meteo',verified_summary=summary,url='https://open-meteo.com/',as_of=current['time'],location=place.model_dump(),current=current,forecast=forecast,timezone=zone)
            ttl=300
        elif kind=='exchange_rates':
            data=json.loads(await self.fetch('fx',request.base+'/'+request.quote))
            rate=number(data.get('rate'))
            if rate<=0 or str(data.get('base','')).upper()!=request.base or str(data.get('quote','')).upper()!=request.quote:raise ValueError('The exchange provider returned a different currency pair')
            as_of=date.fromisoformat(data['date']).isoformat()
            summary=f"{request.amount:g} {request.base} = {request.amount*rate:,.4f} {request.quote}; 1 {request.quote} = {1/rate:.6f} {request.base}. Frankfurter daily reference rate dated {as_of}; bank and cash rates may differ."
            result.update(provider='Frankfurter',verified_summary=summary,url='https://frankfurter.dev/',as_of=as_of,base=request.base,quote=request.quote,rate=rate,amount=request.amount,converted=request.amount*rate)
            ttl=3600
        elif kind=='stocks':
            if not request.symbol:raise ValueError('Specify a stock ticker, such as NVDA, AAPL or a supported exchange suffix')
            data=json.loads(await self.fetch('stocks',request.symbol.upper(),{'range':'1d','interval':'1m'}))
            chart=data['chart']['result'][0];meta=chart['meta'];price=number(meta.get('regularMarketPrice'))
            at=datetime.fromtimestamp(number(meta.get('regularMarketTime')),ZoneInfo(zone)).isoformat()
            symbol=clean(meta.get('symbol'),20);currency=clean(meta.get('currency'),8)
            summary=f"{symbol}: {price:g} {currency}, last reported regular-market trade {at}. Yahoo Finance data may be delayed; this is not a live trading quote."
            history=[]
            quotes=chart.get('indicators',{}).get('quote',[{}])
            closes=quotes[0].get('close',[]) if quotes else []
            for timestamp,close in zip(chart.get('timestamp',[])[:1500],closes[:1500]):
                try:
                    history.append({'at':datetime.fromtimestamp(number(timestamp),ZoneInfo(zone)).isoformat(),'price':number(close)})
                except (ValueError,TypeError,OverflowError):continue
            if len(history)>120:
                stride=math.ceil(len(history)/119)
                history=history[::stride]+([history[-1]] if history[-1] not in history[::stride] else [])
            result.update(history=history,provider='Yahoo Finance (unofficial read endpoint)',verified_summary=summary,url='https://finance.yahoo.com/quote/'+symbol+'/',as_of=at,symbol=symbol,price=price,currency=currency)
            ttl=60
        elif kind=='news':
            query=clean(request.query or (place.name if place else 'Philippines'),500)
            body=await self.fetch('news',params={'q':query,'hl':'en-PH','gl':'PH','ceid':'PH:en'})
            if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():raise ValueError('Unsupported news feed')
            items=[]
            for node in ET.fromstring(body).findall('./channel/item')[:30]:
                link=safe_link(node.findtext('link'))
                if link:items.append({'title':clean(node.findtext('title'),220),'url':link,'published':clean(node.findtext('pubDate'),80),'publisher':clean(node.findtext('source'),80)})
            if not items:raise ValueError('No news headlines were returned for that search')
            def published(item):
                try:return parsedate_to_datetime(item['published']).timestamp()
                except (ValueError,TypeError,OverflowError):return 0
            items=sorted(items,key=published,reverse=True)[:12]
            summary='Matching headlines from Google News RSS: '+ ' '.join(f"{i+1}. {item['title']} ({item['published']})." for i,item in enumerate(items[:3]))+' Headlines only; full articles have not been read.'
            result.update(provider='Google News RSS',verified_summary=summary,results=items,query=query)
            ttl=300
        else:raise ValueError('General search uses the native Hermes DDGS provider. Ask Jarvis to search the web.')
        result['verified_summary']=result['verified_summary'][:1800]
        if generation!=self.generation:raise ValueError('Information settings changed; retry with the current defaults')
        self.cache[key]=(time.monotonic()+ttl,result)
        self.cache.move_to_end(key)
        while len(self.cache)>128:self.cache.popitem(last=False)
        return result
