"""capture.sh against a fixture brief, with a stub `npx` (offline) and a minimal PATH, so the
platform's own grep/sed/awk are used (BSD on macOS, GNU on Linux)."""
import json
import os
import shutil
import stat
import tempfile
import unittest

from helpers import ENGINE, FIXTURES, load, run, save

CAPTURE = os.path.join(ENGINE, 'capture.sh')
BRIEF = os.path.join(FIXTURES, 'capture', 'brief.md')
EXPECTED = [
    'https://example.com/a',
    'https://example.com/b',
    'https://example.com/c',
    'https://example.com/d',
    'https://example.com/e',
    'https://example.com/f',
    'https://example.com/wall?x=1&y=2',
    'https://example.com/s?q="a"b',
]

# Fake `npx -y hyperframes@x capture <url> -o capture/Sxx ...`: like npx it drains stdin, so a
# capture loop that forgets </dev/null loses the rest of its plan. URLs containing "wall" get a
# 2-word page and exit 1; others get 60 words.
STUB = r'''#!/bin/sh
cat > /dev/null
url=""; out=""; prev=""
for a in "$@"; do
  [ "$prev" = capture ] && url=$a
  [ "$prev" = -o ] && out=$a
  prev=$a
done
printf '%s\n' "$url" >> "$STUB_LOG"
mkdir -p "$out/extracted"
case "$url" in
  *wall*) echo "Access denied" > "$out/extracted/visible-text.txt"; echo '{"ok":false}'; exit 1 ;;
esac
i=0; while [ $i -lt 60 ]; do printf 'word%s ' $i; i=$((i+1)); done > "$out/extracted/visible-text.txt"
echo '{"ok":true}'
'''


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='svs-capture-test-')
        self.bin = os.path.join(self.tmp, 'bin')
        os.makedirs(self.bin)
        npx = os.path.join(self.bin, 'npx')
        with open(npx, 'w', encoding='utf-8', newline='\n') as f:
            f.write(STUB)
        os.chmod(npx, os.stat(npx).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.stub_log = os.path.join(self.tmp, 'stub.log')
        self.ep = os.path.join(self.tmp, 'ep')
        os.makedirs(os.path.join(self.ep, 'input'))
        shutil.copy(BRIEF, os.path.join(self.ep, 'input', 'brief.md'))
        self.ledger = os.path.join(self.ep, 'ledger')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def capture(self, **env):
        base = {'PATH': self.bin + os.pathsep + '/usr/bin' + os.pathsep + '/bin', 'STUB_LOG': self.stub_log,
                'HOME': self.tmp, 'TMPDIR': self.tmp}
        base.update(env)
        return run(['sh', CAPTURE, self.ep], env=base)

    def log(self):
        with open(os.path.join(self.ledger, 'capture-log.jsonl'), encoding='utf-8') as f:
            return [json.loads(line) for line in f if line.strip()]

    def stub_calls(self):
        if not os.path.exists(self.stub_log):
            return []
        with open(self.stub_log, encoding='utf-8') as f:
            return [line.rstrip('\n') for line in f]

    def test_extracts_urls_in_brief_order_with_stable_ids(self):
        r = self.capture()
        self.assertEqual(r.returncode, 0, r.stderr)
        sources = load(os.path.join(self.ledger, 'sources.json'))
        self.assertEqual([s['url'] for s in sources], EXPECTED)
        self.assertEqual([s['id'] for s in sources], ['S%02d' % i for i in range(1, 9)])
        log = self.log()
        self.assertEqual([x['url'] for x in log], EXPECTED)  # every URL captured: stdin was not eaten
        self.assertEqual(set(log[0]), {'id', 'url', 'secs', 'words', 'ok'})
        self.assertEqual([x['ok'] for x in log], [True] * 6 + [False, True])
        self.assertEqual(log[6]['words'], 2)
        self.assertIn('FAILED', r.stderr)

    def test_existing_ids_never_renumber_and_selected_go_first(self):
        os.makedirs(self.ledger)
        save([{'id': 'S01', 'url': 'https://example.com/c'}, {'id': 'S07', 'url': 'https://old.example/gone'}],
             os.path.join(self.ledger, 'sources.json'))
        with open(os.path.join(self.ledger, 'selected.txt'), 'w', encoding='utf-8') as f:
            f.write('example.com/d\n\n# a comment\nexample.com/b\n')
        r = self.capture(SVS_MAX_SOURCES='3')
        self.assertEqual(r.returncode, 0, r.stderr)
        ids = {s['url']: s['id'] for s in load(os.path.join(self.ledger, 'sources.json'))}
        self.assertEqual(ids['https://example.com/c'], 'S01')
        self.assertEqual(ids['https://old.example/gone'], 'S07')
        self.assertEqual(ids['https://example.com/a'], 'S08')
        self.assertEqual(ids['https://example.com/b'], 'S09')
        self.assertEqual(ids['https://example.com/d'], 'S10')
        self.assertEqual([(x['id'], x['url']) for x in self.log()],
                         [('S10', 'https://example.com/d'), ('S09', 'https://example.com/b'), ('S08', 'https://example.com/a')])
        self.assertEqual(len(self.stub_calls()), 3)

    def test_rerun_reuses_ok_captures_and_retries_failures(self):
        self.assertEqual(self.capture().returncode, 0)
        self.assertEqual(len(self.stub_calls()), 8)
        self.assertEqual(self.capture().returncode, 0)
        self.assertEqual(self.stub_calls()[8:], ['https://example.com/wall?x=1&y=2'])
        self.assertEqual(self.capture(SVS_RECAPTURE='1').returncode, 0)
        self.assertEqual(len(self.stub_calls()), 17)

    def test_no_urls_is_an_error(self):
        with open(os.path.join(self.ep, 'input', 'brief.md'), 'w', encoding='utf-8') as f:
            f.write('No links here, only example.com/plain and ftp://example.com/x.\n')
        r = self.capture()
        self.assertEqual(r.returncode, 1)
        self.assertIn('no http(s) URL', r.stderr)

    def test_all_failed_exits_nonzero(self):
        with open(os.path.join(self.ep, 'input', 'brief.md'), 'w', encoding='utf-8') as f:
            f.write('https://example.com/wall1 and https://example.com/wall2\n')
        r = self.capture()
        self.assertEqual(r.returncode, 1)
        self.assertEqual([x['ok'] for x in self.log()], [False, False])
        self.assertIn('every capture failed', r.stderr)

    def test_bad_limit_is_a_usage_error(self):
        self.assertEqual(self.capture(SVS_MAX_SOURCES='two').returncode, 2)
        self.assertEqual(run(['sh', CAPTURE]).returncode, 2)


if __name__ == '__main__':
    unittest.main()
