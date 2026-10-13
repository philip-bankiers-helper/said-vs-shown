#!/usr/bin/env python3
"""captions.py — phrase-level caption cues from aligned script words.

usage: captions.py <words.json> <out_dir> --cuts 9.40,19.95 [--display script.json]
                   [--max-chars N] [--max-cps N] [--strict]

Rules: one line per cue, <= max_chars (config.json), clause-first (break on punctuation), long
clauses split into balanced parts with a penalty for stranding a function word at a cue end, very
short chunks merged forward, never a cue across a scene cut, 0.83 s minimum, reading speed
<= max_cps: a cue over it first borrows what its neighbours can spare (the pause after it, up to
0.3 s before its first word, up to 0.1 s of the next cue's lead), then it is reported (--strict
exits 1). Text always comes from the script words; the script's
"display" map then turns spoken forms into written ones on word boundaries only
("five hundred and twenty-two" -> "522"); a phrase split across two cues stays spoken.
Writes cues.json, captions.vtt, captions.srt and prints a QA summary as JSON.
"""
import argparse
import itertools
import json
import os
import re
import sys

ENGINE = os.path.dirname(os.path.abspath(__file__))
STOP = {'a', 'an', 'the', 'at', 'of', 'to', 'and', 'or', 'in', 'on', 'by', 'for', 'with', 'is', 'that', 'its', 'it'}


def load_config():
    with open(os.path.join(ENGINE, 'config.json'), encoding='utf-8') as f:
        return json.load(f)


def text(ws):
    return ' '.join(w['text'] for w in ws)


def make_scene_of(cuts):
    def scene_of(t):
        return sum(1 for c in cuts if t >= c)
    return scene_of


def clauses_of(ws, scene_of):
    out, cur = [], []
    for w in ws:
        if cur and scene_of(w['start']) != scene_of(cur[0]['start']):
            out.append(cur)
            cur = []
        cur.append(w)
        if w['text'][-1] in '.,:;?!':
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def balanced(ws, n):
    """Split ws into n contiguous parts minimising the longest part, penalising a stop word at a part end."""
    best, L = None, len(ws)
    for cut in itertools.combinations(range(1, L), n - 1):
        parts = [ws[i:j] for i, j in zip((0,) + cut, cut + (L,))]
        m = max(len(text(p)) for p in parts)
        # don't strand a function word at a line end ("the top model at / launch")
        m += 8 * sum(1 for p in parts[:-1] if p[-1]['text'].lower().strip(',.') in STOP)
        if best is None or m < best[0]:
            best = (m, parts)
    return best[1]


def chunk(words, cuts, max_chars):
    scene_of = make_scene_of(cuts)
    chunks = []
    for c in clauses_of(words, scene_of):
        n = 1
        while len(text(c)) > n * max_chars - (n - 1) or (n > 1 and max(len(text(p)) for p in balanced(c, n)) > max_chars):
            n += 1
            if n >= len(c):
                n = len(c)
                break
        chunks.extend(balanced(c, n) if n > 1 else [c])
    # merge very short chunks (<14 chars) into the next when same scene, fits, and not a sentence end
    merged = []
    for ch in chunks:
        if merged and len(text(merged[-1])) < 14 and merged[-1][-1]['text'][-1] not in '.?!' \
                and scene_of(merged[-1][0]['start']) == scene_of(ch[0]['start']) \
                and len(text(merged[-1] + ch)) <= max_chars:
            merged[-1] = merged[-1] + ch
        else:
            merged.append(ch)
    return [{'text': text(ch), 'start': ch[0]['start'], 'end': ch[-1]['end'], 'scene': scene_of(ch[0]['start'])}
            for ch in merged]


def display_fn(dmap):
    """A function text -> text that writes out the spoken forms of dmap: whole words/phrases only, one pass (no
    cascading), longest key first. One rule for the captions, deliver.py's transcript.md and any other text."""
    keys = sorted((k for k in (dmap or {}) if k), key=len, reverse=True)
    if not keys:
        return lambda s: s
    pat = re.compile(r'(?<!\w)(' + '|'.join(re.escape(k) for k in keys) + r')(?!\w)')
    return lambda s: pat.sub(lambda m: dmap[m.group(1)], s)


def apply_display(cues, dmap):
    """Spoken -> written forms in each cue's text (display_fn)."""
    fn = display_fn(dmap)
    for c in cues:
        c['text'] = fn(c['text'])
    return cues


MIN_CUE, BORROW_LEAD, BORROW_LAG = 0.83, 0.3, 0.1


def time_cues(cues, cuts, max_cps=None):
    """Lead 0.05 s, tail +0.25 s, clamp to the next cue and to the next scene cut, minimum 0.83 s.

    The next cut is chosen from the cue's ORIGINAL start, and the lead never moves a start before the cut that
    opens the cue's own scene: a cue starting just after a cut would otherwise lead across it, take that same
    cut as its end and flash for a few hundredths of a second.
    With max_cps, a cue faster than that borrows time its neighbours can spare (relieve)."""
    firsts = [c['start'] for c in cues]
    starts = []
    for c in cues:
        own = max((x for x in cuts if x <= c['start']), default=0.0)
        starts.append(round(max(0.0, own, c['start'] - 0.05), 3))
    for i, c in enumerate(cues):
        cut = next((x for x in cuts if x > c['start']), 1e9)
        c['start'] = starts[i]
        nxt = starts[i + 1] if i + 1 < len(cues) else c['end'] + 1.0
        c['end'] = round(min(c['end'] + 0.25, nxt, cut), 3)
        if c['end'] - c['start'] < MIN_CUE:
            c['end'] = round(min(c['start'] + MIN_CUE, nxt, cut), 3)
    if max_cps:
        relieve(cues, firsts, cuts, max_cps)
    for c in cues:
        c['cps'] = round(len(c['text']) / max(0.01, c['end'] - c['start']), 1)
    return cues


