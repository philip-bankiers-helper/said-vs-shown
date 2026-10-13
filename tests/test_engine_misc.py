"""Config, portability and hygiene checks for the core engine files, plus offline smoke tests of
the CLIs (receipt.mjs, loudfix.sh, voice.py, setup.sh, doctor.mjs). Tests that need node, ffmpeg or
a local Chrome skip themselves when those are missing."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

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

    def test_capture_has_no_swallowed_errors(self):
        text = read(os.path.join(ENGINE, 'capture.sh'))
        self.assertNotIn('|| true', text)
        self.assertIn("'https?://[^] )>]+'", text)
        self.assertIn('< /dev/null', text)


class CliTests(unittest.TestCase):
    def test_python_tools_parse_on_this_interpreter(self):
        for name in ('voice.py', 'captions.py', 'scene_words.py', 'assemble.py', 'scope_css.py', 'deliver.py',
                     'fill_scenes.py', 'new_episode.py'):
            r = run([sys.executable, os.path.join(ENGINE, name), '--help'])
            self.assertEqual(r.returncode, 0, name + r.stderr)
            self.assertIn('usage', r.stdout.lower(), name)
        self.assertNotEqual(run([sys.executable, os.path.join(ENGINE, 'align.py')]).returncode, 0)

    def test_setup_help(self):
        r = run(['sh', os.path.join(ENGINE, 'setup.sh'), '--help'])
        self.assertEqual(r.returncode, 0)
        self.assertIn('--with-parakeet', r.stdout)
        self.assertEqual(run(['sh', os.path.join(ENGINE, 'setup.sh'), '--bogus']).returncode, 2)

    @unittest.skipUnless(have('node'), 'node not installed')
    def test_node_tools_parse(self):
        for name in ('receipt.mjs', 'doctor.mjs'):
            r = run(['node', '--check', os.path.join(ENGINE, name)])
            self.assertEqual(r.returncode, 0, name + r.stderr)
            r = run(['node', os.path.join(ENGINE, name), '--help'])  # doctor must not run its checks here
            self.assertEqual(r.returncode, 0, name + r.stderr)
            self.assertIn('usage', r.stdout, name)

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
