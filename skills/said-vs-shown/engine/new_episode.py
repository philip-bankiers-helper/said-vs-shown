#!/usr/bin/env python3
"""new_episode.py — scaffold a new episode folder (layout: references/project-layout.md).

usage: new_episode.py <episodes_root> <YYYY-MM-DD> <edition> [--brief <path>] [--editor "<name>"]
                      [--show "<show name>"] [--window "<Oct 5–8, 2026>"]

Creates <episodes_root>/<date>_<edition-slug>/ with input/ ledger/ edit/ video/ deliver/, copies the brief to
input/brief.md, the HyperFrames project template ($SKILL/templates/project/) into video/, plus
templates/frame.md -> video/frame.md, templates/fonts/ -> video/assets/fonts/, templates/sfx/ -> video/assets/sfx/.
Writes a starter edit/episode.json (show, edition, date, editor, disclosure, credit: true) and video/BRIEF.md.
Refuses to touch an existing episode folder.
"""
import json
import os
import re
import shutil
import sys

ENGINE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(ENGINE)
TEMPLATES = os.path.join(SKILL, 'templates')
SHOW = 'Said vs. Shown'


def die(msg):
    sys.exit(f'new_episode.py: {msg}')


def slugify(s):
    return re.sub(r'[^a-z0-9]+', '-', str(s).lower()).strip('-')


def config():
    p = os.path.join(ENGINE, 'config.json')
    if os.path.isfile(p):
        with open(p, encoding='utf-8') as fh:
            return json.load(fh)
    return {}


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
    for d in ('input', 'ledger/receipts', 'ledger/capture', 'edit', 'deliver',
              'video/specs', 'video/compositions', 'video/audio', 'video/assets/receipts'):
        os.makedirs(os.path.join(ep, d), exist_ok=True)
    shutil.copytree(need['templates/project/'], V, dirs_exist_ok=True)
    # keep the project's pinned HyperFrames version in step with engine/config.json
    pkg = os.path.join(V, 'package.json')
    if os.path.exists(pkg):
        with open(pkg, encoding='utf-8') as fh:
            ptxt = fh.read()
        ptxt = re.sub(r'hyperframes@[0-9][0-9.]*', 'hyperframes@' + config().get('hyperframes', '0.8.147'), ptxt)
        with open(pkg, 'w', encoding='utf-8') as fh:
            fh.write(ptxt)
    shutil.copy2(need['templates/frame.md'], os.path.join(V, 'frame.md'))
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
        'edition': edition,
        'date': date,
        'window': o['window'],
        'captured': '',
        'slug': slugify(f'{o["show"]}-{edition}-{date}'),
        'title': '',
        'thesis': '',
        'one_thing': '',
        'one_thing_highlight': '',
        'editor': editor,
        'disclosure': 'AI-produced · AI voice · every claim sourced' + (f' · reviewed by {editor}' if editor else ''),
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
    cfg = config()
    brief_tpl = os.path.join(V, 'BRIEF.md')
    if os.path.isfile(brief_tpl):
        with open(brief_tpl, encoding='utf-8') as fh:
            b = fh.read()
    else:
        b = ('---\nworkflow: general-video\nflow: automation\nstoryboard: no\ndestination: website\naspect: 1920x1080\n'
             'language: en\nangle: evidence-boundary\nnarration: yes\nvoice: <voice id>\n---\n\n## Intent\n\n'
             f'{o["show"]}, <Edition> edition, dated <YYYY-MM-DD> (window <window>).\n')
    b = b.replace('<Edition>', edition).replace('<YYYY-MM-DD>', date)
    if o['window']:
        b = b.replace('<window>', o['window'])
    if cfg.get('voice'):
        b = re.sub(r'<voice id[^>]*>', cfg['voice'], b)
    with open(brief_tpl, 'w', encoding='utf-8') as fh:
        fh.write(b)

    hf = cfg.get('hyperframes', '0.8.147')
    rel = os.path.relpath(ep)
    eng = '$SKILL/engine'
    print(f'''Created {rel}/
  input/brief.md      {'copied from ' + o['brief'] if o['brief'] else 'placeholder: paste the brief'}
  edit/episode.json   starter (show, edition, date, editor, disclosure, credit)
  video/              HyperFrames project + frame.md, fonts, sfx, BRIEF.md

Next (SKILL={SKILL}):
  1. Fill edit/episode.json as the facts settle: window, captured, title, thesis, one_thing, stories, matrix, chapters
     (schema: $SKILL/references/project-layout.md).
  2. Build the ledger (sources, captures, claims, leads) and the script, voice and captions (SKILL.md stages).
  3. Scenes: python3 "{eng}/board.py" {rel} <n> board-<n> {rel}/video/compositions/NN-board-<n>.html <fill> <next> <zoom> <dur>
             python3 "{eng}/boundary.py" {rel}/video/specs/NN-<scene>.json {rel}/video/compositions/NN-<scene>.html
  4. Assemble and check: python3 "{eng}/assemble.py" {rel}/video && (cd {rel}/video && npx -y hyperframes@{hf} check)
  5. After the render: python3 "{eng}/deliver.py" {rel} --master <render.mp4>''')


if __name__ == '__main__':
    main(sys.argv[1:])
