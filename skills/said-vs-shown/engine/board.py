#!/usr/bin/env python3
"""board.py — generate a between-stories Board interstitial (one file per board) from edit/episode.json.

usage: board.py <episode_dir> <n> <scene_id> <out.html> <fill_at> <next_at> <zoom_at> <zoom_dur>
  episode_dir = the episode root (holds edit/episode.json); its video/ dir is accepted too
  n           = story just finished (1-based); its TEST slot fills at <fill_at>
  next_at     = card n+1 lights (on "Next:")
  zoom_at     = coordinate-target-zoom into card n+1 begins (the cut into the next story), lasting zoom_dur
  With n == number of stories (a closing recap board) there is no next card: next_at/zoom_* are ignored.

One card per story (1-4): stories[].card_title (falls back to topic), stories[].badge, stories[].test.
The meta line is show · edition · window. Times are seconds from the scene's start.
Run engine/scope_css.py afterwards (assemble.py does it for every composition).
"""
import html
import json
import os
import sys

BADGES = {'checked': 'checked', 'verified': 'checked', 'company': 'company', 'company_claim': 'company',
          'reported': 'reported', 'provider': 'provider', 'provider_only': 'provider',
          'older': 'older', 'older_background': 'older'}

# Fonts: templates/fonts/ (FONTS.md). Plex ships as IBM's own pre-split files, declared with IBM's unicode-range.
PLEX_FILE = {400: 'Regular', 500: 'Medium', 600: 'SemiBold'}
PLEX_LATIN1 = ('U+0020-007E, U+00A0-00FF, U+0131, U+0152-0153, U+02C6, U+02DA, U+02DC, U+2013-2014, U+2018-201A, '
               'U+201C-201E, U+2020-2022, U+2026, U+2030, U+2039-203A, U+2044, U+20AC, U+2122, U+2212, U+FB01-FB02')
PLEX_PI = ('U+03C0, U+0E3F, U+2000-200D, U+2010-2012, U+2015, U+2028-2029, U+202F, U+2032-2033, U+203E, U+205F, U+2070, '
           'U+2074-2079, U+2080-2089, U+2113, U+2116, U+2126, U+212E, U+2150-2151, U+2153-215E, U+2190-2199, U+21A9-21AA, '
           'U+21B0-21B3, U+21B6-21B7, U+21BA-21BB, U+21C4, U+21C6, U+2202, U+2206, U+220F, U+2211, U+2215, U+2219-221A, '
           'U+221E, U+222B, U+2236, U+2248, U+2260, U+2264-2265, U+2400-2421, U+2500-259F, U+25CA, U+2713, U+274C, '
           'U+2B0E-2B11, U+3000, U+FEFF, U+FFFD')


def font_faces(newsreader, plex, indent='        '):
    """@font-face rules for the given Newsreader and IBM Plex Mono weights (files under video/assets/fonts/)."""
    rules = [f'@font-face {{ font-family: "Newsreader"; font-weight: {w}; src: url("assets/fonts/newsreader-latin-{w}-normal.woff2") format("woff2"); }}'
             for w in newsreader]
    for w in plex:
        for part, rng in (('Latin1', PLEX_LATIN1), ('Pi', PLEX_PI)):
            rules.append(f'@font-face {{ font-family: "IBM Plex Mono"; font-weight: {w}; '
                         f'src: url("assets/fonts/IBMPlexMono-{PLEX_FILE[w]}-{part}.woff2") format("woff2"); unicode-range: {rng}; }}')
    return ('\n' + indent).join(rules)


def load_episode(path):
    for cand in (os.path.join(path, 'edit', 'episode.json'), os.path.join(path, '..', 'edit', 'episode.json')):
        if os.path.isfile(cand):
            with open(cand, encoding='utf-8') as fh:
                return json.load(fh)
    sys.exit(f'board.py: no edit/episode.json under {path} (pass the episode root)')


def num(x):
    """Compact number for CSS/JS: 12.0 -> 12, 0.8200000001 -> 0.82."""
    x = round(float(x), 3)
    return int(x) if x == int(x) else x


