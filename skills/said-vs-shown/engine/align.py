#!/usr/bin/env python3
"""align.py — put ASR timings on the SCRIPT's words (caption text always comes from the script).

usage: align.py <script.json> <transcript.json> <timeline.json> <out words.json>

Both sides are normalised to the same canonical tokens before matching, so spoken numbers and
digits meet in the middle: "five hundred and twenty-two" / "522", "ninety-three percent" / "93%",
"fifth" / "5th", "Nineteen" / "19". The whole script is aligned against the whole ASR word stream in
one monotonic alignment (most matched tokens; ties go to the match nearest the word's expected time),
so an ASR that puts a line's first words a second early (Whisper does) still matches them to that line.
Each matched word keeps its line: if the line's ASR times spill out of the line's audio (timeline start
.. start + dur), they are mapped back onto it. Script words that share one ASR word share its time span
(split by character length). Runs of unmatched script words are spread across the gap between their
matched neighbours inside their own line, proportional to character length.
Guarantees: word starts never decrease; every word starts in its line's window (from 0.3 s before the
line, never before the previous line's audio end, to the line's end) and lasts >= 0.08 s; no word ends
after its line's audio unless that minimum needs it, and none reaches into the next line's window.
Prints per-line stats as JSON: words, asr_words, unmatched, wer, refit (start/end shift applied, s).
"""
import bisect
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


LEAD = 0.3        # a line's words may start this much before its timeline start (scene cuts sit 0.36 s before it)
REFIT = 0.45      # a line whose first matched word starts earlier than this before the line is refitted (_refit)
MIN_DUR = 0.08    # every word lasts at least this long
REACH = 2.5       # an ASR word this far (s) outside a line's audio can still match that line's words
NEAR = 0.1        # tie-break weight: of equally long alignments, prefer matches near the word's expected time


def _asr_tokens(asr):
    """Canonical ASR tokens [(token, first_word, last_word)], numbers parsed within a sentence and a pause only."""
    out, run_ = [], []

    def flush():
        if run_:
            off = run_[0]
            out.extend((tok, off + w0, off + w1) for tok, (w0, w1) in canon([asr[i]['text'] for i in run_]))
            del run_[:]
    for i, a in enumerate(asr):
        if run_:
            prev = asr[run_[-1]]
            if prev['text'].rstrip('"”’)]').endswith(('.', '?', '!')) or a['start'] - prev['end'] > 0.3:
                flush()
        run_.append(i)
    flush()
    return out


def _lcs(S, A):
    """Global monotonic alignment of script tokens S [(token, lo, hi, t_expected)] with ASR tokens
    A [(token, t)]: the most matched tokens (an ASR token matches a script token only when their text is equal and
    the ASR time is within REACH of the script token's line), ties broken towards the expected time.
    Returns [(script index, asr index)] in increasing order of both."""
    n, m = len(S), len(A)
    where = {}
    for j, (tok, _) in enumerate(A):
        where.setdefault(tok, []).append(j)
    cand = []
    for tok, lo, hi, t_exp in S:
        c = {}
        for j in where.get(tok, ()):
            t = A[j][1]
            if lo - REACH <= t <= hi + REACH:
                c[j + 1] = 1.0 + NEAR * max(0.0, 1.0 - abs(t - t_exp) / REACH)
        cand.append(c)
    prev = [0.0] * (m + 1)
    back = []
    for i in range(n):
        c = cand[i]
        if not c:  # rows are non-decreasing in j, so a row without candidates is the row above
            back.append(None)
            continue
        cur = prev[:]
        bp = bytearray(m + 1)
        for j in range(min(c), m + 1):
            best, b = prev[j], 0
            if cur[j - 1] > best:
                best, b = cur[j - 1], 1
            sc = c.get(j)
            if sc is not None and prev[j - 1] + sc > best:
                best, b = prev[j - 1] + sc, 2
            cur[j], bp[j] = best, b
        back.append(bp)
        prev = cur
    pairs, i, j = [], n, m
    while i > 0 and j > 0:
        b = back[i - 1][j] if back[i - 1] is not None else 0
        if b == 2:
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif b == 1:
            j -= 1
        else:
            i -= 1
    return pairs[::-1]


