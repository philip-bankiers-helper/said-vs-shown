"""Config, portability and hygiene checks for the core engine files, plus offline smoke tests of
the CLIs (receipt.mjs, loudfix.sh, voice.py, setup.sh, doctor.mjs). Tests that need node, ffmpeg or
a local Chrome skip themselves when those are missing."""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from helpers import ENGINE, ROOT, have, load, run

DEMO = os.path.join(os.path.dirname(ENGINE), 'demo')
# every engine file, so a new tool is checked without editing this list
CORE = sorted(f for f in os.listdir(ENGINE) if not f.startswith('.') and os.path.isfile(os.path.join(ENGINE, f)))
SHIPPED = [os.path.join(ENGINE, n) for n in CORE] + sorted(
    os.path.join(DEMO, f) for f in os.listdir(DEMO) if not f.startswith('.') and os.path.isfile(os.path.join(DEMO, f)))
CONFIG = load(os.path.join(ENGINE, 'config.json'))


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def test_files():
    out = []
    for d, _, files in os.walk(os.path.join(ROOT, 'tests')):
        out += [os.path.join(d, f) for f in files if f.endswith(('.py', '.md', '.json'))]
    return out


class ConfigTests(unittest.TestCase):
    def test_config_contract(self):
        self.assertEqual(CONFIG, {'hyperframes': '0.8.147', 'gsap': '3.14.2', 'voice': 'af_heart', 'speed': 1.06,
                                  'lufs': -16, 'true_peak': -1.5, 'wpm': [145, 185], 'max_cps': 21, 'max_chars': 42,
                                  'home': '~/.said-vs-shown'})

    def test_package_pins_are_exact(self):
        pkg = load(os.path.join(ENGINE, 'package.json'))
        self.assertTrue(pkg['private'])
        self.assertEqual(pkg['type'], 'module')
        self.assertEqual(set(pkg['dependencies']), {'puppeteer-core', '@puppeteer/browsers'})
        for v in pkg['dependencies'].values():
            self.assertRegex(v, r'^\d+\.\d+\.\d+$')

    def test_versions_live_only_in_config(self):
        self.assertIn('README.md', os.listdir(DEMO))
        for path in SHIPPED:
            if os.path.basename(path) == 'config.json':
                continue
            for key in ('hyperframes', 'gsap'):
                self.assertNotIn(CONFIG[key], read(path), '%s hardcodes the %s version' % (path, key))


