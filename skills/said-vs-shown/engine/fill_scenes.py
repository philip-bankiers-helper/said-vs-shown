#!/usr/bin/env python3
"""fill_scenes.py — fill the squeeze, payoff, one-thing and close scenes of an episode from its data.

usage: fill_scenes.py <episode_dir> [--only squeeze,close] [--dry-run]

<episode_dir> is the episode root (holds edit/, ledger/, video/); its video/ folder is accepted too.

Reads
  edit/episode.json             show, edition, window, date, captured, title, stories, matrix, one_thing,
                                one_thing_highlight, editor / reviewed_by, credits, credit, lead_badge_overrides
                                optional: close_title, payoff_statement, payoff_highlight, one_thing_lead, one_thing_kicker
  ledger/leads.json             the other leads (card_title or title, status) → squeeze cards and counts
  ledger/sources.json           sources captured (count); falls back to ledger/capture-log.jsonl (ok lines)
  video/audio/scene-words.json  per-scene LOCAL word timings → every beat
  video/assets/receipts/*.json  quotes located (found: true) → count
  video/scenes.json             scene ids → compositions/NN-<scene>.html
  video/frame.md                the edition accent (the `--accent` row)
Writes video/compositions/NN-<scene>.html from <skill>/templates/scenes/<kind>.html by replacing
__SCENE_ID__, __P__ and the template's CFG block. Deterministic: the same inputs give the same files.
Prints the beat table of each scene, and which scenes still need hand authoring (receipts) or another
tool (boards, boundaries). Exit 1 if a requested scene could not be filled.
"""
import argparse
import glob
import io
import json
import os
import re
import sys

ENGINE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(ENGINE)
sys.path.insert(0, ENGINE)
from companion import (CLOSE_CREDIT_CHARS, CLOSE_CREDITS, credit_footer, credits_of, disclosure_of,  # noqa: E402
                       reviewer_of)  # one disclosure and credits rule for the video and the page
TEMPLATES = os.path.join(SKILL, 'templates', 'scenes')
KINDS = ('squeeze', 'payoff', 'one-thing', 'close')
DEFAULT_ACCENT = '#f2c14e'

BADGES = {'checked': 'checked', 'verified': 'checked', 'company': 'company', 'company_claim': 'company',
          'reported': 'reported', 'provider': 'provider', 'provider_only': 'provider',
          'older': 'older', 'older_background': 'older'}
NUMBER_WORDS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven',
                'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen', 'twenty']
STOP = {'a', 'an', 'the', 'at', 'of', 'to', 'and', 'or', 'in', 'on', 'by', 'for', 'with', 'is', 'are', 'be', 'can',
        'that', 'its', 'it', 'it\'s', 'this', 'these', 'those', 'their', 'your', 'our', 'as', 'like', 'whether', 'needs',
        'need', 'does', 'did', 'do', 'was', 'were', 'will', 'would', 'should', 'has', 'have', 'from', 'than', 'then'}
GENERIC = {'test', 'tests', 'tested', 'check', 'checks', 'checked', 'claim', 'claims'}
NEGATIONS = ("doesn't", "don't", "isn't", "aren't", "can't", "won't", "didn't", 'not', 'never', 'no')


# ── small helpers ────────────────────────────────────────────────────────────────────────────────

def load(path, default=None):
    if not os.path.isfile(path):
        return default
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def norm(w):
    w = w.replace('’', "'").replace('‘', "'").lower()
    return re.sub(r"^[^\w']+|[^\w']+$", '', w)


def r2(x):
    return round(float(x) + 1e-9, 2)


def num_words(n):
    out = {str(n)}
    if 0 <= n < len(NUMBER_WORDS):
        out.add(NUMBER_WORDS[n])
    return out


