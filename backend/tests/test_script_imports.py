"""Command helpers must not shadow modules imported by speech dependencies."""
from pathlib import Path
import subprocess
import sys


def test_speech_diagnostic_can_import_standard_profiler():
    scripts = Path(__file__).resolve().parents[2] / 'scripts'
    result = subprocess.run([sys.executable, '-c', 'import sys; sys.path.insert(0, sys.argv[1]); import cProfile; assert callable(cProfile.run)', str(scripts)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
