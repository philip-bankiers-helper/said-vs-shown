#!/usr/bin/env python3
"""demo.py — the zero-friction first run of Said vs. Shown: one sentence, shown on the page it came from.

usage: python3 demo.py <url> "<verbatim sentence on that page>" [--out DIR] [--voice af_heart] [--speed S]
                       [--install-line TEXT]

Makes a ~20–30 s 1920x1080 receipt clip, <out>/demo.mp4 (default out: ./said-vs-shown-demo):
  1. capture  engine/receipt.mjs captures the page at 2x and locates the sentence (its line rects)
  2. voice    Kokoro (npx -y hyperframes@<config.json version> tts): "Here's the sentence, on the page it came
              from." + the sentence, read verbatim + where and when it was captured. Word timings are
              approximated from each line's audio (speech bounds from ffmpeg silencedetect, then spread by
              characters); no ASR.
  3. compose  a one-scene HyperFrames project from templates/scenes/receipt.html: wordmark kicker, domain +
              capture-date chip, push-in, the highlighter synced to the read sentence, burned-in captions,
              then a 2 s end card with the install line
  4. render   npx -y hyperframes@<config.json version> render -q draft -w 2 (--quality looks: sharper page
              text)
Prints the wall time of each step. Exit 1 if the sentence is not on the page (with the closest sentence that
is), 2 if a dependency is missing (run <skill>/engine/setup.sh).
Kokoro: $HYPERFRAMES_PYTHON if set, else $SVS_HOME/kokoro (SVS_HOME defaults to "home" in engine/config.json).
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import difflib
import html
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
ENGINE = os.path.join(SKILL, 'engine')
TEMPLATES = os.path.join(SKILL, 'templates')
SCENE_ID, PREFIX = 'demo-receipt', 'dr-'
LEAD, GAP_QUOTE, GAP_OUTRO, HOLD, END_CARD = 0.5, 0.5, 0.9, 0.7, 2.0
FALLBACK_INSTALL = 'npx skills add philip-bankiers-helper/said-vs-shown'  # works for Claude Code and the other Agent Skills agents
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
          'November', 'December']


def fail(msg, code=1):
    print(f'demo: {msg}', file=sys.stderr)
    sys.exit(code)


def load_config():
    path = os.path.join(ENGINE, 'config.json')
    try:
        with open(path, encoding='utf-8') as fh:
            cfg = json.load(fh)
    except (OSError, ValueError) as e:
        fail(f'cannot read {path} ({e}); reinstall the skill', 2)
    for key in ('hyperframes', 'gsap'):
        if not cfg.get(key):
            fail(f'{path} has no "{key}" version; reinstall the skill', 2)
    home = os.path.abspath(os.path.expanduser(os.environ.get('SVS_HOME') or cfg.get('home') or '~/.said-vs-shown'))
    return {'hf': str(cfg['hyperframes']), 'gsap': str(cfg['gsap']), 'home': home, 'voice': cfg.get('voice') or 'af_heart',
            'speed': float(cfg.get('speed') or 1.0)}


def install_line(override):
    if override:
        return override
    try:
        with open(os.path.join(SKILL, '..', '..', '.claude-plugin', 'plugin.json'), encoding='utf-8') as fh:
            repo = json.load(fh).get('repository', '')
        m = re.search(r'github\.com/([^/]+/[^/.]+)', repo)
        if m:
            return f'npx skills add {m.group(1)}'
    except (OSError, ValueError):
        pass
    return FALLBACK_INSTALL


def kokoro_env(cfg):
    env = dict(os.environ)
    if not env.get('HYPERFRAMES_PYTHON'):
        for rel in (('bin', 'python'), ('Scripts', 'python.exe')):
            p = os.path.join(cfg['home'], 'kokoro', *rel)
            if os.path.exists(p):
                env['HYPERFRAMES_PYTHON'] = p
                break
    return env


class Clock:
    def __init__(self):
        self.rows, self.t0 = [], time.time()

    def step(self, name):
        self.name, self.ts = name, time.time()
        print(f'[{name}] …', flush=True)

    def done(self, note=''):
        secs = time.time() - self.ts
        self.rows.append((self.name, secs, note))
        print(f'[{self.name}] {secs:5.1f} s  {note}', flush=True)

    def report(self):
        print('\nwall time')
        for n, s, note in self.rows:
            print(f'  {n:<8} {s:6.1f} s  {note}')
        print(f'  {"total":<8} {time.time() - self.t0:6.1f} s')


# ── 1. capture ───────────────────────────────────────────────────────────────────────────────────

def norm_text(s):
    s = s.replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"').replace('–', '-').replace('—', '-')
    return re.sub(r'\s+', ' ', s).strip().lower()


def suggest(url, quote):
    try:
        r = subprocess.run(['node', os.path.join(HERE, 'suggest.mjs'), '--url', url], capture_output=True, text=True, timeout=120)
        sentences = json.loads(r.stdout.strip().splitlines()[-1]).get('sentences', []) if r.stdout.strip() else []
    except (subprocess.SubprocessError, ValueError, IndexError):
        sentences = []
    q = norm_text(quote)
    scored = sorted(((difflib.SequenceMatcher(None, q, norm_text(s)).ratio(), s) for s in sentences), reverse=True)
    return [s for _, s in scored[:3]]


def capture(url, quote, png):
    os.makedirs(os.path.dirname(png), exist_ok=True)
    r = subprocess.run(['node', os.path.join(ENGINE, 'receipt.mjs'), '--url', url, '--quote', quote, '--out', png],
                       capture_output=True, text=True)
    if r.returncode == 2:
        fail('the capture tool could not start:\n' + (r.stderr or r.stdout).strip() +
             f'\nRun: {os.path.join(ENGINE, "setup.sh")}', 2)
    side = png[:-4] + '.json'
    data = {}
    if os.path.isfile(side):
        with open(side, encoding='utf-8') as fh:
            data = json.load(fh)
    if r.returncode != 0 or not data.get('found'):
        why = data.get('error') or (f'HTTP {data["status"]}' if data.get('status') and data['status'] >= 400 else '')
        print(f'demo: the sentence is not on {url}' + (f' ({why})' if why else '') + '.', file=sys.stderr)
        print('      It must appear verbatim in the visible page text (quotes, dashes and spaces are normalised).',
              file=sys.stderr)
        tips = suggest(url, quote)
        if tips:
            print('      Closest sentences that ARE on the page:', file=sys.stderr)
            for s in tips:
                print(f'        "{s}"', file=sys.stderr)
            print(f'      Try: python3 {shlex.quote(sys.argv[0])} {shlex.quote(url)} {shlex.quote(tips[0])}', file=sys.stderr)
        elif data.get('sample'):
            print(f'      The page starts: "{data["sample"][:200]}"', file=sys.stderr)
        sys.exit(1)
    return data


# ── 2. voice ─────────────────────────────────────────────────────────────────────────────────────

def tts(cfg, text, out, voice, speed, env):
    cmd = ['npx', '-y', f'hyperframes@{cfg["hf"]}', 'tts', text, '-v', voice, '-s', str(speed), '-o', out, '--json']
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode != 0 or not os.path.isfile(out):
        fail(f'Kokoro TTS failed (run: sh {os.path.join(ENGINE, "setup.sh")}, or set HYPERFRAMES_PYTHON to a python '
             'with kokoro-onnx):\n'
             + (r.stderr or r.stdout).strip()[-800:], 2)
    return out


def media_duration(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def speech_bounds(path, dur):
    """First and last non-silent instants of a TTS line (ffmpeg silencedetect, −40 dB, 60 ms)."""
    r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', path, '-af', 'silencedetect=n=-40dB:d=0.06', '-f',
                        'null', '-'], capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r'silence_start: ([\d.]+)', r.stderr)]
    ends = [float(x) for x in re.findall(r'silence_end: ([\d.]+)', r.stderr)]
    a, b = 0.0, dur
    if starts and starts[0] <= 0.01 and ends:
        a = ends[0]
    if starts and starts[-1] > a and (len(ends) < len(starts) or ends[-1] >= dur - 0.02):
        b = starts[-1]
    return a, max(a + 0.2, b)


def spread_words(text, start, a, b):
    """Approximate word timings: spread the line's speech span over its words by character weight (+pauses)."""
    words = text.split()
    weights = []
    for w in words:
        k = len(re.sub(r'\W', '', w)) + 1.5
        if w.endswith((',', ';', ':')):
            k += 3
        elif w.endswith(('.', '?', '!')):
            k += 4
        weights.append(k)
    total, t, out = sum(weights), start + a, []
    span = b - a
    for w, k in zip(words, weights):
        d = span * k / total
        out.append({'t': w, 's': round(t, 3), 'e': round(t + d, 3)})
        t += d
    return out