class Words:
    """A scene's LOCAL word timings ({t, s, e}) with a few search helpers."""

    def __init__(self, entry):
        self.w = [dict(x, n=norm(x['t'])) for x in (entry or {}).get('words', [])]
        self.duration = float((entry or {}).get('duration') or (self.w[-1]['e'] if self.w else 0.0))

    def __bool__(self):
        return bool(self.w)

    def find(self, cands, after=0.0, start=0):
        cands = {norm(c) for c in cands}
        for i in range(start, len(self.w)):
            if self.w[i]['s'] >= after - 1e-6 and self.w[i]['n'] in cands:
                return i
        return None

    def find_phrase(self, phrase, after=0.0, start=0):
        toks = [norm(t) for t in phrase.split() if norm(t)]
        if not toks:
            return None
        for i in range(start, len(self.w) - len(toks) + 1):
            if self.w[i]['s'] >= after - 1e-6 and all(self.w[i + j]['n'] == toks[j] for j in range(len(toks))):
                return i, i + len(toks) - 1
        return None

    def sentences(self):
        out, i0 = [], 0
        for i, x in enumerate(self.w):
            if x['t'].rstrip('"”’\')').endswith(('.', '?', '!')):
                out.append((i0, i))
                i0 = i + 1
        if i0 < len(self.w):
            out.append((i0, len(self.w) - 1))
        return out

    def text(self, i0, i1):
        return ' '.join(x['t'] for x in self.w[i0:i1 + 1])


class Beats:
    """Collects (name, time, how) rows for the printed beat table."""

    def __init__(self, scene):
        self.scene, self.rows = scene, []

    def add(self, name, t, how):
        t = r2(max(0.0, t))
        self.rows.append((name, t, how))
        return t

    def table(self):
        lines = [f'  {self.scene}']
        for n, t, how in self.rows:
            lines.append(f'    {t:7.2f}  {n:<18} {how}')
        return '\n'.join(lines)


def balanced_chunks(words, n):
    """Split a word list into n contiguous chunks, minimising the longest; don't end a chunk on a stop word."""
    import itertools
    n = max(1, min(n, len(words)))
    if n == 1:
        return [words]
    best = None
    for cut in itertools.combinations(range(1, len(words)), n - 1):
        parts = [words[a:b] for a, b in zip((0,) + cut, cut + (len(words),))]
        score = max(len(' '.join(p)) for p in parts)
        score += 8 * sum(1 for p in parts[:-1] if norm(p[-1]) in STOP)
        if best is None or score < best[0]:
            best = (score, parts)
    return best[1]


def lead_off(mark, tail):
    """Split a highlight that opens the one-thing question into (line1, mark): line 1 takes the highlight's first
    words and the rest stays marked on line 2 (which also carries the tail). The two lines are balanced and line 1
    avoids ending on a stop word. A one-word highlight cannot be split: ('', mark)."""
    mw = mark.split()
    best = None
    for k in range(1, len(mw)):
        a, b = ' '.join(mw[:k]), ' '.join(mw[k:])
        score = max(len(a), len(b + tail)) + (8 if norm(mw[k - 1]) in STOP else 0)
        if best is None or score < best[0]:
            best = (score, a, b)
    return (best[1], best[2]) if best else ('', mark)


def align_tokens(W, toks, start=0, window=6):
    """Greedy in-order alignment of on-screen tokens to spoken words; None where a token wasn't said nearby."""
    out, cur = [], start
    for t in toks:
        n, hit = norm(t), None
        if n:
            for i in range(cur, min(len(W.w), cur + window)):
                if W.w[i]['n'] == n:
                    hit = i
                    break
        out.append(hit)
        if hit is not None:
            cur = hit + 1
    return out


def display_url(u):
    u = re.sub(r'^[a-z]+://', '', u.strip())
    u = re.sub(r'^www\.', '', u)
    return u.rstrip('/')


def short_credit(c, limit=CLOSE_CREDIT_CHARS):
    """(credit as the close card prints it, shortened?): at most `limit` characters, cut at a word with "…"."""
    if len(c) <= limit:
        return c, False
    cut = c[:limit - 1].rsplit(' ', 1)[0].rstrip(',.;:')
    return (cut if len(cut) > c.index(':') + 1 else c[:limit - 1]) + '…', True


def short_title(t, limit=36):
    t = re.split(r'\s*[:;]\s+|\s+[—–]\s+', t.strip())[0]
    if len(t) <= limit:
        return t, False
    cut = t[:limit].rsplit(' ', 1)[0].rstrip(',.;:')
    return cut + '…', True


def js_literal(obj, indent):
    """JSON (valid JS) for the CFG block, re-indented to sit inside the template's script."""
    s = json.dumps(obj, indent=2, ensure_ascii=False).replace('</', '<\\/')
    return s.replace('\n', '\n' + ' ' * indent)


