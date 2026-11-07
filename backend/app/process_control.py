"""Identity checks for signalling only processes launched by this project."""
import json
import os
from pathlib import Path
import signal


def start_time(proc):
    return (proc/'stat').read_text().rsplit(')',1)[1].split()[19]


def invocation(kind,port=8787):
    if kind=='hermes':return ['-m','hermes_cli.main','gateway','run']
    if kind=='backend':return ['-m','uvicorn','app.main:create_app','--factory','--host','127.0.0.1','--port',str(port),'--no-access-log']
    raise ValueError('Unknown project process')


def record_process(root,kind,pid,port=8787):
    proc=Path('/proc')/str(pid)
    record={'pid':pid,'start_time':start_time(proc),'kind':kind,'argv':invocation(kind,port)}
    path=root/'.runtime'/f'{kind}.process.json'
    path.write_text(json.dumps(record));path.chmod(0o600)


def validate_process(record,root,proc_root=Path('/proc')):
    proc=proc_root/str(record['pid'])
    command=[value.decode() for value in (proc/'cmdline').read_bytes().rstrip(b'\0').split(b'\0')]
    environment=(proc/'environ').read_bytes().split(b'\0')
    if start_time(proc)!=record['start_time'] or command[1:]!=record['argv'] or (proc/'cwd').resolve()!=root.resolve() or ('HERMES_HOME='+str(root.resolve()/'hermes/runtime')).encode() not in environment:
        raise ValueError('Refusing to stop an unrelated or reused process')
    kind=record['kind']
    expected=invocation(kind,record['argv'][-2] if kind=='backend' else 8787)
    if record['argv']!=expected:raise ValueError('Unrecognized project process invocation')


def stop_recorded(root,kind):
    path=root/'.runtime'/f'{kind}.process.json'
    if not path.exists():return
    record=json.loads(path.read_text())
    descriptor=None
    try:
        descriptor=os.pidfd_open(record['pid'])
        validate_process(record,root)
        signal.pidfd_send_signal(descriptor,signal.SIGTERM)
    except ProcessLookupError:pass
    except FileNotFoundError:pass
    finally:
        if descriptor is not None:os.close(descriptor)
    path.unlink(missing_ok=True)
