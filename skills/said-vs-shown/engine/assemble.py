#!/usr/bin/env python3
"""assemble.py — write an episode's video/index.html from audio/timeline.json + audio/cues.json + scenes.json.

usage: assemble.py <project_dir>      (the episode's video/ dir; the episode root is accepted too)

scenes.json: {"hold": 0.12, "scenes": [{"id": "squeeze", "src": "compositions/01-squeeze.html"}, ...],
              "sfx": [{"file": "assets/sfx/click-soft.wav", "at": 8.0, "vol": 0.35}, ...]}
Steps: scope every composition's CSS (scope_css.py), check that scenes.json, audio/script.json and
audio/timeline.json agree (one scene per cut + 1, same ids in the same order), check every SFX file, then write
index.html. Scene i spans [cut[i-1], cut[i]) (scene 0 starts at 0); the last scene runs to total + hold.
Captions are one persistent layer; each cue is switched on and off on the main timeline. The page title is
show · edition · date from ../edit/episode.json. GSAP comes from assets/vendor/gsap.min.js when present,
else from the CDN (offline renders then fail; a warning says so). Never hand-edit the generated index.html.
"""
import glob
import html
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scope_css  # noqa: E402

GSAP_DEFAULT = '3.14.2'


def die(msg):
    sys.exit(f'assemble.py: {msg}')


def load(path, what):
    if not os.path.isfile(path):
        die(f'missing {what}: {path}')
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def config():
    p = os.path.join(HERE, 'config.json')
    if os.path.isfile(p):
        with open(p, encoding='utf-8') as fh:
            return json.load(fh)
    return {}


def media_dur(f):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        die(f'ffprobe could not read the duration of {f}: {r.stderr.strip() or "no output"}')


