#!/usr/bin/env python3
"""companion.py — build an episode's companion page: a static folder that works on GitHub Pages or any host.

usage: companion.py <episode_dir> <out_dir> [--video <name.mp4>] [--repo-url <url>] [--install "<line>"]

Reads edit/episode.json, video/audio/{timeline,cues}.json, video/scenes.json, ledger/{leads,claims,sources}.json,
ledger/capture-log.jsonl and the receipts (video/assets/receipts/ or ledger/receipts/ *.png + *.json).
Writes <out_dir>/index.html and receipts/*.jpg (the real capture, quote lines painted with the highlighter), and
copies deliver/<slug>-web.mp4 and deliver/poster.jpg in when they exist (deliver.py makes them). Every path in
the page is relative. No caption <track>: captions are burned into the video, VTT/SRT ship next to the master.

The page: player + chapters, the one thing, the claim/test matrix, each story with PROVES | DOESN'T PROVE and its
receipts, the other leads with badges, a click-to-seek transcript, "The receipt" (computed counts, the generated
disclosure line and, on its own line, every validated episode.json "credit" in "credits") and the badge legend; a
"Made with Said vs. Shown" footer when episode.json "credit" is true.
Every fact comes from episode.json, the ledger or the timeline.
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_NAME = 'Said vs. Shown'
DEFAULT_REPO = 'https://github.com/philipbankier/said-vs-shown'

# badge vocabulary: episode/ledger status -> canonical key -> label (rule: references/editorial.md)
BADGE_KEY = {'checked': 'checked', 'verified': 'checked', 'company': 'company', 'company_claim': 'company',
             'reported': 'reported', 'provider': 'provider', 'provider_only': 'provider',
             'older': 'older', 'older_background': 'older', 'unverifiable': 'unverified', 'unverified': 'unverified',
             'contradicted': 'contradicted'}
BADGE_WORD = {'checked': 'Checked', 'company': 'Company', 'reported': 'Reported', 'provider': 'Provider',
              'older': 'Older', 'unverified': 'Unverified', 'contradicted': 'Contradicted'}
BADGE_CLASS = {'checked': 'g-checked', 'company': 'g-company', 'reported': 'g-reported', 'provider': 'g-provider',
               'older': 'g-older', 'unverified': 'g-provider', 'contradicted': 'g-provider'}


def warn(msg):
    print(f'companion.py: warning: {msg}', file=sys.stderr)


def config():
    p = os.path.join(HERE, 'config.json')
    if os.path.isfile(p):
        with open(p, encoding='utf-8') as fh:
            return json.load(fh)
    return {}


def read_json(path, default=None):
    if not os.path.isfile(path):
        if default is not None:
            return default
        sys.exit(f'companion.py: missing {path}')
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def load_episode(ep_dir):
    return read_json(os.path.join(ep_dir, 'edit', 'episode.json'))


def slugify(s):
    return re.sub(r'[^a-z0-9]+', '-', str(s).lower()).strip('-')


def slug_of(E):
    return E.get('slug') or slugify('-'.join(str(x) for x in (E.get('show') or TOOL_NAME, E.get('edition'), E.get('date')) if x))


def badge_key(status):
    return BADGE_KEY.get(str(status or '').lower(), 'reported')


def lead_badge_key(lead, overrides):
    o = (overrides or {}).get(str(lead.get('lead_id')))
    return badge_key(o) if o else badge_key(lead.get('status'))


def lead_sort_key(lead):
    lid = str(lead.get('lead_id', ''))
    return (0, int(lid), '') if lid.isdigit() else (1, 0, lid)


def lead_num(lead):
    lid = str(lead.get('lead_id', ''))
    return f'{int(lid):02d}' if lid.isdigit() else lid


def capture_log(ep_dir):
    p = os.path.join(ep_dir, 'ledger', 'capture-log.jsonl')
    rows = []
    if os.path.isfile(p):
        with open(p, encoding='utf-8') as fh:
            for line in fh:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def sources_map(ep_dir):
    """id -> url, from ledger/sources.json (falls back to capture-log.jsonl)."""
    src = read_json(os.path.join(ep_dir, 'ledger', 'sources.json'), default=[])
    if src:
        return {s['id']: s['url'] for s in src}
    return {r['id']: r['url'] for r in capture_log(ep_dir) if 'id' in r and 'url' in r}


def captured_count(ep_dir):
    """Sources whose capture succeeded (capture-log.jsonl "ok"); falls back to the size of sources.json."""
    rows = capture_log(ep_dir)
    if rows:
        ok = set()
        for r in rows:
            good = r.get('ok', (r.get('result') or {}).get('ok'))
            if good:
                ok.add(r.get('id') or r.get('url'))
        return len(ok)
    return len(sources_map(ep_dir))


def claims_traced(ep_dir):
    """Story claims that carry a verbatim source quote (ledger/claims.json)."""
    n = 0
    for story in read_json(os.path.join(ep_dir, 'ledger', 'claims.json'), default=[]):
        led = story.get('ledger', story)
        n += sum(1 for c in led.get('claims', []) if str(c.get('quote') or '').strip())
    return n


def mmss(t):
    return f'{int(t // 60)}:{int(t % 60):02d}'


def window_short(window):
    """'Oct 5–8, 2026' -> 'Oct 5–8' (the year is implied on the page)."""
    return re.sub(r',?\s*\d{4}\s*$', '', str(window or '')).strip()


def chapters_of(E, scenes, tl, need_zero=False):
    """[(start_seconds, label)] from episode.json "chapters" {scene_id: label}; falls back to each story's first scene."""
    bounds = [0.0] + list(tl.get('cuts', []))
    start = {s['id']: bounds[i] for i, s in enumerate(scenes) if i < len(bounds)}
    ch = E.get('chapters')
    if not ch:
        ch = {}
        for s in E.get('stories', []):
            ids = list((s.get('scenes') or {}).values())
            if ids:
                ch[ids[0]] = f"{s.get('n', '')} · {s.get('topic', '')}".strip(' ·')
    out = []
    for sid, label in ch.items():
        if sid in start:
            out.append((start[sid], label))
        else:
            warn(f'chapter scene {sid!r} is not in scenes.json; skipped')
    out.sort()
    if need_zero and (not out or out[0][0] > 0) and scenes:
        out.insert(0, (0.0, 'Intro'))
    return out