def voice(cfg, proj, lines, voice_id, speed):
    adir = os.path.join(proj, 'audio')
    os.makedirs(adir, exist_ok=True)
    env = kokoro_env(cfg)
    outs = [os.path.join(adir, f'L{i + 1}.wav') for i in range(len(lines))]
    with cf.ThreadPoolExecutor(max_workers=len(lines)) as ex:
        list(ex.map(lambda p: tts(cfg, p[0]['spoken'], p[1], voice_id, speed, env), zip(lines, outs)))
    t, timeline = LEAD, []
    for i, (L, wav) in enumerate(zip(lines, outs)):
        d = media_duration(wav)
        a, b = speech_bounds(wav, d)
        timeline.append(dict(L, wav=wav, start=round(t, 3), dur=round(d, 3),
                             words=spread_words(L['spoken'], t, a, b)))
        t += d + L.get('gap_after', 0.6)
    narr_end = timeline[-1]['start'] + timeline[-1]['dur']
    inputs, filt = [], []
    for i, L in enumerate(timeline):
        inputs += ['-i', L['wav']]
        ms = int(round(L['start'] * 1000))
        filt.append(f'[{i}:a]aresample=48000,adelay={ms}|{ms}[a{i}]')
    filt.append(''.join(f'[a{i}]' for i in range(len(timeline))) +
                f'amix=inputs={len(timeline)}:normalize=0,apad=whole_dur={narr_end + 0.3:.3f},'
                f'atrim=0:{narr_end + 0.3:.3f},loudnorm=I=-19:TP=-1.5:LRA=11[out]')  # mono −19 → about −16 LUFS once the render plays it on both channels
    narration = os.path.join(adir, 'narration.wav')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', *inputs, '-filter_complex', ';'.join(filt), '-map', '[out]',
                    '-ar', '48000', '-ac', '1', narration], check=True)
    return timeline, media_duration(narration)


