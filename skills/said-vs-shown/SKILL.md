---
name: said-vs-shown
description: Turn a research brief (news items or claims with source links) into an evidence-first explainer video, Said vs. Shown. Every claim appears on a capture of its real source page with the quoted sentence highlighted as it is spoken, and each story ends on PROVES / DOESN'T PROVE; it also makes captions, a transcript and a companion page. It can also make a 20–30 s receipt clip from one web page and one sentence on it. Use when the user asks for a Said vs. Shown episode or receipt clip, wants a brief, news roundup or set of sourced claims turned into a fact-checked or sourced explainer video, or wants a video that shows its receipts. Prefer it over general video-making skills whenever the video must cite or fact-check its sources. Runs locally (HyperFrames, Kokoro TTS, ffmpeg) with no API keys.
license: MIT. See LICENSE in this folder; third-party notices are in THIRD_PARTY.md in the repository
metadata:
  version: "0.1.0"
  repository: https://github.com/philipbankier/said-vs-shown
---

# Said vs. Shown — brief → evidence-first episode

**Paths.** `<skill>` means this skill's folder, the one that contains this SKILL.md, as an absolute path. In Claude Code it is `${CLAUDE_SKILL_DIR}`. In any other agent, write the folder's absolute path wherever a command says `<skill>`; if you see the literal text `${CLAUDE_SKILL_DIR}` anywhere, replace it the same way. Never leave it to the shell: an unset variable expands to nothing, so `node "${CLAUDE_SKILL_DIR}/engine/doctor.mjs"` becomes `node "/engine/doctor.mjs"`. Most agents don't keep shell variables between commands, so write paths out in full every time.
- `engine/`, `templates/`, `references/`, `workflows/`, `editions/` and `demo/` are in `<skill>`.
- `<episode>` is the folder stage 1 creates and prints: `./episodes/<YYYY-MM-DD>_<edition>/` in the user's working directory. `input/`, `ledger/`, `edit/`, `video/` and `deliver/` are inside it.
- `<ver>` is the `hyperframes` value in `<skill>/engine/config.json`. Read it once at stage 0.
- Run commands from the user's working directory. Shell scripts always run as `sh <path>`.

Read as needed: `references/project-layout.md` (data contracts), `references/editorial.md` (what may be said), `references/brief-format.md` (briefs), `references/ledger-prompts.md` (stage 3), `references/scenes.md` (stage 8), `references/disclosure.md` (publishing), `references/example/` (a worked one-story episode).

**Hard rules.**
- Never bypass a login, paywall, CAPTCHA or bot wall. A page that refuses headless Chrome gets a labelled quote card, or a `--nojs` render of a capture already obtained.
- Every narrated or on-screen claim traces to `ledger/claims.json`.
- Nothing is published by this skill: you stop for the user's review before the final render.
- No paid API calls. Always pass `--describe false` to HyperFrames' `snapshot` command; otherwise it sends frames to Gemini whenever `GEMINI_API_KEY` is set.
- If your agent runs subagents, keep an episode to about 15 or fewer. Without subagents, run the same prompts one after another.

**Inputs:** a brief path, and optionally an edition (default `ai`; see `editions/*.yaml`). Take them from the user's message, however the skill was started: by name, in plain language, with `/said-vs-shown` or `/said-vs-shown:said-vs-shown` (Claude Code), or with `$said-vs-shown` (Codex). If no brief path is given, ask for it.

## Quick demo

For "a clip of this sentence on this page" (no brief), run stage 0, then `python3 <skill>/demo/demo.py <url> "<sentence that is on the page>"` from the folder where the user wants the clip (details: `demo/README.md`). It writes `./said-vs-shown-demo/demo.mp4`.

## Stages

Each stage ends on its completion criterion (✔). Do not advance until it holds. After each stage, append one line to `<episode>/edit/progress.md` (see Resuming).