def receipt_paths(ep_dir, name):
    for d in (os.path.join(ep_dir, 'video', 'assets', 'receipts'), os.path.join(ep_dir, 'ledger', 'receipts')):
        if os.path.isfile(os.path.join(d, name + '.json')):
            return os.path.join(d, name + '.json'), os.path.join(d, name + '.png')
    return None, None


def crop(ep_dir, out, name):
    """Receipt crop: the real capture, quote lines painted with the series' highlighter. None if no capture."""
    jp, png = receipt_paths(ep_dir, name)
    if not jp or not os.path.isfile(png):
        warn(f'receipt {name}: no capture (.png/.json) in video/assets/receipts or ledger/receipts; quote shown without image')
        return None
    j = read_json(jp)
    ls = j.get('lines') or []
    if not ls:
        warn(f'receipt {name}: no quote lines in {jp}; quote shown without image')
        return None
    x0 = max(0, min(l['x'] for l in ls) - 40); x1 = min(1440, max(l['x'] + l['w'] for l in ls) + 40)
    y0 = max(0, min(l['y'] for l in ls) - 60); y1 = min(900, max(l['y'] + l['h'] for l in ls) + 60)
    x0, x1 = min(x0, 140), max(x1, 1000)
    boxes = ','.join(f"drawbox=x={(l['x'] - 3 - x0) * 2}:y={(l['y'] - 3 - y0) * 2}:w={(l['w'] + 6) * 2}:h={(l['h'] + 6) * 2}:color=0xF2C14E@0.38:t=fill" for l in ls)
    dst = os.path.join(out, 'receipts', f'{name}.jpg')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', png,
                    '-vf', f"crop={(x1 - x0) * 2}:{(y1 - y0) * 2}:{x0 * 2}:{y0 * 2},{boxes},scale=1200:-2", '-q:v', '4', dst], check=True)
    return f'receipts/{name}.jpg'


def esc(s):
    return html.escape(str(s))


def badge(key):
    return f'<span class="badge"><span class="glyph {BADGE_CLASS[key]}"></span>{BADGE_WORD[key]}</span>'


def install_line(repo_url):
    """The page's install line: `npx skills add owner/repo` works for Claude Code and the other Agent Skills agents."""
    m = re.match(r'https?://github\.com/([^/]+/[^/#?]+)', repo_url or '')
    if not m:
        return f'git clone {repo_url}'
    repo = m.group(1)
    return f'npx skills add {repo[:-4] if repo.endswith(".git") else repo}'


DISCLOSURE_PARTS = ('AI-produced', 'AI voice', 'every claim sourced')
DISCLOSURE_BASE = ' · '.join(DISCLOSURE_PARTS)
UNREVIEWED = 'not yet human-reviewed'

# reviewed_by is a person's name: 1-5 words of Latin-script letters (diacritics included) with . ' ’ - inside a word,
# at most 60 characters, every word capitalised except name particles ("de la", "van", "al-"). Letters that read as a
# separator ("Sam ꞏ Fact-Checked ꞏ Legal") are never name letters, and neither is any letter of another script.
SEPARATOR_LIKE = frozenset('ꞏㆍᐧǀǁǂǃːˑ')  # ꞏ ㆍ ᐧ ǀ ǁ ǂ ǃ ː ˑ
NAME_INNER = frozenset(".-'’ʼʻ")  # period, hyphen and apostrophes (’ ʼ ʻ as in O’Neil, Kaʻiulani)
NAME_PARTICLES = {'de', 'da', 'das', 'del', 'della', 'der', 'den', 'des', 'di', 'do', 'dos', 'du', 'la', 'le', 'van',
                  'von', 'zu', 'ter', 'ten', 'bin', 'ibn', 'al', 'el', 'y', 'e', 'af', 'av'}