# ── 3. compose ───────────────────────────────────────────────────────────────────────────────────

def display_url(u, limit=64):
    u = re.sub(r'^[a-z]+://', '', u.strip())
    u = re.sub(r'^www\.', '', u).rstrip('/')
    return u if len(u) <= limit else u[:limit - 1] + '…'


def time_at_fraction(words, f):
    """Time at which fraction f (0–1, by characters) of a line's text has been said."""
    text = ' '.join(w['t'] for w in words)
    target, pos = f * len(text), 0
    for w in words:
        n = len(w['t']) + 1
        if pos + n >= target:
            k = max(0.0, min(1.0, (target - pos) / n))
            return w['s'] + k * (w['e'] - w['s'])
        pos += n
    return words[-1]['e']


def highlight_beats(lines_px, words):
    widths = [max(1.0, l['w']) for l in lines_px]
    total, acc, out = sum(widths), 0.0, []
    for w in widths:
        t0 = time_at_fraction(words, acc / total)
        acc += w
        t1 = time_at_fraction(words, acc / total)
        out.append({'at': round(t0, 2), 'dur': round(max(0.25, t1 - t0), 2)})
    return out


STOP = {'a', 'an', 'the', 'at', 'of', 'to', 'and', 'or', 'in', 'on', 'by', 'for', 'with', 'is', 'that', 'its', 'it'}