def accent_of(video_dir):
    try:
        with open(os.path.join(video_dir, 'frame.md'), encoding='utf-8') as fh:
            m = re.search(r'`--accent`\s*\|\s*`(#[0-9A-Fa-f]{6})`', fh.read())
        return m.group(1).lower() if m else DEFAULT_ACCENT
    except OSError:
        return DEFAULT_ACCENT


def prefix_for(sid, taken):
    parts = [p for p in re.split(r'[-_]+', sid) if p]
    cand = (''.join(p[0] for p in parts[:2]) if len(parts) > 1 else sid[:2]).lower()
    cand = re.sub(r'[^a-z0-9]', '', cand) or 'sc'
    if cand in taken:
        cand = re.sub(r'[^a-z0-9]+', '-', sid.lower()).strip('-')
    taken.add(cand)
    return cand + '-'


def render(kind, sid, prefix, cfg, accent):
    with open(os.path.join(TEMPLATES, f'{kind}.html'), encoding='utf-8') as fh:
        src = fh.read()
    m = re.search(r'^([ \t]*)const CFG = \{.*?\};(?=\s*// ==== /CFG ====)', src, flags=re.S | re.M)
    if not m:
        raise RuntimeError(f'templates/scenes/{kind}.html has no CFG block')
    indent = len(m.group(1))
    src = src[:m.start()] + m.group(1) + 'const CFG = ' + js_literal(cfg, indent) + ';' + src[m.end():]
    src = src.replace('__SCENE_ID__', sid).replace('__P__', prefix)
    if accent != DEFAULT_ACCENT:
        rgb = ', '.join(str(int(accent[i:i + 2], 16)) for i in (1, 3, 5))
        src = re.sub(re.escape(DEFAULT_ACCENT), accent, src, flags=re.I)
        src = src.replace('242, 193, 78', rgb)
    return src


# ── episode facts ────────────────────────────────────────────────────────────────────────────────

class Episode:
    def __init__(self, root):
        self.root = root
        self.video = os.path.join(root, 'video')
        self.E = load(os.path.join(root, 'edit', 'episode.json'))
        if self.E is None:
            sys.exit(f'fill_scenes.py: no edit/episode.json under {root}')
        self.leads = load(os.path.join(root, 'ledger', 'leads.json'), []) or []
        self.scenes = load(os.path.join(self.video, 'scenes.json'), {}) or {}
        self.words = load(os.path.join(self.video, 'audio', 'scene-words.json'), {}) or {}
        self.stories = self.E.get('stories') or []
        self.notes = []

    def meta(self):
        E = self.E
        return {'show': E.get('show') or 'Said vs. Shown', 'edition': E.get('edition') or '', 'window': E.get('window') or ''}

    def badge(self, raw, where):
        b = BADGES.get(str(raw or '').strip().lower())
        if not b:
            self.notes.append(f'{where}: badge/status {raw!r} is not one of checked|company|reported|provider|older; shown as REPORTED')
            b = 'reported'
        return b

    def lead_cards(self):
        over = {str(k): v for k, v in (self.E.get('lead_badge_overrides') or {}).items()}
        cards = []
        for i, s in enumerate(self.stories):
            cards.append({'title': s.get('card_title') or s.get('topic') or f'Story {i + 1}',
                          'badge': self.badge(s.get('badge'), f'stories[{i}]')})
        for L in self.leads:
            lid = str(L.get('lead_id', ''))
            status = str(over.get(lid) or L.get('status') or '').strip().lower()
            if status in ('contradicted', 'unverifiable'):
                self.notes.append(f'lead {lid}: {status} leads get no squeeze card (no video badge); the companion page '
                                  'lists them. Set lead_badge_overrides to show it with another badge')
                continue
            title = L.get('card_title')
            if not title:
                title, cut = short_title(L.get('title') or f'Lead {lid}')
                if cut:
                    self.notes.append(f'lead {lid}: card title shortened to {title!r}; set "card_title" in leads.json to choose the words')
            cards.append({'title': title, 'badge': self.badge(over.get(lid) or L.get('status'), f'lead {lid}')})
        return cards

    def sources_captured(self):
        src = load(os.path.join(self.root, 'ledger', 'sources.json'))
        if isinstance(src, list):
            return len(src)
        log = os.path.join(self.root, 'ledger', 'capture-log.jsonl')
        if os.path.isfile(log):
            with open(log, encoding='utf-8') as fh:
                rows = [json.loads(l) for l in fh if l.strip()]
            self.notes.append('ledger/sources.json missing: "Sources captured" counted from capture-log.jsonl (ok lines)')
            return sum(1 for r in rows if r.get('ok', (r.get('result') or {}).get('ok')))
        self.notes.append('no ledger/sources.json or capture-log.jsonl: "Sources captured" left off the receipt')
        return None

    def quotes_located(self):
        n = 0
        for p in sorted(glob.glob(os.path.join(self.video, 'assets', 'receipts', '*.json'))):
            if (load(p) or {}).get('found'):
                n += 1
        return n

    def _warnings(self, fn):
        """Run fn(E, warn_to) and keep each warning it prints as a note."""
        buf = io.StringIO()
        out = fn(self.E, buf)
        self.notes.extend('warning: ' + l.split('warning: ', 1)[-1] for l in buf.getvalue().splitlines() if l.strip())
        return out

    def disclosure(self):
        if not reviewer_of(self.E):
            self.notes.append('no reviewed_by yet: the disclosure reads "not yet human-reviewed"; after the review '
                              '(stage 10) set reviewed_by and re-run fill_scenes.py --only close')
        return self._warnings(disclosure_of)

    def credits(self):
        return self._warnings(credits_of)

    def footer(self):
        """The receipt's "Made with" footer: episode.json "credit" (true when unset, as new_episode.py writes it)."""
        return self._warnings(lambda E, warn_to: credit_footer(E, True, warn_to))