PARTICLE_PREFIX = re.compile(r"(?:al|el|ad|ar|as|at|d|l|da|de|di|du)['’-][^\W\d_].*")
# credits: "<label>: <value>", the label from this list only, the value one plain phrase (no separators, no markup)
CREDIT_LABELS = ('music', 'sfx', 'footage', 'images', 'translation', 'data')
CREDIT = re.compile(r'(%s) ?: ?([\w .,\'’&()/+:#@%%!?"“”–-]{1,80})' % '|'.join(CREDIT_LABELS), re.I)
CLOSE_CREDITS = 3  # the close card's receipt prints at most this many credits (all of them: the page, SOURCES.md)
CLOSE_CREDIT_CHARS = 64  # and each in at most this many characters, so the worst case (3 stories, a 60-character
                         # reviewer name, 3 credits) ends at y = 1040 of 1080 (measured in Chrome with IBM Plex Mono)
# a credit that says a person reviewed, checked, approved or verified something (P4): warned, still printed
REVIEW_CLAIM = re.compile(r"(?<![^\W\d_])(?:re-?view|peer[- ]?review|fact[- ]?check|approv|verif|vett|validat|"
                          r"audit|proof-?read|sign(?:ed)?[- ]?off|(?:double[- ]|cross[- ])?checked|confirm|endors)",
                          re.I)
BOOL_WORDS = {'true': True, 'yes': True, 'on': True, '1': True, 'false': False, 'no': False, 'off': False, '0': False,
              'none': False, 'null': False, '': False}


def latin_letter(ch):
    """A cased letter of the Latin script (upper/lower/title case, with or without diacritics). Caseless "letters"
    (category Lo/Lm, e.g. ꟷ ʔ) are refused: several of them read as separators."""
    return (unicodedata.category(ch) in ('Lu', 'Ll', 'Lt') and ch not in SEPARATOR_LIKE
            and unicodedata.name(ch, '').startswith('LATIN '))


def name_word(w):
    """One word of a name: a Latin letter, then Latin letters, . - ' ’ ʼ ʻ, or combining diacritics after a letter."""
    if not w or not latin_letter(w[0]):
        return False
    for prev, ch in zip(w, w[1:]):
        if latin_letter(ch) or ch in NAME_INNER:
            continue
        if '̀' <= ch <= 'ͯ' and ch != '͏' and (latin_letter(prev) or '̀' <= prev <= 'ͯ'):
            continue
        return False
    return True


def is_name(s):
    """True for what reads as a person's name ("Jane Doe", "Dr. Lee", "Mary-Ann O'Neil", "Ana de la Cruz",
    "José Núñez"): Latin-script letters only (NFC; diacritics welcome), spaces, hyphen, apostrophe and period. A name
    in another script is written in its Latin form; a letter that looks like a separator (ꞏ ㆍ ᐧ ǀ ǃ ː ˑ) is refused."""
    s = unicodedata.normalize('NFC', s)
    words = s.split(' ')
    if not 1 <= len(words) <= 5 or len(s) > 60 or not all(name_word(w) for w in words):
        return False

    def capital(w):
        return w[0].isupper() or not w[0].islower()  # a caseless Latin letter (ʔ) counts as capital

    def particle(w):
        return w.lower() in NAME_PARTICLES or bool(PARTICLE_PREFIX.fullmatch(w))
    return all(capital(w) or particle(w) for w in words) and any(capital(w) for w in words)


def _say(warn_to, msg):
    if warn_to is not None:
        print(f'said-vs-shown: warning: {msg}', file=warn_to)


def reviewer_of(E, warn_to=None):
    """The name episode.json "reviewed_by" records (stage 10), NFC-normalised, or None: unset, or not a name (is_name),
    which is named in a warning on warn_to and counts as not reviewed."""
    raw = E.get('reviewed_by')
    name = unicodedata.normalize('NFC', ' '.join(str(raw or '').split()))
    if not name:
        return None
    if not is_name(name):
        _say(warn_to, f'reviewed_by {raw!r} ignored: it must be the reviewer\'s name (capitalised words of Latin letters, '
                      f'diacritics allowed, and . \' - only, at most 5 words and 60 characters; a name in another script '
                      f'in its Latin form); the disclosure says "{UNREVIEWED}"')
        return None
    return name


def _credit_field(E):
    """episode.json "credit" read as (footer switch or None when unset, credit texts it holds, warning or None).
    "credit" is the true/false switch for the "Made with" footer; "credits" holds the credits. A "credit" holding
    text or a list was meant for "credits": the texts are returned (credits_of reads them) and the footer stays on."""
    raw = E.get('credit')
    if raw is None or isinstance(raw, bool):
        return raw, [], None
    if isinstance(raw, (int, float)) and raw in (0, 1):
        return bool(raw), [], f'episode.json "credit" {raw!r} read as {str(bool(raw)).lower()}: write true or false'
    if isinstance(raw, str) and raw.strip().lower() in BOOL_WORDS:
        on = BOOL_WORDS[raw.strip().lower()]
        return on, [], f'episode.json "credit" {raw!r} read as {str(on).lower()}: write true or false, without quotes'
    if isinstance(raw, (list, dict)) and not raw:
        return False, [], f'episode.json "credit" {raw!r} read as false: write true or false'
    items = [raw] if isinstance(raw, str) else list(raw) if isinstance(raw, list) else [raw]
    return True, items, (f'episode.json "credit" HOLDS {raw!r}, BUT "credit" IS ONLY THE true/false SWITCH for the '
                         f'"Made with {TOOL_NAME}" footer. Read as "credits" (rename the field to "credits"); the '
                         f'footer stays on.')