def balanced(ws, n):
    """Split words into n contiguous parts, minimising the longest (chars); avoid ending a part on a stop word."""
    import itertools
    if n <= 1 or len(ws) < 2:
        return [ws]
    best = None
    for cut in itertools.combinations(range(1, len(ws)), min(n, len(ws)) - 1):
        parts = [ws[i:j] for i, j in zip((0,) + cut, cut + (len(ws),))]
        score = max(len(' '.join(w['t'] for w in p)) for p in parts)
        score += 8 * sum(1 for p in parts[:-1] if p[-1]['t'].lower().strip(',.') in STOP)
        if best is None or score < best[0]:
            best = (score, parts)
    return best[1]


def caption_cues(timeline, max_chars=42):
    cues = []
    for L in timeline:
        words = [dict(w) for w in L['words']]
        # display forms ("Said versus Shown" → "Said vs. Shown") become one token, so a cue never splits them
        for spoken, shown in L.get('display', {}).items():
            toks = spoken.split()
            i = 0
            while i <= len(words) - len(toks):
                seg = words[i:i + len(toks)]
                if [w['t'].rstrip('.,;:?!') for w in seg[:-1]] + [seg[-1]['t'][:len(toks[-1])]] == toks:
                    tail = seg[-1]['t'][len(toks[-1]):]
                    words[i:i + len(toks)] = [{'t': shown + tail, 's': seg[0]['s'], 'e': seg[-1]['e']}]
                i += 1
        # clauses first, then balanced splits of any clause longer than max_chars
        clauses, cur = [], []
        for i, w in enumerate(words):
            cur.append(w)
            nxt = words[i + 1]['t'] if i + 1 < len(words) else ''
            date_comma = w['t'].endswith(',') and w['t'][:-1].isdigit() and nxt[:1].isdigit()  # "October 13, 2026"
            if w['t'][-1] in '.,;:?!' and not date_comma:
                clauses.append(cur)
                cur = []
        if cur:
            clauses.append(cur)
        chunks = []
        for c in clauses:
            n = 1
            while n < len(c):
                parts = balanced(c, n)
                if max(len(' '.join(w['t'] for w in p)) for p in parts) <= max_chars:
                    break
                n += 1
            chunks += balanced(c, n)
        merged = []
        for ch in chunks:
            if merged and len(' '.join(w['t'] for w in merged[-1] + ch)) <= max_chars and merged[-1][-1]['t'][-1] not in '.?!':
                merged[-1] = merged[-1] + ch
            else:
                merged.append(ch)
        for ch in merged:
            text = ' '.join(w['t'] for w in ch)
            cues.append({'text': text, 'start': ch[0]['s'] - 0.05, 'end': ch[-1]['e'] + 0.2})
    for i in range(len(cues) - 1):
        # back-to-back cues touch (no one-frame blink between them); a real pause keeps its gap
        nxt = cues[i + 1]['start']
        if cues[i]['end'] > nxt - 0.1:
            cues[i]['end'] = nxt
    return cues


def fill_template(cfg_obj):
    with open(os.path.join(TEMPLATES, 'scenes', 'receipt.html'), encoding='utf-8') as fh:
        src = fh.read()
    m = re.search(r'^([ \t]*)const CFG = \{.*?\};(?=\s*// ==== /CFG ====)', src, flags=re.S | re.M)
    if not m:
        fail('templates/scenes/receipt.html has no CFG block', 2)
    pad = m.group(1)
    body = json.dumps(cfg_obj, indent=2, ensure_ascii=False).replace('</', '<\\/').replace('\n', '\n' + pad)
    src = src[:m.start()] + pad + 'const CFG = ' + body + ';' + src[m.end():]
    return src.replace('__SCENE_ID__', SCENE_ID).replace('__P__', PREFIX)


