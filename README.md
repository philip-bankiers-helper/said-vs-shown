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

- A 2–4 min 16:9 video with burned-in captions, plus vertical cuts (one per story)
- Caption files (VTT, SRT), a transcript, chapters and a source list
- A static companion page: the video, chapters, a click-to-seek transcript, every receipt, and the leads that didn't make the cut
- The full editable [HyperFrames](https://github.com/heygen-com/hyperframes) project (HTML + GSAP), which you can open in HyperFrames Studio

## Install

**Claude Code (plugin):**

```
/plugin install said-vs-shown --marketplace philipbankier/said-vs-shown
```

On Claude Code older than v2.1.275, use `/plugin marketplace add philipbankier/said-vs-shown`, then `/plugin install said-vs-shown@said-vs-shown`.

**Other agents ([Agent Skills](https://agentskills.io) format):**

```
npx skills add philipbankier/said-vs-shown
```

Then run the one-time setup and the health check from the skill folder:

```
skills/said-vs-shown/engine/setup.sh
node skills/said-vs-shown/engine/doctor.mjs
```

**Requirements:** macOS or Linux (Windows via WSL); Node ≥ 22; ffmpeg; Python ≥ 3.10 with [uv](https://docs.astral.sh/uv/); about 2 GB of model and browser downloads; ≥ 5 GB free disk to render.

## Quickstart

1. **A 30-second receipt clip from any page** (no brief needed):
   `python3 skills/said-vs-shown/demo/demo.py https://example.com "a sentence that is on that page"`
2. **A full episode:** put a brief in `./inbox/`, then ask your agent: *"Make a Said vs. Shown episode from inbox/my-brief.md"*. In Claude Code you can also type `/said-vs-shown:said-vs-shown inbox/my-brief.md` (plugin install) or `/said-vs-shown inbox/my-brief.md` (skills install).
   - The skill walks through 11 stages: capture → ledger → script → receipts → voice → scenes → check → render → deliver.
   - It stops for your review before anything is published.
   - Briefs work best when every item links its primary source.

## How it works

```
brief ─▶ capture every source ─▶ ledger: verify ▸ refute ▸ fix wording ─▶ script (each line → claim ids)
      ─▶ receipts (2x captures, quote located) ─▶ voice (Kokoro, local) + word timings (Parakeet/whisper, local)
      ─▶ scenes (HyperFrames: squeeze · receipt · boundary · board · payoff · close) ─▶ lint/check ─▶ render ─▶ deliver
```

Quality gates fail the run instead of shipping quietly:
- 145–185 words per minute
- captions ≤ 42 characters and ≤ 21 characters per second
- −16 LUFS loudness
- zero layout or contrast findings
- the WCAG flash limit
- every on-screen claim traced to the ledger

## What it runs, downloads and sends

- **Fetches** the source pages listed in your brief, using a headless browser. It never logs in, clicks consent banners, solves CAPTCHAs or bypasses bot walls. A page that refuses gets a labelled quote card instead.
- **Downloads, once:**
  - the Kokoro TTS model (~350 MB)
  - a headless Chrome (~200 MB)
  - optionally Parakeet ASR (~640 MB); whisper small.en is the fallback
  - the HyperFrames CLI and skills via `npx`
- **Runs locally:** text-to-speech, speech recognition, rendering. It needs **no API keys and no paid services**.
- **Sends:** nothing of its own. Your agent (e.g. Claude Code) uses your own account as usual. The HyperFrames CLI collects anonymous usage telemetry by default; turn it off with `npx hyperframes telemetry disable` or `HYPERFRAMES_NO_TELEMETRY=1`.
- **Never redistributes captures.** Source screenshots are made at build time on your machine and are git-ignored.

## Using it responsibly

- **Disclosure is built in.** Videos carry an "AI-produced · AI voice · every claim sourced · reviewed by <you>" line. Platforms differ: Meta requires an AI label for realistic AI voiceovers, and YouTube asks you to disclose realistic synthetic content. Label your uploads.
- **A human reviews every episode before it's published.** The skill stops for that review.
- **The badges and PROVES / DOESN'T PROVE are editorial judgments made from the sources you gave it.** They show what the sources support, not absolute truth.
- **Screenshots of third-party pages are quotation for commentary.** Keep crops tight on the quoted sentence, credit the source on screen, and don't put outlet photos or logos in thumbnails.

The video end card says **"Made with Said vs. Shown"**. Turn it off with `"credit": false` in `edit/episode.json`.

## Credits and licenses

MIT © 2026 Philip Bankier. Built on [HyperFrames](https://github.com/heygen-com/hyperframes) (Apache-2.0, HeyGen) and [GSAP](https://gsap.com/standard-license/). Third-party licenses are listed in [THIRD_PARTY.md](THIRD_PARTY.md).
