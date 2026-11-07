#!/usr/bin/env python3
"""Resolve installed Hermes without changing its global home or installing dependencies."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import shlex
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.runtime import discover_runtime, profile_home

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--shell',action='store_true')
    parser.add_argument('--profile-home',action='store_true')
    args=parser.parse_args()
    if args.profile_home:
        try:print(profile_home(ROOT,os.getenv('HERMES_HOME')))
        except ValueError as exc:sys.exit(str(exc))
        sys.exit(0)
    try:runtime=discover_runtime(ROOT)
    except ValueError as exc:sys.exit(str(exc))
    if args.shell:
        print('export HERMES_SOURCE='+shlex.quote(str(runtime.source)))
        print('export HERMES_PYTHON='+shlex.quote(str(runtime.python)))
    else:print(json.dumps(asdict(runtime),default=str,indent=2))