def _split_shared(toks, iv):
    """Script words that share an ASR span (e.g. "five hundred and twenty-two" -> "522") split it by length."""
    times = [None] * len(toks)
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
    return times


def _refit(toks, iv, start, end):
    """Map the line's matched ASR times onto its audio when they spill out of it. Whisper can put a line's first
    words up to ~1 s before the line starts and its last ones well after the line's audio ends; the words in between
    drift with them. The first matched start goes to the line start when it is more than REFIT before it (Parakeet
    starts lines up to ~0.3 s early, which the clamp to `lo` handles); the last matched start, when it is at or
    after the line's end, goes to where the last words must begin to fit (by character length); everything in
    between is mapped linearly."""
    got = [k for k, x in enumerate(iv) if x is not None]
    if not got:
        return iv, (0.0, 0.0)
    k0, k1 = got[0], got[-1]
    a0, a1 = iv[k0][0], iv[k1][0]
    chars = float(sum(len(t) + 1 for t in toks))
    tail = max(MIN_DUR, (end - start) * sum(len(t) + 1 for t in toks[k1:]) / chars)  # time the last words need
    b0 = a0 if a0 >= start - REFIT else start
    b1 = a1 if a1 < end else max(b0, end - tail)
    if (b0, b1) == (a0, a1):
        return iv, (0.0, 0.0)
    if a1 - a0 > 0.05 and b1 - b0 > 0.05:
        f = lambda t: b0 + (t - a0) * (b1 - b0) / (a1 - a0)  # noqa: E731
    else:  # one word, or a span that cannot be mapped: shift it
        d = (b0 - a0) if b0 != a0 else (b1 - a1)
        f = lambda t: t + d  # noqa: E731
    return [None if x is None else (f(x[0]), f(x[1])) for x in iv], (round(b0 - a0, 3), round(b1 - a1, 3))


def _fill(toks, times, start, end):
    """Spread runs of unmatched words across the gap between their matched neighbours in the line (or the line's
    start / end), proportional to character length."""
    i = 0
    while i < len(toks):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(toks) and times[j] is None:
            j += 1
        g0 = times[i - 1][1] if i > 0 else start
        g1 = times[j][0] if j < len(toks) else end
        g1 = max(g1, g0 + MIN_DUR * (j - i))
        lens = [len(t) + 1 for t in toks[i:j]]
        tot, acc = float(sum(lens)), g0
        for k in range(i, j):
            d = (g1 - g0) * lens[k - i] / tot
            times[k] = (acc, acc + d)
            acc += d
        i = j
    return times


