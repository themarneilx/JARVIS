"""Exercise the real Hermes memory bridge in a disposable, isolated profile."""
import asyncio
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.config import Settings
from app.memory import MemoryManager
from app.runtime import discover_runtime


async def main():
    runtime = discover_runtime(ROOT)
    with tempfile.TemporaryDirectory(prefix='memory-check-', dir=ROOT / '.runtime') as temporary:
        root = Path(temporary)
        home = root / 'hermes'
        home.mkdir()
        shutil.copyfile(ROOT / 'hermes/runtime/config.yaml', home / 'config.yaml')
        shutil.copyfile(ROOT / 'hermes/SOUL.md', home / 'SOUL.md')
        settings = Settings(state_dir=root / 'app', hermes_home=home, hermes_python=str(runtime.python), hermes_source=str(runtime.source))
        manager = MemoryManager(settings)
        original = {'action': 'add', 'target': 'user', 'content': 'Integration fixture: prefers concise diagnostic reports.', 'reason': 'Disposable integration fixture, never a live user preference'}
        proposal = await manager.propose(original)
        assert not (await manager.inventory())['entries'], 'An unapproved proposal wrote memory'
        await manager.resolve(proposal['id'], True)
        fresh = MemoryManager(settings)
        entries = (await fresh.inventory())['entries']
        assert len(entries) == 1 and entries[0]['text'] == original['content']
        try:
            await fresh.propose(original)
        except ValueError:
            pass
        else:
            raise AssertionError('Duplicate memory accepted')
        changed = 'Integration fixture: prefers detailed diagnostic reports.'
        proposal = await fresh.propose({**original, 'action': 'patch', 'old_text': original['content'], 'content': changed})
        await fresh.resolve(proposal['id'], True)
        assert (await MemoryManager(settings).inventory())['entries'][0]['text'] == changed
        proposal = await fresh.propose({**original, 'action': 'remove', 'old_text': changed, 'content': ''})
        await fresh.resolve(proposal['id'], True)
        assert not (await MemoryManager(settings).inventory())['entries']
        try:
            await fresh.propose({**original, 'content': changed}, automatic=True)
        except ValueError:
            pass
        else:
            raise AssertionError('Deleted memory resurrected')
        assert (home / 'SOUL.md').read_bytes() == (ROOT / 'hermes/SOUL.md').read_bytes()
    result = {'mocked': False, 'hermes_version': runtime.version, 'isolated_profile': True, 'approved_write': True, 'fresh_process_retrieval': True, 'edit': True, 'deletion': True, 'duplicates_refused': True, 'deleted_suggestions_refused': True, 'identity_preserved': True}
    (ROOT / '.runtime/memory-check.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


asyncio.run(main())
