import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.process_control import record_process
record_process(ROOT,sys.argv[1],int(sys.argv[2]),int(os.getenv('JARVIS_PORT','8787')))
