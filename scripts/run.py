"""Foreground supervisor for the dedicated local Hermes and browser command center."""
import argparse
import asyncio
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.config import Settings
from app.hermes import HermesClient, HermesError
from app.runtime import discover_runtime, profile_home
from app.process_control import stop_recorded as stop_project_process
from app.models import ModelManager


def stop_recorded(name):
    stop_project_process(ROOT,name)


async def preflight(settings):
    client=HermesClient(settings)
    models=ModelManager(settings)
    if models.selected_model:client.set_model(models.selected_model)
    try:return await client.preflight()
    finally:
        await client.close()
        await models.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--no-token',action='store_true',help='Hide the pairing token in automated checks')
    parser.add_argument('--stop',action='store_true',help='Stop only recorded project processes')
    parser.add_argument('--dev',action='store_true')
    args=parser.parse_args()
    profile_home(ROOT,os.getenv('HERMES_HOME'))
    if args.stop:
        for name in ('backend','hermes'):stop_recorded(name)
        return
    settings=Settings()
    runtime=discover_runtime(ROOT)
    base=f'http://127.0.0.1:{settings.port}'
    stopped=threading.Event()
    children=[]
    logs=[]
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:stopped.set())
    directory=settings.state_dir/'logs'
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)

    def launch(name,command):
        log=(directory/f'{name}.log').open('a')
        logs.append(log)
        child=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        children.append((name,child))
        return child

    def alive():
        for name,child in children:
            if child.poll() is not None:
                raise RuntimeError(f'{name} exited. Inspect {directory/name}.log')
        if stopped.is_set():raise KeyboardInterrupt

    try:
        with httpx.Client(trust_env=False,timeout=1) as probe:
            try:
                probe.get(base+'/api/health')
            except httpx.ConnectError:
                pass
            else:
                raise RuntimeError('Application port is already occupied. Stop the project with npm start -- --stop before relaunching.')
            try:
                probe.get(settings.hermes_url+'/v1/capabilities')
            except httpx.ConnectError:
                print(f'Starting installed Hermes {runtime.version} with the dedicated J.A.R.V.I.S. profile…',flush=True)
                launch('hermes',['bash','scripts/hermes.sh'])
            else:
                asyncio.run(preflight(settings))
                print('Reusing the verified local J.A.R.V.I.S. gateway.',flush=True)
            deadline=time.monotonic()+60
            while True:
                alive()
                try:
                    asyncio.run(preflight(settings))
                    break
                except HermesError:
                    if time.monotonic()>deadline:raise
                    stopped.wait(0.4)
            if not args.dev and not (ROOT/'frontend/dist/index.html').is_file():
                subprocess.run(['npm','run','build'],cwd=ROOT,check=True)
            print('Starting the browser command center…',flush=True)
            if args.dev:os.environ['JARVIS_DEV_MODE']='1'
            launch('backend',['bash','scripts/start.sh','--backend'])
            deadline=time.monotonic()+30
            while True:
                alive()
                try:
                    if probe.get(base+'/api/health').is_success:break
                except httpx.ConnectError:pass
                if time.monotonic()>deadline:raise RuntimeError('Backend startup timed out')
                stopped.wait(0.25)
        url=base
        if args.dev:
            launch('frontend',['npm','--prefix','frontend','run','dev','--','--port',os.getenv('JARVIS_FRONTEND_PORT','3000')])
            url=f"http://127.0.0.1:{os.getenv('JARVIS_FRONTEND_PORT','3000')}"
            with httpx.Client(trust_env=False,timeout=1) as frontend_probe:
                deadline=time.monotonic()+30
                while True:
                    alive()
                    try:
                        if frontend_probe.get(url).is_success:break
                    except httpx.ConnectError:pass
                    if time.monotonic()>deadline:raise RuntimeError('Vite startup timed out')
                    stopped.wait(0.25)
        print(f'\nJ.A.R.V.I.S. is ready: {url}',flush=True)
        if not args.no_token:print(f'Local pairing token: {settings.login_token}',flush=True)
        print('Paste the token into the browser once. Ctrl+C stops the processes started here.',flush=True)
        print(f'Private logs: {directory}\n',flush=True)
        if not args.no_browser:
            try:subprocess.Popen(['xdg-open',url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            except OSError:print('Open the local URL above in your browser.',flush=True)
        while not stopped.wait(0.5):alive()
    except KeyboardInterrupt:
        pass
    finally:
        for _,child in reversed(children):
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGTERM)
        for name,child in reversed(children):
            try:child.wait(timeout=12)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGKILL)
                child.wait()
            path=ROOT/'.runtime'/f'{name}.process.json'
            if path.exists():
                import json
                if json.loads(path.read_text()).get('pid')==child.pid:path.unlink()
        for log in logs:log.close()


if __name__=='__main__':
    try:main()
    except (RuntimeError,ValueError,HermesError,httpx.HTTPError) as exc:
        sys.exit(str(exc))
