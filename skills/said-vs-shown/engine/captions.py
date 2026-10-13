#!/usr/bin/env python3
"""captions.py — phrase-level caption cues from aligned script words.

usage: captions.py <words.json> <out_dir> --cuts 9.40,19.95 [--display script.json]
                   [--max-chars N] [--max-cps N] [--strict]

Rules: one line per cue, <= max_chars (config.json), clause-first (break on punctuation), long
clauses split into balanced parts with a penalty for stranding a function word at a cue end, very
short chunks merged forward, never a cue across a scene cut, 0.83 s minimum where the next cue
allows it and never under 0.5 s (a shorter cue merges with a neighbour that fits). Reading speed:
chunking aims at max_cps - 2 (19 chars/s for 21) so ASR jitter has room: a chunk spoken faster
than that, which relief could not bring to it, becomes up to 4 shorter cues. The gate stays at
max_cps: a cue over it borrows what its neighbours can spare (the pause after it, up to 0.3 s
before its first word, up to 0.1 s of the next cue's lead; a neighbour with nothing to spare
passes the request on to its own neighbour), as a last resort up to 0.5 s before its first word,
then it is reported (--strict exits 1). Text always comes from the script words; the script's
"display" map then turns spoken forms into written ones on word boundaries only
("five hundred and twenty-two" -> "522"); a phrase split across two cues stays spoken.
Writes cues.json, captions.vtt, captions.srt and prints a QA summary as JSON.
"""
import argparse
import itertools
import json
import math
import os
import re
import sys

ENGINE = os.path.dirname(os.path.abspath(__file__))
STOP = {'a', 'an', 'the', 'at', 'of', 'to', 'and', 'or', 'in', 'on', 'by', 'for', 'with', 'is', 'that', 'its', 'it'}
MIN_CUE, BORROW_LEAD, BORROW_LAG = 0.83, 0.3, 0.1
LAST_LEAD = 0.5          # relief's last resort: a cue still too fast may start this far (s) before its first word
LEAD, TAIL = 0.05, 0.25  # a cue shows from LEAD before its first word to TAIL after its last (time_cues)
CPS_MARGIN = 2.0         # chunking aims at max_cps - CPS_MARGIN (19 for 21); the gate stays at max_cps
MAX_SPLIT = 4            # a chunk spoken faster than that may become up to 4 cues (fast_split)
MIN_PART = 0.5           # no cue shorter than this (s): fast_split never makes one, build merges one away
RELIEF_DEPTH = 4         # relief passes a request on through at most this many neighbours each way
MAX_CANDIDATES = 5000    # fast_split tries at most this many splits for one part count


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


def predicted(parts, after=None, cut=None):
    """Each part's display time as time_cues gives it before relief: from LEAD before its first word to the next
    part's lead, the last part to TAIL after its last word (at least MIN_CUE), never past the next chunk's lead
    (`after`: that chunk's first word) or the next scene cut."""
    out = []
    for k, p in enumerate(parts):
        s = p[0]['start'] - LEAD
        if k + 1 < len(parts):
            e = parts[k + 1][0]['start'] - LEAD
        else:
            e = max(p[-1]['end'] + TAIL, s + MIN_CUE)
            if after is not None:
                e = min(e, after - LEAD)
            if cut is not None:
                e = min(e, cut)
        out.append(e - s)
    return out


def spoken_cps(ws):
    """Characters over spoken time (first word's start to last word's end)."""
    return len(text(ws)) / max(0.01, ws[-1]['end'] - ws[0]['start'])


def stranded(p):
    return p[-1]['text'].lower().strip(',.') in STOP


