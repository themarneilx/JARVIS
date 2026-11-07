"""Measure the original CPU voice with private, disposable artifacts."""
import asyncio
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.audio import JarvisTTS, speech_phrases
from app.config import Settings


async def main(device):
    with tempfile.TemporaryDirectory(prefix='jarvis-tts-latency-') as state:
        directory = Path(state)
        (directory / 'speech-models').symlink_to(ROOT / '.runtime/speech-models', target_is_directory=True)
        tts = JarvisTTS(Settings(state_dir=directory, tts_device=device))
        samples = []
        short = 'At your service, sir. All available system readings are ready for review.'
        long = 'Your system is currently responding normally. The processor and graphics card readings are available in the system panel. No service changes have been made. I can inspect an individual application or service if you would like a closer look, sir.'

        async def measure(label, text):
            start = time.monotonic()
            result = await tts.synthesize(text)
            sample = {'test': label, 'wall_seconds': round(time.monotonic()-start, 3), 'audio_seconds': round(result['duration'], 3), 'characters': len(text)}
            samples.append(sample)
            print(json.dumps(sample), flush=True)
        try:
            start = time.monotonic()
            await tts.prepare()
            preparation = round(time.monotonic()-start, 3)
            print(json.dumps({'prepare_seconds': preparation, 'device': tts.device, 'speed': tts.settings.tts_speed}), flush=True)
            await measure('prepared_short', short)
            await measure('warm_full_reply', long)
            phrases = speech_phrases(long)
            await measure('warm_first_phrase', phrases[0])
            for index, phrase in enumerate(phrases[1:], 2):
                await measure(f'warm_phrase_{index}', phrase)
            status = Path(f'/proc/{tts.proc.pid}/status').read_text().splitlines()
            rss = next(line for line in status if line.startswith('VmRSS:'))
            print(json.dumps({'worker_memory': rss, 'phrases': len(phrases), 'mocked_audio': False, 'physical_playback_verified': False}), flush=True)
        finally:
            await tts.close(cleanup=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', choices=['cpu','cuda'], default='cpu')
    asyncio.run(main(parser.parse_args().device))