def credit_footer(E, default, warn_to=None):
    """Whether the "Made with Said vs. Shown" footer prints: episode.json "credit" when it is true or false, default
    when it is unset. A "credit" written as "false"/"no"/0 (or "true"/"yes"/1) is read as that boolean with a warning;
    one holding credits text keeps the footer on (credits_of warns and moves the text to "credits")."""
    on, items, msg = _credit_field(E)
    if msg and not items:
        _say(warn_to, msg)
    return default if on is None else on


def _legacy_segments(E):
    """The segments of the legacy episode.json "disclosure" field, whitespace-normalised."""
    return [seg for seg in (' '.join(x.split()) for x in str(E.get('disclosure') or '').split('·')) if seg]


def credits_of(E, warn_to=sys.stderr):
    """The episode's third-party credits as normalised "<label>: <value>" strings ("music: CC0 loops by Kevin
    MacLeod"), label one of CREDIT_LABELS (any case): episode.json "credits", then credits text written in "credit" by
    mistake (that field is the footer switch; warned loudly and read as credits), then legacy "disclosure" segments
    that are allowlisted credits ("music: …"), migrated with a warning. Duplicates (any case) are dropped. Anything
    else is dropped with a warning on warn_to (None: silent); a separator-like letter (ꞏ ǀ ː …) in the value counts as
    a separator. A credit that mentions a review, fact-check, approval or verification is kept, with a warning: the
    line is labelled "Credits", and only "reviewed_by" records a review. Credits print on their own "Credits" line
    (credits_line), never in the disclosure line; the close card prints at most CLOSE_CREDITS of them."""
    raw = E.get('credits')
    items = [] if raw in (None, '', []) else [raw] if isinstance(raw, str) else list(raw) if isinstance(raw, list) else None
    if items is None:
        _say(warn_to, f'credits {raw!r} ignored: write a list of "<label>: <value>" ({", ".join(CREDIT_LABELS)})')
        items = []
    _, from_credit, msg = _credit_field(E)
    if from_credit:
        _say(warn_to, msg)
    legacy = [seg for seg in _legacy_segments(E) if CREDIT.fullmatch(seg)]
    if legacy:
        _say(warn_to, f'episode.json "disclosure" holds {" · ".join(legacy)!r}: moved to the Credits line. The disclosure '
                      f'line is generated; write credits in "credits", e.g. ["music: CC0 loops by <artist>"].')
    out, seen = [], set()
    for item in items + from_credit + legacy:
        s = ' '.join(item.split()) if isinstance(item, str) else ''
        m = CREDIT.fullmatch(s) if s else None
        if not m or any(ch in SEPARATOR_LIKE for ch in s):
            _say(warn_to, f'credit {item!r} dropped: write "<label>: <value>" with a label from {", ".join(CREDIT_LABELS)} '
                          f'and a plain value (at most 80 characters, no · | ; or markup)')
            continue
        credit = f'{m.group(1).lower()}: {m.group(2).strip()}'
        if credit.lower() in seen:
            continue
        seen.add(credit.lower())
        if REVIEW_CLAIM.search(m.group(2)):
            _say(warn_to, f'credit {credit!r} mentions a review, fact-check, approval or verification. "Credits" credit '
                          f'third-party media and data; they never record that a person reviewed the episode (only '
                          f'"reviewed_by" does, stage 10). It still prints, on the line labelled "Credits".')
        out.append(credit)
    return out


def credits_line(credits):
    """The "Credits" line for the page, or '' when there are none (the close card builds the same line from at most
    CLOSE_CREDITS of them, then "+N more")."""
    return ('Credits: ' + ' · '.join(credits)) if credits else ''


def disclosure_parts(E, warn_to=None):
    """The disclosure's segments: the fixed parts (AI-produced · AI voice · every claim sourced), then the one
    generated review segment, "reviewed by <reviewed_by>" when reviewer_of(E) has a name, else "not yet
    human-reviewed". Nothing from episode.json "disclosure" ever enters it: when that legacy field holds anything
    beyond these segments it is ignored, with a warning that points to "credits"; a segment that is an allowlisted
    credit ("music: …") moves to the Credits line instead (credits_of, which warns about it)."""
    reviewer = reviewer_of(E, warn_to)
    generated = f'reviewed by {reviewer}' if reviewer else UNREVIEWED
    known = {x.lower() for x in DISCLOSURE_PARTS} | {UNREVIEWED, generated.lower()}
    extra = [seg for seg in _legacy_segments(E) if seg.lower() not in known and not CREDIT.fullmatch(seg)]
    if extra:
        _say(warn_to, f'episode.json "disclosure" text {" · ".join(extra)!r} ignored: the disclosure line is generated '
                      f'("{DISCLOSURE_BASE} · reviewed by <reviewed_by>"). Put third-party credits in "credits", e.g. '
                      f'["music: CC0 loops by <artist>"] (labels: {", ".join(CREDIT_LABELS)}); a review is recorded '
                      f'only by "reviewed_by" (stage 10).')
    return list(DISCLOSURE_PARTS) + [generated]