def achievable(parts, lo, hi, after=None, cut=None):
    """The lowest worst reading speed (chars/s) relief can give these consecutive parts: the first starts no earlier
    than lo, each later one between BORROW_LEAD before and BORROW_LAG after its first word, the last ends by hi, and
    no part shrinks below what it shows before relief or MIN_CUE, whichever is less (relief never takes a neighbour
    below MIN_CUE). A stranded function word counts 8 extra characters. Binary search over the rate, greedy earliest
    boundaries."""
    sizes = [len(text(p)) + (8 if k + 1 < len(parts) and stranded(p) else 0) for k, p in enumerate(parts)]
    floors = [min(MIN_CUE, d) for d in predicted(parts, after, cut)]

    def fits(rate):
        b = lo
        for k, n in enumerate(sizes):
            b += max(n / rate, floors[k])
            if k + 1 < len(parts):
                f = parts[k + 1][0]['start']
                if b > f + BORROW_LAG:
                    return False
                b = max(b, f - BORROW_LEAD)
        return b <= hi
    r0, r1 = 1.0, 400.0
    if not fits(r1):
        return r1
    for _ in range(40):
        mid = (r0 + r1) / 2
        r0, r1 = (r0, mid) if fits(mid) else (mid, r1)
    return r1


def fast_split(c, parts0, max_chars, target_cps, lo, hi, after=None, cut=None):
    """Cues for words spoken faster than target_cps (a clause, or a chunk merged from short clauses). parts0, the
    usual chunking, stays when relief can bring it to target_cps (achievable, between lo and hi). Otherwise the words
    become more, shorter cues, so relief has more boundaries to move, with the boundaries placed by reading speed: of
    the splits into len(parts0) to MAX_SPLIT contiguous parts that fit max_chars and each show at least MIN_PART
    before relief, the fewest parts that reach target_cps, else the lowest worst rate (fewer parts on a tie)."""
    if achievable(parts0, lo, hi, after, cut) <= target_cps:
        return parts0
    best = None
    for n in range(len(parts0), max(len(parts0), min(MAX_SPLIT, len(c))) + 1):
        if math.comb(len(c) - 1, n - 1) > MAX_CANDIDATES:  # a very long unpunctuated clause: keep the usual split
            continue
        for cut_at in itertools.combinations(range(1, len(c)), n - 1):
            parts = [c[i:j] for i, j in zip((0,) + cut_at, cut_at + (len(c),))]
            if any(len(text(p)) > max_chars for p in parts) or (n > 1 and min(predicted(parts, after, cut)) < MIN_PART):
                continue
            worst = achievable(parts, lo, hi, after, cut)
            key = (worst > target_cps, n if worst <= target_cps else 0, round(worst, 2), n)
            if best is None or key < best[0]:
                best = (key, parts)
    return best[1] if best else parts0


