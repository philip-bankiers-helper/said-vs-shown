# Scene kinds: order, ids, tools, CFG keys and motion

Stage 8 of `SKILL.md`. Placeholders: `<skill>` = this skill's folder (absolute path), `<episode>` = the episode root, `<video>` = `<episode>/video`, `<ver>` = `engine/config.json` → `hyperframes`.

Every scene is a HyperFrames sub-composition: one HTML file with a `<template>` holding its `<style>` and `<script>`, a root `<div id="root" data-composition-id="<scene id>" data-width="1920" data-height="1080">`, one paused GSAP timeline registered last on `window.__timelines["<scene id>"]`, ids prefixed per scene (`__P__`), CSS selectors scoped to `[data-composition-id="<scene id>"]` (`engine/assemble.py` runs `engine/scope_css.py` on every file). The contract itself is in the `hyperframes-core` skill (see SKILL.md → HyperFrames knowledge).

Times inside a scene are LOCAL seconds from the scene's start. They come from `<video>/audio/scene-words.json` → `<scene id>`: `duration`, `global_start` and `words[]` (`t` = word, `s` = start, `e` = end). Sync every beat to the words that say it. Read one scene at a time:

```sh
python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))[sys.argv[2]]))' <video>/audio/scene-words.json <scene id>
```

`<video>/frame.md` is the design truth (palette, type, badges, motifs, motion). Keep y 920–1080 empty for captions, and text at 18 px or larger.

## Order and ids

Write `<video>/scenes.json` at the end of stage 5, before `voice.py`: one entry per script scene, the same ids in the same order as the `scene` fields in `audio/script.json` (`assemble.py` refuses a mismatch). Tools find scenes by these ids, so use them as given.

| Position | id | src | Built by |
|---|---|---|---|
| first | `squeeze` | `compositions/01-squeeze.html` | `engine/fill_scenes.py` |
| per story | `<slug>-receipt` | `compositions/NN-<slug>-receipt.html` | you, from `templates/scenes/receipt.html` |
| per story | `<slug>-boundary` | `compositions/NN-<slug>-boundary.html` | `engine/boundary.py` + `<video>/specs/NN-<slug>-boundary.json` |
| between stories | `board-<n>` (n = the story just finished) | `compositions/NN-board-<n>.html` | `engine/board.py` |
| last three | `payoff`, `one-thing`, `close` | `compositions/NN-<id>.html` | `engine/fill_scenes.py` |

- `fill_scenes.py` recognises the squeeze, payoff, one-thing and close only by these ids, or by a src named `NN-<kind>.html`. It lists every other scene with the tool that makes it: ids ending in `receipt` (or named in `stories[].scenes.receipt`), ids ending in `boundary`, ids starting with `board`.
- Set `edit/episode.json` → `stories[].scenes` to `{"receipt": "<slug>-receipt", "boundary": "<slug>-boundary"}`.
- A one-story episode has no board.

`scenes.json` shape:

```json
{
  "title": "AI · 2026-10-08",
  "hold": 0.12,
  "scenes": [
    { "id": "squeeze", "src": "compositions/01-squeeze.html" },
    { "id": "math-receipt", "src": "compositions/02-math-receipt.html" },
    { "id": "math-boundary", "src": "compositions/03-math-boundary.html" },
    { "id": "board-1", "src": "compositions/04-board-1.html" },
    { "id": "payoff", "src": "compositions/10-payoff.html" },
    { "id": "one-thing", "src": "compositions/11-one-thing.html" },
    { "id": "close", "src": "compositions/12-close.html" }
  ],
  "sfx": [
    { "file": "assets/sfx/whoosh-short.wav", "at": 3.8, "vol": 0.3 },
    { "file": "assets/sfx/click-soft.wav", "at": 8.0, "vol": 0.32 }
  ]
}
```