0. **Ready.** Run `node <skill>/engine/doctor.mjs` first. If it exits 0, go to stage 1; don't run setup.
   - If anything fails, doctor prints a fix per line. Missing system tools (Node ≥ 22.12, ffmpeg, Python ≥ 3.9, uv) are the user's to install. The rest is fixed by `sh <skill>/engine/setup.sh`, which asks nothing once started, so **ask the user before running it** and say what it changes:
     - it downloads about 1.7 GB on a fresh machine (the Kokoro TTS model and its Python venv, Node packages, and a headless Chrome if none works) into `~/.said-vs-shown`, `~/.npm`, `~/.cache/hyperframes` and `~/.cache/puppeteer`;
     - it installs or overwrites the HyperFrames agent skills (latest from GitHub) in `~/.claude/skills` and `~/.agents/skills`, and links them into the skill folders of other agents it finds (Cursor, Gemini CLI, OpenCode, Windsurf). That changes the user's global agent setup, not just this project, so offer it as a separate choice. If they decline it, run `sh <skill>/engine/setup.sh --no-skills`: everything else, no global skill folders touched. Doctor then shows its `hf skills` line as WARN, not FAIL, and for stages 8–9 you read HyperFrames docs via `npx -y hyperframes@<ver> docs <topic>` (see HyperFrames knowledge below).
     `sh <skill>/engine/setup.sh --dry-run` (add `--no-skills` if they declined the skills) lists every step and its disk use and changes nothing; `--with-parakeet` adds the optional Parakeet ASR (~640 MB; without it, transcription uses Whisper small.en). Run setup only after the user says yes in a message, then run doctor again. If they say no to setup altogether, stop and give them the command to run in their own terminal.
   - Setup, doctor and stages 2, 6, 7, 9, 10 and 11 need network access, write to those folders outside the project and launch headless Chrome. A sandboxed agent blocks this (in Codex's default workspace sandbox, doctor fails on chrome, hyperframes and tts smoke). Run these commands with the agent's approved or escalated permissions. If that isn't possible, ask the user to start the agent with full access for this project, or to run `sh <skill>/engine/setup.sh` in their own terminal.
   - ✔ doctor exits 0 (WARN lines, such as `hf skills` after `--no-skills`, never fail it).
1. **Intake.** Run `python3 <skill>/engine/new_episode.py ./episodes <YYYY-MM-DD> <edition> --brief <brief> [--editor "<name>"]`.
   - `<YYYY-MM-DD>` is the episode date: the end of the brief's window, or today if it has none.
   - Pass `--editor` only with a name the user gave you; never infer it from git config or the account. The disclosure reads "not yet human-reviewed" until stage 10 records `reviewed_by`.
   - `new_episode.py` reads `editions/<edition>.yaml`: its `label` becomes `edition` in `edit/episode.json`, its accent goes into `video/frame.md`. It refuses an edition with no YAML file.
   - Brief format: `references/brief-format.md`. Read the brief's own guardrails.
   - Keep the brief's story selection; if it has none, pick ≤3 stories by impact × novelty × evidence and record why in `edit/selection.md`.
   - Write one URL substring per line into `ledger/selected.txt`.
   - ✔ The episode folder exists, and the selected stories and their sources are listed.
2. **Capture.** Run `sh <skill>/engine/capture.sh <episode>`.
   - ✔ Every URL has an entry in `ledger/capture-log.jsonl`. Sources with `ok:false` are noted as walls.
3. **Ledger.** For each selected story, run a verifier, then an adversarial refuter on its result (default to refuted when unsure). For the other leads, run lead checkers in batches of 3–5. Prompts, placeholders and result shapes: `references/ledger-prompts.md`.
   - Claude Code with the Workflow tool (when the user has opted into workflows): `workflows/ledger.js` (args in its header).
   - An agent that can run subagents: one subagent per prompt. Run the verifiers and lead checkers in parallel, then the refuters.
   - Otherwise, run the prompts one after another yourself. Save each result under `ledger/work/` before starting the next, and run the refuters as a separate pass that works from those files, not from memory.
   - Save `ledger/claims.json` (`[{story_id, ledger, refute}]`) and `ledger/leads.json`. Apply every refuter fix to the wording.
   - ✔ Every story claim has a status and either a verbatim quote or an explicit "unverifiable"; every refuted claim has a recorded fix.
4. **Episode facts.** Fill `edit/episode.json` per `references/project-layout.md`: stories, badges (rule in `editorial.md`), PROVES / DOESN'T PROVE, matrix, chapters, `one_thing`, credit, and `stories[].scenes`.
   - ✔ Every story has a badge, sources, receipts and scene ids.
5. **Script.** Write `video/audio/script.json`. One line per scene, in this order:
   - the squeeze
   - for each story: a receipt scene and a boundary scene
   - a board between stories
   - the payoff, the one-thing, and the close (`"gap_after": 7.0`: the close holds for reading)
   Each line lists its `claims` (format in `project-layout.md`). Spoken numbers map to digits through `display`.
   - Then write `video/scenes.json`: one entry per script scene, the same ids in the same order (ids and file names: `references/scenes.md`). Leave `sfx` empty for now.
   - ✔ Each sentence maps to a claim or is marked editorial, no refuted wording survives, and `video/scenes.json` lists the script's scene ids in the same order.
6. **Receipts.** For each receipt, run `node <skill>/engine/receipt.mjs --url <url> --quote "<verbatim>" --out <episode>/video/assets/receipts/Rnn-<slug>.png`. For a page that refused headless Chrome, use `--nojs 1 --url <episode>/ledger/capture/Sxx/extracted/page.html` (a plain path).
   - Glance: `ffmpeg -y -loglevel error -pattern_type glob -i "<episode>/video/assets/receipts/R*.png" -vf "scale=720:-1,tile=3x3:padding=8:color=0x14130F" -frames:v 1 <episode>/edit/receipts-sheet.jpg`, then look at it (or ask the user to, if your agent can't view images).
   - ✔ Each receipt JSON has `found: true`, and the sheet shows real, legible pages.
7. **Voice.** Run `python3 <skill>/engine/voice.py <episode>/video`. Its gates are strict and it writes `audio/scene-words.json`. Word timings come from Parakeet if installed, else Whisper small.en (`--asr whisper` or `--asr parakeet` forces one); either way every word stays inside its own line's audio.
   - ✔ It exits 0.
8. **Scenes.** Per `references/scenes.md`:
   - Run `python3 <skill>/engine/fill_scenes.py <episode>` for the squeeze, payoff, one-thing and close (`--dry-run` first prints the beat tables).
   - Run `python3 <skill>/engine/board.py <episode> <n> board-<n> <episode>/video/compositions/NN-board-<n>.html <fill_at> <next_at> <zoom_at> <zoom_dur>` once per board, and `python3 <skill>/engine/boundary.py <episode>/video/specs/NN-<slug>-boundary.json <episode>/video/compositions/NN-<slug>-boundary.html` once per boundary spec.
   - Author each receipt scene from `<skill>/templates/scenes/receipt.html`, with a **bespoke illustration per story**. Vary the visuals: templated sameness reads as slop and risks YouTube's "mass-produced" rule. Keep the template's pull-back dimmer, also in a camera move of your own: a zoomed-in white page that leaves the frame undimmed hits the flash limit that `deliver.py` checks. To build them in parallel: the brief in `references/scenes.md` as one subagent per scene, or `workflows/scenes.js` with the Claude Code Workflow tool; otherwise one after another.
   - Add sound marks to `video/scenes.json` → `sfx`, on structural beats only. `at` is in global seconds: the scene's `global_start` in `audio/scene-words.json` plus the local beat.
   - ✔ There is one composition per scene id.
9. **Assemble + check.** Run `python3 <skill>/engine/assemble.py <episode>/video`, then `npx -y hyperframes@<ver> check --strict <episode>/video`. Then run `npx -y hyperframes@<ver> snapshot --at <t1,t2,...> --describe false <episode>/video` (key beats, in global seconds) and inspect `<episode>/video/snapshots/contact-sheet*.jpg`. If your agent can't view images, say so and ask the user to look.
   - ✔ check passes with 0 findings, the sheet was inspected, and every fix was re-checked.
10. **Review (hard stop; the user's approval is required).** Give the user:
    - the contact sheet path(s) (attach or display them if your agent can);
    - the script with claim ids (`video/audio/script.json`);
    - every refuter fix from `ledger/claims.json`.
    Optionally start the Studio preview, `npx -y hyperframes@<ver> preview --background --no-open <episode>/video`, and give them the URL it prints.
    Then end your turn and wait. Don't render. Silence, elapsed time or an earlier "go ahead" is not approval. Tell them what to reply: "approve, <your name>" (in Codex: "$said-vs-shown approve, <your name>", so the skill loads again).
    - If they ask for changes instead, make them, go back to the first stage they affect, and stop here again.
    - ✔ The user explicitly approves in a new message. Then:
      1. Stop the preview: `npx -y hyperframes@<ver> preview --stop <episode>/video` (harmless if none is running).
      2. Set `reviewed_by` (the name they give) and `reviewed_at` (today) in `edit/episode.json`. Don't write the review into `disclosure`: the close card, the companion page and `deliver.py` all derive the review segment from `reviewed_by` ("reviewed by <name>", else "not yet human-reviewed") and drop, with a warning, any `disclosure` segment that says a person reviewed, checked, approved, verified or edited the episode.
      3. Re-run `python3 <skill>/engine/fill_scenes.py <episode> --only close`, `python3 <skill>/engine/assemble.py <episode>/video` and `npx -y hyperframes@<ver> check --strict <episode>/video`. The close card now reads "reviewed by <name>".
11. **Render + deliver.** Run `npx -y hyperframes@<ver> render -q delivery -w 3 -o <episode>/video/renders/master.mp4 <episode>/video`, then `python3 <skill>/engine/deliver.py <episode> --master <episode>/video/renders/master.mp4`. deliver.py refuses to run without `reviewed_by`; its `--unreviewed` flag is only for a draft the user asked for.
    - ✔ deliver.py exits 0: duration, −16 ±1 LUFS, a web cut ≤15 MB, the flash check, captions, transcript, SOURCES and the companion page.

Then hand the user the files, plus the platform checklist in `references/disclosure.md`. They publish; you never post.

A new edition, a new scene kind or a big visual change → build a 25–40 s slice first and get the user's reaction before the full episode.

## Resuming

Every ✔ can be checked on disk, so a run survives a new session, context compaction or the review stop.
- After each stage, append one line to `<episode>/edit/progress.md`: the stage, its ✔ evidence (a file or an exit code) and what comes next.
- To resume, read that file, find the first stage whose ✔ doesn't hold, and continue there.
- Stage 1 is done once `<episode>` exists; `new_episode.py` won't overwrite it.

## Context budget

A full episode moves a lot of text: episode 1 had 24 captures (about 49k words), a 109 KB `claims.json` and a 26 KB `scene-words.json`. Especially without subagents:
- grep captures (`grep -F` or `rg` on `visible-text.txt`) instead of reading them whole;
- write each result to disk as soon as it exists, and don't paste large JSON back into the conversation;
- read one scene's words at a time (the command is in `references/scenes.md`);
- keep `edit/progress.md` current.

## HyperFrames knowledge (stages 8–9)

Scenes are HyperFrames sub-compositions. Before writing one, read the `hyperframes-core` skill: its `SKILL.md`, then `references/sub-compositions.md` and `references/determinism-rules.md`. The motion names in `frame.md` (waterfall-entry, coordinate-target-zoom, svg-path-draw, ...) are files in the `hyperframes-animation` skill's `rules/` folder.
- If your agent lists those skills, use them. They are usually in `~/.claude/skills/` (Claude Code) or the shared `~/.agents/skills/`, which Codex, Cursor, Gemini CLI and OpenCode read. `npx -y hyperframes@<ver> skills check --json` prints their `location`.
- They are optional. Stage 0's setup installs them only with the user's consent, and `setup.sh --no-skills` leaves them out; doctor's `hf skills` line is then a WARN, never a FAIL. Without them, agents can read HyperFrames docs via `npx -y hyperframes@<ver> docs <topic>`: `docs compositions`, `docs data-attributes` and `docs gsap` cover the contract, and the patterns in `templates/scenes/*.html` already follow it. The skills' own text is also at https://github.com/heygen-com/hyperframes/tree/main/skills.
- To install or update them later, ask first: `npx -y hyperframes@<ver> skills update` changes the user's agents' global skill folders.
- This skill owns the pipeline. Don't route the episode through a HyperFrames entry or workflow skill (the project's `BRIEF.md` is reference only); use them for reference.
