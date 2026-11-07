#!/usr/bin/env python3
"""Import local single-file GGUF models through Ollama's loopback API."""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import struct
import sys
from urllib.parse import urlsplit

JARVIS_SYSTEM = (
    'You are J.A.R.V.I.S., short for Just A Rather Very Intelligent System. '
    'Speak with calm precision and understated wit. Keep ordinary replies concise. '
    'Use verified tools before claiming live readings or completed actions.'
)


def model_name(value):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._/-]*(?::[a-zA-Z0-9._-]+)?', value) or len(value)>240:
        raise ValueError('Use a model name such as qwen35-2b:q4_k_m; URLs and control characters are refused')
    model, separator, tag = value.partition(':')
    if any(part in ('', '.', '..') for part in model.split('/')):
        raise ValueError('Invalid model namespace')
    return model + ':' + (tag if separator else 'latest')


def check_file(path):
    if not path.is_file() or path.suffix.lower() != '.gguf':
        raise ValueError(f'Not a readable GGUF file: {path}')
    if re.search(r'-\d{5}-of-\d{5}', path.stem):
        raise ValueError('This installer handles single-file GGUF models, not split shards')
    with path.open('rb') as file:
        header = file.read(24)
    if len(header)<24 or header[:4] != b'GGUF' or struct.unpack('<I', header[4:8])[0] not in (2,3):
        raise ValueError(f'Invalid or unsupported GGUF header: {path.name}')


def make_plan(inputs, name=None, jarvis=False, context=64000):
    if not isinstance(context,int) or isinstance(context,bool) or not 512<=context<=1048576:
        raise ValueError('Context must be between 512 and 1048576 tokens')
    files=[]
    for value in inputs:
        path=Path(value).expanduser().resolve()
        candidates=sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower()=='.gguf') if path.is_dir() else [path]
        for candidate in candidates:
            candidate=candidate.resolve()
            if candidate not in files:files.append(candidate)
    if not files:raise ValueError('No GGUF files found; directory scans are not recursive')
    if len(files)>200:raise ValueError('Import at most 200 files in one batch')
    if name and len(files)!=1:raise ValueError('--name applies to one file only')
    planned=set();result=[]
    for file in files:
        check_file(file)
        automatic=re.sub(r'[^a-z0-9._-]+','-',file.stem.lower()).strip('._-')
        base=model_name(name or automatic)
        model,tag=base.split(':')
        suffix=f'{context//1000}k' if context%1000==0 else f'{context}ctx'
        alias=model_name(f'jarvis-{model}-{suffix}:{tag}') if jarvis else None
        for target in (base,alias):
            if target is None:continue
            if target.casefold() in planned:raise ValueError('Two inputs produce the same model name; import them separately with --name')
            planned.add(target.casefold())
        result.append({'file':file,'model':base,'jarvis_model':alias,'context':context})
    return result


def local_endpoint(value):
    parsed=urlsplit(value if '://' in value else 'http://'+value)
    if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost','::1') or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:
        raise ValueError('Only a loopback HTTP Ollama endpoint without credentials is supported')
    return parsed.hostname,parsed.port or 11434


class Ollama:
    def __init__(self,url):self.host,self.port=local_endpoint(url)

    def request(self,method,path,body=None,headers=None):
        connection=http.client.HTTPConnection(self.host,self.port,timeout=600)
        try:
            connection.request(method,path,body=body,headers=headers or {})
            response=connection.getresponse()
            data=response.read(8*1024*1024+1)
            if len(data)>8*1024*1024:raise ValueError('Ollama returned an unexpectedly large response')
            if response.status>=400:
                detail=data.decode('utf-8',errors='replace')[:1000]
                raise ValueError(f'Ollama returned HTTP {response.status}: {detail}')
            return response.status,json.loads(data) if data else {}
        finally:connection.close()

    def json(self,path,payload=None):
        _,result=self.request('POST' if payload is not None else 'GET',path,
                              json.dumps(payload).encode() if payload is not None else None,
                              {'Content-Type':'application/json'})
        if not isinstance(result,dict) or result.get('error'):
            raise ValueError(f'Ollama reported an error: {str(result)[:1000]}')
        return result

    def tags(self):
        rows=self.json('/api/tags').get('models')
        if not isinstance(rows,list):raise ValueError('Unsupported Ollama model inventory')
        return {row['name'] for row in rows if isinstance(row,dict) and isinstance(row.get('name'),str)}

    def upload(self,path,digest):
        connection=http.client.HTTPConnection(self.host,self.port,timeout=10)
        try:
            connection.request('HEAD','/api/blobs/'+digest)
            response=connection.getresponse();response.read()
            if response.status==200:return
            if response.status!=404:raise ValueError(f'Ollama blob check returned HTTP {response.status}')
        finally:connection.close()
        print(f'Uploading {path.stat().st_size/1e9:.2f} GB to local Ollama…',flush=True)
        with path.open('rb') as file:
            self.request('POST','/api/blobs/'+digest,file,
                         {'Content-Type':'application/octet-stream','Content-Length':str(os.fstat(file.fileno()).st_size)})

    def create(self,payload):return self.json('/api/create',{**payload,'stream':False})
    def show(self,name):return self.json('/api/show',{'model':name})


