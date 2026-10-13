#!/usr/bin/env python3
"""new_episode.py — scaffold a new episode folder (layout: references/project-layout.md).

usage: new_episode.py <episodes_root> <YYYY-MM-DD> <edition> [--brief <path>] [--editor "<name>"]
                      [--show "<show name>"] [--window "<Oct 5–8, 2026>"]

<edition> names a file in <skill>/editions/ (ai -> editions/ai.yaml); its `label` becomes episode.json "edition"
and its `design.accent` the `--accent` row of video/frame.md. An edition without a YAML file is refused.
Creates <episodes_root>/<date>_<edition-slug>/ with input/ ledger/ edit/ video/ deliver/, copies the brief to
input/brief.md, the HyperFrames project template (<skill>/templates/project/) into video/, plus
templates/frame.md -> video/frame.md, templates/fonts/ -> video/assets/fonts/, templates/sfx/ -> video/assets/sfx/.
Writes a starter edit/episode.json (show, edition, date, editor, disclosure, credit: true) and video/BRIEF.md.
The disclosure reads "not yet human-reviewed" until the review (stage 10) sets "reviewed_by" (companion.disclosure_of);
--editor only records who edits the episode. Refuses to touch an existing episode folder.
The printed commands use paths relative to the current directory when the episode is inside it, else absolute.
"""
import json
import os
import re
import shutil
import sys

ENGINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE)
from companion import disclosure_of  # noqa: E402  (the one disclosure rule)
SKILL = os.path.dirname(ENGINE)
TEMPLATES = os.path.join(SKILL, 'templates')
SHOW = 'Said vs. Shown'


def die(msg):
    sys.exit(f'new_episode.py: {msg}')


def slugify(s):
    return re.sub(r'[^a-z0-9]+', '-', str(s).lower()).strip('-')


def config():
    p = os.path.join(ENGINE, 'config.json')
    if not os.path.isfile(p):
        die(f'missing {p} (reinstall the skill)')
    with open(p, encoding='utf-8') as fh:
        cfg = json.load(fh)
    if not cfg.get('hyperframes'):
        die(f'{p} has no "hyperframes" version')
    return cfg


def edition_info(ed_slug):
    """label and accent from editions/<edition>.yaml (a regex read: the standard library has no YAML parser)."""
    p = os.path.join(SKILL, 'editions', f'{ed_slug}.yaml')
    if not os.path.isfile(p):
        have = sorted(f[:-5] for f in os.listdir(os.path.join(SKILL, 'editions')) if f.endswith('.yaml'))
        die(f'no edition file {p}; editions: {", ".join(have)}. A new edition needs its YAML first (copy ai.yaml), '
            'then a 25–40 s slice for the user to react to')
    with open(p, encoding='utf-8') as fh:
        text = fh.read()
    label = re.search(r'^label:\s*"?([^"#\n]+?)"?\s*(?:#.*)?$', text, flags=re.M)
    accent = re.search(r'\baccent:\s*"?(#[0-9A-Fa-f]{6})\b', text)
    return (label.group(1).strip() if label else ed_slug), (accent.group(1) if accent else None)


def shown_path(path):
    """A path for printed commands: relative to the working directory when the path is inside it, else absolute
    (never a ../../.. chain); double-quoted when it holds spaces or shell characters."""
    path = os.path.abspath(path)
    try:
        rel = os.path.relpath(path)
    except ValueError:  # another drive on Windows
        rel = path
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):
        rel = path
    return rel if re.fullmatch(r'[\w@%+=:,./\\-]+', rel) else f'"{rel}"'


def set_accent(frame_md, accent):
    """Point frame.md's palette at the edition accent (fill_scenes.py reads the `--accent` row)."""
    with open(frame_md, encoding='utf-8') as fh:
        text = fh.read()
    rgb = ','.join(str(int(accent[i:i + 2], 16)) for i in (1, 3, 5))
    text = re.sub(r'(\|\s*`--accent`\s*\|\s*`)#[0-9A-Fa-f]{6}(`)', lambda m: m.group(1) + accent.upper() + m.group(2), text, count=1)
    text = re.sub(r'(\|\s*`--accent-wash`\s*\|\s*`rgba\()\d+,\s*\d+,\s*\d+(,)', lambda m: m.group(1) + rgb + m.group(2), text, count=1)
    with open(frame_md, 'w', encoding='utf-8') as fh:
        fh.write(text)


def parse(argv):
    opts, args = {'brief': None, 'editor': '', 'show': SHOW, 'window': ''}, []
    it = iter(argv)
    for a in it:
        if a in ('--brief', '--editor', '--show', '--window'):
            v = next(it, None)
            if v is None:
                die(f'{a} needs a value')
            opts[a[2:]] = v
        elif a in ('-h', '--help'):
            print(__doc__.strip())
            sys.exit(0)
        else:
            args.append(a)
    if len(args) != 3:
        die('usage: new_episode.py <episodes_root> <YYYY-MM-DD> <edition> [--brief <path>] [--editor "<name>"]')
    return args, opts