FONT_FACES = '''      @font-face { font-family: "Newsreader"; font-weight: 300; src: url("assets/fonts/newsreader-latin-300-normal.woff2") format("woff2"); }
      @font-face { font-family: "Newsreader"; font-weight: 500; src: url("assets/fonts/newsreader-latin-500-normal.woff2") format("woff2"); }
      @font-face { font-family: "IBM Plex Mono"; font-weight: 400; src: url("assets/fonts/IBMPlexMono-Regular-Latin1.woff2") format("woff2"); unicode-range: U+0020-007E, U+00A0-00FF, U+0131, U+0152-0153, U+02C6, U+02DA, U+02DC, U+2013-2014, U+2018-201A, U+201C-201E, U+2020-2022, U+2026, U+2030, U+2039-203A, U+2044, U+20AC, U+2122, U+2212, U+FB01-FB02; }
      @font-face { font-family: "IBM Plex Mono"; font-weight: 600; src: url("assets/fonts/IBMPlexMono-SemiBold-Latin1.woff2") format("woff2"); unicode-range: U+0020-007E, U+00A0-00FF, U+0131, U+0152-0153, U+02C6, U+02DA, U+02DC, U+2013-2014, U+2018-201A, U+201C-201E, U+2020-2022, U+2026, U+2030, U+2039-203A, U+2044, U+20AC, U+2122, U+2212, U+FB01-FB02; }'''


def index_html(total, end_at, narr_dur, cues, sfx, gsap):
    e = html.escape
    caps = '\n'.join(f'        <span class="cap-text" id="cap-{i:02d}">{e(c["text"])}</span>' for i, c in enumerate(cues))
    cap_js = '\n'.join(f'      tl.set("#cap-{i:02d}", {{ opacity: 1 }}, {c["start"]:.2f}); tl.set("#cap-{i:02d}", {{ opacity: 0 }}, {c["end"]:.2f});'
                       for i, c in enumerate(cues))
    sfx_tags = '\n'.join(f'      <audio id="sfx-{i:02d}" src="{x["file"]}" data-start="{x["at"]:.2f}" data-duration="{x["dur"]:.2f}" '
                         f'data-track-index="{11 + i}" data-volume="{x["vol"]}"></audio>' for i, x in enumerate(sfx))
    return f'''<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <title>Said vs. Shown — demo</title>
    <script src="https://cdn.jsdelivr.net/npm/gsap@{gsap}/dist/gsap.min.js"></script>
    <style>
{FONT_FACES}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ margin: 0; width: 1920px; height: 1080px; overflow: hidden; background: #14130f; }}
      #root {{ position: relative; width: 100%; height: 100%; overflow: hidden; background: #14130f; color: #eee8dc; }}
      /* persistent background: ledger hairlines + one breathing accent glow (frame.md) */
      #bg {{ position: absolute; inset: 0; }}
      #bg-rules {{ position: absolute; inset: 0;
        background-image: repeating-linear-gradient(180deg, transparent 0 71px, #26231d 71px 73px); opacity: 0.9; }}
      #bg-glow {{ position: absolute; left: -380px; top: -520px; width: 1500px; height: 1500px; border-radius: 50%;
        background: radial-gradient(circle, rgba(242, 193, 78, 0.16) 0%, rgba(242, 193, 78, 0.06) 38%, transparent 62%);
        transform-origin: 50% 50%; will-change: transform; }}
      /* captions: one persistent layer; phrase cues switched on the main timeline */
      #captions {{ position: absolute; left: 0; right: 0; bottom: 54px; height: 72px; pointer-events: none; }}
      .cap-text {{ position: absolute; left: 50%; bottom: 0; opacity: 0; transform: translateX(-50%); display: inline-block; max-width: 1500px; padding: 10px 28px 12px; border-radius: 8px;
        background: rgba(20, 19, 15, 0.88); font-family: "Newsreader", serif; font-weight: 500; font-size: 40px;
        line-height: 1.2; letter-spacing: -0.005em; color: #eee8dc; text-align: center; white-space: nowrap; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total:.2f}" data-width="1920" data-height="1080">
      <div id="bg"><div id="bg-rules"></div><div id="bg-glow"></div></div>
      <div id="{SCENE_ID}" class="clip" data-composition-id="{SCENE_ID}" data-composition-src="compositions/01-{SCENE_ID}.html"
        data-start="0" data-duration="{end_at:.2f}" data-track-index="1" data-width="1920" data-height="1080"></div>
      <div id="end-card" class="clip" data-composition-id="end-card" data-composition-src="compositions/02-end-card.html"
        data-start="{end_at:.2f}" data-duration="{total - end_at:.2f}" data-track-index="2" data-width="1920" data-height="1080"></div>
      <div id="captions">
{caps}
      </div>
      <audio id="narration" src="audio/narration.wav" data-start="0" data-duration="{narr_dur:.2f}" data-track-index="10" data-volume="1"></audio>
{sfx_tags}
    </div>
    <script>
      const tl = gsap.timeline({{ paused: true }});
      // sine-wave-loop: the accent glow breathes for the whole piece (finite repeats under the root duration)
      const CYCLE = 6;
      tl.fromTo("#bg-glow", {{ scale: 1, x: 0 }}, {{ scale: 1.08, x: 40, duration: CYCLE / 2, ease: "sine.inOut",
        yoyo: true, repeat: Math.max(0, Math.floor({total:.2f} / (CYCLE / 2)) - 1) }}, 0);
{cap_js}
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
'''


