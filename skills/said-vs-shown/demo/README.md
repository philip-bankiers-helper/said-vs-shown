# Demo: one sentence, shown on its page

The fastest way to see what Said vs. Shown does. Give it a web page and a sentence that is on that page. About a minute later (longer on the first run, while models download) you have a 20–30 s, 1920×1080 clip: the real page, captured at 2x; the camera pushing in on the sentence; a highlighter sweeping it as a synthetic voice reads it word for word; burned-in captions; and an end card.

First run the health check, `node <skill>/engine/doctor.mjs`, where `<skill>` is the installed skill folder (README → Install). If it fails, run setup once, `sh <skill>/engine/setup.sh`, then doctor again. Setup downloads about 1.7 GB on a fresh machine and installs the HyperFrames agent skills in your global skill folders (`--dry-run` lists every step and changes nothing). Then, from the folder where you want the clip (not the skill folder: a plugin or skills update replaces it):

```sh
mkdir -p ~/svs-try && cd ~/svs-try
python3 <skill>/demo/demo.py https://example.com "This domain is for use in documentation examples without needing permission."
```

Output: `./said-vs-shown-demo/demo.mp4`, plus the editable HyperFrames project in `./said-vs-shown-demo/project/` (`npx -y hyperframes@<ver> preview <project>` opens it in Studio; `<ver>` is `hyperframes` in `engine/config.json`). Your agent can run it too: ask for "a Said vs. Shown receipt clip of <sentence> on <url>".

## Options

| Flag | Default | |
|---|---|---|
| `--out DIR` | `./said-vs-shown-demo` | output folder |
| `--voice ID` | `af_heart` (`engine/config.json`) | Kokoro voice |
| `--speed S` | `1.06` (`engine/config.json`) | speech speed |
| `--quality` | `draft` | `draft` (fast) · `looks` (sharper page text, slower) · `delivery` |
| `--install-line TEXT` | `npx skills add <repo>` (repo from `.claude-plugin/plugin.json` when present) | end-card install line. Until the repo is public that command won't resolve, so pass your own line for clips you share |

## What it does

| Step | Tool | Typical time |
|---|---|---|
| capture | `engine/receipt.mjs`: headless Chrome, 1440×900 at 2x; finds the sentence in the visible text and records each line's rectangle | 3–5 s |
| voice | `npx -y hyperframes@<ver> tts` (Kokoro, local): "Here's the sentence, on the page it came from.", then the sentence read verbatim, then where and when it was captured. Word timings are approximated from each line's audio (speech bounds via ffmpeg `silencedetect`, then spread by characters). No speech recognition. | 10–25 s |
| compose | one scene from `templates/scenes/receipt.html` (kicker `SAID VS. SHOWN · DEMO`, domain + capture-date chip, push-in, synced highlighter, pull-back), an end card, phrase captions, two sound marks | < 1 s |
| render | `npx -y hyperframes@<ver> render -q draft -w 2` | 1–2× real time |

Measured on an Apple M1 with warm caches: example.com, 20 s clip, 40 s end to end (voice 10 s, render 26 s), and 46–63 s while another render loaded the machine; a GitHub README sentence, 26 s clip, about 54 s. The first run also downloads the Kokoro model (~340 MB) and HyperFrames' own Chrome.

## When the sentence is not found

The sentence must appear verbatim in the page's visible text. Curly and straight quotes, dashes and runs of whitespace are treated as equal. If it is not there, the demo exits with status 1 and prints the closest sentences that are on the page, plus a command to retry with the first of them.

Exit status 2 means a dependency is missing. Run `sh <skill>/engine/setup.sh`, then `node <skill>/engine/doctor.mjs` (the error message prints the full path).

## Ground rules

These are the same as the full skill:
- The capture never logs in, never accepts consent dialogs, never clicks anything, and never disguises the browser.
- Sticky overlays are hidden visually only.
- A page that refuses headless Chrome is reported, not worked around.
- The voice is synthetic. The end card says so, names the page and its capture date, and names the tool that made the clip.
- Captures stay on your machine. Before you publish a clip, check that you are allowed to show the page.