class HygieneTests(unittest.TestCase):
    # built from pieces so this file does not match itself
    PRIVATE = [re.compile(p, re.I) for p in (
        '/' + 'Users/', 'ja' + 'ques', 'flee' + 't', 'gate' + 'way', 'Act' + 'Run', 'Kai' + 'rox',
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')]

    def test_no_personal_paths_or_private_names(self):
        for path in SHIPPED + test_files():
            text = read(path)
            for pat in self.PRIVATE:
                self.assertIsNone(pat.search(text), '%s matches %s' % (path, pat.pattern))

    def test_python_opens_use_utf8(self):
        for path in SHIPPED:
            if path.endswith('.py'):
                for line in read(path).splitlines():
                    if re.search(r'\bopen\(', line) and 'def ' not in line:
                        self.assertIn('encoding=', line, '%s: %s' % (path, line.strip()))

    def test_shell_is_portable(self):
        for name in CORE:
            if name.endswith('.sh'):
                text = read(os.path.join(ENGINE, name))
                self.assertNotRegex(text, r'sed\s+-i', name)
                self.assertTrue(text.startswith('#!/bin/sh'), name)
                self.assertEqual(run(['sh', '-n', os.path.join(ENGINE, name)]).returncode, 0, name)

    def test_snapshots_never_describe(self):
        # `hyperframes snapshot` sends frames to a paid vision model unless told not to
        for path in SHIPPED:
            for n, line in enumerate(read(path).splitlines(), 1):
                if re.search(r'\bsnapshot\b', line) and re.search(r'hyperframes|\bHF\b|npx', line):
                    self.assertRegex(line, r'--describe[\'",\s=]+false', '%s:%d %s' % (path, n, line.strip()))

    def test_capture_has_no_swallowed_errors(self):
        text = read(os.path.join(ENGINE, 'capture.sh'))
        self.assertNotIn('|| true', text)
        self.assertIn("'https?://[^] )>]+'", text)
        self.assertIn('< /dev/null', text)


class CliTests(unittest.TestCase):
    def test_python_tools_parse_on_this_interpreter(self):
        names = [n for n in CORE if n.endswith('.py')]
        self.assertGreaterEqual(len(names), 12)
        for name in names + [os.path.join('..', 'demo', 'demo.py')]:
            for flag in ('--help', '-h'):
                r = run([sys.executable, os.path.join(ENGINE, name), flag])
                self.assertEqual(r.returncode, 0, name + flag + r.stderr)
                self.assertIn('usage', r.stdout.lower(), name)
        for name in ('align.py', 'board.py', 'boundary.py', 'companion.py'):  # wrong arguments stay an error
            self.assertNotEqual(run([sys.executable, os.path.join(ENGINE, name)]).returncode, 0, name)

    def test_shell_tools_help(self):
        for name in [n for n in CORE if n.endswith('.sh')]:
            r = run(['sh', os.path.join(ENGINE, name), '--help'])
            self.assertEqual(r.returncode, 0, name + r.stderr)
            self.assertIn('usage', r.stdout.lower(), name)
        self.assertEqual(run(['sh', os.path.join(ENGINE, 'loudfix.sh')]).returncode, 2)

    @unittest.skipUnless(have('swift') and sys.platform == 'darwin', 'swift (macOS) not available')
    def test_ocr_locate_help(self):
        swift = os.path.join(ENGINE, 'ocr-locate.swift')
        r = run(['swift', swift, '--help'], timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('usage', r.stdout)
        self.assertEqual(run(['swift', swift], timeout=300).returncode, 2)

    def test_setup_help(self):
        r = run(['sh', os.path.join(ENGINE, 'setup.sh'), '--help'])
        self.assertEqual(r.returncode, 0)
        self.assertIn('--with-parakeet', r.stdout)
        self.assertEqual(run(['sh', os.path.join(ENGINE, 'setup.sh'), '--bogus']).returncode, 2)

    @unittest.skipUnless(have('node'), 'node not installed')
    def test_node_tools_parse(self):
        for path in [os.path.join(ENGINE, n) for n in CORE if n.endswith('.mjs')] + [os.path.join(DEMO, 'suggest.mjs')]:
            name = os.path.basename(path)
            r = run(['node', '--check', path])
            self.assertEqual(r.returncode, 0, name + r.stderr)
            r = run(['node', path, '--help'])  # doctor must not run its checks here, suggest must not open Chrome
            self.assertEqual(r.returncode, 0, name + r.stderr)
            self.assertIn('usage', r.stdout, name)
        self.assertEqual(run(['node', os.path.join(DEMO, 'suggest.mjs')]).returncode, 2)

    @unittest.skipUnless(have('node'), 'node not installed')
    def test_receipt_usage_and_chrome_lookup(self):
        receipt = os.path.join(ENGINE, 'receipt.mjs')
        self.assertEqual(run(['node', receipt]).returncode, 2)
        env = dict(os.environ, CHROME_PATH=sys.executable)
        r = run(['node', receipt, '--find-chrome'], env=env)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, sys.executable))
        env['CHROME_PATH'] = os.path.join(tempfile.gettempdir(), 'no-such-chrome-binary')
        r = run(['node', receipt, '--find-chrome'], env=env)
        self.assertEqual(r.returncode, 1)
        self.assertIn('CHROME_PATH', r.stderr)


def chrome_ready():
    if not have('node'):
        return False
    receipt = os.path.join(ENGINE, 'receipt.mjs')
    if run(['node', receipt, '--find-chrome']).returncode != 0:
        return False
    probe = ("const {createRequire}=require('module');const path=require('path');const os=require('os');"
             "const h=process.env.SVS_HOME||path.join(os.homedir(),'.said-vs-shown');"
             "for (const b of [path.join(h,'node','package.json'), process.argv[1]]) {"
             "try{createRequire(b)('puppeteer-core');process.exit(0)}catch{}} process.exit(1)")
    return run(['node', '-e', probe, os.path.join(ENGINE, 'package.json')]).returncode == 0


@unittest.skipUnless(chrome_ready(), 'needs node, puppeteer-core (setup.sh) and a local Chrome')
class ReceiptOfflineTests(unittest.TestCase):
    """receipt.mjs on a saved capture (file://), so no network is used."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='svs-receipt-test-')
        self.page = os.path.join(self.tmp, 'ep', 'ledger', 'capture', 'S01', 'extracted', 'page.html')
        os.makedirs(os.path.dirname(self.page))
        with open(self.page, 'w', encoding='utf-8') as f:
            f.write('<html><body><div style="position:fixed;top:0">Cookie bar</div>'
                    '<p>Saved pages keep their words: the quote is right here.</p>'
                    '<script>document.body.innerHTML = "app shell"</script></body></html>')
        self.out = os.path.join(self.tmp, 'ep', 'ledger', 'receipts', 'R01-test.png')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def receipt(self, quote, *extra):
        url = 'file://' + self.page.replace(os.sep, '/')
        return run(['node', os.path.join(ENGINE, 'receipt.mjs'), '--url', url, '--quote', quote, '--out', self.out, *extra],
                   timeout=180)

    def test_found_with_nojs_and_relative_url(self):
        r = self.receipt('the quote is right here', '--nojs', '1')
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        meta = load(self.out[:-4] + '.json')
        self.assertTrue(meta['found'])
        self.assertEqual(meta['url'], 'capture/S01/extracted/page.html')
        self.assertNotIn(self.tmp, json.dumps(meta))
        self.assertTrue(os.path.exists(self.out))
        self.assertEqual(len(meta['lines']), 1)

    def test_miss_writes_json_but_no_png(self):
        r = self.receipt('the quote is right here')  # page JS replaces the text: a miss
        self.assertEqual(r.returncode, 1)
        meta = load(self.out[:-4] + '.json')
        self.assertFalse(meta['found'])
        self.assertFalse(os.path.exists(self.out))


def node_at_least(major, minor):
    if not have('node'):
        return False
    r = run(['node', '-p', 'process.versions.node'])
    a, b = (int(x) for x in r.stdout.strip().split('.')[:2])
    return (a, b) >= (major, minor)


@unittest.skipUnless(node_at_least(22, 12), 'node >= 22.12 not installed')
class GlobalSkillsDeclineTests(unittest.TestCase):
    """A user may decline the global HyperFrames skills install: setup.sh --no-skills leaves those folders alone
    and doctor only WARNs (agents read the docs through the pinned CLI), so stage 0 can still pass. Offline: npx,
    uv, ffmpeg and ffprobe are stubs; python3 is this interpreter."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='svs-skills-test-')
        self.bin = os.path.join(self.tmp, 'bin')
        os.makedirs(self.bin)
        self.skills = os.path.join(self.tmp, 'skills-check.json')
        stubs = {
            'npx': '#!/bin/sh\n# fake npx: answers the HyperFrames calls setup/doctor make, offline\n'
                   'shift; shift\ncase "$*" in\n'
                   '  --version) echo %s ;;\n'
                   '  "models list --json") echo \'{"ok":true,"models":[{"engine":"whisper","installed":true}]}\' ;;\n'
                   '  "skills check --json") cat "%s" ;;\n'
                   '  "telemetry status") echo "Status: disabled" ;;\n'
                   '  *) echo "fake npx: unexpected $*" >&2; exit 9 ;;\nesac\n' % (CONFIG['hyperframes'], self.skills),
            'uv': '#!/bin/sh\necho "uv 0.0.0"\n',
            'ffmpeg': '#!/bin/sh\necho "ffmpeg version 0"\n',
            'ffprobe': '#!/bin/sh\necho "ffprobe version 0"\n',
            'python3': '#!/bin/sh\nexec "%s" "$@"\n' % sys.executable,
        }
        for name, body in stubs.items():
            path = os.path.join(self.bin, name)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(body)
            os.chmod(path, 0o755)
        self.env = {'PATH': os.pathsep.join([self.bin, os.path.dirname(shutil.which('node')), '/usr/bin', '/bin']),
                    'HOME': self.tmp, 'SVS_HOME': os.path.join(self.tmp, 'svs'),
                    'CHROME_PATH': os.path.join(self.tmp, 'no-such-chrome')}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def doctor(self, summary):
        with open(self.skills, 'w', encoding='utf-8') as f:
            json.dump({'location': os.path.join(self.tmp, '.claude', 'skills'), 'summary': summary}, f)
        r = run(['node', os.path.join(ENGINE, 'doctor.mjs'), '--no-smoke'], env=self.env, timeout=120)
        line = next((ln for ln in r.stdout.splitlines() if ln[6:].startswith('hf skills')), None)
        self.assertIsNotNone(line, r.stdout + r.stderr)
        return line, r.stdout

    def test_doctor_warns_not_fails_without_core_skills(self):
        line, out = self.doctor({'current': 0, 'outdated': 0, 'missing': 21, 'coreMissing': 11})
        self.assertTrue(line.startswith('WARN '), line)
        self.assertIn('11 core skill(s) not installed', line)
        self.assertIn('agents can read HyperFrames docs via `npx -y hyperframes@%s docs <topic>`' % CONFIG['hyperframes'], line)
        self.assertNotRegex(out, r'(?m)^FAIL\s+hf skills')
        line, _ = self.doctor({'current': 11, 'outdated': 0, 'missing': 10, 'coreMissing': 0})
        self.assertTrue(line.startswith('PASS '), line)

    def test_setup_no_skills_leaves_global_skill_folders_alone(self):
        setup = os.path.join(ENGINE, 'setup.sh')
        update = '[dry-run] npx -y hyperframes@%s skills update' % CONFIG['hyperframes']
        r = run(['sh', setup, '--dry-run'], env=self.env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(update, r.stdout)
        r = run(['sh', setup, '--dry-run', '--no-skills'], env=self.env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn('skills update', r.stdout.split('==> 3/6')[1].split('==> 4/6')[0])
        self.assertIn('skipped (--no-skills)', r.stdout)
        self.assertIn('npx -y hyperframes@%s docs <topic>' % CONFIG['hyperframes'], r.stdout)
        self.assertNotIn('~/.claude/skills', r.stdout)
        self.assertIn('--no-skills', run(['sh', setup, '--help']).stdout)


class VoiceAsrTests(unittest.TestCase):
    """voice.py --asr auto|whisper|parakeet picks the transcription engine (auto: Parakeet if installed)."""

    @classmethod
    def setUpClass(cls):
        import voice
        cls.voice = voice

    def listing(self, parakeet_installed):
        models = [{'engine': 'parakeet', 'installed': parakeet_installed}, {'engine': 'whisper', 'installed': True}]
        return mock.Mock(stdout=json.dumps({'ok': True, 'models': models}), returncode=0)

    def test_whisper_needs_no_model_lookup(self):
        with mock.patch.object(self.voice.subprocess, 'run', side_effect=AssertionError('no lookup for whisper')):
            self.assertEqual(self.voice.asr_args('whisper', ['npx']), ['--engine', 'whisper', '--model', 'small.en'])

    def test_auto_and_parakeet(self):
        with mock.patch.object(self.voice.subprocess, 'run', return_value=self.listing(True)):
            self.assertEqual(self.voice.asr_args('auto', ['npx']), ['--engine', 'parakeet'])
            self.assertEqual(self.voice.asr_args('parakeet', ['npx']), ['--engine', 'parakeet'])
        with mock.patch.object(self.voice.subprocess, 'run', return_value=self.listing(False)):
            self.assertEqual(self.voice.asr_args('auto', ['npx']), ['--engine', 'whisper', '--model', 'small.en'])
            with mock.patch('sys.stderr', new_callable=io.StringIO) as err, self.assertRaises(SystemExit):
                self.voice.asr_args('parakeet', ['npx'])
            self.assertIn('--with-parakeet', err.getvalue())

    def test_cli(self):
        r = run([sys.executable, os.path.join(ENGINE, 'voice.py'), '--help'])
        self.assertIn('--asr {auto,whisper,parakeet}', r.stdout)
        r = run([sys.executable, os.path.join(ENGINE, 'voice.py'), 'x', '--asr', 'vosk'])
        self.assertEqual(r.returncode, 2)


@unittest.skipUnless(have('ffmpeg'), 'ffmpeg not installed')
class LoudfixTests(unittest.TestCase):
    def test_normalises_to_target_and_fails_on_silence(self):
        with tempfile.TemporaryDirectory() as d:
            tone, silent = os.path.join(d, 'tone.mp4'), os.path.join(d, 'silent.mp4')
            for src, out in (('sine=frequency=440:duration=3', tone), ('anullsrc=d=3', silent)):
                subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', src, '-f', 'lavfi', '-i',
                                'color=c=black:s=160x90:d=3', '-af', 'volume=-25dB', '-c:v', 'mpeg4', '-c:a', 'aac',
                                '-shortest', out], check=True, stdin=subprocess.DEVNULL)
            r = run(['sh', os.path.join(ENGINE, 'loudfix.sh'), tone, os.path.join(d, 'out.mp4')])
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('I: -16', r.stdout)
            r = run(['sh', os.path.join(ENGINE, 'loudfix.sh'), silent, os.path.join(d, 'out2.mp4')])
            self.assertEqual(r.returncode, 1)


if __name__ == '__main__':
    unittest.main()
