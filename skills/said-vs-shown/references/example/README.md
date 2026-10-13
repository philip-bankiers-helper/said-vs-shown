# Worked example: a one-story mini episode

Every data file an episode needs before the voice, in the exact shapes the tools read, for one story (OpenAI's math release from episode 1, Oct 2026) and two other leads. The paths mirror an episode root (`references/project-layout.md`).

| File | Stage | What it shows |
|---|---|---|
| `input/brief.md` | 1 | the brief format (`references/brief-format.md`): window, one selected story with its sources and cautions, numbered other leads, guardrails |
| `ledger/selected.txt` | 1 | one URL substring per line: the selected story's sources, captured first |
| `ledger/sources.json` | 2 | the stable source map `capture.sh` writes |
| `ledger/claims.json` | 3 | one story: verifier result (4 claims, 2 receipt candidates) + refuter result (1 claim not upheld, with its fix) |
| `ledger/leads.json` | 3 | two lead cards (an *Older* lead and a *Company* lead) |
| `edit/episode.json` | 4 | complete episode facts; no `reviewed_by` yet, so the disclosure reads "not yet human-reviewed" |
| `video/audio/script.json` | 5 | one line per scene, claim ids per line, spoken numbers → digits via `display`, the close's 7 s hold (`gap_after: 7.0`), and a per-line `speed` where a line needs one to land inside the voice gates (145–185 wpm, captions ≤ 21 chars/s) |
| `video/scenes.json` | 5 (sfx after 7) | the scene ids in script order, with two sound marks |
| `video/specs/03-math-boundary.json` | 8 | a boundary spec for `engine/boundary.py` |

Not included, because tools make them: the captures (`capture.sh`), the receipts `video/assets/receipts/R01-math-intro.*` and `R02-math-issues.*` (`receipt.mjs`), the audio and `scene-words.json` (`voice.py`), and the compositions (stage 8). A one-story episode has no board.

Claim ids in `script.json` → `claims`: `storyN:cNN` points at `ledger/claims.json`, with an optional note in parentheses (`story1:c01(fixed: attributed)`); `brief:<anchor>` points at the brief; `editorial` marks the production's own framing. Lines with no factual claim (the close) have `[]`.

Scene times in the spec and the sound marks are illustrative: real ones come from your `scene-words.json` (see `references/scenes.md`).

## Try it

Copy the brief into your working folder and ask your agent for an episode:

```sh
mkdir -p inbox && cp <skill>/references/example/input/brief.md inbox/example-brief.md
```

Then: *"Make a Said vs. Shown episode from inbox/example-brief.md"*. The sources are public pages that rendered for headless Chrome when episode 1 was made (Oct 11, 2026). Pages change: if a quote has moved or a page now refuses, the skill reports it rather than working around it.
