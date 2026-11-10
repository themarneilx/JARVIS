import os
from pathlib import Path
import sys
import argparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.process_control import record_process
parser=argparse.ArgumentParser()
parser.add_argument('kind')
parser.add_argument('pid',type=int)
parser.add_argument('--host',default='127.0.0.1')
parser.add_argument('--tls-cert')
parser.add_argument('--tls-key')
args=parser.parse_args()
record_process(ROOT,args.kind,args.pid,int(os.getenv('JARVIS_PORT','8787')),args.host,args.tls_cert,args.tls_key)
