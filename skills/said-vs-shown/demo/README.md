# Demo: one sentence, shown on its page

The fastest way to see what Said vs. Shown does. Give it a web page and a sentence that is on that page. About half a minute later you have a 20–30 s, 1920×1080 clip: the real page, captured at 2x; the camera pushing in on the sentence; a highlighter sweeping it as a synthetic voice reads it word for word; burned-in captions; and an end card.

```sh
python3 demo/demo.py https://example.com "This domain is for use in documentation examples without needing permission."
```

Output: `./said-vs-shown-demo/demo.mp4`, plus the editable HyperFrames project in `./said-vs-shown-demo/project/` (`npx -y hyperframes@<version> preview <project>` opens it in Studio).

## Options

| Flag | Default | |
|---|---|---|
| `--out DIR` | `./said-vs-shown-demo` | output folder |
| `--voice ID` | `af_heart` (`engine/config.json`) | Kokoro voice |
| `--speed S` | `1.06` (`engine/config.json`) | speech speed |
| `--quality` | `draft` | `looks` renders sharper page text, more slowly |
| `--install-line TEXT` | from `.claude-plugin/plugin.json` | end-card install line |

## What it does

| Step | Tool | Typical time |
|---|---|---|
| capture | `engine/receipt.mjs`: headless Chrome, 1440×900 at 2x; finds the sentence in the visible text and records each line's rectangle | 3–5 s |
| voice | `npx hyperframes tts` (Kokoro, local): "Here's the sentence, on the page it came from.", then the sentence read verbatim, then where and when it was captured. Word timings are approximated from each line's audio (speech bounds via ffmpeg `silencedetect`, then spread by characters). No speech recognition. | 8–10 s |
| compose | one scene from `templates/scenes/receipt.html` (kicker `SAID VS. SHOWN · DEMO`, domain + capture-date chip, push-in, synced highlighter, pull-back), an end card, phrase captions, two sound marks | < 1 s |
| render | `npx hyperframes render -q draft -w 2` | about 1× real time |

Measured on an Apple M1: example.com, 20 s clip, about 32 s end to end. A GitHub README sentence, 26 s clip, about 41 s.

## When the sentence is not found

The sentence must appear verbatim in the page's visible text. Curly and straight quotes, dashes and runs of whitespace are treated as equal. If it is not there, the demo exits with status 1 and prints the closest sentences that are on the page, plus a command to retry with the first of them.

Exit status 2 means a dependency is missing. Run `engine/setup.sh`, then `node engine/doctor.mjs`.

## Ground rules

These are the same as the full skill:
- The capture never logs in, never accepts consent dialogs, never clicks anything, and never disguises the browser.
- Sticky overlays are hidden visually only.
- A page that refuses headless Chrome is reported, not worked around.
- The voice is synthetic. The end card says so, names the page and its capture date, and names the tool that made the clip.
- Captures stay on your machine. Before you publish a clip, check that you are allowed to show the page.