Leave `sfx` empty until `voice.py` has run. Then add sound marks on structural beats only (frame.md → Sound): `at` is GLOBAL seconds = the scene's `global_start` + the local beat, `vol` 0.2–0.35. Files: `assets/sfx/whoosh-short.wav` (the squeeze, a camera move into a story), `click-soft.wav` (a boundary drawing, a slot filling), `pop.wav` (a card landing).

The close holds still for about 7 s of reading: give the close line `"gap_after": 7.0` in `audio/script.json` (the default gap is 0.7).

## Squeeze, payoff, one-thing, close (filled from data)

```sh
python3 <skill>/engine/fill_scenes.py <episode> --dry-run      # print every beat table, write nothing
python3 <skill>/engine/fill_scenes.py <episode>                # write the four compositions
python3 <skill>/engine/fill_scenes.py <episode> --only close   # after the review (stage 10)
```

It reads `edit/episode.json`, `ledger/leads.json`, `ledger/sources.json`, `audio/scene-words.json`, `assets/receipts/*.json`, `scenes.json` and `frame.md` (the `--accent` row), and rewrites the template's `CFG` block. Read its notes: they say which episode.json key changes a beat or a label. Fix the data and re-run; do not hand-edit the generated files.

| Kind | Template | CFG keys | Data it comes from | Motion |
|---|---|---|---|---|
| Squeeze | `templates/scenes/squeeze.html` | `meta{show,edition,window}`, `leads[{title,badge}]` (story cards first, grid shows 20), `stories` (1–4), `total_leads`, `beats{cards,squeeze,tests,boundary}` | `stories[].card_title`/`topic`/`badge`; `leads.json` `card_title`/`title`/`status`; `lead_badge_overrides` | waterfall-entry cards → nudge-curve pile (piled cards lose their text) → story row rises → svg-path-draw evidence line |
| Payoff | `templates/scenes/payoff.html` | `meta`, `heads{claim,test}`, `rows[{num,label,claim,test[],at{label,claim,idx,test[]}}]`, `statement{lead,mark,tail,at{lead,mark,underline,underline_dur}}`, `beats{plate,head_claim,head_test,skeleton}` | `matrix` (one `[claim, test]` row per story; test may be a list of fragments), `stories[].n`/`topic`, `payoff_statement`, `payoff_highlight` | svg-path-draw column divider, rows build as each pairing is said, accent underline under the statement's key phrase |
| One-thing | `templates/scenes/one-thing.html` | `meta`, `kicker`, `quiet[{text,at}]`, `line1`, `mark`, `tail`, `beats{kicker,nudge,line1,line2,highlight,highlight_dur}` | `one_thing` ("lead: question"), `one_thing_highlight`, `one_thing_lead`, `one_thing_kicker` | waterfall quiet fragments as said, nudge-curve up, two display lines, marker highlight |
| Close | `templates/scenes/close.html` | `meta`, `eyebrow`, `title`, `cta{a,b}`, `key_label`, `receipt{wordmark,edition_line,number,stories[{num,topic,badge,sources[]}],counts[[label,value]],disclosure,credits[],credits_more,credit}`, `beats{title,receipt,cta_a,cta_b,key}` | `title`, `close_title`, `stories[].sources[].url`, `captured`, counts computed from `leads.json`/`stories`/`sources.json`/receipts, `reviewed_by` (the generated disclosure), `credits`, `credit` | the printed receipt clips in top→bottom at a constant feed, lines cascade, then ~7 s still |

One-thing: `one_thing_highlight` is the marked phrase on line 2. If it opens the question (or is the whole question), `fill_scenes.py` moves its first words to line 1 and keeps the rest marked (a one-word highlight stays whole on a single line) and prints a note; pick a highlight later in the question to keep both lines. Close: the disclosure line is generated, its review segment from `reviewed_by`; `credits` print on their own line, at most 3 of at most 64 characters on the receipt, then "+N more" (`credits_more`; the page lists all) (`references/project-layout.md`).