# ── scene builders ───────────────────────────────────────────────────────────────────────────────

def build_squeeze(ep, W, bt):
    cards = ep.lead_cards()
    K = len(ep.stories)
    if not 1 <= K <= 4:
        raise RuntimeError(f'the squeeze shows 1–4 stories; episode.json has {K}')
    if len(cards) > 20:
        ep.notes.append(f'squeeze: {len(cards)} leads; the grid shows the first 20 (the ticker and pile count all of them)')
    sents = W.sentences()
    t_cards = bt.add('cards', (W.w[0]['s'] - 0.07) if W else 0.25, 'first word − 0.07')
    after = W.w[sents[0][1]]['e'] if len(sents) > 1 else 0.0
    i = W.find(num_words(K), after=after)
    if i is not None:
        sq = bt.add('squeeze', W.w[i]['s'], f'"{W.w[i]["t"]}"')
    elif len(sents) > 1:
        sq = bt.add('squeeze', W.w[sents[1][0]]['s'], 'second sentence (no story-count word found)')
    else:
        sq = bt.add('squeeze', 0.41 * W.duration, 'fallback 41% of the line')
    j = W.find(['test', 'tests', 'tested'], after=sq)
    if j is not None and j > 0:
        tests = bt.add('tests', W.w[j - 1]['s'], f'"{W.w[j - 1]["t"]} {W.w[j]["t"]}"')
    else:
        tests = bt.add('tests', sq + 1.28, 'fallback squeeze + 1.28')
    k = W.find(['evidence', 'boundary', 'stops', 'proves'], after=tests + 0.3)
    if k is not None and W.w[k]['n'] == 'proves':
        k2 = W.find(['evidence', 'boundary', 'stops'], after=W.w[k]['e'])
        k = k2 if k2 is not None else k
    boundary = bt.add('boundary', W.w[k]['s'] if k is not None else max(tests + 1.0, W.duration - 1.3),
                      f'"{W.w[k]["t"]}"' if k is not None else 'fallback end − 1.3')
    return {
        'meta': ep.meta(),
        'leads': cards,
        'stories': K,
        'total_leads': len(ep.stories) + len(ep.leads),  # every lead reviewed, carded or not
        'beats': {'cards': t_cards, 'squeeze': sq, 'tests': tests, 'boundary': boundary},
    }


def match_fragment(W, frag, lo, hi):
    toks = [norm(t) for t in frag.split()]
    toks = [t for t in toks if t and t not in STOP and t not in GENERIC]
    for i, x in enumerate(W.w):
        if lo - 1e-6 <= x['s'] <= hi and x['n'] in toks:
            return i
    return None


