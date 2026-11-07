import asyncio,json
import httpx,pytest
from app.config import Settings
from app.hermes import HermesClient,HermesError

@pytest.mark.parametrize('block',[{'host':'0.0.0.0'},{'model_routes':{'hermes-agent':{'provider':'openrouter','model':'remote'}}}])
def test_public_bind_or_cloud_routes_fail_closed(tmp_path,block):
    async def run():
        home=tmp_path/'profile';home.mkdir()
        (home/'config.yaml').write_text(json.dumps({'model':{'provider':'custom','base_url':'http://127.0.0.1:11434/v1'},'platform_toolsets':{'api_server':['jarvis_desktop','no_mcp']},'plugins':{'enabled':['jarvis_desktop']},'gateway':{'api_server':block},'auxiliary':{'background_review':{'enabled':False}}}))
        client=HermesClient(Settings(state_dir=tmp_path,hermes_home=home,hermes_key='test'),httpx.MockTransport(lambda r:httpx.Response(200,json={})))
        try:
            with pytest.raises(HermesError):await client.preflight()
        finally:await client.close()
    asyncio.run(run())