def align(script, transcript, timeline):
    """(words, report): the script's words with times, and per-line match stats.

    1. One global, monotonic alignment of the whole script against the whole ASR word stream (canonical tokens,
       so spoken numbers meet digits). No per-line search window: a word the ASR put early or late still matches.
    2. Each matched word belongs to its script line. If the line's matched ASR times spill out of the line's audio,
       they are mapped back onto it (`_refit`).
    3. Unmatched runs are interpolated inside their line only.
    4. Guarantees, per line [lo = start - LEAD (never before the previous line's audio end), end = start + dur]:
       lo <= word start, starts never decrease, word end >= start + MIN_DUR, end <= the line's end unless the
       minimum length needs more, and no word reaches the next line's lo."""
    asr = transcript if isinstance(transcript, list) else transcript.get('words', [])
    asr = sorted((a for a in asr if canon([a['text']])), key=lambda a: a['start'])
    s_lines, t_lines = script['lines'], timeline['lines']
    if [L['id'] for L in s_lines] != [T['id'] for T in t_lines]:
        raise SystemExit('align.py: script.json and timeline.json list different lines; re-run voice.py')
    lines = []
    prev_end = 0.0
    for L, T in zip(s_lines, t_lines):
        start, end = float(T['start']), float(T['start']) + float(T['dur'])
        lines.append({'id': L['id'], 'toks': L['text'].split(), 'start': start, 'end': end,
                      'lo': min(start, max(start - LEAD, prev_end, 0.0))})
        prev_end = end

    # 1. global alignment on canonical tokens
    S, owner = [], []  # owner: (line index, first word, last word) per script token
    for li, ln in enumerate(lines):
        toks = ln['toks']
        chars = float(sum(len(t) + 1 for t in toks)) or 1.0
        offs, acc = [], 0
        for t in toks:
            offs.append(acc)
            acc += len(t) + 1
        for tok, (w0, w1) in canon(toks):
            S.append((tok, ln['start'], ln['end'], ln['start'] + (ln['end'] - ln['start']) * offs[w0] / chars))
            owner.append((li, w0, w1))
    At = _asr_tokens(asr)
    pairs = _lcs(S, [(tok, asr[a0]['start']) for tok, a0, _ in At])

    ivs = [[None] * len(ln['toks']) for ln in lines]
    asr_line = [None] * len(asr)
    for si, aj in pairs:
        li, w0, w1 = owner[si]
        _, a0, a1 = At[aj]
        t0, t1 = asr[a0]['start'], asr[a1]['end']
        for w in range(w0, w1 + 1):
            x = ivs[li][w]
            ivs[li][w] = (t0, t1) if x is None else (min(x[0], t0), max(x[1], t1))
        for a in range(a0, a1 + 1):
            asr_line[a] = li

    # ASR words no script word matched belong to the line of their matched neighbours (or the nearer one)
    known = [k for k, li in enumerate(asr_line) if li is not None]
    for k in range(len(asr)):
        if asr_line[k] is not None or not known:
            continue
        b = bisect.bisect(known, k)
        cands = [asr_line[known[x]] for x in (b - 1, b) if 0 <= x < len(known)]
        t = asr[k]['start']
        asr_line[k] = min(cands, key=lambda li: max(0.0, lines[li]['lo'] - t, t - lines[li]['end']))

    words, report = [], []
    for li, ln in enumerate(lines):
        toks, start, end, lo = ln['toks'], ln['start'], ln['end'], ln['lo']
        nxt = lines[li + 1]['lo'] if li + 1 < len(lines) else float('inf')
        iv = ivs[li]
        matched = sum(1 for x in iv if x is not None)
        # 2. refit spill, then clamp into the line's window; a word whose ASR span lies wholly outside is re-spread
        iv, shift = _refit(toks, iv, start, end)
        iv = [None if x is None or x[1] <= lo or x[0] >= end else (max(x[0], lo), min(x[1], end)) for x in iv]
        times = _split_shared(toks, iv)
        # 3. unmatched runs, inside the line only
        times = _fill(toks, times, start, end)
        # 4. guarantees
        s_max = min(end, nxt - MIN_DUR)
        last = lo
        for k, (s, e) in enumerate(times):
            s = round(min(max(s, lo, last), s_max), 3)
            last = s
            e = round(min(max(min(e, end), s + MIN_DUR), nxt), 3)
            words.append({'id': 'w%d' % len(words), 'line': ln['id'], 'text': toks[k], 'start': s, 'end': e})
        errs = len(toks) - matched
        report.append({'line': ln['id'], 'words': len(toks), 'asr_words': sum(1 for x in asr_line if x == li),
                       'unmatched': errs, 'wer': round(errs / max(1, len(toks)), 3), 'refit': list(shift)})
    return words, report


def main(argv):
    if any(a in ('-h', '--help') for a in argv):
        print(__doc__.strip())
        sys.exit(0)
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