def end_card_html(install, note):
    """The 2 s end card: wordmark · tagline, the evidence line, the install command (hard cut in, waterfall-entry)."""
    sid = 'end-card'
    sc = f'[data-composition-id="{sid}"]'
    return f'''<!DOCTYPE html>
<html>
  <head>
    <meta charset="UTF-8">
  </head>
  <body>
    <template>
      <style>
{FONT_FACES}
        {sc}#root {{ position: absolute; inset: 0; overflow: hidden; color: #eee8dc; }}
        {sc} #ec-line {{ position: absolute; left: 120px; top: 404px; display: flex; align-items: baseline; gap: 26px; white-space: nowrap; opacity: 0; }}
        {sc} #ec-wm {{ font-family: "IBM Plex Mono", monospace; font-weight: 600; font-size: 40px; letter-spacing: 0.16em; color: #f2c14e; }}
        {sc} #ec-dot {{ font-family: "IBM Plex Mono", monospace; font-size: 40px; color: #a59d8d; }}
        {sc} #ec-tag {{ font-family: "Newsreader", serif; font-weight: 300; font-size: 64px; letter-spacing: -0.02em; color: #eee8dc; }}
        {sc} #ec-rule {{ position: absolute; left: 120px; top: 506px; width: 1680px; height: 12px; overflow: visible; }}
        {sc} #ec-rule path {{ fill: none; stroke: #f2c14e; stroke-width: 3; stroke-dasharray: 14 10; }}
        {sc} #ec-install {{ position: absolute; left: 120px; top: 566px; display: flex; align-items: baseline; gap: 22px; white-space: nowrap; opacity: 0;
          padding: 14px 22px; border-radius: 8px; background: #1c1a15; border: 2px solid #3a352c;
          font-family: "IBM Plex Mono", monospace; font-size: 28px; color: #eee8dc; }}
        {sc} #ec-note {{ position: absolute; left: 120px; top: 666px; font-family: "IBM Plex Mono", monospace; font-size: 20px; letter-spacing: 0.08em; text-transform: uppercase; color: #a59d8d; opacity: 0; }}
        {sc} #ec-install b {{ font-weight: 400; font-size: 22px; letter-spacing: 0.08em; text-transform: uppercase; color: #a59d8d; }}
      </style>
      <div id="root" data-composition-id="{sid}" data-width="1920" data-height="1080">
        <div id="ec-line"><span id="ec-wm">SAID VS. SHOWN</span><span id="ec-dot">·</span><span id="ec-tag">every claim, shown on its source</span></div>
        <svg id="ec-rule" viewBox="0 0 1680 12" preserveAspectRatio="none"><path d="M 0 6 L 1680 6" /></svg>
        <div id="ec-install"><b>Install</b><span>{html.escape(install)}</span></div>
        <div id="ec-note">{html.escape(note)}</div>
      </div>
      <script>
        (function () {{
          const tl = gsap.timeline({{ paused: true }});
          tl.set("#ec-line", {{ opacity: 1, y: 40 }}, 0.05);
          tl.to("#ec-line", {{ y: 0, duration: 0.2, ease: "power4.out" }}, 0.05);
          tl.fromTo("#ec-rule", {{ clipPath: "inset(0 100% 0 0)" }}, {{ clipPath: "inset(0 0% 0 0)", duration: 0.7, ease: "power2.inOut" }}, 0.2);
          tl.set("#ec-install", {{ opacity: 1, y: 30 }}, 0.45);
          tl.to("#ec-install", {{ y: 0, duration: 0.18, ease: "power4.out" }}, 0.45);
          tl.set("#ec-note", {{ opacity: 1, y: 20 }}, 0.6);
          tl.to("#ec-note", {{ y: 0, duration: 0.15, ease: "power4.out" }}, 0.6);
          window.__timelines["{sid}"] = tl;
        }})();
      </script>
    </template>
  </body>
</html>
'''


