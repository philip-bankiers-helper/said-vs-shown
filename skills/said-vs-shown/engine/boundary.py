#!/usr/bin/env python3
"""boundary.py — generate an evidence-boundary scene (PROVES | DOESN'T PROVE + a real receipt) from a JSON spec.

usage: boundary.py <spec.json> <out.html> [--project <video_dir>]

The story-closing beat (frame.md "Evidence boundary"). Paths inside the spec (receipt.img, receipt.json) are
relative to the episode's video/ project dir: --project, or inferred when the spec sits in <video>/specs/.
Never relative to the current directory. The receipt alt text's capture date is edit/episode.json "captured".

Spec keys:
  sid, prefix, kicker{num,topic,glyph(checked|company|reported|provider|older),text}, boundary_at,
  proves{header?, header_at, lines:[{html,at}], subs:[{text,at}], underline_at?, underline_dur?},
  nots{header?, header_at, rows:[{kind:item|tag|chip|heading, text, at}]},
  receipt{img, json, css_x0, css_y0, f, chrome_left, chrome_right, rise_at, highlights:[{line,at,dur}]},
  dim_at? (columns recede when the receipt rises), cols_top? (default 172)
Rect math: receipts are 1440x900 CSS captures at 2x; the window shows CSS x from css_x0, y from css_y0, scaled by f.
Run engine/scope_css.py afterwards (assemble.py does it for every composition).
"""
import html as H
import json
import os
import sys

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


def die(msg):
    sys.exit(f'boundary.py: {msg}')


def parse_args(argv):
    if any(a in ('-h', '--help') for a in argv):
        print(__doc__.strip())
        sys.exit(0)
    args, project = [], None
    it = iter(argv)
    for a in it:
        if a == '--project':
            project = next(it, None) or die('--project needs a path')
        else:
            args.append(a)
    if len(args) != 2:
        die('usage: boundary.py <spec.json> <out.html> [--project <video_dir>]')
    spec_path, out = args
    if project is None:
        spec_dir = os.path.dirname(os.path.abspath(spec_path))
        if os.path.basename(spec_dir) == 'specs':
            project = os.path.dirname(spec_dir)
        else:
            die(f'cannot infer the project dir from {spec_path} (not in <video>/specs/); pass --project <video_dir>')
    return spec_path, out, os.path.abspath(project)