Leads with status `contradicted` or `unverifiable` get no squeeze card (there is no video badge for them); the companion page lists them as Contradicted / Unverified.

## Receipt (one per story, written by you)

1. Copy `<skill>/templates/scenes/receipt.html` to `<video>/compositions/NN-<slug>-receipt.html`.
2. Follow the steps in its header comment: replace `__SCENE_ID__` and `__P__` (a short prefix with its dash, e.g. `mr-`), and fill `CFG`:
   - `kicker{num,topic,badge,meta,wordmark,sep}` and `source{label,captured}`, `url`: from `edit/episode.json` → the story;
   - `receipt{img,alt,viewport,lines}`: from `<video>/assets/receipts/Rnn-<slug>.json` (`viewport`, `lines` in CSS px);
   - `beats{kicker,source,frame}`, `camera{at,dur,zoom}` (zoom 0 = auto), `highlight[{at,dur,ease?}]` (one entry per quote line: when its first word is said and how long its words take), `after{mode,at,dur,dim?}` (`illustration` | `pullback` | `hold`; `dim` defaults to 0.5, see Motion): from this scene's words;
   - `illustration{tag,tag_at,nodes[{t,s,at,accent?,arrow_at?}],check_at}`: the default diagram's data.
3. Replace the default diagram in the ILLUSTRATION SLOT (markup and motion) with a visual made for this story. Vary it per story; templated sameness reads as mass-produced. Keep the visible ILLUSTRATION tag, and never present it as a product's real output.
4. Run `npx -y hyperframes@<ver> lint <video>` and fix your findings.

Motion: arrivals are `tl.set` + `tl.to` (waterfall-entry, power4.out); the camera is coordinate-target-zoom (`zoom-outer` scales, `zoom-inner` translates, power3.inOut, 1.2–1.6 s); the highlighter sweeps left→right synced to the spoken words; the browser bar's URL fades while the camera is pushed in. During a pull-back the page dims (`#__P__dim`, power2.out to `after.dim` over the first 60% of the move, back to 0 in 0.8 s after the camera lands). Keep it, and keep something like it in a camera move of your own: a white page that fills the frame and leaves it undimmed in about a second measured 3 frame-to-frame luma jumps over 10%, the WCAG 2.3.1 flash limit `deliver.py` checks; with the dimmer the largest jump halves.

To build several receipts at once, give each one the brief below: in Claude Code with the Workflow tool, `workflows/scenes.js`; in an agent with subagents, one subagent per receipt; otherwise build them one after another yourself.

## Boundary (one per story)

Write the spec at `<video>/specs/NN-<slug>-boundary.json`, starting from `<skill>/templates/specs/boundary.example.json` (a real spec from episode 1). Its keys are listed in `engine/boundary.py`'s header:

- `sid`, `prefix`, `kicker{num,topic,glyph,text}`, `boundary_at`;
- `proves{header?,header_at,lines[{html,at}],subs[{text,at}],underline_at?,underline_dur?}` (a `<b>…</b>` in a line gets the underline);
- `nots{header?,header_at,rows[{kind: item|tag|chip|heading, text, at}]}`;
- `receipt{img,json,css_x0,css_y0,f,chrome_left,chrome_right,rise_at,highlights[{line,at,dur}]}`, plus optional `dim_at`, `cols_top`.

Paths inside the spec are relative to `<video>`. Then:

```sh
python3 <skill>/engine/boundary.py <video>/specs/NN-<slug>-boundary.json <video>/compositions/NN-<slug>-boundary.html
```

(`--project <video>` is needed only when the spec is not in `<video>/specs/`.)

Receipt window geometry: the window is 1400 × 192 px and shows the capture's CSS pixels from (`css_x0`, `css_y0`), scaled by `f`.
- Take the quote's `lines[]` (x, y, w, h in CSS px) from the receipt JSON. `highlights[].line` indexes `lines[]`.
- Choose `f` between 1.5 and 2.0 so that 1400 / f is wider than the widest line plus margins.
- `css_x0` = the lines' x − about 30.
- `css_y0` = the first line's y − (192 / f − the block's height) / 2. Example: lines spanning y 378–420 with f 1.75 give 344.