def compose(proj, receipt, url, quote, timeline, narr_dur, install, gsap):
    # project skeleton, design spec, fonts, sound marks
    for f in ('hyperframes.json', 'package.json'):
        shutil.copy(os.path.join(TEMPLATES, 'project', f), os.path.join(proj, f))
    shutil.copy(os.path.join(TEMPLATES, 'frame.md'), os.path.join(proj, 'frame.md'))
    for sub in ('fonts', 'sfx'):
        dst = os.path.join(proj, 'assets', sub)
        os.makedirs(dst, exist_ok=True)
        for f in os.listdir(os.path.join(TEMPLATES, sub)):
            shutil.copy(os.path.join(TEMPLATES, sub, f), os.path.join(dst, f))
    os.makedirs(os.path.join(proj, 'compositions'), exist_ok=True)

    L1, L2, L3 = timeline
    final = receipt.get('finalUrl') or url
    domain = re.sub(r'^www\.', '', re.sub(r'^[a-z]+://', '', final).split('/')[0])
    cap = dt.datetime.fromisoformat(receipt['capturedAt'].replace('Z', '+00:00')).date()
    cap_short = f'{MONTHS[cap.month - 1][:3]} {cap.day}, {cap.year}'
    q0 = L2['start']
    cam_at = round(max(0.9, q0 - 1.25), 2)
    end_at = round(L3['start'] + L3['dur'] + HOLD, 2)
    total = round(end_at + END_CARD, 2)
    cfg = {
        'kicker': {'num': 'Said vs. Shown', 'topic': 'Demo', 'badge': '', 'meta': '', 'wordmark': True, 'sep': True},
        'source': {'label': domain, 'captured': f'captured {cap_short}'},
        'url': display_url(final),
        'receipt': {'img': 'assets/receipts/R01-demo.png', 'alt': f'{domain}, captured {cap.isoformat()}',
                    'viewport': {'width': receipt['viewport']['width'], 'height': receipt['viewport']['height']},
                    'lines': [{k: round(l[k], 1) for k in ('x', 'y', 'w', 'h')} for l in receipt['lines']]},
        'beats': {'kicker': 0.15, 'source': 0.3, 'frame': 0.4},
        'camera': {'at': cam_at, 'dur': 1.4, 'zoom': 0},
        'highlight': highlight_beats(receipt['lines'], L2['words']),
        'after': {'mode': 'pullback', 'at': round(L3['start'] + 0.1, 2), 'dur': 1.4},
        'illustration': {'tag': 'Illustration', 'tag_at': 0, 'nodes': [], 'check_at': None},
    }
    with open(os.path.join(proj, 'compositions', f'01-{SCENE_ID}.html'), 'w', encoding='utf-8') as fh:
        fh.write(fill_template(cfg))
    cues = caption_cues(timeline)
    sfx = [{'file': 'assets/sfx/whoosh-short.wav', 'at': cam_at + 0.1, 'dur': 0.5, 'vol': 0.25},
           {'file': 'assets/sfx/click-soft.wav', 'at': end_at + 0.05, 'dur': 0.12, 'vol': 0.3}]
    with open(os.path.join(proj, 'compositions', '02-end-card.html'), 'w', encoding='utf-8') as fh:
        fh.write(end_card_html(install, f'AI voice (Kokoro) · page captured {cap_short} · {domain}'))
    with open(os.path.join(proj, 'index.html'), 'w', encoding='utf-8') as fh:
        fh.write(index_html(total, end_at, narr_dur, cues, sfx, gsap))
    with open(os.path.join(proj, 'demo.json'), 'w', encoding='utf-8') as fh:
        json.dump({'url': url, 'quote': quote, 'domain': domain, 'captured': cap.isoformat(), 'total': total,
                   'end_card_at': end_at, 'camera': cfg['camera'], 'highlight': cfg['highlight'],
                   'lines': [{k: L[k] for k in ('spoken', 'start', 'dur')} for L in timeline], 'cues': cues},
                  fh, indent=1, ensure_ascii=False)
    return total, end_at, cfg


