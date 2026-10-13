---
name: said-vs-shown
description: Turn a research brief into an evidence-first explainer video (Said vs. Shown) — every claim shown on a capture of its real source with the quote highlighted as it is spoken, each story closed on PROVES / DOESN'T PROVE, plus captions, vertical cuts and a companion page. Use when the user asks to make a Said vs. Shown episode, to turn a brief or a set of sourced claims into a fact-checked explainer video, or runs /said-vs-shown.
---

# Said vs. Shown — brief → evidence-first episode

Paths below use `${CLAUDE_SKILL_DIR}`, the folder containing this file. In agents other than Claude Code, read it as "this skill's folder"; every path is relative to it. Episodes are created in the user's working directory (`./episodes/<date>_<edition>/`). Data contracts: `references/project-layout.md`. Editorial rules: `references/editorial.md`. Scene kinds: `references/scenes.md`. Disclosure: `references/disclosure.md`.

**Hard rules.**
- Never bypass a login, paywall, CAPTCHA or bot wall. A page that refuses headless Chrome gets a labelled quote card, or a `--nojs` render of a capture already obtained.
- Every narrated or on-screen claim traces to `ledger/claims.json`.
- Nothing is published by this skill: you stop for the user's review before the final render.
- No paid API calls.
- Keep an episode to roughly 15 subagents or fewer.

Usage: `/said-vs-shown [edition] <brief path>`. The edition defaults to `ai` (`${CLAUDE_SKILL_DIR}/editions/<edition>.yaml`).

## Stages

Each stage ends on its completion criterion (✔). Do not advance until it holds.

0. **Ready.** Run `node "${CLAUDE_SKILL_DIR}/engine/doctor.mjs"`. If anything fails, run `"${CLAUDE_SKILL_DIR}/engine/setup.sh"` (it asks nothing and prints what it installs), then doctor again.
   - ✔ doctor exits 0.
1. **Intake.** Run `python3 "${CLAUDE_SKILL_DIR}/engine/new_episode.py" ./episodes <YYYY-MM-DD> <edition> --brief <brief> --editor "<user's name>"`.
   - Read the brief's own guardrails.
   - Keep the brief's story selection; if it has none, pick ≤3 stories by impact × novelty × evidence and record why in `edit/selection.md`.
   - Write one URL substring per line into `ledger/selected.txt`.
   - ✔ The episode folder exists, and the selected stories and their sources are listed.
2. **Capture.** Run `"${CLAUDE_SKILL_DIR}/engine/capture.sh" <episode>`.
   - ✔ Every URL has an entry in `ledger/capture-log.jsonl`. Sources with `ok:false` are noted as walls.
3. **Ledger.** Run the story verifiers, the adversarial refuters (default to refuted when unsure) and the lead checkers. Use `workflows/ledger.js` with the Workflow tool when the user has opted into workflows; otherwise use the same prompts as parallel subagents.
   - Save `ledger/claims.json` and `ledger/leads.json`.
   - Apply every refuter fix to the wording.
   - ✔ Every story claim has a status and either a verbatim quote or an explicit "unverifiable"; every refuted claim has a recorded fix.
4. **Episode facts.** Fill `edit/episode.json` per `references/project-layout.md`: stories, badges (rule in `editorial.md`), PROVES / DOESN'T PROVE, matrix, chapters, `one_thing`, disclosure, credit.
   - ✔ Every story has a badge, sources, receipts and scene ids.
5. **Script.** Write `video/audio/script.json`. One line per scene, in this order:
   - the squeeze
   - for each story: a receipt scene and a boundary scene
   - a board between stories
   - the payoff, the one-thing, and the close
   Each line lists its `claims`. Spoken numbers map to digits through `display`.
   - ✔ Each sentence maps to a claim or is marked editorial, and no refuted wording survives.
6. **Receipts.** Run `node "${CLAUDE_SKILL_DIR}/engine/receipt.mjs" --url <url> --quote "<verbatim>" --out <episode>/video/assets/receipts/Rnn-<slug>.png` for each receipt. For a page that 403s, use `--nojs 1 --url file://<episode>/ledger/capture/Sxx/extracted/page.html`.
   - ✔ Each receipt JSON has `found: true`, and a tiled glance shows real, legible pages.
7. **Voice.** Run `python3 "${CLAUDE_SKILL_DIR}/engine/voice.py" <episode>/video`. Its gates are strict and it writes `audio/scene-words.json`.
   - ✔ It exits 0.
8. **Scenes.** Per `references/scenes.md`:
   - Run `python3 "${CLAUDE_SKILL_DIR}/engine/fill_scenes.py" <episode>` for the squeeze, payoff, one-thing and close.
   - Run `board.py` once per board, and `boundary.py` once per boundary spec.
   - Author each receipt scene from `${CLAUDE_SKILL_DIR}/templates/scenes/receipt.html`, with a **bespoke illustration per story**. Vary the visuals: templated sameness reads as slop and risks YouTube's "mass-produced" rule.
   - Write `video/scenes.json`, with sound marks on structural beats only.
   - ✔ There is one composition per scene id.
9. **Assemble + check.** Run `python3 "${CLAUDE_SKILL_DIR}/engine/assemble.py" <episode>/video`, then `npx -y hyperframes@<version from engine/config.json> check` inside `video/`. Then run `snapshot --at <key beats>` and inspect one contact sheet.
   - ✔ check passes with 0 findings, the sheet was inspected, and every fix was re-checked.
10. **Review (hard stop).** Show the user the contact sheet, the script with claim ids, and the ledger's refuter fixes. Open the Studio preview (`npx hyperframes preview --background`).
    - ✔ The user explicitly approves. Record their name and the date in `edit/episode.json` as `reviewed_by` / `reviewed_at`, then re-run `fill_scenes.py --only close` and `assemble.py` so the disclosure says "reviewed by". The disclosure line depends on this being true.
11. **Render + deliver.** Run `npx -y hyperframes@<version> render -q delivery -w 3 -o video/renders/master.mp4`, then `python3 "${CLAUDE_SKILL_DIR}/engine/deliver.py" <episode> --master video/renders/master.mp4`.
    - ✔ deliver.py exits 0: duration, −16 ±1 LUFS, a web cut ≤15 MB, the flash check, captions, transcript, SOURCES and the companion page.

Then hand the user the files, plus the platform checklist in `references/disclosure.md`. They publish; you never post.

A new edition, a new scene kind or a big visual change → build a 25–40 s slice first and get the user's reaction before the full episode.
