"""Docs and templates: every HyperFrames command in a shipped file (docs, docstrings, usage strings, the episode
project template) is pinned to engine/config.json, every documented snapshot command opts out of Gemini, stage 0
asks before setup and has a decline path for the global skills, stage 10 stops the preview, and the receipt
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


# A HyperFrames command is written runnable and pinned: `npx -y hyperframes@<the config.json version, or a
# placeholder for it> <command>`. Checked in every shipped text file, prose, docstrings and usage strings included.
HF_SUBCOMMANDS = ('render|preview|check|snapshot|tts|transcribe|capture|docs|skills|models|lint|telemetry|init|add|'
                  'catalog|play|present|compositions|doctor|info|upgrade|benchmark|publish|keyframes|beats|browser|'
                  'validate|inspect|layout|timeline|remove-background')
PIN_RULES = (
    ('npx without a version', re.compile(r'\bnpx(?:\s+(?:-y|--yes))?\s+hyperframes(?!@)')),
    # a literal version or tag must be the config one; placeholders (<ver>, {hf}, %s, $HF_VER, ...) are fine
    ('version other than config.json\'s', re.compile(
        r'hyperframes@(?=[0-9A-Za-z])(?!' + re.escape(HF) + r'(?![0-9A-Za-z.]*[0-9A-Za-z]))')),
    ('bare CLI command', re.compile(r'(?<![\w@/.$-])hyperframes\s+(?:' + HF_SUBCOMMANDS + r')\b')),
)
TEXT_EXT = ('.md', '.py', '.mjs', '.js', '.sh', '.swift', '.html', '.json', '.yaml', '.yml', '.txt', '.css')


def shipped_text_files():
    """Every Markdown file in the repo and every text file of the skill and the plugin manifests; not the tests'
    code or fixtures (they hold deliberate fakes such as `hyperframes@x`)."""
    out = []
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in ('.git', 'node_modules', '__pycache__')]
        rel = os.path.relpath(d, ROOT).replace(os.sep, '/')
        if rel == 'tests/fixtures' or rel.startswith('tests/fixtures/'):
            continue
        in_skill = rel == 'skills' or rel.startswith('skills/') or rel.startswith('.claude-plugin')
        out += [os.path.join(d, f) for f in files if f.endswith('.md') or (in_skill and f.endswith(TEXT_EXT))]
    return sorted(out)


def pin_violations(text):
    return [(n, why, line.strip()) for n, line in enumerate(text.splitlines(), 1)
            for why, pat in PIN_RULES if pat.search(line)]


class PinTests(unittest.TestCase):
    def test_every_shipped_file_pins_hyperframes_to_config(self):
        files = shipped_text_files()
        names = {os.path.relpath(f, ROOT).replace(os.sep, '/') for f in files}
        for must in ('README.md', 'THIRD_PARTY.md', 'tests/README.md', 'skills/said-vs-shown/SKILL.md',
                     'skills/said-vs-shown/demo/demo.py', 'skills/said-vs-shown/demo/README.md',
                     'skills/said-vs-shown/engine/setup.sh', 'skills/said-vs-shown/engine/voice.py',
                     'skills/said-vs-shown/workflows/scenes.js', 'skills/said-vs-shown/templates/project/AGENTS.md',
                     'skills/said-vs-shown/references/scenes.md'):
            self.assertIn(must, names)
        self.assertFalse(any(n.startswith('tests/fixtures/') for n in names))
        bad = ['%s:%d %s: %s' % (os.path.relpath(f, ROOT), n, why, line)
               for f in files for n, why, line in pin_violations(read(f))]
        self.assertEqual(bad, [])

    def test_the_rules_catch_what_they_should(self):
        for text in ('npx hyperframes telemetry disable', 'Kokoro (npx hyperframes tts)', 'npx -y hyperframes render',
                     'npx --yes hyperframes preview', 'npx -y hyperframes@latest render', 'hyperframes@0.8.146 check',
                     'npx -y hyperframes@%s1 check' % HF, 'run `hyperframes check --strict`', 'hyperframes snapshot'):
            self.assertTrue(pin_violations(text), text)
        for text in ('npx -y hyperframes@%s telemetry disable' % HF, 'npx -y hyperframes@<ver> docs <topic>',
                     'npx hyperframes@<version> skills update', "['npx', '-y', f'hyperframes@{cfg[\"hf\"]}', 'tts']",
                     'HF="hyperframes@$HF_VER"', "'hyperframes@%s' % cfg['hyperframes']", 'HyperFrames\' `snapshot` command',
                     'npx -y hyperframes@%s.' % HF, 'github.com/heygen-com/hyperframes'):
            self.assertEqual(pin_violations(text), [], text)


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

    def test_stage0_has_a_decline_path_for_the_global_skills(self):
        text = read(os.path.join(SKILL, 'SKILL.md'))
        s0 = stage(text, 0)
        self.assertIn('setup.sh --no-skills', s0)
        self.assertRegex(s0, r'`hf skills` line as WARN, not FAIL')
        self.assertIn('npx -y hyperframes@<ver> docs <topic>', s0)
        self.assertNotRegex(s0, r'(?i)doctor fails while the core HyperFrames skills are missing')
        hf = text[text.index('## HyperFrames knowledge'):]
        self.assertIn('--no-skills', hf)
        self.assertIn('agents can read HyperFrames docs via `npx -y hyperframes@<ver> docs <topic>`', hf)
        self.assertNotIn('line fails', hf)

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