def disclosure_of(E, warn_to=sys.stderr):
    """The one disclosure line for the video (fill_scenes.py close), the page and deliver.py (frame.md → Disclosure
    line format): fixed parts plus the generated review segment (disclosure_parts). User free text never enters it;
    whatever is ignored is named in a warning on warn_to (None: silent)."""
    return ' · '.join(disclosure_parts(E, warn_to))


def build(ep_dir, out, video_name=None, repo_url=None, install=None):
    E = load_episode(ep_dir)
    V = os.path.join(ep_dir, 'video')
    tl = read_json(os.path.join(V, 'audio', 'timeline.json'))
    cues = read_json(os.path.join(V, 'audio', 'cues.json'))
    scenes = read_json(os.path.join(V, 'scenes.json'))['scenes']
    leads = read_json(os.path.join(ep_dir, 'ledger', 'leads.json'), default=[])
    srcmap = sources_map(ep_dir)
    stories = E.get('stories', [])
    show = E.get('show') or TOOL_NAME
    slug = slug_of(E)
    video_name = video_name or f'{slug}-web.mp4'
    cfg = config()
    repo_url = repo_url or cfg.get('repo_url') or DEFAULT_REPO
    install = install or cfg.get('install') or install_line(repo_url)
    os.makedirs(os.path.join(out, 'receipts'), exist_ok=True)

    # media: copy the web cut and poster from deliver/ when the page is built elsewhere
    deliver = os.path.join(ep_dir, 'deliver')
    for name in (video_name, 'poster.jpg'):
        src, dst = os.path.join(deliver, name), os.path.join(out, name)
        if os.path.isfile(src):
            if os.path.abspath(src) != os.path.abspath(dst):
                shutil.copy2(src, dst)
        elif not os.path.isfile(dst):
            warn(f'{name} not found in {deliver} (run deliver.py); the page references it')

    chapters = chapters_of(E, scenes, tl)

    stories_html = []
    for s in stories:
        rec = []
        for r in s.get('receipts', []):
            src = crop(ep_dir, out, r['img'])
            img = f'<img src="{src}" alt="Capture: {esc(r["quote"])}" loading="lazy">' if src else ''
            rec.append(f'''<figure class="receipt">{img}<figcaption><span class="mono">{esc(r['source'])} · captured {esc(E.get('captured', ''))}</span><q>{esc(r['quote'])}</q></figcaption></figure>''')
        srcs = ''.join(f'<li><a href="{esc(x["url"])}" target="_blank" rel="noopener">{esc(x["label"])}</a> <span class="url">{esc(re.sub(r"^https?://", "", x["url"]))}</span></li>' for x in s.get('sources', []))
        note = f'<p class="note">{esc(s["note"])}</p>' if s.get('note') else ''
        stories_html.append(f'''
  <section class="story" id="story-{esc(s['n'])}">
    <div class="kicker mono"><span class="num">{esc(s['n'])}</span><span class="topic">{esc(s['topic'])}</span>{badge(badge_key(s.get('badge')))}<span>{esc(s.get('date', ''))}</span></div>
    <h2>{esc(s['headline'])}</h2>
    <p class="lede">{esc(s['happened'])}</p>
    <div class="boundary">
      <div class="col"><h3 class="mono accent">Proves</h3><ul>{''.join(f"<li>{esc(x)}</li>" for x in s.get('proves', []))}</ul></div>
      <div class="col"><h3 class="mono">Doesn't prove</h3><ul class="nots">{''.join(f"<li>{esc(x)}</li>" for x in s.get('not', []))}</ul></div>
    </div>
    {f'<div class="receipts">{"".join(rec)}</div>' if rec else ''}
    {note}
    <ul class="sources">{srcs}</ul>
  </section>''')

    overrides = E.get('lead_badge_overrides') or {}
    lead_cards = []
    for l in sorted(leads, key=lead_sort_key):
        urls = [srcmap[sid] for sid in l.get('source_ids', []) if sid in srcmap]
        url = urls[0] if urls else ''
        link = (f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(re.sub(r"^https?://", "", url).split("/")[0])}</a>'
                if url else '<span class="url">no primary link</span>')
        lead_cards.append(f'''<article class="lead"><div class="lead-top mono"><span class="num">{esc(lead_num(l))}</span>{badge(lead_badge_key(l, overrides))}</div>
      <h4>{esc(l['title'])}</h4><p class="date mono">{esc(l.get('date', ''))}</p><p>{esc(l.get('one_liner', ''))}</p>{f'<p class="caution">{esc(l["caution"])}</p>' if l.get('caution') else ''}<p class="src">{link}</p></article>''')

    one = esc(E.get('one_thing', ''))
    hi = E.get('one_thing_highlight')
    if hi:
        if esc(hi) in one:
            one = one.replace(esc(hi), f'<mark>{esc(hi)}</mark>', 1)
        else:
            warn('one_thing_highlight is not a substring of one_thing; nothing highlighted')

    matrix_rows = E.get('matrix') or [[s.get('topic', ''), s.get('test', '')] for s in stories]
    transcript = ''.join(f'<button class="cue" data-t="{c["start"]:.2f}" type="button"><span class="ts mono">{mmss(c["start"])}</span>{esc(c["text"])}</button>' for c in cues)
    chap = ''.join(f'<button class="chap" data-t="{t:.2f}" type="button"><span class="ts mono">{mmss(t)}</span>{esc(n)}</button>' for t, n in chapters)
    matrix = ''.join(f'<div class="mrow"><span class="mi mono">{i + 1:02d}</span><span class="claim">{esc(a)}</span><span class="test">{esc(b)}</span></div>' for i, (a, b) in enumerate(matrix_rows))
    duration = mmss(tl['total'])
    captured = E.get('captured', '')
    counts = {
        'leads': len(leads) + len(stories),
        'stories': len(stories),
        'sources': captured_count(ep_dir),
        'claims': claims_traced(ep_dir),
    }
    win = window_short(E.get('window'))
    leads_head = f'{len(leads)} more lead{"" if len(leads) == 1 else "s"}' + (f' from {esc(win)}' if win else '') + ' · not in the video'
    leads_html = (f'''<section aria-label="Other leads"><h2 class="sec">{leads_head}</h2>
    <div class="leads">{''.join(lead_cards)}</div>
  </section>''' if leads else '')
    disclosure = f'<p class="disc">{esc(disclosure_of(E))}</p>'
    cred = credits_line(credits_of(E))
    disclosure += f'\n      <p class="credits">{esc(cred)}</p>' if cred else ''
    footer = (f'''<footer class="credit">
    <span class="mono">Made with <a href="{esc(repo_url)}">{TOOL_NAME}</a></span>
    <a class="url" href="{esc(repo_url)}">{esc(re.sub(r"^https?://", "", repo_url))}</a>
    <code class="install">{esc(install)}</code>
  </footer>''' if credit_footer(E, False, sys.stderr) else '')
    strip = ''.join(f'<span>{x}</span>' for x in (
        f'<b>{esc(show)}</b>' + (f' · {esc(E["edition"])}' if E.get('edition') else ''),
        esc(E.get('window', '')), f'{duration} video', f'sources captured {esc(captured)}' if captured else '') if x)
    title = ' · '.join(x for x in (E.get('title'), show) if x)

    page = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(E.get('thesis', ''))}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Newsreader:opsz,wght@6..72,300;6..72,500;6..72,700&display=swap">