def chunk(words, cuts, max_chars, target_cps=None):
    """Word lists, one per cue: clause-first; a clause longer than max_chars is split into balanced parts; very short
    chunks merge forward; then words spoken faster than target_cps that relief could not bring to it (a clause's
    parts, or one merged chunk) become more, shorter cues with boundaries placed by reading speed (fast_split)."""
    scene_of = make_scene_of(cuts)
    chunks = []
    for ci, c in enumerate(clauses_of(words, scene_of)):
        n = 1
        while len(text(c)) > n * max_chars - (n - 1) or (n > 1 and max(len(text(p)) for p in balanced(c, n)) > max_chars):
            n += 1
            if n >= len(c):
                n = len(c)
                break
        chunks.extend((p, ci) for p in (balanced(c, n) if n > 1 else [c]))
    # merge very short chunks (<14 chars) into the next when same scene, fits, and not a sentence end
    merged = []
    for ch, ci in chunks:
        if merged and len(text(merged[-1][0])) < 14 and merged[-1][0][-1]['text'][-1] not in '.?!' \
                and scene_of(merged[-1][0][0]['start']) == scene_of(ch[0]['start']) \
                and len(text(merged[-1][0] + ch)) <= max_chars:
            merged[-1] = (merged[-1][0] + ch, ci if merged[-1][1] == ci else None)  # None: spans two clauses
        else:
            merged.append((ch, ci))
    if not target_cps:
        return [ch for ch, _ in merged]
    groups = []  # consecutive chunks of one clause, or one merged chunk
    for ch, ci in merged:
        if groups and ci is not None and groups[-1][1] == ci:
            groups[-1][0].append(ch)
        else:
            groups.append(([ch], ci))
    out = []
    for k, (parts0, _) in enumerate(groups):
        c = [w for p in parts0 for w in p]
        if len(c) < 2 or spoken_cps(c) <= target_cps:
            out.extend(parts0)
            continue
        f0 = c[0]['start']
        own = max((x for x in cuts if x <= f0), default=0.0)
        cut = next((x for x in cuts if x > f0), None)
        lo = max(own, f0 - BORROW_LEAD)
        if out and scene_of(out[-1][0]['start']) == scene_of(f0):  # the previous cue keeps what it needs
            lo = max(lo, out[-1][0]['start'] - LEAD + max(MIN_CUE, len(text(out[-1])) / target_cps))
        after = groups[k + 1][0][0][0]['start'] if k + 1 < len(groups) else None
        hi = min(after + BORROW_LAG if after is not None else c[-1]['end'] + TAIL + 1.0, cut if cut is not None else 1e9)
        out.extend(fast_split(c, parts0, max_chars, target_cps, lo, hi, after, cut))
    return out


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
        starts.append(round(max(0.0, own, c['start'] - LEAD), 3))
    for i, c in enumerate(cues):
        cut = next((x for x in cuts if x > c['start']), 1e9)
        c['start'] = starts[i]
        nxt = starts[i + 1] if i + 1 < len(cues) else c['end'] + 1.0
        c['end'] = round(min(c['end'] + TAIL, nxt, cut), 3)
        if c['end'] - c['start'] < MIN_CUE:
            c['end'] = round(min(c['start'] + MIN_CUE, nxt, cut), 3)
    if max_cps:
        relieve(cues, firsts, cuts, max_cps)
    for c in cues:
        c['cps'] = round(len(c['text']) / max(0.01, c['end'] - c['start']), 1)
    return cues


def relieve(cues, firsts, cuts, max_cps, depth=RELIEF_DEPTH):
    """Give a cue faster than max_cps the time it needs (len / max_cps) from what its neighbours can spare, in this
    order: the pause after it, an earlier start (at most BORROW_LEAD before its first word, never before the cut that
    opens its scene), then a later start for the next cue (at most BORROW_LAG after that cue's first word, never
    across a cut). A neighbour never drops below its own need; when it has nothing to spare it can still move, within
    the same limits, by passing the request on to its own neighbour (up to `depth` cues away), so the slack of a slow
    cue reaches a run of fast ones. ASR timing jitter of a tenth or two of a second therefore cannot fail the
    reading-speed gate on its own, while genuinely fast speech still does."""
    n = len(cues)
    own = [max((x for x in cuts if x <= f), default=0.0) for f in firsts]
    cut = [next((x for x in cuts if x > f), 1e9) for f in firsts]

    def need(i):
        return max(MIN_CUE, len(cues[i]['text']) / float(max_cps) + 0.002)

    def spare(i):
        return max(0.0, cues[i]['end'] - cues[i]['start'] - need(i))

    def pull_back(i, x, d, lead):
        """Cue i ends up to x earlier: from its spare, then by starting earlier itself (at most `lead` before its
        first word). Returns what it gave."""
        c = cues[i]
        got = min(x, spare(i))
        c['end'] -= got
        want = min(x - got, max(0.0, c['start'] - max(own[i], firsts[i] - lead)))
        if want > 1e-9 and d > 0:
            pause = max(0.0, c['start'] - cues[i - 1]['end']) if i > 0 else want
            moved = min(want, pause)
            if want - moved > 1e-9 and i > 0:
                moved += pull_back(i - 1, want - moved, d - 1, lead)
            c['start'] -= moved
            c['end'] -= moved
            got += moved
        return got

    def push_forward(i, x, d):
        """Cue i starts up to x later: from its spare, then by ending later itself. Returns what it gave."""
        c = cues[i]
        x = min(x, max(0.0, min(firsts[i] + BORROW_LAG, cut[i]) - c['start']))
        got = min(x, spare(i))
        c['start'] += got
        want = min(x - got, max(0.0, cut[i] - c['end']))
        if want > 1e-9 and d > 0:
            pause = max(0.0, cues[i + 1]['start'] - c['end']) if i + 1 < n else want
            moved = min(want, pause)
            if want - moved > 1e-9 and i + 1 < n and cues[i + 1]['start'] < cut[i]:
                moved += push_forward(i + 1, want - moved, d - 1)
            c['start'] += moved
            c['end'] += moved
            got += moved
        return got

    def earlier(i, short, lead):
        """Cue i starts up to `short` earlier, at most `lead` before its first word: the pause before it, then the
        previous cue (and, through it, the ones before). Returns how much it moved."""
        c = cues[i]
        want = min(short, max(0.0, c['start'] - max(own[i], firsts[i] - lead)))
        moved = min(want, max(0.0, c['start'] - cues[i - 1]['end'])) if i > 0 else want
        if want - moved > 1e-9 and i > 0:
            moved += pull_back(i - 1, want - moved, depth, lead)
        c['start'] -= moved
        return moved

    for i, c in enumerate(cues):
        short = need(i) - (c['end'] - c['start'])
        if len(c['text']) / max(0.01, c['end'] - c['start']) <= max_cps or short <= 0:
            continue
        # 1. the pause before the next cue (or the next cut)
        room = min(cues[i + 1]['start'] if i + 1 < n else c['end'] + short, cut[i]) - c['end']
        take = min(short, max(0.0, room))
        c['end'] += take
        short -= take
        # 2. start earlier, up to BORROW_LEAD before the first word
        if short > 1e-9:
            short -= earlier(i, short, BORROW_LEAD)
        # 3. the next cue starts a little later (and, through it, the ones after)
        if short > 1e-9 and i + 1 < n and cues[i + 1]['start'] < cut[i]:
            got = push_forward(i + 1, min(short, max(0.0, cut[i] - c['end'])), depth)
            c['end'] += got
            short -= got
        # 4. last resort, still too fast to read: it (and the cues before it that it moves) may start up to LAST_LEAD
        #    before the first word
        short = len(c['text']) / float(max_cps) + 0.002 - (c['end'] - c['start'])
        if short > 1e-9:
            earlier(i, short, LAST_LEAD)
    for c in cues:
        c['start'], c['end'] = round(c['start'], 3), round(c['end'], 3)