def build_payoff(ep, W, bt):
    E = ep.E
    matrix = E.get('matrix') or []
    rows_in = matrix[:4]
    if not rows_in:
        raise RuntimeError('episode.json has no "matrix" rows ([claim, test] per story)')
    if len(rows_in) != len(ep.stories):
        ep.notes.append(f'payoff: matrix has {len(rows_in)} rows but there are {len(ep.stories)} stories')
    sents = W.sentences()
    NR = len(rows_in)
    if not W or len(sents) < 2:
        raise RuntimeError('no payoff word timings (run voice.py; scene-words.json needs this scene)')
    s0 = sents[0]
    row_sents = sents[1:1 + NR] if len(sents) >= NR + 2 else None
    stmt_sent = sents[-1]
    if row_sents is None:
        ep.notes.append(f'payoff: expected 1 intro + {NR} row sentences + 1 statement, found {len(sents)} sentences; rows spread evenly')
    w0 = W.w[0]['s']
    labels = [bt.add(f'label {i + 1}', w0 + 0.1 + i * 0.165, 'first word + stagger') for i in range(NR)]
    comma = next((i for i in range(s0[0], s0[1]) if W.w[i]['t'].endswith(',')), None)
    if comma is not None:
        head = bt.add('head claim', W.w[comma + 1]['s'] + 0.02, f'"{W.w[comma + 1]["t"]}" (2nd clause)')
    else:
        head = bt.add('head claim', (W.w[s0[0]]['s'] + W.w[s0[1]]['e']) / 2, 'middle of the intro sentence')
    bt.add('head test', head + 0.6, 'head claim + 0.6')
    bt.add('skeleton', head + 0.08, 'head claim + 0.08')

    stmt_lo, stmt_hi = W.w[stmt_sent[0]]['s'], W.w[stmt_sent[1]]['e']
    rows = []
    for i, r in enumerate(rows_in):
        story = ep.stories[i] if i < len(ep.stories) else {}
        claim, test = r[0], r[1]
        frags = [f for f in (test if isinstance(test, list) else [test]) if f]
        if row_sents:
            a, b = row_sents[i]
            lo, hi = W.w[a]['s'], W.w[b]['e']
        else:
            span = (stmt_lo - W.w[s0[1]]['e']) / NR
            lo = W.w[s0[1]]['e'] + i * span
            hi = lo + span
        t_claim = bt.add(f'row {i + 1} claim', lo + 0.05, 'sentence start + 0.05')
        times, prev = [], t_claim + 0.3
        fracs = [0.55] if len(frags) == 1 else [0.45 + 0.3 * j / (len(frags) - 1) for j in range(len(frags))]
        for j, f in enumerate(frags):
            m = match_fragment(W, f, prev, hi)
            if m is not None:
                t = W.w[m]['s'] - 0.04
                how = f'"{W.w[m]["t"]}"'
            else:
                t = max(prev, lo + fracs[j] * (hi - lo))
                how = f'{int(fracs[j] * 100)}% of the sentence (no spoken match)'
            t = bt.add(f'row {i + 1} test {j + 1}', t, how)
            times.append(t)
            prev = t + 0.3
        idx = bt.add(f'row {i + 1} index', min(max(t_claim + 0.5, times[0] - 0.6), times[0] - 0.1), 'first test − 0.6')
        rows.append({'num': story.get('n') or f'{i + 1:02d}', 'label': story.get('topic') or claim, 'claim': claim,
                     'test': frags, 'at': {'label': labels[i], 'claim': t_claim, 'idx': idx, 'test': times}})

    text = E.get('payoff_statement') or W.text(*stmt_sent)
    mark = E.get('payoff_highlight')
    toks = text.split()
    if not mark:
        ni = next((i for i, t in enumerate(toks) if norm(t) in NEGATIONS), None)
        mark = ' '.join(toks[ni:ni + 2]).rstrip('.,;:!?') if ni is not None else ''
    pos = text.find(mark) if mark else -1
    if mark and pos < 0:
        ep.notes.append(f'payoff: highlight {mark!r} is not in the statement {text!r}; no underline')
        mark = ''
    lead = text[:pos].rstrip() if mark else text
    tail = text[pos + len(mark):] if mark else ''
    if len(text) > 60:
        ep.notes.append(f'payoff: statement is {len(text)} chars (one 56px line holds ~60); shorten payoff_statement')
    t_lead = bt.add('statement', stmt_lo + 0.02, 'last sentence start + 0.02')
    ph = W.find_phrase(mark, after=stmt_lo - 0.5) if mark else None
    if ph:
        t_mark = bt.add('statement mark', W.w[ph[0]]['s'] - 0.04, f'"{mark}"')
        ul = bt.add('underline', W.w[ph[0]]['s'] + 0.04, 'mark + 0.04')
        ul_d = r2(max(0.4, W.w[ph[1]]['e'] - W.w[ph[0]]['s']))
    else:
        t_mark = bt.add('statement mark', t_lead + (0.75 if lead else 0), 'fallback')
        ul, ul_d = r2(t_mark + 0.08), 0.8
    return {
        'meta': ep.meta(),
        'heads': {'claim': 'Claim', 'test': 'Test that fits'},
        'rows': rows,
        'statement': {'lead': lead, 'mark': mark, 'tail': tail,
                      'at': {'lead': t_lead, 'mark': t_mark, 'underline': ul, 'underline_dur': ul_d}},
        'beats': {'plate': 0.05, 'head_claim': head, 'head_test': r2(head + 0.6), 'skeleton': r2(head + 0.08)},
    }