def main(argv):
    if len(argv) != 1:
        die('usage: assemble.py <project_dir>')
    proj = os.path.abspath(argv[0])
    if not os.path.isfile(os.path.join(proj, 'scenes.json')) and os.path.isfile(os.path.join(proj, 'video', 'scenes.json')):
        proj = os.path.join(proj, 'video')
    cfg = load(os.path.join(proj, 'scenes.json'), 'scenes.json')
    tl = load(os.path.join(proj, 'audio', 'timeline.json'), 'audio/timeline.json (run align.py)')
    cues = load(os.path.join(proj, 'audio', 'cues.json'), 'audio/cues.json (run captions.py)')
    script = load(os.path.join(proj, 'audio', 'script.json'), 'audio/script.json')
    ep_path = os.path.join(proj, '..', 'edit', 'episode.json')
    E = load(ep_path, 'edit/episode.json') if os.path.isfile(ep_path) else {}
    scenes = cfg.get('scenes') or die('scenes.json has no scenes')

    # 1. scope every composition (the assembled page shares one CSS namespace)
    srcs = sorted(set(glob.glob(os.path.join(proj, 'compositions', '*.html'))) |
                  {os.path.join(proj, s['src']) for s in scenes})
    scoped = 0
    for src in srcs:
        if not os.path.isfile(src):
            die(f'scene source missing: {os.path.relpath(src, proj)}')
        sid, changed, _ = scope_css.scope_file(src)
        scoped += changed
    for s in scenes:
        with open(os.path.join(proj, s['src']), encoding='utf-8') as fh:
            m = re.search(r'data-composition-id="([^"]+)"', fh.read())
        if not m or m.group(1) != s['id']:
            die(f'{s["src"]}: data-composition-id is {m.group(1) if m else "missing"!r}, scenes.json says {s["id"]!r}')

    # 2. scenes, script and timeline must agree
    cuts = tl.get('cuts', [])
    if len(scenes) != len(cuts) + 1:
        die(f'scenes.json has {len(scenes)} scenes but audio/timeline.json has {len(cuts)} cuts '
            f'(need {len(scenes) - 1}); re-run align.py after changing scenes or script lines')
    line_scenes = []
    for ln in script.get('lines', []):
        if not line_scenes or line_scenes[-1] != ln.get('scene'):
            line_scenes.append(ln.get('scene'))
    ids = [s['id'] for s in scenes]
    if ids != line_scenes:
        diff = next((i for i, (a, b) in enumerate(zip(ids, line_scenes)) if a != b), min(len(ids), len(line_scenes)))
        die('scenes.json ids and audio/script.json line scenes disagree at position '
            f'{diff + 1}:\n  scenes.json: {ids}\n  script.json: {line_scenes}')
    if any(b <= a for a, b in zip([0.0] + cuts, cuts)):
        die(f'audio/timeline.json cuts are not strictly increasing: {cuts}')

    # 3. every SFX file must exist before probing
    sfx_cfg = cfg.get('sfx', [])
    missing = [x['file'] for x in sfx_cfg if not os.path.isfile(os.path.join(proj, x['file']))]
    if missing:
        die('SFX file(s) missing under ' + proj + ':\n  ' + '\n  '.join(sorted(set(missing))) +
            '\n  (copy them into assets/sfx/ or remove the cues from scenes.json)')
    if not os.path.isfile(os.path.join(proj, 'audio', 'narration.wav')):
        die('missing audio/narration.wav (run voice.py)')

    total = round(tl['total'] + cfg.get('hold', 0.12), 2)
    bounds = [0.0] + cuts + [total]
    if total <= bounds[-2]:
        die(f'last cut {bounds[-2]} is past the end of narration + hold ({total})')

    # GSAP: local vendor copy if present (offline-safe), else CDN
    if os.path.isfile(os.path.join(proj, 'assets', 'vendor', 'gsap.min.js')):
        gsap_src = 'assets/vendor/gsap.min.js'
    else:
        gsap_src = f'https://cdn.jsdelivr.net/npm/gsap@{config().get("gsap", GSAP_DEFAULT)}/dist/gsap.min.js'
        print(f'assemble.py: warning: GSAP loads from {gsap_src}; offline renders need assets/vendor/gsap.min.js',
              file=sys.stderr)

    title = ' · '.join(str(x) for x in (E.get('show') or 'Said vs. Shown', E.get('edition'), E.get('date')) if x)

    hosts = []
    for i, sc in enumerate(scenes):
        st, en = bounds[i], bounds[i + 1]
        hosts.append(f'''      <div id="{sc['id']}" class="clip" data-composition-id="{sc['id']}" data-composition-src="{sc['src']}"
        data-start="{st:.2f}" data-duration="{en - st:.2f}" data-track-index="1" data-width="1920" data-height="1080"></div>''')
    caps = [f'''        <span class="cap-text" id="cap-{i:02d}">{html.escape(c['text'], quote=False)}</span>''' for i, c in enumerate(cues)]
    cap_js = '\n'.join(f'      tl.set("#cap-{i:02d}", {{ opacity: 1 }}, {c["start"]:.2f}); tl.set("#cap-{i:02d}", {{ opacity: 0 }}, {c["end"]:.2f});'
                       for i, c in enumerate(cues))
    sfx = [f'''      <audio id="sfx-{i:02d}" src="{x['file']}" data-start="{x['at']:.2f}" data-duration="{media_dur(os.path.join(proj, x['file'])):.2f}" data-track-index="{11 + i % 2}" data-volume="{x.get('vol', 0.35)}"></audio>'''
           for i, x in enumerate(sfx_cfg)]

    page = f'''<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <title>{html.escape(title)}</title>
    <script src="{gsap_src}"></script>
    <style>
      @font-face {{ font-family: "Newsreader"; font-weight: 500; src: url("assets/fonts/newsreader-latin-500-normal.woff2") format("woff2"); }}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ margin: 0; width: 1920px; height: 1080px; overflow: hidden; background: #14130f; }}
      #root {{ position: relative; width: 100%; height: 100%; overflow: hidden; background: #14130f; color: #eee8dc; }}
      /* persistent background: ledger hairlines + one breathing amber glow (frame.md) */
      #bg {{ position: absolute; inset: 0; }}
      #bg-rules {{ position: absolute; inset: 0;
        background-image: repeating-linear-gradient(180deg, transparent 0 71px, #26231d 71px 73px); opacity: 0.9; }}
      #bg-glow {{ position: absolute; left: -380px; top: -520px; width: 1500px; height: 1500px; border-radius: 50%;
        background: radial-gradient(circle, rgba(242, 193, 78, 0.16) 0%, rgba(242, 193, 78, 0.06) 38%, transparent 62%);
        transform-origin: 50% 50%; will-change: transform; }}
      /* captions: one persistent layer; cues switched on the main timeline (phrase-level, from audio/cues.json) */
      #captions {{ position: absolute; left: 0; right: 0; bottom: 54px; height: 72px; pointer-events: none; }}
      .cap-text {{ position: absolute; left: 50%; bottom: 0; opacity: 0; transform: translateX(-50%); display: inline-block; max-width: 1500px; padding: 10px 28px 12px; border-radius: 8px;
        background: rgba(20, 19, 15, 0.88); font-family: "Newsreader", serif; font-weight: 500; font-size: 40px;
        line-height: 1.2; letter-spacing: -0.005em; color: #eee8dc; text-align: center; white-space: nowrap; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total:.2f}" data-width="1920" data-height="1080">
      <div id="bg"><div id="bg-rules"></div><div id="bg-glow"></div></div>
{chr(10).join(hosts)}
      <div id="captions">
{chr(10).join(caps)}
      </div>
      <audio id="narration" src="audio/narration.wav" data-start="0" data-duration="{tl['total']:.2f}" data-track-index="10" data-volume="1"></audio>
{chr(10).join(sfx)}
    </div>
    <script>
      const tl = gsap.timeline({{ paused: true }});
      // sine-wave-loop: the amber glow breathes for the whole piece (finite repeats under the root duration)
      const CYCLE = 6;
      tl.fromTo("#bg-glow", {{ scale: 1, x: 0 }}, {{ scale: 1.08, x: 40, duration: CYCLE / 2, ease: "sine.inOut",
        yoyo: true, repeat: Math.max(0, Math.floor({total:.2f} / (CYCLE / 2)) - 1) }}, 0);
{cap_js}
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
'''
    with open(os.path.join(proj, 'index.html'), 'w', encoding='utf-8') as fh:
        fh.write(page)
    print(json.dumps({'total': total, 'scenes': [(s['id'], bounds[i], bounds[i + 1]) for i, s in enumerate(scenes)],
                      'captions': len(caps), 'sfx': len(sfx), 'scoped': scoped, 'gsap': gsap_src}))


if __name__ == '__main__':
    main(sys.argv[1:])
