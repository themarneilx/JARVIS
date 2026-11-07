import asyncio
import json
import os
from pathlib import Path
import re
import time
import psutil
import math


def cpu_temperature(readings):
    for source in ('coretemp','k10temp','zenpower','cpu_thermal','cpu-thermal','x86_pkg_temp'):
        sensors=readings.get(source,[])
        valid=[s for s in sensors if isinstance(s.current,(int,float)) and math.isfinite(s.current) and -20<s.current<150]
        preferred=[s for s in valid if any(label in str(s.label or '').lower() for label in ('package','tctl','tdie'))]
        if preferred or valid:
            sensor=max(preferred or valid,key=lambda s:s.current)
            return float(sensor.current),f'{source} / {sensor.label or "CPU sensor"}'
    return None,None


async def command(argv, *, json_output=False, timeout=3):
    try:
        proc = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            proc.kill()
            await proc.wait()
            raise
        if proc.returncode:
            return None
        text = stdout[:131072].decode(errors='replace')
        return json.loads(text) if json_output else text.strip()
    except (OSError, ValueError, asyncio.TimeoutError):
        return None


class Telemetry:
    def __init__(self):
        self.snapshot = None
        self.timestamp = 0
        self.lock = asyncio.Lock()
        psutil.cpu_percent(None)

    async def sample(self):
        async with self.lock:
            if self.snapshot and time.monotonic()-self.timestamp < 4:
                return self.snapshot
            gpu, clients, focused, workspaces, services, user_services, audio = await asyncio.gather(
                command(['nvidia-smi','--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total,power.draw','--format=csv,noheader,nounits']),
                command(['hyprctl','-j','clients'],json_output=True),
                command(['hyprctl','-j','activewindow'],json_output=True),
                command(['hyprctl','-j','workspaces'],json_output=True),
                command(['systemctl','list-units','--type=service','--all','--no-pager','--output=json'],json_output=True),
                command(['systemctl','--user','list-units','--type=service','--all','--no-pager','--output=json'],json_output=True),
                command(['wpctl','get-volume','@DEFAULT_AUDIO_SINK@']))
            graphics = None
            if gpu:
                try:
                    name, util, temp, used, total, power = gpu.splitlines()[0].split(',')
                    def number(v):
                        try: return float(v.strip())
                        except ValueError: return None
                    graphics = dict(name=name.strip(), utilization=number(util),temperature=number(temp),vram_used_mb=number(used),vram_total_mb=number(total),power_w=number(power))
                except ValueError:
                    pass
            battery = psutil.sensors_battery()
            try: cpu_temp,cpu_source=cpu_temperature(psutil.sensors_temperatures())
            except (AttributeError,OSError):cpu_temp,cpu_source=None,None
            ram, disk = psutil.virtual_memory(), psutil.disk_usage('/')
            try:
                networks = [{'name':name,'up':stat.isup,'speed_mbps':stat.speed} for name,stat in psutil.net_if_stats().items() if name != 'lo']
            except (OSError, PermissionError):
                networks = None
            def safe_window(w):
                return {'class':str(w.get('class',''))[:100],'title':str(w.get('title',''))[:160],'workspace':w.get('workspace',{}).get('id')}
            self.snapshot = {
                'sampled_at':time.time(), 'cpu_percent':psutil.cpu_percent(None),
                'cpu_temperature':cpu_temp,'cpu_temperature_source':cpu_source,
                'ram':{'used':ram.total-ram.available,'total':ram.total,'percent':ram.percent},
                'disk':{'used':disk.used,'total':disk.total,'percent':disk.percent},
                'uptime_seconds':int(time.time()-psutil.boot_time()),
                'battery':{'percent':battery.percent,'charging':bool(battery.power_plugged) if battery.power_plugged is not None else None} if battery else None,
                'gpu':graphics,'network':networks,
                'desktop': {'available':clients is not None, 'clients':[safe_window(w) for w in (clients or [])][:80], 'focused':safe_window(focused) if focused else None,'workspaces':[{'id':w.get('id'),'windows':w.get('windows')} for w in (workspaces or [])]},
                'services': None if services is None and user_services is None else [dict(unit=s.get('unit'),active=s.get('active'),sub=s.get('sub'),scope=scope) for scope,items in [('system',services),('user',user_services)] for s in (items or [])][:350],
                'audio': {'pipewire_reachable':audio is not None,'volume':audio},
                'backend_rss':psutil.Process().memory_info().rss,
                'unavailable':[name for name,value in [('NVIDIA',graphics),('Hyprland',clients),('systemd',services),('PipeWire',audio)] if value is None],
            }
            self.timestamp = time.monotonic()
            return self.snapshot

    async def processes(self):
        rows=[]
        for process in psutil.process_iter(['pid','name','memory_info','username']):
            try:
                data=process.info
                rows.append({'pid':data['pid'],'name':data['name'],'rss':data['memory_info'].rss})
            except (psutil.NoSuchProcess,psutil.AccessDenied):
                continue
        return sorted(rows,key=lambda x:x['rss'],reverse=True)[:25]

    async def journal(self, service):
        if not re.fullmatch(r'[a-zA-Z0-9_.@-]{1,100}\.service',service):
            raise ValueError('Invalid service name')
        output=await command(['journalctl','--user','--unit',service,'-n','30','--no-pager','--output=cat'])
        from .memory import redact
        return {'service':service,'lines':redact(output or 'Journal unavailable')[:10000]}