def relieve(cues, firsts, cuts, max_cps):
    """Give a cue faster than max_cps the time it needs (len / max_cps) from what its neighbours can spare, in this
    order: the pause after it, an earlier start (at most BORROW_LEAD before its first word, never before the cut that
    opens its scene), then a later start for the next cue (at most BORROW_LAG after that cue's first word, never
    across a cut). A neighbour never drops below its own need, so ASR timing jitter of a tenth or two of a second
    cannot fail the reading-speed gate on its own, while genuinely fast speech still does."""
    def need(c):
        return max(MIN_CUE, len(c['text']) / float(max_cps) + 0.002)
    for i, c in enumerate(cues):
        short = need(c) - (c['end'] - c['start'])
        if len(c['text']) / max(0.01, c['end'] - c['start']) <= max_cps or short <= 0:
            continue
        own = max((x for x in cuts if x <= firsts[i]), default=0.0)
        cut = next((x for x in cuts if x > firsts[i]), 1e9)
        nxt = cues[i + 1] if i + 1 < len(cues) else None
        prv = cues[i - 1] if i > 0 else None
        # 1. the pause before the next cue (or the next cut)
        room = min(nxt['start'] if nxt else c['end'] + short, cut) - c['end']
        take = min(short, max(0.0, room))
        c['end'] = round(c['end'] + take, 3)
        short -= take
        # 2. start earlier
        if short > 0:
            lo = max(own, firsts[i] - BORROW_LEAD, (prv['start'] + need(prv)) if prv else 0.0)
            take = min(short, max(0.0, c['start'] - lo))
            c['start'] = round(c['start'] - take, 3)
            if prv and prv['end'] > c['start']:
                prv['end'] = c['start']
            short -= take
        # 3. the next cue starts a little later
        if short > 0 and nxt and nxt['start'] < cut:
            hi = min(cut, firsts[i + 1] + BORROW_LAG, nxt['end'] - need(nxt))
            take = min(short, max(0.0, hi - c['end']))
            c['end'] = round(c['end'] + take, 3)
            nxt['start'] = max(nxt['start'], c['end'])


def ts(t, sep):
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return '%02d:%02d:%02d%s%03d' % (h, m, s, sep, ms)


def build(words, cuts, max_chars, dmap=None, max_cps=None):
    """Cues from aligned words. max_cps defaults to config.json's; a cue over it borrows neighbours' slack (relieve)."""
    cues = chunk(words, cuts, max_chars)
    apply_display(cues, dmap or {})
    return time_cues(cues, cuts, load_config()['max_cps'] if max_cps is None else max_cps)


def write(cues, out):
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'cues.json'), 'w', encoding='utf-8') as f:
        json.dump(cues, f, indent=1, ensure_ascii=False)
    with open(os.path.join(out, 'captions.vtt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('WEBVTT\n\n')
        for c in cues:
            f.write('%s --> %s\n%s\n\n' % (ts(c['start'], '.'), ts(c['end'], '.'), c['text']))
    with open(os.path.join(out, 'captions.srt'), 'w', encoding='utf-8', newline='\n') as f:
        for i, c in enumerate(cues, 1):
            f.write('%d\n%s --> %s\n%s\n\n' % (i, ts(c['start'], ','), ts(c['end'], ','), c['text']))


def main(argv=None):
    cfg = load_config()
    ap = argparse.ArgumentParser(description='phrase-level caption cues from aligned script words')
    ap.add_argument('words')
    ap.add_argument('out')
    ap.add_argument('--cuts', default='')
    ap.add_argument('--max-chars', type=int, default=cfg['max_chars'])
    ap.add_argument('--max-cps', type=float, default=cfg['max_cps'])
    ap.add_argument('--display', default='', help='script.json whose "display" map turns spoken forms into caption forms')
    ap.add_argument('--strict', action='store_true', help='exit 1 when a cue breaks max-chars or max-cps')
    a = ap.parse_args(argv)
    with open(a.words, encoding='utf-8') as f:
        words = json.load(f)
    if not words:
        raise SystemExit('captions.py: no words in %s' % a.words)
    cuts = sorted(float(c) for c in a.cuts.split(',') if c.strip())
    dmap = {}
    if a.display:
        with open(a.display, encoding='utf-8') as f:
            dmap = json.load(f).get('display', {}) or {}
    cues = build(words, cuts, a.max_chars, dmap, a.max_cps)
    write(cues, a.out)
    bad = [c for c in cues if c['cps'] > a.max_cps or len(c['text']) > a.max_chars]
    print(json.dumps({'cues': len(cues), 'max_chars': max(len(c['text']) for c in cues),
                      'max_cps': max(c['cps'] for c in cues), 'limits': {'chars': a.max_chars, 'cps': a.max_cps},
                      'violations': bad}, ensure_ascii=False))
    return 1 if (a.strict and bad) else 0


if __name__ == '__main__':
    sys.exit(main())
