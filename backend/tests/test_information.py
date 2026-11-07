import asyncio,json
import httpx,pytest
from app.information import Information,Lookup,OnlineSettings


def test_online_requires_consent_and_time_stays_local(tmp_path):
    async def run():
        calls=[]
        def handler(r):calls.append(r);return httpx.Response(200,json={})
        service=Information(tmp_path,transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(ValueError,match='disabled'):await service.lookup(Lookup(kind='weather'))
            assert (await service.lookup(Lookup(kind='time')))['covered']==['time']
            assert not calls
        finally:await service.close()
    asyncio.run(run())


def test_exchange_uses_fixed_destination_and_reference_date_cache(tmp_path):
    async def run():
        calls=[]
        def handler(r):
            calls.append(r)
            assert str(r.url)=='https://api.frankfurter.dev/v2/rate/USD/PHP'
            assert 'authorization' not in r.headers
            return httpx.Response(200,json={'date':'2026-11-04','base':'USD','quote':'PHP','rate':63.46})
        service=Information(tmp_path,transport=httpx.MockTransport(handler))
        service.save(OnlineSettings(enabled=True))
        try:
            first=await service.lookup(Lookup(kind='exchange_rates'))
            second=await service.lookup(Lookup(kind='exchange_rates'))
            assert len(calls)==1 and second['cached']
            assert '2026-11-04' in first['verified_summary'] and 'reference' in first['verified_summary']
            assert first['source']=='jarvis_online/v1'
            assert service.client.follow_redirects is False
        finally:await service.close()
    asyncio.run(run())


def test_lookup_validation_refuses_urls_in_symbols_and_nonfinite_amounts():
    from app.information import safe_link
    assert not safe_link('https://example.org/\nInjected content')
    assert not safe_link('javascript:alert(1)')
    assert safe_link('https://example.org/report?q=test')
    for body in [{'kind':'stocks','symbol':'../127.0.0.1'}, {'kind':'exchange_rates','base':'USD/..'}, {'kind':'exchange_rates','base':'USD','quote':'USD'}, {'kind':'exchange_rates','amount':float('nan')},{'kind':'weather','url':'http://localhost'}]:
        with pytest.raises(ValueError):Lookup(**body)
    with pytest.raises(ValueError):OnlineSettings(timezone='Bad/Unknown')


def test_weather_requires_location_and_marks_model_estimate(tmp_path):
    async def run():
        def handler(r):
            assert r.url.host=='api.open-meteo.com'
            return httpx.Response(200,json={'current':{'time':'2026-11-05T00:15','temperature_2m':27.2,'apparent_temperature':31.0,'weather_code':3,'wind_speed_10m':8.2},'daily':{'time':['2026-11-05'],'temperature_2m_max':[32],'temperature_2m_min':[25],'precipitation_probability_max':[65]}})
        service=Information(tmp_path,transport=httpx.MockTransport(handler));service.save(OnlineSettings(enabled=True))
        try:
            with pytest.raises(ValueError,match='city'):await service.lookup(Lookup(kind='weather'))
            config=OnlineSettings(enabled=True,location={'id':1,'name':'Test City','country':'Philippines','country_code':'PH','latitude':10.3,'longitude':123.9,'timezone':'Asia/Manila'})
            service.save(config)
            result=await service.lookup(Lookup(kind='weather'))
            assert 'Test City' in result['verified_summary'] and '27.2' in result['verified_summary'] and 'estimate' in result['verified_summary']
            assert '65%' in result['verified_summary']
            assert (tmp_path/'online-settings.json').stat().st_mode&0o077==0
        finally:await service.close()
    asyncio.run(run())


def test_redirects_and_oversized_responses_fail_closed(tmp_path):
    async def run():
        for response in [httpx.Response(302,headers={'location':'http://127.0.0.1:8642'}),httpx.Response(200,content=b'x'*1048577)]:
            service=Information(tmp_path,transport=httpx.MockTransport(lambda r:response));service.save(OnlineSettings(enabled=True))
            try:
                with pytest.raises(ValueError):await service.lookup(Lookup(kind='exchange_rates'))
            finally:await service.close()
    asyncio.run(run())


def test_desktop_receipts_cannot_answer_online_questions(tmp_path):
    from app.hermes import HermesClient,HermesError,online_kinds
    from app.config import Settings
    assert online_kinds("What's the current exchange rate to the US dollar?")=={'exchange_rates'}
    assert online_kinds("What's the weather like today?")=={'weather'}
    assert online_kinds("What's my location?")=={'location'}
    assert online_kinds('What is the weather and current USD/PHP exchange rate?')=={'weather','exchange_rates'}
    async def run():
        def handler(r):
            if r.method=='GET':return httpx.Response(200,json={'data':[{'role':'user','content':'weather'},{'role':'tool','content':json.dumps({'source':'jarvis_desktop/v1','covered':['network'],'verified_summary':'Network is active.'})}]})
            return httpx.Response(200,text='data: {"choices":[{"delta":{"content":"It is sunny based on network usage"}}]}\n\ndata: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n')
        client=HermesClient(Settings(state_dir=tmp_path),httpx.MockTransport(handler))
        try:
            with pytest.raises(HermesError,match='unverified'):
                [event async for event in client.stream("What's the weather today?",'session','request')]
        finally:await client.close()
    asyncio.run(run())


def test_online_evidence_and_source_links_survive_refresh(tmp_path):
    from app.hermes import HermesClient
    from app.config import Settings
    async def run():
        rows=[{'role':'user','content':'Current exchange rate?'},{'role':'tool','tool_name':'jarvis_online','content':json.dumps({'source':'jarvis_online/v1','covered':['exchange_rates'],'verified_summary':'Dated daily reference rate.','provider':'Frankfurter','url':'https://frankfurter.dev/'})},{'role':'assistant','content':'Model invented an intraday quote.'}]
        def handler(r):
            if r.method=='GET':return httpx.Response(200,json={'data':rows})
            return httpx.Response(200,text='data: {"choices":[{"delta":{"content":"Model invented an intraday quote."}}]}\n\ndata: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n')
        client=HermesClient(Settings(state_dir=tmp_path),httpx.MockTransport(handler))
        try:
            events=[e async for e in client.stream('Current exchange rate?','session','request')]
            text=''.join(e.get('text','') for e in events if e['type']=='delta')
            assert text=='Dated daily reference rate. Sources: [Frankfurter](https://frankfurter.dev/).'
            assert (await client.history('session'))[-1]['text']==text
        finally:await client.close()
    asyncio.run(run())


def test_settings_change_discards_inflight_city_response(tmp_path):
    async def run():
        entered=asyncio.Event();release=asyncio.Event()
        async def handler(request):
            entered.set();await release.wait()
            return httpx.Response(200,json={'date':'2026-11-04','base':'USD','quote':'PHP','rate':63.46})
        service=Information(tmp_path,transport=httpx.MockTransport(handler));service.save(OnlineSettings(enabled=True))
        try:
            task=asyncio.create_task(service.lookup(Lookup(kind='exchange_rates')))
            await entered.wait();service.save(OnlineSettings(enabled=True,timezone='UTC'));release.set()
            with pytest.raises(ValueError,match='settings changed'):await task
            assert not service.cache
            result=await service.lookup(Lookup(kind='exchange_rates'))
            assert not result['cached']
        finally:await service.close()
    asyncio.run(run())


def test_disabling_consent_blocks_already_queued_http_calls(tmp_path):
    async def run():
        calls=[]
        service=Information(tmp_path,transport=httpx.MockTransport(lambda r:calls.append(r) or httpx.Response(200,json={})))
        service.save(OnlineSettings(enabled=True))
        for _ in range(3):await service.slots.acquire()
        task=asyncio.create_task(service.lookup(Lookup(kind='exchange_rates')))
        await asyncio.sleep(0)
        service.save(OnlineSettings(enabled=False));service.slots.release()
        try:
            with pytest.raises(ValueError,match='disabled'):await task
            assert not calls
        finally:await service.close()
    asyncio.run(run())


def test_stock_chart_receipt_keeps_samples_out_of_native_prompt(tmp_path):
    async def run():
        data={'chart':{'result':[{'meta':{'symbol':'NVDA','currency':'USD','regularMarketPrice':150,'regularMarketTime':1700000200},'timestamp':[1700000000,1700000060,1700000120],'indicators':{'quote':[{'close':[149.0,None,150.0]}]}}]}}
        service=Information(tmp_path,transport=httpx.MockTransport(lambda r:httpx.Response(200,json=data)))
        service.save(OnlineSettings(enabled=True))
        try:
            result=await service.lookup(Lookup(kind='stocks',symbol='NVDA'))
            assert 'history' not in result
            view=service.presentation(result['information_receipt'])
            assert view['kind']=='stocks' and len(view['history'])==2
            assert view['history'][0]['price']==149.0
            service.save(OnlineSettings(enabled=False))
            with pytest.raises(ValueError,match='disabled'):service.presentation(result['information_receipt'])
        finally:await service.close()
    asyncio.run(run())


def test_information_receipts_require_current_native_news_or_stock_result():
    from app.hermes import information_receipt
    receipt='info-'+'b'*24
    row={'role':'tool','tool_name':'jarvis_online','content':json.dumps({'source':'jarvis_online/v1','covered':['news'],'information_receipt':receipt})}
    assert information_receipt([{'role':'user'},row],'information')==receipt
    assert information_receipt([row,{'role':'user'}],'information') is None
    assert information_receipt([{'role':'user'},{**row,'tool_name':'jarvis_home_files'}],'information') is None


def test_grammar_articles_do_not_force_news_search():
    from app.hermes import online_kinds
    assert online_kinds('Explain definite and indefinite articles') == set()
    assert online_kinds('Find recent articles about Cebu') == {'news'}