def ts(t, sep):
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return '%02d:%02d:%02d%s%03d' % (h, m, s, sep, ms)


def build(words, cuts, max_chars, dmap=None, max_cps=None, target_cps=None):
    """Cues from aligned words. max_cps (the gate) defaults to config.json's; a cue over it borrows neighbours' slack
    (relieve); 0 turns relief off. Chunking aims at target_cps, by default max_cps (or config's) - CPS_MARGIN; 0 turns
    the reading-speed split off. A cue shorter than MIN_PART merges with a neighbour of its scene when the two fit
    max_chars, and the cues are timed again."""
    cfg_cps = load_config()['max_cps']
    gate = cfg_cps if max_cps is None else max_cps
    if target_cps is None:
        target_cps = (gate or cfg_cps) - CPS_MARGIN
    scene_of = make_scene_of(cuts)
    fn = display_fn(dmap)
    chunks = chunk(words, cuts, max_chars, target_cps)
    while True:
        cues = [{'text': fn(text(ch)), 'start': ch[0]['start'], 'end': ch[-1]['end'], 'scene': scene_of(ch[0]['start'])}
                for ch in chunks]
        time_cues(cues, cuts, gate)
        for k, c in enumerate(cues):
            if c['end'] - c['start'] >= MIN_PART - 1e-9:
                continue
            opts = [j for j in (k + 1, k - 1) if 0 <= j < len(chunks) and cues[j]['scene'] == c['scene']
                    and len(fn(text(chunks[min(j, k)] + chunks[max(j, k)]))) <= max_chars]
            if opts:
                j = min(opts, key=lambda j: len(text(chunks[j])))
                a, b = min(j, k), max(j, k)
                chunks[a:b + 1] = [chunks[a] + chunks[b]]
                break
        else:
            return cues


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
