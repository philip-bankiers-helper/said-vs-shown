# Engine tests

From the repo root (Python 3.9+, standard library only, offline):

```sh
python3 -m unittest discover -s tests -v
```

What runs:

- `test_align.py`: spoken numbers ↔ digits, and alignment of the example episode's script against its real ASR transcript (`fixtures/example/audio/`, text only).
- `test_captions.py`: cue limits, scene cuts, the display map (word boundaries only), `--strict`.
- `test_scene_words.py`: slicing `words.json` into per-scene local times, and the scene/cut desync check.
- `test_capture.py`: `capture.sh` on `fixtures/capture/brief.md` with a stub `npx` and a minimal `PATH`, so the system's own `grep` runs (BSD on macOS, GNU on Linux). Covers stable ids, selected-first ordering, `SVS_MAX_SOURCES`, reuse and failure exits.
- `test_engine_misc.py`: the config contract, exact npm pins, no hardcoded HyperFrames or GSAP version and no personal paths in any engine or demo file, UTF-8 `open()`, shell syntax, and CLI smoke tests (`--help` on every Python and Node tool; `doctor.mjs --help` must not run the checks).

Some tests skip themselves when a tool is missing. The `loudfix.sh` test needs `ffmpeg`. The `receipt.mjs` render tests need `node`, `puppeteer-core` (`engine/setup.sh`) and a local Chrome; they render a saved `file://` page and use no network. To point them at a non-default install, set `SVS_HOME`.
