"""Prepare native empty memory files and queue local candidates for browser review."""
import asyncio
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.config import Settings
from app.memory import MemoryManager,fingerprint
from app.runtime import profile_home


async def main():
    settings=Settings()
    home=profile_home(ROOT,str(settings.hermes_home))
    directory=home/'memories'
    directory.mkdir(mode=0o700,exist_ok=True)
    for name in ('USER.md','MEMORY.md'):
        (directory/name).touch(mode=0o600,exist_ok=True)
    path=ROOT/'.runtime/memory-candidates.json'
    if not path.exists():
        print('Native USER.md and MEMORY.md are ready. Add proposals in the browser Memory panel.')
        return
    manager=MemoryManager(settings)
    queued=0
    for candidate in json.loads(path.read_text()):
        inventory=await manager.inventory()
        with manager.db() as db:
            deleted=db.execute('SELECT 1 FROM metadata WHERE hash=? AND deleted=1',(fingerprint(candidate['content']),)).fetchone()
        if deleted or any(e['text']==candidate['content'] for e in inventory['entries']+inventory['pending'] if 'text' in e):continue
        if any(e.get('content')==candidate['content'] for e in inventory['pending']):continue
        await manager.propose({'action':'add',**candidate})
        queued+=1
    print(f'Queued {queued} native memory proposals for browser review. No preference was saved without approval.')


asyncio.run(main())