def main(argv):
    (root, date, edition), o = parse(argv)
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        die(f'date must be YYYY-MM-DD, got {date!r}')
    ed_slug = slugify(edition)
    if not ed_slug:
        die(f'edition {edition!r} has no usable characters')
    label, accent = edition_info(ed_slug)
    cfg = config()
    hf = cfg['hyperframes']
    if o['brief'] and not os.path.isfile(o['brief']):
        die(f'brief not found: {o["brief"]}')

    # the skill's templates must all be present before anything is created
    need = {'templates/project/': os.path.join(TEMPLATES, 'project'), 'templates/frame.md': os.path.join(TEMPLATES, 'frame.md'),
            'templates/fonts/': os.path.join(TEMPLATES, 'fonts'), 'templates/sfx/': os.path.join(TEMPLATES, 'sfx')}
    missing = [k for k, p in need.items() if not os.path.exists(p)]
    if missing:
        die(f'the skill is incomplete: missing {", ".join(missing)} under {SKILL}\n'
            '  (reinstall or update the skill; new_episode.py copies these into every episode)')

    ep = os.path.join(os.path.abspath(root), f'{date}_{ed_slug}')
    if os.path.exists(ep) and os.listdir(ep):
        die(f'{ep} already exists and is not empty; pick another date/edition or remove it yourself')

    V = os.path.join(ep, 'video')
    for d in ('input', 'ledger/capture', 'edit', 'deliver',
              'video/specs', 'video/compositions', 'video/audio', 'video/assets/receipts'):
        os.makedirs(os.path.join(ep, d), exist_ok=True)
    shutil.copytree(need['templates/project/'], V, dirs_exist_ok=True)
    # keep the project's pinned HyperFrames version in step with engine/config.json
    pkg = os.path.join(V, 'package.json')
    if os.path.exists(pkg):
        with open(pkg, encoding='utf-8') as fh:
            ptxt = fh.read()
        ptxt = re.sub(r'hyperframes@[0-9][0-9.]*', 'hyperframes@' + hf, ptxt)
        with open(pkg, 'w', encoding='utf-8') as fh:
            fh.write(ptxt)
    shutil.copy2(need['templates/frame.md'], os.path.join(V, 'frame.md'))
    if accent:
        set_accent(os.path.join(V, 'frame.md'), accent)
    shutil.copytree(need['templates/fonts/'], os.path.join(V, 'assets', 'fonts'), dirs_exist_ok=True)
    shutil.copytree(need['templates/sfx/'], os.path.join(V, 'assets', 'sfx'), dirs_exist_ok=True)

    brief_dst = os.path.join(ep, 'input', 'brief.md')
    if o['brief']:
        shutil.copy2(o['brief'], brief_dst)
    else:
        with open(brief_dst, 'w', encoding='utf-8') as fh:
            fh.write('# Brief\n\nPaste the research brief here: the leads, their links, the window and any editorial guardrails.\n')

    editor = o['editor'].strip()
    E = {
        'show': o['show'],
        'edition': label,
        'date': date,
        'window': o['window'],
        'captured': '',
        'slug': slugify(f'{o["show"]}-{ed_slug}-{date}'),
        'title': '',
        'thesis': '',
        'one_thing': '',
        'one_thing_highlight': '',
        'editor': editor,
        'disclosure': disclosure_of({}),  # "… · not yet human-reviewed"; the review (stage 10) adds reviewed_by
        'credit': True,
        'lead_badge_overrides': {},
        'stories': [],
        'matrix': [],
        'chapters': {},
    }
    with open(os.path.join(ep, 'edit', 'episode.json'), 'w', encoding='utf-8') as fh:
        json.dump(E, fh, ensure_ascii=False, indent=1)
        fh.write('\n')

    # video/BRIEF.md: the template's, with what is already known filled in
    brief_tpl = os.path.join(V, 'BRIEF.md')
    if os.path.isfile(brief_tpl):
        with open(brief_tpl, encoding='utf-8') as fh:
            b = fh.read()
    else:
        b = ('---\nworkflow: general-video\nflow: automation\nstoryboard: no\ndestination: website\naspect: 1920x1080\n'
             'language: en\nangle: evidence-boundary\nnarration: yes\nvoice: <voice id>\n---\n\n## Intent\n\n'
             f'{o["show"]}, <Edition> edition, dated <YYYY-MM-DD> (window <window>).\n')
    b = b.replace('<Edition>', label).replace('<YYYY-MM-DD>', date)
    if o['window']:
        b = b.replace('<window>', o['window'])
    if cfg.get('voice'):
        b = re.sub(r'<voice id[^>]*>', cfg['voice'], b)
    with open(brief_tpl, 'w', encoding='utf-8') as fh:
        fh.write(b)

    rel, vid = shown_path(ep), shown_path(V)
    comp = shown_path(os.path.join(V, 'compositions'))
    specs = shown_path(os.path.join(V, 'specs'))
    master = shown_path(os.path.join(V, 'renders', 'master.mp4'))
    eng = os.path.join(SKILL, 'engine')
    print(f'''Created {rel}   (edition {label}{', accent ' + accent if accent else ''})
  input/brief.md      {'copied from ' + o['brief'] if o['brief'] else 'placeholder: paste the brief'}
  edit/episode.json   starter (show, edition, date, editor, disclosure, credit)
  video/              HyperFrames project + frame.md, fonts, sfx, BRIEF.md

Next (skill: {SKILL}; stages in SKILL.md, data contracts in references/project-layout.md):
  1. Fill edit/episode.json as the facts settle: window, captured, title, thesis, one_thing, stories, matrix, chapters.
  2. Capture, ledger, script + video/scenes.json, receipts, voice:
       sh "{eng}/capture.sh" {rel}
       python3 "{eng}/voice.py" {vid}
  3. Scenes (references/scenes.md):
       python3 "{eng}/fill_scenes.py" {rel}
       python3 "{eng}/board.py" {rel} <n> board-<n> {comp}/NN-board-<n>.html <fill_at> <next_at> <zoom_at> <zoom_dur>
       python3 "{eng}/boundary.py" {specs}/NN-<scene>.json {comp}/NN-<scene>.html
  4. Assemble and check: python3 "{eng}/assemble.py" {vid} && npx -y hyperframes@{hf} check --strict {vid}
  5. After the review (sets reviewed_by) and the render: python3 "{eng}/deliver.py" {rel} --master {master}''')


if __name__ == '__main__':
    main(sys.argv[1:])
