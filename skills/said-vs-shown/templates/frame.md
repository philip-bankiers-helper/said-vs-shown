# frame.md — Said vs. Shown design spec (series)

Concept: **what was said vs. what the source shows.** Human claims speak in a serif; machine checks, sources and metadata speak in mono. Real source pages are the exhibits, lit on a dark table. One accent, the edition's highlighter, marks exactly what is being checked and nothing else.

This file is the design truth for one episode's `video/` project. It is copied from the skill's `templates/frame.md`; only the `--accent` row changes per edition.

## Palette (strict)

| Token | Hex | Use |
|---|---|---|
| `--ink` | `#14130F` | background, every scene (warm near-black, never #000) |
| `--ink-2` | `#1C1A15` | cards, panels, caption plate |
| `--line` | `#3A352C` | hairlines, card borders (2px on video) |
| `--paper` | `#EEE8DC` | primary text (never #fff); the closing receipt's paper |
| `--muted` | `#A59D8D` | secondary text, metadata (6.9:1 on ink) |
| `--accent` | `#F2C14E` | highlighter, evidence boundary, kicker numerals, focus |
| `--accent-wash` | `rgba(242,193,78,0.42)` | highlighter bar over real (white) pages |
| `--correction` | `#E5484D` | corrections ONLY (strike-through). Never decorative. |
| `--receipt-ink-2` | `#5E584C` | secondary text on the closing receipt only (5.8:1 on paper) |

### Per-edition accent

Only `--accent` (and `--accent-wash`, the same color at 0.42) changes per edition. Background and neutrals never change.

| Edition | `--accent` | Name |
|---|---|---|
| AI | `#F2C14E` | highlighter amber |
| Markets (planned) | set at the edition's first slice | |

The scene templates are authored in AI amber. `engine/new_episode.py` writes the edition's accent (`editions/<edition>.yaml` → `design.accent`) into the `--accent` row above, and `engine/fill_scenes.py` swaps `#f2c14e` / `242, 193, 78` for it.

## Type

- **Newsreader** (serif): statements, story text, captions. 300 / 500 / 700 / 800. Display tracking −0.03em.
- **IBM Plex Mono**: kickers, badges, sources, metadata, labels, the wordmark and the closing receipt. 400 / 500 / 600; uppercase labels tracked +0.08em.
- Files: `assets/fonts/` (sources and licenses in `FONTS.md`). Plex ships as IBM's own pre-split files: `IBMPlexMono-<Weight>-Latin1.woff2` (Latin text and punctuation) plus `IBMPlexMono-<Weight>-Pi.woff2` (arrows, ✓, box drawing), declared with IBM's `unicode-range`.
- Sizes (1920×1080, full-screen viewing): statements 54–72px · story text 40–44px · captions 40px · labels ≥20px · card micro-labels 18px minimum.
- Light-on-dark: body weight 300–500, line-height +0.08.

## Confidence badges (shape + word, colorblind-safe)

Rule: the badge grades the HEADLINE claim of the item (`references/editorial.md`).

| Status | Glyph | Word |
|---|---|---|
| headline fact directly observable in a primary source (published artifact, dated release entry, signed agreement, official record) | solid square | CHECKED |
| headline rests on the company's/authors' own account of capability, performance or results | half-filled square | COMPANY |
| secondary reporting | outlined square | REPORTED |
| provider only (unverified) | dashed square | PROVIDER |
| older than the window | outlined square + muted | OLDER |
| teaching diagram | none | ILLUSTRATION tag |

Glyph CSS: 13–15px square, 2px `--paper` border; CHECKED filled `--paper`; COMPANY `linear-gradient(90deg, paper 50%, transparent 50%)`; PROVIDER dashed `--muted` border; OLDER `--muted` border.

## Motifs

- **Evidence boundary:** a dashed accent line (stroke 3px, dash 14/10). Draws with svg-path-draw. Separates PROVES | DOESN'T PROVE; underlines what the story covers.
- **Receipts:** real 2x captures inside a generic browser frame (no site chrome cloned), radius 14, 2px `--line` border, soft shadow. The camera pushes in with coordinate-target-zoom; the highlighter sweeps left→right synced to the spoken words. A pull-back dims the page while it moves and brings it back once the camera lands, so a white page never leaves the frame as a flash.
- **Source chip:** mono 20px, `--muted`, "SOURCE  domain/path · captured date".
- **Kicker / meta plate:** top-left, mono 22px on `rgba(20,19,15,0.94)`, radius 8: story number in accent, topic in paper, then badge · date · who. Outside story scenes the plate reads `<show> · <edition> · <window>` with the show name in accent.

## Brand

- **Show / tool name:** "Said vs. Shown". In running text, write it exactly so.
- **Wordmark:** the text `SAID VS. SHOWN` set in IBM Plex Mono 600, uppercase, tracked +0.16em, in `--paper` (or `--accent` inside a meta plate). No logo, no lockup, no animation sting. Inside a kicker it may carry a suffix after a muted middle dot: `SAID VS. SHOWN · DEMO`.
- **Closing card = a printed receipt.** The close is a paper slip (`--paper` background, `--ink` text, `--receipt-ink-2` for secondary text) on the dark table, 640px wide, right of center, with a torn (zig-zag) bottom edge and a soft shadow. Everything on it is IBM Plex Mono (20px lines, a 26px wordmark), uppercase labels tracked +0.06em. It prints in: a clip reveal top→bottom at a constant feed rate (~1.3 s), each line appearing as the feed passes it. Structure, top to bottom, separated by dashed rules (2px, dash 8/6, `--receipt-ink-2`):
  1. header: the wordmark (or the episode's `show`), then `<EDITION> · <WINDOW>` and `NO. <date>`;
  2. line items, one per story: `NN TOPIC` left, badge glyph + word right, each source below it as a muted `domain/path` line (truncated with … to fit);
  3. counts, dot-leader rows: `LEADS REVIEWED`, `STORIES`, `SOURCES CAPTURED`, `QUOTES LOCATED`, `CAPTURED <date>`. Counts are always computed (`fill_scenes.py`), never typed;
  4. the disclosure line (format below), wrapped, in `--ink`;
  5. footer, only when `credit` is true: `MADE WITH SAID VS. SHOWN`, centered, `--receipt-ink-2`.
  Left of the receipt: the sign-off (Newsreader 500, 64px), the companion-page call to action (mono 24px, accent) and the badge key. The card then holds still for reading (about 7 s of silence).
- **Disclosure line format:** `AI-produced · AI voice · every claim sourced · reviewed by <Name>`. Segments are joined by ` · `. The tools write the last segment from `episode.json` → `reviewed_by`: `reviewed by <Name>` only when a named person actually reviewed the episode, `not yet human-reviewed` until then; review wording typed into `disclosure` is dropped. Never shorten it to a logo or an icon. The same line goes on the companion page and in the video description.
- **Credit:** `episode.json` → `credit: true` prints the `MADE WITH SAID VS. SHOWN` footer on the receipt. It is the only place the tool is credited inside the picture.

## Layout

- Safe area: 120px sides, 80px top. Caption band: y 920–1080 (captions sit at 920–1040). Nothing else lives there.
- Meta strip top-left (kicker) and top-right (source chip), mono.
- Edge-anchored compositions; no centered floating stacks except the Squeeze story row.

## Motion

- Arrivals: waterfall-entry (binary opacity, power4.out). Group moves: nudge-curve. Camera: coordinate-target-zoom (power3.inOut, 1.2–1.6s). Lines: svg-path-draw.
- One transition family between stories: hard cut inside the episode; no wipes, no glitch.
- Ambient: a single accent radial glow breathing (sine-wave-loop), hairline ledger rules at 12%. Never more.
- Motion names are rule files in the `hyperframes-animation` skill (`rules/<name>.md`). Without that skill, copy the implementations in the Said vs. Shown skill's `templates/scenes/*.html`.

## Sound

- Sound marks only, at low level (mix volume 0.2–0.35), on structural beats: `assets/sfx/whoosh-short.wav` (the squeeze, a camera move into a story), `click-soft.wav` (a boundary drawing, a slot filling), `pop.wav` (a card landing). No music under voice.

## Don't

- No gradient text, neon, purple-blue gradients, stock imagery, avatars, AI imagery of real people/events.
- No music under voice. No word-by-word karaoke captions. No logo sting.
- No numbers the brief marks as unstable (repo counts).
- Never present an illustration as a product's real output.