def build_one_thing(ep, W, bt):
    E = ep.E
    one = (E.get('one_thing') or '').strip()
    if not one:
        raise RuntimeError('episode.json has no "one_thing"')
    hl = (E.get('one_thing_highlight') or '').strip()
    pre, q = (one.rsplit(':', 1) + [''])[:2] if ':' in one else ('', one)
    pre, q = pre.strip(), q.strip()
    quiet = (E.get('one_thing_lead') or (pre.rsplit(',', 1)[0] if ',' in pre else pre)).strip().rstrip(',;:—–- ')
    qtext = q[:1].upper() + q[1:]
    if hl and hl.lower() in qtext.lower():
        p = qtext.lower().index(hl.lower())
        line1, mark, tail = qtext[:p].rstrip(), qtext[p:p + len(hl)], qtext[p + len(hl):]
    else:
        if hl:
            ep.notes.append(f'one-thing: highlight {hl!r} is not in the question {q!r}; the last two words are marked')
        toks = qtext.split()
        line1, mark, tail = ' '.join(toks[:-2]), ' '.join(toks[-2:]), ''
    if not line1 and mark:
        # the highlight opens the question (or is all of it): line 1 takes its first words, the rest stays marked
        whole, line1, mark = mark, *lead_off(mark, tail)
        if line1:
            ep.notes.append(f'one-thing: the highlight {whole!r} starts the question, so line 1 is {line1!r} and the '
                            f'highlight marks {mark!r} on line 2; set one_thing_highlight to a later phrase to choose')
        else:
            ep.notes.append(f'one-thing: the highlight {whole!r} is the first word of the question; the question '
                            'shows on one line with that word marked')

    kicker = bt.add('kicker', W.w[0]['s'] if W else 0.14, 'first word')
    frags = balanced_chunks(quiet.split(), 2 if len(quiet) <= 44 else 3) if quiet else []
    if frags:
        frags[-1] = frags[-1] + ['—']  # the dash rides on the last fragment
    idx = align_tokens(W, [t for f in frags for t in f])
    quiet_cfg, k, last_idx = [], 0, None
    for f in frags:
        hits = [i for i in idx[k:k + len(f)] if i is not None]
        k += len(f)
        if hits:
            t = bt.add('quiet: ' + ' '.join(f), W.w[hits[0]]['s'] - 0.02, f'"{W.w[hits[0]]["t"]}"')
            last_idx = hits[-1]
        else:
            t = bt.add('quiet: ' + ' '.join(f), (quiet_cfg[-1]['at'] + 0.6) if quiet_cfg else kicker + 0.45, 'no spoken match')
        quiet_cfg.append({'text': ' '.join(f), 'at': t})
    qidx = [i for i in align_tokens(W, (line1 or mark).split(), start=(last_idx + 1) if last_idx is not None else 0)
            if i is not None]
    if last_idx is not None and last_idx + 1 < len(W.w):
        nudge = bt.add('nudge', W.w[last_idx + 1]['s'] + 0.02, f'"{W.w[last_idx + 1]["t"]}" (after the lead line)')
    else:
        nudge = bt.add('nudge', (W.w[qidx[0]]['s'] - 1.3) if qidx else 3.36, 'question − 1.3')
    l1 = bt.add('line 1', (W.w[qidx[0]]['s'] - 0.02) if qidx else nudge + 1.3, f'"{W.w[qidx[0]]["t"]}"' if qidx else 'fallback')
    mp = W.find_phrase(mark, after=l1) if mark else None
    if mp:
        l2 = bt.add('line 2', W.w[mp[0]]['s'] - 0.02, f'"{mark}"')
        h = bt.add('highlight', W.w[mp[0]]['s'] + 0.04, 'mark + 0.04')
        hd = r2(min(1.6, max(0.5, 0.77 * (W.w[mp[1]]['e'] - W.w[mp[0]]['s']))))
    else:
        l2 = bt.add('line 2', l1 + 1.12, 'fallback line 1 + 1.12')
        h, hd = r2(l2 + 0.06), 1.05
    return {
        'meta': ep.meta(),
        'kicker': E.get('one_thing_kicker') or 'One thing for your week',
        'quiet': quiet_cfg,
        'line1': line1, 'mark': mark, 'tail': tail,
        'beats': {'kicker': kicker, 'nudge': nudge, 'line1': l1, 'line2': l2, 'highlight': h, 'highlight_dur': hd},
    }