def main(argv):
    if len(argv) != 8:
        sys.exit(__doc__.strip())
    ep_dir, n, sid, out = argv[0], int(argv[1]), argv[2], argv[3]
    fill_at, next_at, zoom_at, zoom_dur = map(float, argv[4:8])
    E = load_episode(ep_dir)
    stories = E.get('stories') or []
    N = len(stories)
    if not 1 <= N <= 4:
        sys.exit(f'board.py: the board shows 1-4 stories; episode.json has {N}')
    if not 1 <= n <= N:
        sys.exit(f'board.py: n must be 1..{N} (story just finished); got {n}')
    for i, s in enumerate(stories):
        if s.get('badge') not in BADGES:
            sys.exit(f'board.py: stories[{i}].badge {s.get("badge")!r} is not one of checked|company|reported|provider|older')
        if not s.get('test'):
            sys.exit(f'board.py: stories[{i}] has no "test" (the TEST slot text)')

    # layout: 3 cards = 450px wide, 60px apart, centred (x = 450/960/1470); 4 cards shrink to fit the 120px margins
    GAP, MARGIN = 60, 120
    W = min(450, (1920 - 2 * MARGIN - (N - 1) * GAP) // N)
    H, CY = 225, 552
    x_start = round(960 - (N * W + (N - 1) * GAP) / 2)
    LEFT = [x_start + k * (W + GAP) for k in range(N)]
    CX = [x + W / 2 for x in LEFT]
    title_px = 42 if W >= 450 else 36
    p = f'b{n}-'
    def esc(x):  # text nodes only
        return html.escape(str(x), quote=False)

    cards = []
    for k, s in enumerate(stories):
        st = BADGES[s['badge']]
        title = s.get('card_title') or s.get('topic') or f'Story {k + 1}'
        state = 'done' if k < n else ('next' if k == n else 'idle')
        slot = (f'<span class="slot-text" id="{p}slot-{k}">{esc(s["test"])}</span>' if k < n else '<span class="slot-blank"></span>')
        cards.append(f'''        <div class="bcard {state}" id="{p}card-{k}" style="left:{LEFT[k]}px; top:{CY - H // 2}px">
          <div class="bcard-top"><span class="bcard-id">{k + 1:02d}</span><span class="badge"><span class="glyph g-{st}"></span>{st.upper()}</span></div>
          <div class="bcard-title">{esc(title)}</div>
        </div>
        <div class="bslot" id="{p}slotrow-{k}" style="left:{LEFT[k]}px; top:{CY + H // 2 + 14}px">TEST {slot}</div>''')

    js = [
        '// the slot of the story just finished fills (earlier slots are already filled)',
        f'tl.fromTo("#{p}slot-{n - 1}", {{ opacity: 0, y: 22 }}, {{ opacity: 1, y: 0, duration: 0.16, ease: "power4.out" }}, {num(fill_at)});',
        f'tl.fromTo("#{p}card-{n - 1}", {{ borderColor: "#f2c14e" }}, {{ borderColor: "#3a352c", duration: 0.4, ease: "power1.out" }}, {num(fill_at + 0.2)});',
    ]
    if n < N:
        off_x, off_y = CX[n] - 960, CY - 540
        js += [
            '// "Next:" — the next card lights',
            f'tl.fromTo("#{p}card-{n}", {{ borderColor: "#3a352c" }}, {{ borderColor: "#f2c14e", duration: 0.25, ease: "power2.out" }}, {num(next_at)});',
            '// coordinate-target-zoom into the next card: the cut into the next story',
            f'tl.fromTo("#{p}zoom-outer", {{ scale: 1 }}, {{ scale: 2.6, duration: {num(zoom_dur)}, ease: "power3.in" }}, {num(zoom_at)});',
            f'tl.fromTo("#{p}zoom-inner", {{ x: 0, y: 0 }}, {{ x: {num(-off_x)}, y: {num(-off_y)}, duration: {num(zoom_dur)}, ease: "power3.in" }}, {num(zoom_at)});',
            f'tl.to(["#{p}meta-l", "#{p}meta-r"], {{ opacity: 0, duration: 0.3 }}, {num(zoom_at)});',
        ]

    meta_l = ' · '.join(esc(x) for x in (E.get('edition'), E.get('window')) if x)
    show = esc(E.get('show') or 'Said vs. Shown')
    FONT_FACES = font_faces((500,), (400, 600))
    page = f'''<!doctype html>
<html>
  <head>
    <meta charset="UTF-8" />
  </head>
  <body>
    <template>
      <style>
        {FONT_FACES}
        #root {{ position: absolute; inset: 0; overflow: hidden; color: #eee8dc; font-family: "Newsreader", serif; }}
        .mono {{ font-family: "IBM Plex Mono", monospace; text-transform: uppercase; letter-spacing: 0.08em; }}
        #{p}meta-l, #{p}meta-r {{ position: absolute; top: 56px; font-size: 22px; color: #a59d8d; white-space: nowrap; }}
        #{p}meta-l {{ left: 120px; }}
        #{p}meta-l b {{ color: #f2c14e; font-weight: 600; }}
        #{p}meta-r {{ right: 120px; }}
        #{p}meta-r b {{ color: #eee8dc; font-weight: 600; }}
        #{p}zoom-outer {{ position: absolute; inset: 0; transform-origin: 50% 50%; will-change: transform; }}
        #{p}zoom-inner {{ position: absolute; inset: 0; will-change: transform; }}
        .bcard {{ position: absolute; width: {W}px; height: {H}px; padding: 26px 30px; background: #1c1a15;
          border: 3px solid #3a352c; border-radius: 14px; display: flex; flex-direction: column; justify-content: space-between; }}
        .bcard.next {{ border-color: #f2c14e; }}
        .bcard.done {{ border-color: #3a352c; }}
        .bcard-top {{ display: flex; justify-content: space-between; align-items: center;
          font-family: "IBM Plex Mono", monospace; font-size: 24px; letter-spacing: 0.06em; color: #a59d8d; }}
        .bcard-id {{ color: #f2c14e; font-weight: 600; }}
        .badge {{ display: inline-flex; align-items: center; gap: 10px; }}
        .glyph {{ display: inline-block; width: 18px; height: 18px; border: 2px solid #eee8dc; }}
        .g-checked {{ background: #eee8dc; }}
        .g-company {{ background: linear-gradient(90deg, #eee8dc 50%, transparent 50%); }}
        .g-reported {{ background: transparent; }}
        .g-provider {{ border-style: dashed; border-color: #a59d8d; }}
        .g-older {{ border-color: #a59d8d; }}
        .bcard-title {{ font-size: {title_px}px; font-weight: 500; line-height: 1.12; letter-spacing: -0.01em; }}
        .bslot {{ position: absolute; width: {W}px; display: flex; gap: 14px; align-items: baseline;
          font-family: "IBM Plex Mono", monospace; font-size: 22px; letter-spacing: 0.06em; color: #a59d8d; }}
        .slot-text {{ color: #f2c14e; text-transform: none; letter-spacing: 0.02em; }}
        .slot-blank {{ flex: 1; height: 2px; border-bottom: 2px dashed #6b6455; transform: translateY(-6px); }}
      </style>

      <div id="root" data-composition-id="{sid}" data-width="1920" data-height="1080">
        <div id="{p}meta-l" class="mono"><b>{show}</b>{' · ' + meta_l if meta_l else ''}</div>
        <div id="{p}meta-r" class="mono"><b>Test {n}</b> of {N}</div>
        <div id="{p}zoom-outer" data-layout-allow-overflow="true">
          <div id="{p}zoom-inner">
{chr(10).join(cards)}
          </div>
        </div>
      </div>

      <script>
        (function () {{
          var tl = gsap.timeline({{ paused: true }});
          {(chr(10) + '          ').join(js)}
          window.__timelines["{sid}"] = tl;
        }})();
      </script>
    </template>
  </body>
</html>
'''
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(page)
    print(out)


if __name__ == '__main__':
    main(sys.argv[1:])