def main(argv):
    spec_path, out, proj = parse_args(argv)
    with open(spec_path, encoding='utf-8') as fh:
        spec = json.load(fh)
    captured = ''
    ep_json = os.path.join(proj, '..', 'edit', 'episode.json')
    if os.path.isfile(ep_json):
        with open(ep_json, encoding='utf-8') as fh:
            captured = json.load(fh).get('captured', '')
    else:
        print(f'boundary.py: warning: no {os.path.normpath(ep_json)}; alt text has no capture date', file=sys.stderr)

    S, P = spec['sid'], spec['prefix']
    K, PR, NO, R = spec['kicker'], spec['proves'], spec['nots'], spec['receipt']
    rec_json = R['json'] if os.path.isabs(R['json']) else os.path.join(proj, R['json'])
    if not os.path.isfile(rec_json):
        die(f'receipt json not found: {rec_json} (receipt.json is relative to {proj})')
    with open(rec_json, encoding='utf-8') as fh:
        rec = json.load(fh)
    if not os.path.isfile(os.path.join(proj, R['img'])):
        print(f'boundary.py: warning: receipt image {R["img"]} is not in {proj} yet (capture it before rendering)', file=sys.stderr)
    for h in R['highlights']:
        if not 0 <= h['line'] < len(rec.get('lines', [])):
            die(f'highlight line {h["line"]} is out of range: {rec_json} has {len(rec.get("lines", []))} quote lines')
    f, x0, y0 = R['f'], R['css_x0'], R['css_y0']
    top = spec.get('cols_top', 172)

    def hl_rect(l):
        return dict(left=round((l['x'] - 4 - x0) * f, 2), top=round((l['y'] - 3 - y0) * f, 2),
                    width=round((l['w'] + 8) * f, 2), height=round((l['h'] + 6) * f, 2))

    lines_html = []
    for i, l in enumerate(PR['lines']):
        lh = l['html']
        if PR.get('underline_at') is not None and '<b>' in lh:
            lh = lh.replace('</b>', f'<svg id="{P}ul" class="ul" viewBox="0 0 100 10" preserveAspectRatio="none"><path d="M 1 6 L 99 6" /></svg></b>', 1)
        lines_html.append(f'<span class="stmt-line" id="{P}stmt-{i}">{lh}</span>')
    subs_html = ''.join(f'<div class="sub mono" id="{P}sub-{i}">{H.escape(s["text"])}</div>' for i, s in enumerate(PR.get('subs', [])))
    rows_html = []
    for i, r in enumerate(NO['rows']):
        if r['kind'] == 'item':
            rows_html.append(f'<div class="item" id="{P}row-{i}"><span class="dash">—</span><span>{H.escape(r["text"])}</span></div>')
        elif r['kind'] == 'tag':
            rows_html.append(f'<div class="tag mono" id="{P}row-{i}">{H.escape(r["text"])}</div>')
        elif r['kind'] == 'heading':
            rows_html.append(f'<div class="heading mono" id="{P}row-{i}">{H.escape(r["text"])}</div>')
        else:
            rows_html.append(f'<div class="chip mono" id="{P}row-{i}">{H.escape(r["text"])}</div>')
    hls = ''
    for i, h in enumerate(R['highlights']):
        r = hl_rect(rec['lines'][h['line']])
        hls += f'<div class="hlr" id="{P}hl-{i}" style="left:{r["left"]}px; top:{r["top"]}px; width:{r["width"]}px; height:{r["height"]}px"></div>'

    js = [f'tl.fromTo("#{P}boundary", {{ clipPath: "inset(0 0 100% 0)" }}, {{ clipPath: "inset(0 0 0% 0)", duration: 0.9, ease: "power2.inOut" }}, {spec["boundary_at"]});',
          f'tl.set("#{P}head-proves", {{ opacity: 1, y: 30 }}, {PR["header_at"]}); tl.to("#{P}head-proves", {{ y: 0, duration: 0.15, ease: "power4.out" }}, {PR["header_at"]});']
    for i, l in enumerate(PR['lines']):
        js.append(f'tl.set("#{P}stmt-{i}", {{ opacity: 1, y: 70 }}, {l["at"]}); tl.to("#{P}stmt-{i}", {{ y: 0, duration: 0.2, ease: "power4.out" }}, {l["at"]});')
    if PR.get('underline_at') is not None:
        js.append(f'tl.fromTo("#{P}ul", {{ clipPath: "inset(0 100% 0 0)" }}, {{ clipPath: "inset(0 0% 0 0)", duration: {PR.get("underline_dur", 1.0)}, ease: "power1.inOut" }}, {PR["underline_at"]});')
    for i, s in enumerate(PR.get('subs', [])):
        js.append(f'tl.set("#{P}sub-{i}", {{ opacity: 1, y: 26 }}, {s["at"]}); tl.to("#{P}sub-{i}", {{ y: 0, duration: 0.15, ease: "power4.out" }}, {s["at"]});')
    js.append(f'tl.set("#{P}head-not", {{ opacity: 1, y: 30 }}, {NO["header_at"]}); tl.to("#{P}head-not", {{ y: 0, duration: 0.15, ease: "power4.out" }}, {NO["header_at"]});')
    for i, r in enumerate(NO['rows']):
        js.append(f'tl.set("#{P}row-{i}", {{ opacity: 1, y: 40 }}, {r["at"]}); tl.to("#{P}row-{i}", {{ y: 0, duration: 0.17, ease: "power4.out" }}, {r["at"]});')
    if spec.get('dim_at') is not None:
        js.append(f'tl.to("#{P}cols", {{ opacity: 0.42, duration: 0.6, ease: "power2.out" }}, {spec["dim_at"]});')
    js.append(f'tl.fromTo("#{P}receipt", {{ opacity: 0, y: 90 }}, {{ opacity: 1, y: 0, duration: 0.7, ease: "power3.out" }}, {R["rise_at"]});')
    for i, h in enumerate(R['highlights']):
        js.append(f'tl.fromTo("#{P}hl-{i}", {{ scaleX: 0 }}, {{ scaleX: 1, duration: {h["dur"]}, ease: "power1.inOut" }}, {h["at"]});')

    alt = R['chrome_left'] + (f', captured {captured}' if captured else '')
    FONT_FACES = font_faces((300, 700), (400, 600))
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
        #{P}kicker {{ position: absolute; left: 104px; top: 44px; padding: 10px 16px; border-radius: 8px;
          display: flex; gap: 22px; align-items: baseline; font-size: 22px; color: #a59d8d; white-space: nowrap; }}
        #{P}kicker .num {{ color: #f2c14e; font-weight: 600; font-size: 26px; }}
        #{P}kicker .topic {{ color: #eee8dc; font-weight: 600; font-size: 26px; }}
        .badge {{ display: inline-flex; align-items: center; gap: 10px; }}
        .glyph {{ display: inline-block; width: 15px; height: 15px; border: 2px solid #eee8dc; }}
        .g-checked {{ background: #eee8dc; }}
        .g-company {{ background: linear-gradient(90deg, #eee8dc 50%, transparent 50%); }}
        .g-reported {{ background: transparent; }}
        .g-provider {{ border-style: dashed; border-color: #a59d8d; }}
        .g-older {{ border-color: #a59d8d; }}
        #{P}cols {{ position: absolute; left: 0; top: 0; width: 1920px; height: 620px; }}
        .col {{ position: absolute; top: {top}px; width: 780px; }}
        #{P}col-proves {{ left: 120px; }}
        #{P}col-not {{ left: 1020px; }}
        .head {{ font-size: 24px; font-weight: 600; opacity: 0; }}
        #{P}head-proves {{ color: #f2c14e; }}
        .stmt {{ margin-top: 28px; font-size: 56px; font-weight: 300; line-height: 1.14; letter-spacing: -0.02em; }}
        .stmt-line {{ display: block; white-space: nowrap; opacity: 0; }}
        .stmt-line b {{ font-weight: 700; position: relative; display: inline-block; }}
        .ul {{ position: absolute; left: 0; bottom: -10px; width: 100%; height: 10px; overflow: visible; }}
        .ul path {{ fill: none; stroke: #f2c14e; stroke-width: 4; stroke-linecap: round; }}
        .sub {{ margin-top: 18px; font-size: 22px; color: #a59d8d; opacity: 0; }}
        .rows {{ margin-top: 28px; display: flex; flex-direction: column; gap: 16px; }}
        .item {{ display: flex; gap: 20px; font-size: 40px; font-weight: 300; line-height: 1.16; opacity: 0; }}
        .item .dash {{ font-family: "IBM Plex Mono", monospace; color: #a59d8d; font-size: 32px; line-height: 1.4; }}
        .tag {{ font-size: 22px; color: #f2c14e; opacity: 0; padding-left: 52px; }}
        .heading {{ margin-top: 10px; font-size: 22px; color: #f2c14e; font-weight: 600; opacity: 0; }}
        .chip {{ align-self: flex-start; font-size: 20px; color: #eee8dc; border: 2px solid #3a352c; border-radius: 6px; padding: 6px 12px; opacity: 0; }}
        #{P}boundary {{ position: absolute; left: 954px; top: {top - 12}px; width: 12px; height: 420px; overflow: visible; }}
        #{P}boundary path {{ fill: none; stroke: #f2c14e; stroke-width: 3; stroke-dasharray: 14 10; }}
        #{P}receipt {{ position: absolute; left: 260px; top: 636px; width: 1400px; height: 234px; border-radius: 12px; overflow: hidden;
          border: 2px solid #3a352c; background: #ffffff; box-shadow: 0 24px 70px rgba(0, 0, 0, 0.55); opacity: 0; }}
        #{P}chrome {{ height: 40px; background: #1c1a15; border-bottom: 2px solid #3a352c; display: flex; align-items: center;
          justify-content: space-between; padding: 0 18px; font-family: "IBM Plex Mono", monospace; font-size: 18px; color: #a59d8d; letter-spacing: 0.04em; }}
        #{P}chrome .who {{ color: #f2c14e; text-transform: uppercase; letter-spacing: 0.08em; }}
        #{P}window {{ position: relative; width: 1400px; height: 192px; overflow: hidden; }}
        #{P}window img {{ position: absolute; left: {round(-x0 * f, 2)}px; top: {round(-y0 * f, 2)}px; width: {round(1440 * f, 2)}px; height: {round(900 * f, 2)}px; display: block; }}
        .hlr {{ position: absolute; background: rgba(242, 193, 78, 0.42); border-radius: 3px; mix-blend-mode: multiply; transform-origin: left center; }}
      </style>

      <div id="root" data-composition-id="{S}" data-width="1920" data-height="1080">
        <div id="{P}kicker" class="mono"><span class="num">{K['num']}</span><span class="topic">{H.escape(K['topic'])}</span>
          <span class="badge"><span class="glyph g-{K['glyph']}"></span>{H.escape(K['text'])}</span></div>
        <div id="{P}cols">
          <svg id="{P}boundary" viewBox="0 0 12 420" preserveAspectRatio="none"><path d="M 6 0 L 6 420" /></svg>
          <div class="col" id="{P}col-proves">
            <div class="head mono" id="{P}head-proves">{H.escape(PR.get('header', 'Proves'))}</div>
            <div class="stmt">{''.join(lines_html)}</div>
            {subs_html}
          </div>
          <div class="col" id="{P}col-not">
            <div class="head mono" id="{P}head-not">{H.escape(NO.get('header', "Doesn't prove"))}</div>
            <div class="rows">{''.join(rows_html)}</div>
          </div>
        </div>
        <div id="{P}receipt">
          <div id="{P}chrome"><span>{H.escape(R['chrome_left'])}</span><span class="who">{H.escape(R['chrome_right'])}</span></div>
          <div id="{P}window" data-layout-allow-overflow="true">
            <img src="{H.escape(R['img'])}" alt="{H.escape(alt)}" />
            {hls}
          </div>
        </div>
      </div>

      <script>
        (function () {{
          var tl = gsap.timeline({{ paused: true }});
          {(chr(10) + '          ').join(js)}
          window.__timelines["{S}"] = tl;
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
