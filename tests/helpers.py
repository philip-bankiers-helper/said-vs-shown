"""Shared paths and helpers for the engine tests (offline; standard library only)."""
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(ROOT, 'skills', 'said-vs-shown', 'engine')
FIXTURES = os.path.join(ROOT, 'tests', 'fixtures')
EXAMPLE_AUDIO = os.path.join(FIXTURES, 'example', 'audio')
WORKED_AUDIO = os.path.join(FIXTURES, 'worked-example', 'audio')  # references/example voiced, real Whisper + Parakeet

if ENGINE not in sys.path:
    sys.path.insert(0, ENGINE)


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save(obj, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)


def example():
    """(script, transcript, timeline) of the example episode fixture."""
    return tuple(load(os.path.join(EXAMPLE_AUDIO, n)) for n in ('script.json', 'transcript.json', 'timeline.json'))


def worked_example(engine):
    """(script, transcript, timeline) of the worked example (skills/said-vs-shown/references/example), voiced by
    voice.py and transcribed by `hyperframes transcribe --engine whisper --model small.en` or `--engine parakeet`."""
    return (load(os.path.join(WORKED_AUDIO, 'script.json')), load(os.path.join(WORKED_AUDIO, 'transcript-%s.json' % engine)),
            load(os.path.join(WORKED_AUDIO, 'timeline.json')))


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                          stdin=subprocess.DEVNULL, **kw)


def have(tool):
    return shutil.which(tool) is not None
