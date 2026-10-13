# Engine tests

From the repo root (Python 3.9+, standard library only, offline):

```sh
python3 -m unittest discover -s tests -v
```

What runs:

- `test_align.py`: spoken numbers ↔ digits, alignment of the example episode's script against its real ASR transcript (`fixtures/example/audio/`, text only), and word ends clamped to their line's audio end.
- `test_captions.py`: cue limits, scene cuts (a cue's lead never crosses the cut that opens its scene), the display map (word boundaries only), `--strict`.
- `test_scene_words.py`: slicing `words.json` into per-scene local times, and the scene/cut desync check.
- `test_capture.py`: `capture.sh` on `fixtures/capture/brief.md` with a stub `npx` and a minimal `PATH`, so the system's own `grep` runs (BSD on macOS, GNU on Linux). Covers stable ids, selected-first ordering, `SVS_MAX_SOURCES`, reuse and failure exits, `--help`, and the `EVIDENCE.md` note that replaces HyperFrames' `AGENTS.md`/`CLAUDE.md`/`.cursorrules` in every capture.
- `test_episode_tools.py`: the disclosure rule (only `reviewed_by` can make it say "reviewed by": companion page, `fill_scenes.py` close, `new_episode.py` starter, `deliver.py` gate), the one-thing question split when the highlight opens the question, `deliver.py`'s `transcript.md` display forms, and the paths `new_episode.py` prints.
- `test_engine_misc.py`: the config contract, exact npm pins, no hardcoded HyperFrames or GSAP version and no personal paths in any engine or demo file, UTF-8 `open()`, shell syntax, every `hyperframes snapshot` call passing `--describe false`, and CLI smoke tests (`--help` exits 0 on every Python, shell, Node and Swift tool, demo included; `doctor.mjs --help` must not run the checks).

Some tests skip themselves when a tool is missing. The `loudfix.sh` and `deliver.py` tests need `ffmpeg`; the `ocr-locate.swift` test needs `swift` on macOS. The `receipt.mjs` render tests need `node`, `puppeteer-core` (`engine/setup.sh`) and a local Chrome; they render a saved `file://` page and use no network. To point them at a non-default install, set `SVS_HOME`.
