"""Docs and templates: the episode project template pins HyperFrames to engine/config.json, every documented
snapshot command opts out of Gemini, stage 0 asks before setup, stage 10 stops the preview, and the receipt
template keeps its flash-safe pull-back. Offline, text only (plus demo.fill_template, which needs no tools)."""
import os
import re
import sys
import unittest

from helpers import ENGINE, ROOT, load

SKILL = os.path.dirname(ENGINE)
PROJECT = os.path.join(SKILL, 'templates', 'project')
RECEIPT = os.path.join(SKILL, 'templates', 'scenes', 'receipt.html')
HF = load(os.path.join(ENGINE, 'config.json'))['hyperframes']


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def project_files():
    return sorted(os.path.join(PROJECT, f) for f in os.listdir(PROJECT) if os.path.isfile(os.path.join(PROJECT, f)))


def docs():
    """The repo README, every Markdown file in the skill, and the project template's files."""
    out = [os.path.join(ROOT, 'README.md')]
    for d, _, files in os.walk(SKILL):
        out += [os.path.join(d, f) for f in files if f.endswith('.md')]
    return sorted(set(out + project_files()))


def commands(text):
    """(line number, command) for every inline code span and every line inside a fenced code block."""
    out, fenced = [], False
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith('```'):
            fenced = not fenced
            continue
        if fenced:
            out.append((n, line))
        else:
            out += [(n, c) for c in re.findall(r'`([^`]+)`', line)]
    return out


def stage(text, n):
    """The text of SKILL.md stage n, up to the next stage."""
    m = re.search(r'^%d\. \*\*.*?(?=^%d\. \*\*|^## )' % (n, n + 1), text, flags=re.S | re.M)
    return m.group(0) if m else ''


class ProjectTemplateTests(unittest.TestCase):
    def test_every_hyperframes_command_is_pinned_to_config(self):
        # new_episode.py re-pins package.json at intake, but AGENTS.md is copied as is
        for path in project_files():
            text = read(path)
            for m in re.finditer(r'hyperframes@([0-9][0-9.]*[0-9])', text):
                self.assertEqual(m.group(1), HF, os.path.basename(path))
            self.assertNotRegex(text, r'npx\s+(?:-y\s+|--yes\s+)?hyperframes(?!@)', os.path.basename(path))

    def test_agent_notes_import_one_file(self):
        self.assertIn('hyperframes@' + HF, read(os.path.join(PROJECT, 'AGENTS.md')))
        for name in ('CLAUDE.md', 'GEMINI.md'):
            self.assertEqual(read(os.path.join(PROJECT, name)).strip(), '@AGENTS.md', name)

    def test_npm_scripts(self):
        scripts = load(os.path.join(PROJECT, 'package.json'))['scripts']
        self.assertRegex(scripts['snapshot'], r'\bsnapshot --describe false\b')
        self.assertRegex(scripts['check'], r'\bcheck --strict\b')
        for name, cmd in scripts.items():
            self.assertIn('hyperframes@%s ' % HF, cmd + ' ', name)


class DocumentedCommandTests(unittest.TestCase):
    def test_every_documented_snapshot_opts_out_of_describe(self):
        # `hyperframes snapshot` sends frames to Gemini whenever GEMINI_API_KEY is set, unless told not to
        seen = 0
        for path in docs():
            for n, cmd in commands(read(path)):
                if re.search(r'\bsnapshot\b', cmd) and re.search(r'\bnpx\b', cmd):
                    seen += 1
                    self.assertRegex(cmd, r'--describe[=\s]+false', '%s:%d %s' % (path, n, cmd))
        self.assertGreater(seen, 0)

    def test_stage0_runs_doctor_and_asks_before_setup(self):
        s0 = stage(read(os.path.join(SKILL, 'SKILL.md')), 0)
        self.assertIn('doctor.mjs', s0)
        self.assertLess(s0.index('doctor.mjs'), s0.index('setup.sh'))
        self.assertRegex(s0, r'(?i)ask the user before running it')
        for changed in ('~/.claude/skills', '~/.agents/skills', '1.7 GB'):
            self.assertIn(changed, s0)

    def test_stage10_stops_preview_and_derives_disclosure(self):
        s10 = stage(read(os.path.join(SKILL, 'SKILL.md')), 10)
        self.assertIn('npx -y hyperframes@<ver> preview --stop <episode>/video', s10)
        self.assertIn('fill_scenes.py <episode> --only close', s10)
        self.assertIn('assemble.py <episode>/video', s10)
        self.assertIn('reviewed_by', s10)


class ReceiptTemplateTests(unittest.TestCase):
    def test_pullback_dims_the_page(self):
        # a zoomed-in white page that leaves the frame undimmed measured 3 luma jumps > 10% in 1 s (WCAG 2.3.1)
        t = read(RECEIPT)
        self.assertIn('<div id="__P__dim"></div>', t)
        self.assertRegex(t, r'fromTo\("#" \+ P \+ "dim", \{ opacity: 0 \}, \{ opacity: DIM,.*\}, A\.at\);')
        self.assertRegex(t, r'fromTo\("#" \+ P \+ "dim", \{ opacity: DIM \}, \{ opacity: 0,.*\}, A\.at \+ A\.dur\);')

    def test_demo_fills_the_template(self):
        demo_dir = os.path.join(SKILL, 'demo')
        if demo_dir not in sys.path:
            sys.path.insert(0, demo_dir)
        import demo
        cfg = {'kicker': {'num': 'Said vs. Shown', 'topic': 'Demo', 'badge': '', 'meta': '', 'wordmark': True, 'sep': True},
               'source': {'label': 'example.com', 'captured': 'captured Oct 13, 2026'}, 'url': 'example.com',
               'receipt': {'img': 'assets/receipts/R01-demo.png', 'alt': 'example.com', 'viewport': {'width': 1440, 'height': 900},
                           'lines': [{'x': 100, 'y': 200, 'w': 600, 'h': 18}]},
               'beats': {'kicker': 0.15, 'source': 0.3, 'frame': 0.4}, 'camera': {'at': 2.2, 'dur': 1.4, 'zoom': 0},
               'highlight': [{'at': 3.4, 'dur': 2.0}], 'after': {'mode': 'pullback', 'at': 9.0, 'dur': 1.4},
               'illustration': {'tag': 'Illustration', 'tag_at': 0, 'nodes': [], 'check_at': None}}
        html = demo.fill_template(cfg)
        self.assertNotIn('__P__', html)
        self.assertNotIn('__SCENE_ID__', html)
        self.assertIn('<div id="dr-dim"></div>', html)
        self.assertIn('"mode": "pullback"', html)


if __name__ == '__main__':
    unittest.main()
