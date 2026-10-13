#!/usr/bin/env python3
"""align.py — put ASR timings on the SCRIPT's words (caption text always comes from the script).

usage: align.py <script.json> <transcript.json> <timeline.json> <out words.json>

Both sides are normalised to the same canonical tokens before matching, so spoken numbers and
digits meet in the middle: "five hundred and twenty-two" / "522", "ninety-three percent" / "93%",
"fifth" / "5th", "Nineteen" / "19". Script words that share one ASR word share its time span
(split by character length). Runs of unmatched script words are spread across the gap between
their matched neighbours, proportional to character length. Prints per-line WER as JSON.
"""
import difflib
import json
import re
import sys

UNITS = {w: i for i, w in enumerate(
    'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen '
    'fifteen sixteen seventeen eighteen nineteen'.split())}
TENS = {w: 10 * i for i, w in enumerate('twenty thirty forty fifty sixty seventy eighty ninety'.split(), 2)}
ORD_UNITS = {w: i for i, w in enumerate(
    'zeroth first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth '
    'thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth'.split())}
ORD_TENS = {w: 10 * i for i, w in enumerate(
    'twentieth thirtieth fortieth fiftieth sixtieth seventieth eightieth ninetieth'.split(), 2)}
SCALES = {'hundred': 100, 'thousand': 1000, 'million': 10 ** 6, 'billion': 10 ** 9}
ORD_SCALES = {'hundredth': 100, 'thousandth': 1000, 'millionth': 10 ** 6, 'billionth': 10 ** 9}
PLURAL_SCALES = {'hundreds': '100s', 'thousands': '1000s', 'millions': '1000000s'}
NUMWORDS = set(UNITS) | set(TENS) | set(ORD_UNITS) | set(ORD_TENS) | set(SCALES) | set(ORD_SCALES)
DIGITS = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(%|st|nd|rd|th|s)?")
EDGE = ".,;:!?\"()[]{}<>*_`…—–-"