# ── main ─────────────────────────────────────────────────────────────────────────────────────────

def main(argv):
    ap = argparse.ArgumentParser(description='One sentence, shown on the page it came from: a 20–30 s receipt clip.')
    ap.add_argument('url')
    ap.add_argument('sentence', help='a sentence that appears verbatim on the page')
    ap.add_argument('--out', default='said-vs-shown-demo', help='output folder (default ./said-vs-shown-demo)')
    ap.add_argument('--voice', default=None, help='Kokoro voice id (default from engine/config.json, af_heart)')
    ap.add_argument('--speed', type=float, default=None, help='speech speed (default from engine/config.json)')
    ap.add_argument('--install-line', default=None, help='text of the end card install line')
    ap.add_argument('--quality', default='draft', choices=['draft', 'looks', 'delivery'],
                    help='render quality (default draft: fast, soft on fine page text; looks = sharper)')
    a = ap.parse_args(argv)
    for tool in ('node', 'npx', 'ffmpeg', 'ffprobe'):
        if not shutil.which(tool):
            fail(f'{tool} is not on PATH (run {os.path.join(ENGINE, "setup.sh")})', 2)
    cfg = load_config()
    out = os.path.abspath(a.out)
    proj = os.path.join(out, 'project')
    os.makedirs(proj, exist_ok=True)
    quote = re.sub(r'\s+', ' ', a.sentence).strip()
    clock = Clock()

    clock.step('capture')
    png = os.path.join(proj, 'assets', 'receipts', 'R01-demo.png')
    receipt = capture(a.url, quote, png)
    clock.done(f'{len(receipt["lines"])} line(s) located on {receipt.get("finalUrl") or a.url}')

    clock.step('voice')
    final = receipt.get('finalUrl') or a.url
    domain = re.sub(r'^www\.', '', re.sub(r'^[a-z]+://', '', final).split('/')[0])
    cap = dt.datetime.fromisoformat(receipt['capturedAt'].replace('Z', '+00:00')).date()
    spoken_domain = domain.replace('.', ' dot ')
    lines = [
        {'spoken': "Here's the sentence, on the page it came from.", 'gap_after': GAP_QUOTE},
        {'spoken': quote, 'gap_after': GAP_OUTRO},
        {'spoken': f'Captured from {spoken_domain}, on {MONTHS[cap.month - 1]} {cap.day}, {cap.year}. '
                   'Every claim in Said versus Shown gets a receipt like this.',
         'display': {spoken_domain: domain, 'Said versus Shown': 'Said vs. Shown'}},
    ]
    timeline, narr_dur = voice(cfg, proj, lines, a.voice or cfg['voice'], a.speed or cfg['speed'])
    clock.done(f'{narr_dur:.1f} s of narration, {a.voice or cfg["voice"]} @ {a.speed or cfg["speed"]}')

    clock.step('compose')
    total, end_at, scene = compose(proj, receipt, a.url, quote, timeline, narr_dur, install_line(a.install_line), cfg['gsap'])
    clock.done(f'{total:.1f} s timeline, end card at {end_at:.1f} s')

    clock.step('render')
    mp4 = os.path.join(out, 'demo.mp4')
    r = subprocess.run(['npx', '-y', f'hyperframes@{cfg["hf"]}', 'render', '-q', a.quality, '-w', '2', '-o', mp4, proj],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.isfile(mp4):
        fail('render failed:\n' + (r.stderr or r.stdout).strip()[-1500:], 2)
    clock.done(f'{media_duration(mp4):.1f} s video')

    clock.report()
    print(f'\n{mp4}')
    print(f'project: {proj}  (open it with: npx -y hyperframes@{cfg["hf"]} preview {proj})')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
