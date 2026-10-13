# Said vs. Shown

An agent skill that turns a research brief into a short explainer video that **shows its receipts**. Every claim appears on a capture of its real source page, with the quoted sentence highlighted as it is spoken. Every story ends on what the evidence **proves** and what it **doesn't prove**.

<!-- media: docs/media/receipt.gif — a 10 s loop of one receipt: page → push-in → highlight → PROVES / DOESN'T PROVE -->

▶ **Watch an episode:** _link to the hosted sample, added at launch_ · **Make a 30-second receipt clip from any web page:** [`demo/`](skills/said-vs-shown/demo/)

---

## Why

AI explainer videos are getting easy to make and hard to trust. Most narrate a script over stock visuals, and the viewer can't see where a claim came from or how far the evidence goes.

Said vs. Shown works like a careful newsroom desk:

- **Receipts.** It captures each source page and finds the exact sentence (verbatim, never paraphrased) that backs a claim. On screen, the camera pushes in on that sentence and highlights it while the narrator says it.
- **A fact-check that checks itself.** One pass of agents verifies each claim against the captured text. A second pass, prompted to refute, tries to break those verifications. In the first episode the refuter caught the narration saying OpenAI's manuscripts were "produced by an unreleased internal model". That's OpenAI's own claim, so the line became "manuscripts it **says were** produced by…".
- **Boundaries.** Each story closes on PROVES / DOESN'T PROVE. A benchmark score is not general intelligence. A product launch is not evidence that the answers are accurate. A formal proof checks its exact statement, not whether that statement is the one the paper claims.
- **Badges.** Every lead is graded: *Checked* (visible in a primary source), *Company* (rests on the company's or authors' own account), *Reported*, *Provider* or *Older*.

## What you get per episode