def ordinal(n):
    if 10 <= n % 100 <= 20:
        return '%dth' % n
    return '%d%s' % (n, {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th'))


def pieces(word):
    """Split one written/ASR word into normalised pieces: ('w', text) | ('num', '93') | ('ord', 5)."""
    s = word.lower().replace('’', "'").replace('‘', "'")
    core = s.strip(EDGE + ' ')
    if not core:
        return []
    m = DIGITS.fullmatch(core)
    if m:
        whole, frac, suf = m.group(1).replace(',', ''), m.group(2), m.group(3)
        num = whole + ('.' + frac if frac else '')
        if suf == '%':
            return [('num', num), ('w', 'percent')]
        if suf in ('st', 'nd', 'rd', 'th') and not frac:
            return [('ord', int(whole))]
        if suf == 's':
            return [('w', num + 's')]
        return [('num', num)]
    if core in PLURAL_SCALES:
        return [('w', PLURAL_SCALES[core])]
    parts = [p for p in core.split('-') if p]
    if len(parts) > 1:  # "twenty-two", "side-by-side", "GPT-6": one piece per part, on both sides
        return [x for p in parts for x in pieces(p)]
    tok = re.sub(r"[^a-z0-9']", '', core)
    return [('w', tok)] if tok else []


def _parse_number(stream, k):
    """Longest spoken number starting at stream[k]. Returns (token, end) or (None, k)."""
    total = cur = 0
    last = None
    j = end = k
    token = None
    while j < len(stream):
        kind, v, _ = stream[j]
        if kind != 'w':
            break
        nxt = stream[j + 1][1] if j + 1 < len(stream) and stream[j + 1][0] == 'w' else None
        if v in UNITS or v in ORD_UNITS:
            n = UNITS.get(v, ORD_UNITS.get(v))
            if not (last in (None, 'scale', 'and') or (last == 'tens' and n < 10)):
                break
            cur += n
            last = 'unit'
            j = end = j + 1
            if v in ORD_UNITS:
                token = ordinal(total + cur)
                break
        elif v in TENS or v in ORD_TENS:
            if last not in (None, 'scale', 'and'):
                break
            cur += TENS.get(v, ORD_TENS.get(v))
            last = 'tens'
            j = end = j + 1
            if v in ORD_TENS:
                token = ordinal(total + cur)
                break
        elif v in SCALES or v in ORD_SCALES:
            scale = SCALES.get(v, ORD_SCALES.get(v))
            if last is None:
                cur = scale  # "hundred" alone, as in "a hundred"
            elif scale == 100:
                if last not in ('unit', 'tens') or not 0 < cur < 100:
                    break
                cur *= 100
            else:
                if last not in ('unit', 'tens', 'scale') or cur <= 0:
                    break
                total += cur * scale
                cur = 0
            last = 'scale'
            j = end = j + 1
            if v in ORD_SCALES:
                token = ordinal(total + cur)
                break
        elif v == 'and' and last == 'scale' and nxt in NUMWORDS and nxt not in SCALES and nxt not in ORD_SCALES:
            last = 'and'
            j += 1
        elif v == 'point' and last in ('unit', 'tens', 'scale') and nxt in UNITS and UNITS[nxt] < 10:
            digits = ''
            j += 1
            while j < len(stream) and stream[j][0] == 'w' and stream[j][1] in UNITS and UNITS[stream[j][1]] < 10:
                digits += str(UNITS[stream[j][1]])
                j += 1
            end = j
            token = '%d.%s' % (total + cur, digits)
            break
        else:
            break
    if end == k:
        return None, k
    return (token or str(total + cur)), end


def canon(words):
    """Canonical tokens for a word list: [(token, (first_word_idx, last_word_idx)), ...]."""
    stream = [(kind, v, i) for i, w in enumerate(words) for kind, v in pieces(w)]
    out = []
    k = 0
    while k < len(stream):
        kind, v, i = stream[k]
        if kind == 'w' and v in NUMWORDS:
            tok, end = _parse_number(stream, k)
            if tok is not None:
                idx = [stream[x][2] for x in range(k, end)]
                out.append((tok, (min(idx), max(idx))))
                k = end
                continue
        if kind == 'ord':
            out.append((ordinal(v), (i, i)))
        else:
            out.append((str(v), (i, i)))
        k += 1
    return out


def align_line(toks, seg, start, dur):
    """Times for one script line. toks: script words; seg: ASR words [{text,start,end}] near the line."""
    sc = canon(toks)
    ac = canon([a['text'] for a in seg])
    sm = difflib.SequenceMatcher(a=[t for t, _ in sc], b=[t for t, _ in ac], autojunk=False)
    iv = [None] * len(toks)
    for blk in sm.get_matching_blocks():
        for m in range(blk.size):
            (w0, w1), (a0, a1) = sc[blk.a + m][1], ac[blk.b + m][1]
            t0, t1 = seg[a0]['start'], seg[a1]['end']
            for w in range(w0, w1 + 1):
                iv[w] = (t0, t1) if iv[w] is None else (min(iv[w][0], t0), max(iv[w][1], t1))
    matched = sum(1 for x in iv if x is not None)
    times = [None] * len(toks)
    # script words that share an ASR span (e.g. "five hundred and twenty-two" -> "522") split it by length
    i = 0
    while i < len(toks):
        if iv[i] is None:
            i += 1
            continue
        j, lo, hi = i + 1, iv[i][0], iv[i][1]
        while j < len(toks) and iv[j] is not None and iv[j][0] < hi - 1e-6:
            hi = max(hi, iv[j][1])
            j += 1
        lens = [len(t) + 1 for t in toks[i:j]]
        tot, acc = float(sum(lens)), lo
        for k in range(i, j):
            d = (hi - lo) * lens[k - i] / tot
            times[k] = (acc, acc + d)
            acc += d
        i = j
    # interpolate runs of unmatched words across the gap between their matched neighbours,
    # proportional to character length
    i = 0
    while i < len(toks):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(toks) and times[j] is None:
            j += 1
        g0 = times[i - 1][1] if i > 0 else start
        g1 = times[j][0] if j < len(toks) else start + dur
        g1 = max(g1, g0 + 0.08 * (j - i))
        lens = [len(t) + 1 for t in toks[i:j]]
        tot, acc = float(sum(lens)), g0
        for k in range(i, j):
            d = (g1 - g0) * lens[k - i] / tot
            times[k] = (acc, acc + d)
            acc += d
        i = j
    return times, matched


def align(script, transcript, timeline):
    asr = transcript if isinstance(transcript, list) else transcript.get('words', [])
    asr = [a for a in asr if canon([a['text']])]
    s_lines, t_lines = script['lines'], timeline['lines']
    if [L['id'] for L in s_lines] != [T['id'] for T in t_lines]:
        raise SystemExit('align.py: script.json and timeline.json list different lines; re-run voice.py')
    words, report = [], []
    for L, T in zip(s_lines, t_lines):
        toks = L['text'].split()
        lo, hi = T['start'] - 0.6, T['start'] + T['dur'] + 0.3
        seg = [a for a in asr if lo <= a['start'] <= hi]
        times, matched = align_line(toks, seg, T['start'], T['dur'])
        errs = len(toks) - matched
        report.append({'line': L['id'], 'words': len(toks), 'asr_words': len(seg), 'unmatched': errs,
                       'wer': round(errs / max(1, len(toks)), 3)})
        for t, (s, e) in zip(toks, times):
            words.append({'id': 'w%d' % len(words), 'line': L['id'], 'text': t,
                          'start': round(s, 3), 'end': round(max(e, s + 0.08), 3)})
    return words, report


def main(argv):
    if len(argv) != 4:
        raise SystemExit('usage: align.py <script.json> <transcript.json> <timeline.json> <out words.json>')
    loaded = []
    for p in argv[:3]:
        with open(p, encoding='utf-8') as f:
            loaded.append(json.load(f))
    words, report = align(*loaded)
    with open(argv[3], 'w', encoding='utf-8') as f:
        json.dump(words, f, indent=0, ensure_ascii=False)
    print(json.dumps(report))


if __name__ == '__main__':
    main(sys.argv[1:])