def build_close(ep, W, bt):
    E = ep.E
    K = len(ep.stories)
    other = len(ep.leads)
    n_src = ep.sources_captured()
    n_quotes = ep.quotes_located()
    counts = [['Leads reviewed', str(K + other)], ['Stories', str(K)]]
    if n_src is not None:
        counts.append(['Sources captured', str(n_src)])
    if n_quotes:
        counts.append(['Quotes located', str(n_quotes)])
    if E.get('captured'):
        counts.append(['Captured', E['captured']])
    stories = [{'num': s.get('n') or f'{i + 1:02d}', 'topic': s.get('topic') or f'Story {i + 1}',
                'badge': ep.badge(s.get('badge'), f'stories[{i}]'),
                'sources': [display_url(x.get('url', '')) for x in (s.get('sources') or []) if x.get('url')]}
               for i, s in enumerate(ep.stories)]
    title = bt.add('title', (W.w[0]['s'] + 0.02) if W else 0.08, 'first word')
    i = W.find(['source', 'sources'])
    if i is not None:
        j = i - 1 if i > 0 and W.w[i - 1]['n'] in ('every', 'all', 'each', 'the') else i
        rc = bt.add('receipt prints', W.w[j]['s'], f'"{W.w[j]["t"]}"')
    else:
        sents = W.sentences()
        rc = bt.add('receipt prints', W.w[sents[1][0]]['s'] if len(sents) > 1 else 1.4, 'second sentence')
    i = W.find(['leads'], after=rc)
    if i is not None:
        j = i
        while j > 0 and (W.w[j - 1]['n'] in ('other', 'more', 'remaining') or any(W.w[j - 1]['n'] in num_words(n) for n in range(0, 100))):
            j -= 1
        cta_a = bt.add('cta a', W.w[j]['s'] - 0.02, f'"{W.text(j, i)}"')
    else:
        cta_a = bt.add('cta a', rc + 1.1, 'fallback receipt + 1.1')
    i = W.find(['companion'], after=cta_a)
    cta_b = bt.add('cta b', (W.w[i]['s'] - 0.02) if i is not None else cta_a + 1.7, '"companion"' if i is not None else 'fallback')
    key = bt.add('badge key', cta_b + 0.4, 'cta b + 0.4')
    credits = ep.credits()
    if len(credits) > CLOSE_CREDITS:  # the receipt has room for CLOSE_CREDITS; the page and SOURCES.md list all
        ep.notes.append(f'close: {len(credits)} credits; the receipt prints the first {CLOSE_CREDITS} and '
                        f'"+{len(credits) - CLOSE_CREDITS} more"; all {len(credits)} are on the companion page and in '
                        f'SOURCES.md (put the ones the video must show first in "credits")')
    card_credits = []
    for c in credits[:CLOSE_CREDITS]:
        short, cut = short_credit(c)
        card_credits.append(short)
        if cut:
            ep.notes.append(f'close: credit {c!r} prints as {short!r} on the receipt (at most {CLOSE_CREDIT_CHARS} '
                            f'characters each); the companion page and SOURCES.md print it in full')
    return {
        'meta': ep.meta(),
        'eyebrow': E.get('title') or '',
        'title': E.get('close_title') or 'Every claim, shown on its source.',
        'cta': {'a': f'{other} more leads + every source' if other else 'Every source', 'b': '→ companion page'},
        'key_label': 'Badges',
        'receipt': {
            'wordmark': ep.meta()['show'],
            'edition_line': ' · '.join(x for x in (E.get('edition'), E.get('window')) if x),
            'number': f'No. {E["date"]}' if E.get('date') else '',
            'stories': stories,
            'counts': counts,
            'disclosure': ep.disclosure(),
            'credits': card_credits,
            'credits_more': max(0, len(credits) - CLOSE_CREDITS),
            'credit': ep.footer(),
        },
        'beats': {'title': title, 'receipt': rc, 'cta_a': cta_a, 'cta_b': cta_b, 'key': key},
    }


