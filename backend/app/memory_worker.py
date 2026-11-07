"""Compatibility boundary for Hermes' native memory tooling. Never writes files itself."""
import contextlib
import json
import sys


def main():
    payload=json.load(sys.stdin)
    with contextlib.redirect_stdout(sys.stderr):
        from tools.memory_tool import load_on_disk_store, apply_memory_pending
        store=load_on_disk_store()
        if payload['action']=='read':
            result={'success':True,'user':store.user_entries,'memory':store.memory_entries,'limits':{'user':store.user_char_limit,'memory':store.memory_char_limit}}
        elif payload.get('approved') is True and payload['action'] in ('add','patch','remove'):
            if payload['action'] in ('patch','remove'):
                payload['matched_entry']=payload['old_text']
            result=apply_memory_pending(payload,store)
        else:
            result={'success':False,'error':'An exact browser-approved proposal is required'}
    json.dump(result,sys.stdout)


if __name__=='__main__':
    main()