def context_limit(metadata):
    return max((value for key,value in metadata.get('model_info',{}).items()
                if key.endswith('.context_length') and isinstance(value,int) and not isinstance(value,bool)),default=0)


def digest_file(path):
    with path.open('rb') as file:
        before=os.fstat(file.fileno())
        digest=hashlib.file_digest(file,'sha256').hexdigest()
        after=os.fstat(file.fileno())
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise ValueError('The GGUF file changed while hashing; retry after its download finishes')
    return 'sha256:'+digest


def install(plan, client, replace=False):
    existing={name.casefold() for name in client.tags()}
    conflicts={target for item in plan for target in (item['model'],item['jarvis_model']) if target and target.casefold() in existing}
    if conflicts and not replace:
        raise ValueError('These model names already exist: '+', '.join(sorted(conflicts))+'. Choose another --name or explicitly use --replace.')
    results=[]
    for item in plan:
        result={key:str(value) if isinstance(value,Path) else value for key,value in item.items()}
        result.update(status='failed',metadata_ready_for_hermes=False,runtime_verified=False)
        try:
            print(f"Hashing {item['file'].name}…",flush=True)
            digest=digest_file(item['file']);result['sha256']=digest
            client.upload(item['file'],digest)
            print(f"Creating {item['model']}…",flush=True)
            client.create({'model':item['model'],'files':{item['file'].name:digest}})
            result['model']=next((name for name in client.tags() if name.casefold()==item['model'].casefold()),None)
            if not result['model']:raise ValueError('Ollama did not register the imported base tag')
            metadata=client.show(result['model'])
            limit=context_limit(metadata)
            if item['jarvis_model']:
                if limit<item['context']:
                    raise ValueError(f"Base imported, but its advertised context ({limit}) is below requested {item['context']}; no J.A.R.V.I.S. alias created")
                print(f"Creating {item['jarvis_model']}…",flush=True)
                client.create({'model':item['jarvis_model'],'files':{item['file'].name:digest},
                               'parameters':{'num_ctx':item['context']},'system':JARVIS_SYSTEM})
                result['jarvis_model']=next((name for name in client.tags() if name.casefold()==item['jarvis_model'].casefold()),None)
                if not result['jarvis_model']:raise ValueError('Ollama did not register the J.A.R.V.I.S. tag')
                metadata=client.show(result['jarvis_model'])
                configured=re.search(r'(?m)^\s*num_ctx\s+(\d+)\s*$',metadata.get('parameters',''))
                if not configured or int(configured[1])!=item['context']:
                    raise ValueError('Ollama did not preserve the requested context default')
                result['metadata_ready_for_hermes']=bool(item['context']>=64000 and context_limit(metadata)>=64000 and 'tools' in metadata.get('capabilities',[]))
            result.update(status='installed',capabilities=metadata.get('capabilities',[]),
                          context_limit=context_limit(metadata),quantization=metadata.get('details',{}).get('quantization_level'))
            print('Installed. Runtime performance remains unverified.',flush=True)
        except (OSError,ValueError,http.client.HTTPException) as exc:
            result['error']=str(exc);print(f"Failed: {exc}",file=sys.stderr,flush=True)
        results.append(result)
    return results


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs',nargs='+',help='GGUF files or directories (not recursive)')
    parser.add_argument('--name',help='Custom raw tag for a single file, e.g. qwen35-2b:q4_k_m')
    parser.add_argument('--jarvis',action='store_true',help='Also create a separate J.A.R.V.I.S. tag with a concise identity and configured context')
    parser.add_argument('--context',type=int,default=64000,help='J.A.R.V.I.S. context default (64000)')
    parser.add_argument('--url',default=os.getenv('OLLAMA_HOST','http://127.0.0.1:11434'))
    parser.add_argument('--replace',action='store_true',help='Explicitly allow replacing the planned Ollama tags')
    parser.add_argument('--dry-run',action='store_true',help='Inspect files and print names without contacting Ollama')
    parser.add_argument('--report',type=Path,help='Write a new private JSON report; existing report files are refused')
    args=parser.parse_args(argv)
    try:
        plan=make_plan(args.inputs,args.name,args.jarvis,args.context)
        local_endpoint(args.url)
        if args.report and (args.report.exists() or args.report.is_symlink() or args.report.suffix.lower()=='.gguf'):
            raise ValueError('Use a new JSON report path; existing files and GGUF destinations are refused')
        for item in plan:print(f"{item['file']}\n  → {item['model']}"+(f"\n  → {item['jarvis_model']}" if item['jarvis_model'] else ''))
        print(f"Total source weights: {sum(item['file'].stat().st_size for item in plan)/1e9:.2f} GB. Ollama may need this much additional disk space.")
        if args.dry_run:return 0
        results=install(plan,Ollama(args.url),args.replace)
        if args.report:
            args.report.parent.mkdir(parents=True,exist_ok=True)
            descriptor=os.open(args.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(descriptor,'w') as file:json.dump(results,file,indent=2);file.write('\n')
        print(json.dumps(results,indent=2))
        return 0 if all(row['status']=='installed' for row in results) else 1
    except (OSError,ValueError,http.client.HTTPException) as exc:
        print(f'Error: {exc}',file=sys.stderr);return 1


if __name__=='__main__':
    raise SystemExit(main())