<style>
/* Layout: one reading column (~68ch) under a full-width player; the dashed amber "evidence boundary" splits every PROVES | DOESN'T PROVE. */
:root {{
  --ink: #14130f; --ink-2: #1c1a15; --line: #3a352c; --paper: #eee8dc; --muted: #a59d8d; --accent: #f2c14e; --accent-ink: #f2c14e; --hl: rgba(242,193,78,.22);
  --serif: "Newsreader", Georgia, "Times New Roman", serif; --mono: "IBM Plex Mono", ui-monospace, Menlo, monospace;
  color-scheme: dark;
}}
@media (prefers-color-scheme: light) {{ :root:not([data-theme="dark"]) {{ --ink: #f4efe4; --ink-2: #ebe4d6; --line: #cfc5b2; --paper: #1d1b16; --muted: #5f584b; --accent: #b98a12; --accent-ink: #8a6406; --hl: rgba(242,193,78,.35); color-scheme: light; }} }}
:root[data-theme="light"] {{ --ink: #f4efe4; --ink-2: #ebe4d6; --line: #cfc5b2; --paper: #1d1b16; --muted: #5f584b; --accent: #b98a12; --accent-ink: #8a6406; --hl: rgba(242,193,78,.35); color-scheme: light; }}
* {{ box-sizing: border-box; }}
body {{ background: var(--ink); color: var(--paper); font-family: var(--serif); font-size: 18px; line-height: 1.55; margin: 0; }}
.wrap {{ max-width: 1080px; margin: 0 auto; padding-inline: 20px; padding-block: 28px 80px; display: flex; flex-direction: column; gap: 56px; }}
.mono {{ font-family: var(--mono); text-transform: uppercase; letter-spacing: .08em; font-size: 13px; }}
.accent {{ color: var(--accent-ink); }}
a {{ color: var(--paper); text-decoration-color: var(--accent); text-underline-offset: 3px; }}
a:focus-visible, button:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
header {{ display: flex; flex-direction: column; gap: 14px; }}
.strip {{ display: flex; flex-wrap: wrap; gap: 10px 18px; color: var(--muted); }}
.strip b {{ color: var(--accent-ink); font-weight: 600; }}
h1 {{ font-weight: 300; font-size: clamp(38px, 6vw, 64px); line-height: 1.04; letter-spacing: -.025em; margin: 0; text-wrap: balance; }}
.thesis {{ font-size: 21px; max-width: 62ch; margin: 0; color: var(--paper); }}
.player {{ display: flex; flex-direction: column; gap: 14px; }}
video {{ width: 100%; aspect-ratio: 16 / 9; background: #000; border: 1px solid var(--line); border-radius: 10px; display: block; }}
.chapters {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.chap, .cue {{ font: inherit; color: inherit; background: none; border: 1px solid var(--line); border-radius: 6px; padding: 6px 10px; cursor: pointer; display: inline-flex; gap: 10px; align-items: baseline; text-align: left; }}
.chap {{ font-size: 15px; }}
.chap:hover, .cue:hover {{ border-color: var(--accent); }}
.ts {{ color: var(--accent-ink); font-size: 12px; }}
.onething {{ border-left: 0; padding: 26px 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }}
.onething p {{ font-size: clamp(26px, 3.6vw, 38px); font-weight: 300; line-height: 1.2; margin: 10px 0 0; max-width: 30ch; }}
.onething mark {{ background: var(--hl); color: inherit; padding: 0 .1em; font-weight: 700; }}
.matrix {{ display: flex; flex-direction: column; gap: 0; }}
.mhead, .mrow {{ display: grid; grid-template-columns: 44px 1fr 1fr; gap: 0 20px; align-items: baseline; padding: 14px 0; border-bottom: 1px solid var(--line); }}
.mhead {{ color: var(--muted); }}
.mrow .claim, .mrow .test {{ font-size: 24px; }}
.mrow .test {{ padding-left: 20px; border-left: 2px dashed var(--accent); font-weight: 300; }}
.mhead span:last-child {{ padding-left: 22px; }}
.mi {{ color: var(--accent-ink); }}
.story {{ display: flex; flex-direction: column; gap: 18px; scroll-margin-top: 20px; }}
.kicker {{ display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; color: var(--muted); }}
.kicker .num, .lead .num {{ color: var(--accent-ink); font-weight: 600; }}
.kicker .topic {{ color: var(--paper); font-weight: 600; }}
.badge {{ display: inline-flex; gap: 8px; align-items: center; }}
.glyph {{ width: 11px; height: 11px; border: 2px solid var(--paper); display: inline-block; }}
.g-checked {{ background: var(--paper); }}
.g-company {{ background: linear-gradient(90deg, var(--paper) 50%, transparent 50%); }}
.g-reported {{ background: transparent; }}
.g-provider {{ border-style: dashed; border-color: var(--muted); }}
.g-older {{ border-color: var(--muted); }}
h2 {{ font-weight: 500; font-size: clamp(26px, 3.4vw, 36px); line-height: 1.15; letter-spacing: -.015em; margin: 0; text-wrap: balance; max-width: 30ch; }}
.lede {{ margin: 0; max-width: 68ch; }}
.boundary {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }}
.boundary .col {{ padding: 16px 0; min-width: 0; }}
.boundary .col + .col {{ border-left: 2px dashed var(--accent); padding-left: 22px; }}
.boundary .col:first-child {{ padding-right: 22px; }}
.boundary h3 {{ margin: 0 0 8px; color: var(--muted); }}
.boundary h3.accent {{ color: var(--accent-ink); }}
.boundary ul {{ margin: 0; padding-left: 18px; display: flex; flex-direction: column; gap: 6px; }}
.receipts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }}
.receipt {{ margin: 0; display: flex; flex-direction: column; gap: 8px; min-width: 0; }}
.receipt img {{ width: 100%; height: auto; border: 1px solid var(--line); border-radius: 8px; display: block; background: #fff; }}
.receipt figcaption {{ display: flex; flex-direction: column; gap: 4px; color: var(--muted); font-size: 15px; }}
.receipt q {{ color: var(--paper); font-style: italic; }}
.note {{ margin: 0; color: var(--muted); font-size: 16px; max-width: 72ch; }}
.sources {{ margin: 0; padding-left: 18px; font-size: 16px; display: flex; flex-direction: column; gap: 4px; }}
.url {{ font-family: var(--mono); font-size: 12px; color: var(--muted); word-break: break-all; }}
.leads {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 14px; }}
.lead {{ border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; display: flex; flex-direction: column; gap: 6px; background: var(--ink-2); min-width: 0; }}
.lead-top {{ display: flex; justify-content: space-between; color: var(--muted); }}
.lead h4 {{ margin: 0; font-weight: 500; font-size: 20px; line-height: 1.2; }}
.lead p {{ margin: 0; font-size: 15px; }}
.lead .date {{ color: var(--muted); }}
.lead .caution {{ color: var(--muted); font-style: italic; }}
.lead .src a {{ font-family: var(--mono); font-size: 12px; }}
.transcript {{ display: flex; flex-direction: column; gap: 6px; max-height: 520px; overflow-y: auto; padding-right: 6px; }}
.cue {{ border-color: transparent; font-size: 17px; width: 100%; }}
.cue.on {{ border-color: var(--accent); background: var(--hl); }}
.facts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }}
.label {{ border: 2px solid var(--paper); padding: 12px 16px; font-family: var(--mono); font-size: 14px; align-self: start; }}
.label h3 {{ font-family: var(--serif); font-weight: 700; font-size: 26px; margin: 0 0 6px; text-transform: none; letter-spacing: 0; }}
.label .row {{ display: flex; justify-content: space-between; gap: 12px; border-top: 1px solid var(--line); padding: 6px 0; }}
.label .disc {{ margin: 0; border-top: 2px solid var(--paper); padding-top: 8px; color: var(--muted); font-size: 13px; line-height: 1.5; }}
.label .credits {{ margin: 6px 0 0; color: var(--muted); font-size: 13px; line-height: 1.5; }}
.legend {{ display: flex; flex-direction: column; gap: 10px; font-size: 16px; }}
.legend div {{ display: grid; grid-template-columns: 120px 1fr; gap: 12px; align-items: baseline; }}
section > h2.sec {{ font-family: var(--mono); font-size: 13px; text-transform: uppercase; letter-spacing: .1em; color: var(--accent-ink); font-weight: 600; margin: 0 0 16px; }}
.credit {{ display: flex; flex-wrap: wrap; gap: 8px 18px; align-items: baseline; border-top: 1px solid var(--line); padding-top: 18px; color: var(--muted); }}
.credit .install {{ font-family: var(--mono); font-size: 13px; color: var(--paper); background: var(--ink-2); border: 1px solid var(--line); border-radius: 6px; padding: 4px 8px; overflow-wrap: anywhere; }}
@media (max-width: 640px) {{
  .boundary {{ grid-template-columns: 1fr; }}
  .boundary .col + .col {{ border-left: 0; border-top: 2px dashed var(--accent); padding-left: 0; }}
  .mhead, .mrow {{ grid-template-columns: 32px 1fr; }}
  .mrow .test {{ grid-column: 2; border-left: 0; padding-left: 0; color: var(--accent-ink); }}
  .mhead span:last-child {{ display: none; }}
}}
@media (prefers-reduced-motion: reduce) {{ * {{ scroll-behavior: auto !important; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="strip mono">{strip}</div>
    <h1>{esc(E.get('title', ''))}</h1>
    <p class="thesis">{esc(E.get('thesis', ''))}</p>
  </header>

  <section class="player" aria-label="Video">
    <video id="v" controls playsinline preload="metadata" poster="poster.jpg">
      <source src="{esc(video_name)}" type="video/mp4">
    </video>
    <div class="chapters">{chap}</div>
  </section>

  <section class="onething"><div class="mono accent">One thing for your week</div><p>{one}</p></section>

  <section aria-label="The test that fits"><h2 class="sec">The test that fits the claim</h2>
    <div class="matrix"><div class="mhead mono"><span></span><span>Claim</span><span>Test that fits</span></div>{matrix}</div>
  </section>
{''.join(stories_html)}

  {leads_html}

  <section aria-label="Transcript"><h2 class="sec">Transcript · tap a line to jump</h2><div class="transcript" id="tr">{transcript}</div></section>

  <section class="facts" aria-label="The receipt">
    <div class="label"><h3>The receipt</h3>
      <div class="row"><span>Leads reviewed</span><span>{counts['leads']}</span></div>
      <div class="row"><span>Stories</span><span>{counts['stories']}</span></div>
      <div class="row"><span>Sources captured</span><span>{counts['sources']}{f' · {esc(captured)}' if captured else ''}</span></div>
      <div class="row"><span>Claims traced to a quote</span><span>{counts['claims']}</span></div>
      {disclosure}
    </div>
    <div class="legend"><h2 class="sec">Badges</h2>
      <div>{badge('checked')}<span>The headline fact is visible in a primary source: a published artifact, a dated release entry, a signed agreement.</span></div>
      <div>{badge('company')}<span>The headline rests on the company's or authors' own account of capability or results.</span></div>
      <div>{badge('reported')}<span>Only secondary reporting was found.</span></div>
      <div>{badge('provider')}<span>Reported by the discovery provider; no primary source was established.</span></div>
      <div>{badge('older')}<span>Real, but older than this window; background only.</span></div>
    </div>
  </section>

  {footer}
</div>

<script>
(function () {{
  var v = document.getElementById('v');
  function seek(t) {{ try {{ v.currentTime = t; v.play().catch(function () {{}}); }} catch (e) {{}} }}
  document.querySelectorAll('[data-t]').forEach(function (b) {{ b.addEventListener('click', function () {{ seek(parseFloat(b.dataset.t)); }}); }});
  var cues = Array.prototype.slice.call(document.querySelectorAll('.cue')), last = null;
  v.addEventListener('timeupdate', function () {{
    var t = v.currentTime, cur = null;
    for (var i = 0; i < cues.length; i++) {{ if (parseFloat(cues[i].dataset.t) <= t) cur = cues[i]; else break; }}
    if (cur !== last) {{ if (last) last.classList.remove('on'); if (cur) cur.classList.add('on'); last = cur; }}
  }});
}})();
</script>
</body>
</html>
'''
    with open(os.path.join(out, 'index.html'), 'w', encoding='utf-8') as fh:
        fh.write(page)
    return {'out': out, 'video': video_name, 'chapters': len(chapters), 'cues': len(cues), 'lead_cards': len(lead_cards),
            'leads_reviewed': counts['leads'], 'stories': counts['stories'], 'sources': counts['sources'], 'claims': counts['claims']}


def main(argv):
    if any(a in ('-h', '--help') for a in argv):
        print(__doc__.strip())
        sys.exit(0)
    args, opts = [], {}
    it = iter(argv)
    for a in it:
        if a in ('--video', '--repo-url', '--install'):
            opts[a[2:].replace('-', '_')] = next(it, None)
        else:
            args.append(a)
    if len(args) != 2:
        sys.exit(__doc__.strip())
    info = build(args[0], args[1], video_name=opts.get('video'), repo_url=opts.get('repo_url'), install=opts.get('install'))
    print(json.dumps(info))


if __name__ == '__main__':
    main(sys.argv[1:])
