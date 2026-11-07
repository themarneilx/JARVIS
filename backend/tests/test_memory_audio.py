import asyncio
import pytest
from app.config import Settings
from app.memory import MemoryManager
from app.audio import speech_text,validate_audio


def test_native_memory_review_edit_delete_dedup_and_tombstone(tmp_path):
    # Contract test with an in-memory bridge; does not prove installed Hermes integration.
    stores={'user':[],'memory':[]}
    async def bridge(p):
        if p['action']=='read':return {'success':True,**stores}
        target=stores[p['target']]
        if p['action']=='add':target.append(p['content'])
        else:
            assert p['old_text'] in target
            i=target.index(p['old_text'])
            if p['action']=='patch':target[i]=p['content']
            else:target.pop(i)
        return {'success':True}
    async def run():
        m=MemoryManager(Settings(state_dir=tmp_path),bridge)
        p={'action':'add','target':'user','content':'Prefers concise explanations.','reason':'User explicitly stated a stable style preference'}
        suggestion=await m.propose(p)
        assert not stores['user']
        await m.resolve(suggestion['id'],True)
        with pytest.raises(ValueError):await m.propose(p)
        entry=(await m.inventory())['entries'][0]
        m.pin(entry['id'],True)
        removal={**p,'action':'remove','old_text':p['content'],'content':''}
        with pytest.raises(ValueError):await m.propose(removal,automatic=True)
        proposal=await m.propose(removal)
        await m.resolve(proposal['id'],True)
        assert not stores['user']
        with pytest.raises(ValueError):await m.propose(p,automatic=True)
        assert m.epoch==2
        history=(await m.inventory())['history']
        assert all('text' not in h for h in history)
    asyncio.run(run())


def test_memory_rejects_secrets_and_disabled_suggestions(tmp_path):
    async def run():
        async def bridge(p):return {'success':True,'user':[],'memory':[]}
        m=MemoryManager(Settings(state_dir=tmp_path),bridge)
        with pytest.raises(ValueError):await m.propose({'action':'add','target':'user','content':'password=hunter2','reason':'secret'})
        with pytest.raises(ValueError):await m.propose({'action':'add','target':'user','content':'{"api_key": "not-for-memory"}','reason':'explicit'})
        m.suggestions(False)
        with pytest.raises(ValueError):await m.propose({'action':'add','target':'user','content':'Prefers tea','reason':'explicit'},automatic=True)
    asyncio.run(run())


def test_repeating_a_pending_fact_reuses_the_review_without_changing_its_snapshot(tmp_path):
    async def run():
        async def bridge(p):return {'success':True,'user':[],'memory':[]}
        manager=MemoryManager(Settings(state_dir=tmp_path),bridge)
        payload={'action':'add','target':'user','content':"User's name is Alex.",'reason':'User explicitly asked to remember their name'}
        first=await manager.propose(payload)
        second=await manager.propose({**payload,'reason':'A differently worded rationale'},automatic=True)
        assert first==second
        assert len(manager.pending())==1
        assert (await manager.inventory())['proposal_states'][first['id']]=='pending'
        await manager.resolve(first['id'],False)
        assert (await manager.inventory())['proposal_states'][first['id']]=='rejected'
    asyncio.run(run())


def test_speech_normalization_omits_code_markup_credentials():
    text=speech_text('# Report\n**Ready**. [details](https://example.org)\n```sh\nrm -rf /\n```\napi_key=private123')
    assert 'rm -rf' not in text and '```' not in text and 'private123' not in text
    assert 'Ready' in text and 'details' in text


def test_quoted_configuration_and_header_credentials_are_redacted():
    from app.memory import redact
    for text in ['{"api_key": "example-sensitive-value"}',"password = 'secret with spaces'",'Authorization: Bearer header-secret-value']:
        result=redact(text)
        assert not any(value in result for value in ('example-sensitive-value','secret with spaces','header-secret-value'))


def test_audio_signatures_and_limits():
    assert validate_audio(b'\x1aE\xdf\xa3payload','audio/webm;codecs=opus')=='.webm'
    with pytest.raises(ValueError):validate_audio(b'OggSbad','audio/webm')
    with pytest.raises(ValueError):validate_audio(b'RIFF' + b'0'*(13*1024*1024),'audio/wav')