BUILDERS = {'squeeze': build_squeeze, 'payoff': build_payoff, 'one-thing': build_one_thing, 'close': build_close}


# ── main ─────────────────────────────────────────────────────────────────────────────────────────

def kind_of(sc):
    sid = sc.get('id', '')
    base = os.path.basename(sc.get('src', ''))
    for k in KINDS:
        if sid == k or re.fullmatch(rf'\d+-{re.escape(k)}\.html', base):
            return k
    return None


def main(argv):
    ap = argparse.ArgumentParser(description='Fill the squeeze, payoff, one-thing and close scenes from episode data.')
    ap.add_argument('episode')
    ap.add_argument('--only', default='', help='comma-separated kinds (squeeze,payoff,one-thing,close)')
    ap.add_argument('--dry-run', action='store_true', help='print the beat tables, write nothing')
    a = ap.parse_args(argv)
    root = os.path.abspath(a.episode)
    if os.path.basename(root) == 'video' and os.path.isfile(os.path.join(root, '..', 'edit', 'episode.json')):
        root = os.path.dirname(root)
    ep = Episode(root)
    only = {k.strip() for k in a.only.split(',') if k.strip()}
    scenes = ep.scenes.get('scenes') or []
    if not scenes:
        sys.exit('fill_scenes.py: video/scenes.json lists no scenes')
    accent = accent_of(ep.video)
    taken = set()
    prefixes = {sc['id']: prefix_for(sc['id'], taken) for sc in scenes}

    failed, written = [], []
    print(f'fill_scenes: {os.path.basename(root)} · accent {accent}')
    for sc in scenes:
        kind = kind_of(sc)
        if kind is None or (only and kind not in only):
            continue
        sid = sc['id']
        bt = Beats(f'{sid} ({kind}) → {sc["src"]}')
        try:
            W = Words(ep.words.get(sid))
            if not W and kind != 'close':
                raise RuntimeError(f'no word timings for "{sid}" in audio/scene-words.json (run voice.py first)')
            cfg = BUILDERS[kind](ep, W, bt)
            html = render(kind, sid, prefixes[sid], cfg, accent)
        except Exception as e:  # report and carry on with the other scenes
            failed.append(sid)
            print(f'  {sid}: FAILED — {e}')
            continue
        print(bt.table())
        if not a.dry_run:
            out = os.path.join(ep.video, sc['src'])
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, 'w', encoding='utf-8') as fh:
                fh.write(html)
            written.append(sc['src'])

    # what is left for other tools or for hand authoring
    receipt_ids = {(s.get('scenes') or {}).get('receipt') for s in ep.stories} - {None}
    boundary_ids = {(s.get('scenes') or {}).get('boundary') for s in ep.stories} - {None}
    todo = []
    for sc in scenes:
        if kind_of(sc):
            continue
        sid, path = sc['id'], sc.get('src', '')
        exists = os.path.isfile(os.path.join(ep.video, path))
        if sid in receipt_ids or sid.endswith('receipt'):
            how = 'HAND-AUTHOR from templates/scenes/receipt.html (bespoke ILLUSTRATION)'
        elif sid in boundary_ids or sid.endswith('boundary'):
            how = 'engine/boundary.py (spec in video/specs/)'
        elif sid.startswith('board'):
            how = 'engine/board.py'
        else:
            how = 'hand-author'
        todo.append(f'  {"exists " if exists else "MISSING"}  {sid:<16} {path:<34} {how}')
    if todo:
        print('not filled by this tool:')
        print('\n'.join(todo))
    if ep.notes:
        print('notes:')
        for n in dict.fromkeys(ep.notes):
            print(f'  - {n}')
    print(json.dumps({'written': written, 'failed': failed, 'dry_run': a.dry_run}))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