- A 2–4 min 16:9 video with burned-in captions
- Caption files (VTT, SRT), a transcript, chapters and a source list
- A static companion page: the video, chapters, a click-to-seek transcript, every receipt, and the leads that didn't make the cut
- The full editable [HyperFrames](https://github.com/heygen-com/hyperframes) project (HTML + GSAP), which you can open in HyperFrames Studio

## Install

Pick one way per agent. In Claude Code, install either the plugin or the personal skill, not both: Claude would see two skills with the same description.

**Claude Code (plugin, from GitHub):**

```
/plugin marketplace add philipbankier/said-vs-shown
/plugin install said-vs-shown@said-vs-shown
```

On Claude Code v2.1.275 or later, one line does both: `/plugin install said-vs-shown --marketplace philipbankier/said-vs-shown`. From a shell, the same commands are `claude plugin marketplace add …` and `claude plugin install …`. Invoke it as `/said-vs-shown:said-vs-shown`, or just ask.

**Claude Code (plugin, from a local folder):** clone or download the repo to `/path/to/said-vs-shown`, then

```
claude plugin marketplace add /path/to/said-vs-shown
claude plugin install said-vs-shown@said-vs-shown
```

**Claude Code (personal skill, from a clone):** link the inner skill folder, not the repo root (a folder with `.claude-plugin/` inside `~/.claude/skills/` loads as a plugin instead):

```
mkdir -p ~/.claude/skills && ln -s /path/to/said-vs-shown/skills/said-vs-shown ~/.claude/skills/said-vs-shown
```

Then `/said-vs-shown <brief>`, or just ask.

**Other agents ([Agent Skills](https://agentskills.io) format: Codex, Cursor, Gemini CLI, OpenCode and more):** list the agents you use with `-a`. Without `-a`, the CLI may install for every agent it knows and add folders such as `./agent/` to your project.

```
npx skills add philipbankier/said-vs-shown -a codex -a cursor -a gemini-cli -a opencode -y      # this project: .agents/skills/said-vs-shown
npx skills add philipbankier/said-vs-shown -g -a codex -a cursor -a gemini-cli -a opencode -y   # every project: ~/.agents/skills/said-vs-shown
```

Add `-a claude-code` to also link it for Claude Code (`.claude/skills/said-vs-shown`). Cursor and OpenCode also read `.claude/skills`, so if you use them, skip `-a claude-code` in the same project to avoid duplicate entries. `npx skills ls` shows where a skill landed. A project install (no `-g`) also writes `skills-lock.json` at the project root (each skill's source and hash); commit it or ignore it, as you prefer.

**Codex:** invoke it with `$said-vs-shown inbox/my-brief.md`, through `/skills`, or by asking. Codex's default workspace sandbox blocks what the pipeline needs (network, writes to `~/.said-vs-shown`, `~/.npm` and `~/.cache`, and launching headless Chrome): under it the health check fails on chrome and hyperframes, and passes in full access. Either approve the escalations when Codex asks, or start Codex in the project with `codex --sandbox danger-full-access --ask-for-approval on-request`. Run the one-time setup in your own terminal before the first session.

**Gemini CLI:** it activates the skill after asking your consent. Episode projects carry a `GEMINI.md` that imports their `AGENTS.md`.

### Setup and health check

The easiest way is to ask your agent to "set up Said vs. Shown": stage 0 of the skill runs the health check, and if something is missing it tells you what setup will change (downloads, plus the global HyperFrames skills below) and runs setup only after you say yes. By hand, find the skill folder for your install:

| Install | Skill folder (`<skill>`) |
|---|---|
| Claude Code plugin | `~/.claude/plugins/cache/said-vs-shown/said-vs-shown/<version>/skills/said-vs-shown` |
| Claude Code personal skill | `~/.claude/skills/said-vs-shown` |
| `npx skills add` | `.agents/skills/said-vs-shown` in your project, or `~/.agents/skills/said-vs-shown` with `-g` |
| git clone | `/path/to/said-vs-shown/skills/said-vs-shown` |

```
node <skill>/engine/doctor.mjs         # health check: exits 0 when everything is ready
sh <skill>/engine/setup.sh --dry-run   # what setup would download and change; changes nothing
sh <skill>/engine/setup.sh             # then run doctor again
```

Setup is idempotent; doctor prints a fix (with the full path) for anything that fails. Setup also installs the HyperFrames agent skills globally (see [What it runs, downloads and sends](#what-it-runs-downloads-and-sends)); `setup.sh --no-skills` leaves your agents' skill folders alone, and doctor then only warns: agents read the HyperFrames docs through the pinned CLI instead.

**Requirements:** macOS or Linux (Windows via WSL); Node ≥ 22.12; ffmpeg; Python ≥ 3.9 and [uv](https://docs.astral.sh/uv/) (setup creates its own Python 3.12 venv for Kokoro); about 1.7 GB of model and browser downloads on a fresh machine; ≥ 5 GB free disk to render.

## Try it locally before the repo is public

Everything above works from a local clone. Run episodes and demos from a separate, empty folder (for example `mkdir -p ~/svs-try && cd ~/svs-try`), never inside the repo: a local plugin install copies the whole folder, ignored files included.

- **Claude Code, live from your clone** (edits apply after `/reload-plugins`):
  ```
  cd ~/svs-try && claude --plugin-dir /path/to/said-vs-shown
  ```
  `claude --plugin-dir /path/to/said-vs-shown plugin list` shows `said-vs-shown@inline ✔ loaded` without starting a session.
- **Claude Code, installed copy:** the local-folder plugin commands above. A local install is a snapshot: `claude plugin update` keeps it while the version stays the same, so refresh it with
  ```
  claude plugin uninstall said-vs-shown@said-vs-shown && claude plugin install said-vs-shown@said-vs-shown
  ```
- **Other agents:** the same `npx skills add` commands with the path instead of the GitHub name, e.g. `npx skills add /path/to/said-vs-shown -a codex -y`.
- **Demo clips before launch:** the demo's end card shows `npx skills add philipbankier/said-vs-shown`, which won't resolve until the repo is public. Pass your own line, e.g. `--install-line "coming soon"`. Episode companion pages link the repo too; `deliver.py --repo-url <url>` changes that link.
- **Releasing:** bump `version` in `.claude-plugin/plugin.json` (and `metadata.version` in `SKILL.md`) for every release, or installed plugins won't pick up the change. The HyperFrames version lives in `skills/said-vs-shown/engine/config.json` → `hyperframes`; when you bump it, update the pins in `templates/project/package.json` and `templates/project/AGENTS.md` too (`tests/test_templates.py` fails until they match).

## Quickstart

1. **A 30-second receipt clip from any page** (no brief needed). From the folder where you want the clip:
   `python3 <skill>/demo/demo.py https://example.com "This domain is for use in documentation examples without needing permission."`
   It writes `./said-vs-shown-demo/demo.mp4`. The sentence must be on the page verbatim.
2. **A full episode:** put a brief in `./inbox/` (format: [`references/brief-format.md`](skills/said-vs-shown/references/brief-format.md); a small real one: `<skill>/references/example/input/brief.md`), then ask your agent: *"Make a Said vs. Shown episode from inbox/my-brief.md"*. You can also type `/said-vs-shown:said-vs-shown inbox/my-brief.md` (Claude Code plugin), `/said-vs-shown inbox/my-brief.md` (Claude Code personal skill, Cursor) or `$said-vs-shown inbox/my-brief.md` (Codex).
   - The skill walks through 12 stages (0–11): ready → intake → capture → ledger → episode facts → script → receipts → voice → scenes → assemble + check → review (hard stop) → render + deliver.
   - It stops for your review before the final render, and never publishes.
   - Briefs work best when every item links its primary source.

## How it works

```
brief ─▶ capture every source ─▶ ledger: verify ▸ refute ▸ fix wording ─▶ script (each line → claim ids)
      ─▶ receipts (2x captures, quote located) ─▶ voice (Kokoro, local) + word timings (Whisper, or Parakeet if installed; local)
      ─▶ scenes (HyperFrames: squeeze · receipt · boundary · board · payoff · close) ─▶ lint/check ─▶ render ─▶ deliver
```

Quality gates fail the run instead of shipping quietly:
- 145–185 words per minute
- captions ≤ 42 characters and ≤ 20 characters per second (21 tolerated)
- −16 LUFS loudness
- zero layout or contrast findings (`npx -y hyperframes@<version> check --strict`)
- the WCAG flash limit

Every on-screen claim is traced to the ledger by the agent at the script stage (each line lists its claim ids); that check is not yet automated.

## What it runs, downloads and sends

- **Fetches** the source pages listed in your brief, using a headless browser. It never logs in, clicks consent banners, solves CAPTCHAs or bypasses bot walls. A page that refuses gets a labelled quote card instead.
- **Downloads, once:**
  - the Kokoro TTS model (~340 MB) and a Python 3.12 venv for it (~150 MB)
  - the HyperFrames CLI via `npx` (~120 MB), plus HyperFrames' own Chrome (~390 MB) on the first capture or render
  - a headless Chrome (~200 MB), only if none is found
  - Whisper small.en (~470 MB) on the first transcription, or optionally Parakeet ASR (~640 MB) instead
- **Installs agent skills globally:** setup runs `npx hyperframes@<version> skills update`, which installs or overwrites the HyperFrames skills (latest from GitHub) in `~/.claude/skills` and `~/.agents/skills` and links them into the skill folders of other agents it finds (Cursor, Gemini CLI, OpenCode, Windsurf). Everything else goes under `~/.said-vs-shown`. When your agent runs the skill, it asks you before it runs setup, and `--no-skills` skips this step.
- **Runs locally:** text-to-speech, speech recognition, rendering. It needs **no API keys and no paid services**. HyperFrames' `snapshot` command would send frames to Gemini when `GEMINI_API_KEY` is set; the skill always passes `--describe false`.
- **Sends:** nothing of its own. Your agent (e.g. Claude Code) uses your own account as usual. Compositions load GSAP from cdn.jsdelivr.net when previewed or rendered (put `gsap.min.js` in `video/assets/vendor/` to render offline). The HyperFrames CLI collects anonymous usage telemetry by default; turn it off with `npx -y hyperframes@0.8.147 telemetry disable` or `HYPERFRAMES_NO_TELEMETRY=1`.
- **Never redistributes captures.** Source screenshots are made at build time on your machine and are git-ignored.

## Using it responsibly

- **Disclosure is built in.** Videos carry an "AI-produced · AI voice · every claim sourced · reviewed by <you>" line; until you review the episode it reads "not yet human-reviewed". The tools generate that line; nothing typed into the episode can extend it. Credits for third-party music, sound, footage, images, translation or data go in `credits` (`"music: …"`) and print on their own line. Platforms differ: Meta requires an AI label for realistic AI voiceovers, and YouTube asks you to disclose realistic synthetic content. Label your uploads.
- **A human reviews every episode before it's published.** The skill stops for that review.
- **The badges and PROVES / DOESN'T PROVE are editorial judgments made from the sources you gave it.** They show what the sources support, not absolute truth.
- **Screenshots of third-party pages are quotation for commentary.** Keep crops tight on the quoted sentence, credit the source on screen, and don't put outlet photos or logos in thumbnails.

The video end card says **"Made with Said vs. Shown"**. Turn it off with `"credit": false` in `edit/episode.json`.

## Credits and licenses

MIT © 2026 Philip Bankier. Built on [HyperFrames](https://github.com/heygen-com/hyperframes) (Apache-2.0, HeyGen) and [GSAP](https://gsap.com/standard-license/). Third-party licenses are listed in [THIRD_PARTY.md](THIRD_PARTY.md).
