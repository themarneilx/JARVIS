#!/usr/bin/env python3
"""Prepare a dedicated Hermes home without replacing global identity or configuration."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model')
    args=parser.parse_args()
    home=ROOT/'hermes/runtime'
    if home.exists() and any(home.iterdir()):
        sys.exit('Runtime profile already exists. Review it manually; refusing to overwrite identity or configuration.')
    model=args.model
    if not model:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:11434/api/tags',timeout=4) as r:
            rows=json.load(r)['models']
        candidates=[m['name'] for m in rows if m['name']=='jarvis-qwen35-4b-64k:latest']
        if not candidates:
            candidates=[m['name'] for m in rows if 'qwen3.5' in m['name'].lower()]
        if len(candidates)!=1: sys.exit('Model discovery is ambiguous. Supply --model with the exact verified local tag.')
        model=candidates[0]
    if not model or '\n' in model: sys.exit('Invalid model tag')
    home.mkdir(parents=True,mode=0o700,exist_ok=True)
    state=ROOT/'.runtime';state.mkdir(mode=0o700,exist_ok=True)
    sys.path.insert(0,str(ROOT/'backend'))
    from app.config import private_secret
    key=private_secret(state/'hermes.token');plugin=private_secret(state/'plugin.token')
    shutil.copyfile(ROOT/'hermes/SOUL.md',home/'SOUL.md')
    (home/'plugins').mkdir(mode=0o700)
    shutil.copytree(ROOT/'hermes/plugins/jarvis_desktop',home/'plugins/jarvis_desktop',ignore=shutil.ignore_patterns('__pycache__'))
    config=json.dumps({
        'model':{'provider':'custom','base_url':'http://127.0.0.1:11434/v1','default':model,'context_length':64000,'ollama_num_ctx':64000},
        'platform_toolsets':{'api_server':['jarvis_desktop','no_mcp'],'cli':['jarvis_desktop','no_mcp']},
        'plugins':{'enabled':['jarvis_desktop'],'auto_update_check_hours':0},
        'tools':{'tool_search':{'enabled':False}},
        'memory':{'memory_enabled':True,'user_profile_enabled':True,'memory_char_limit':2200,'user_char_limit':1375,'write_approval':True},
        'skills':{'write_approval':True},'fallback_providers':[],
        'auxiliary':{'background_review':{'enabled':False}},
        'gateway':{'platforms':{'api_server':{'enabled':True,'host':'127.0.0.1','port':8642,'max_concurrent_runs':1,'tool_progress_events':True}}}
    },indent=2)+'\n'
    (home/'config.yaml').write_text(config)
    env='\n'.join(['API_SERVER_ENABLED=true','API_SERVER_HOST=127.0.0.1','API_SERVER_PORT=8642',f'API_SERVER_KEY={key}',f'JARVIS_PLUGIN_TOKEN={plugin}','JARVIS_BACKEND_URL=http://127.0.0.1:8787','OPENAI_API_KEY=local-ollama','HF_HUB_DISABLE_TELEMETRY=1','DO_NOT_TRACK=1'])+'\n'
    path=home/'.env';path.write_text(env);path.chmod(0o600)
    (home/'SOUL.md').chmod(0o600);(home/'config.yaml').chmod(0o600)
    print(f'Prepared {home}. Global ~/.hermes was untouched. Model: {model}')

if __name__=='__main__':main()