Header words: PROVES / DOESN'T PROVE, or "Establishes / Doesn't establish", "Shows / Doesn't show" (`references/editorial.md`). Put every `at` on the words that say it. Motion: svg-path-draw boundary, waterfall rows, receipt rise, highlight sweep.

## Board (between stories)

```sh
python3 <skill>/engine/board.py <episode> <n> board-<n> <video>/compositions/NN-board-<n>.html <fill_at> <next_at> <zoom_at> <zoom_dur>
```

- `n`: the story just finished (1-based). Its TEST slot fills at `fill_at`, on the word that names the test.
- `next_at`: the next card lights up, on "Next".
- `zoom_at`, `zoom_dur`: the coordinate-target-zoom into the next card, which is the cut into the next story. It ends with the scene: `zoom_at + zoom_dur ≈ duration`.
- Card text: `stories[]` → `card_title` (falls back to `topic`), `badge`, `test` (≤ 26 characters; the slot is 450 px wide).
- Example from episode 1: board-1 says "That's test one. Next: interfaces." and lasts 3.08 s: `fill_at 0.62`, `next_at 1.5`, `zoom_at 2.15`, `zoom_dur 0.9`.

Motion: slot fill, border light, coordinate-target-zoom as the cut.

## Receipt scene brief (for a subagent, or for yourself)

> You build one HyperFrames sub-composition scene for a Said vs. Shown episode. Project: `<video>`.
>
> Read first: `<video>/frame.md`; `<skill>/references/editorial.md`; `<skill>/references/scenes.md` (Receipt); `<skill>/templates/scenes/receipt.html`; `<video>/audio/scene-words.json` → your scene (sync every beat to these LOCAL times); the `hyperframes-core` skill's `SKILL.md` and `references/sub-compositions.md`.
>
> Contract: a `<template>` wrapper with `<style>` and `<script>` inside; root `<div id="root" data-composition-id="<SCENE_ID>" data-width="1920" data-height="1080">`; one paused GSAP timeline, registered last on `window.__timelines["<SCENE_ID>"]`; ids prefixed, CSS selectors prefixed with `[data-composition-id="<SCENE_ID>"]`; no `Math.random`, no `Date.now`, no network; no CSS transform on GSAP-transformed elements (use `fromTo`); keep y 920–1080 empty (captions); text ≥ 18 px.
>
> Truth: on-screen words come from the narration, the ledger quotes or the spec. The illustration carries a visible ILLUSTRATION tag and is never presented as a product's real output.
>
> Edit only your file. Run `npx -y hyperframes@<ver> lint <video>` and fix your findings. Return the file path, a beat table (local time → visual → synced words) and any concerns.
>
> Your scene: `<file>`, SCENE_ID `"<id>"`, prefix `"<p>-"`. `<what it shows, beat by beat>`

## Gotchas that `check` catches (fix them while authoring)

- A CSS transform and a GSAP transform on one element: use `fromTo`, and keep CSS transforms off anything GSAP moves.
- Overlapping text in piled cards: fade the text as the cards pile.
- Kicker text over a zoomed white page: keep the kicker's dark plate.
- An SFX `<audio>` without `data-duration`: put sound marks in `scenes.json` → `sfx` (assemble.py writes the tags), never inside a composition.
- More than 18 timed elements on one track: captions are one persistent layer switched on the main timeline (assemble.py does this); don't add per-word elements.

## Worked example

`references/example/` holds a one-story mini episode (brief, ledger, episode.json, script, scenes.json and a boundary spec) in the exact shapes the tools read. Its scene times are illustrative; real ones come from your `scene-words.json`.
