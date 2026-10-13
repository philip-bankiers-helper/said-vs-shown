import os
import sys
import tempfile
import unittest

from helpers import ENGINE, example, load, run, save

import align
import captions


def w(text, start, end):
    return {'text': text, 'start': start, 'end': end}


class CaptionsExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script, transcript, cls.timeline = example()
        cls.words, _ = align.align(cls.script, transcript, cls.timeline)
        cls.cuts = cls.timeline['cuts']
        cls.cues = captions.build(cls.words, cls.cuts, 42, cls.script['display'])

    def test_one_line_cues_within_limits(self):
        self.assertGreater(len(self.cues), 80)
        for c in self.cues:
            self.assertLessEqual(len(c['text']), 42, c)
            self.assertLessEqual(c['cps'], 21, c)
            self.assertGreaterEqual(c['end'] - c['start'], 0.5, c)

    def test_no_cue_crosses_a_scene_cut(self):
        for c in self.cues:
            for cut in self.cuts:
                self.assertFalse(c['start'] < cut - 1e-6 and c['end'] > cut + 1e-6, (c, cut))

    def test_cues_do_not_overlap(self):
        for a, b in zip(self.cues, self.cues[1:]):
            self.assertLessEqual(a['end'], b['start'] + 1e-6, (a, b))

    def test_text_comes_from_script_with_display_forms(self):
        texts = [c['text'] for c in self.cues]
        self.assertEqual(texts[0], '19 AI developments,')
        self.assertEqual(texts[1], 'October 5 to 8.')
        joined = ' '.join(texts)
        self.assertIn('522', joined)
        self.assertIn('93%', joined)
        self.assertNotIn('five hundred and twenty-two', joined)

    def test_clause_first_and_no_stranded_function_word(self):
        for c in self.cues[:-1]:
            last = c['text'].split()[-1].lower().strip(',.')
            self.assertNotIn(last, {'the', 'a', 'an', 'of', 'to'}, c)


class SceneCutLeadTests(unittest.TestCase):
    """A cue that starts just after a scene cut keeps its lead on its own side of the cut (the 0.02 s flash of
    "What does the release establish?" at 65.02-65.04 when L5 ran at speed 1.1)."""
    CUT = 65.04

    def words(self, first_start):
        prev = [w('That', 63.1, 63.4), w('ships', 63.4, 63.8), w('today.', 63.8, 64.3)]
        q = ['What', 'does', 'the', 'release', 'establish?']
        nxt = [w(t, first_start + 0.3 * i, first_start + 0.3 * i + 0.28) for i, t in enumerate(q)]
        return prev + nxt + [w('Shipping.', 67.0, 67.6)]

    def check(self, cues):
        for c in cues:
            self.assertGreaterEqual(round(c['end'] - c['start'], 3), 0.83, c)
            self.assertFalse(c['start'] < self.CUT - 1e-6 < c['end'] - 2e-6, (c, 'crosses the cut'))
        for a, b in zip(cues, cues[1:]):
            self.assertLessEqual(a['end'], b['start'] + 1e-6, (a, b))

    def test_lead_never_crosses_its_own_cut(self):
        cues = captions.build(self.words(65.07), [self.CUT], 42)
        q = next(c for c in cues if c['text'].startswith('What does'))
        self.assertEqual(q['start'], self.CUT)
        self.assertGreater(q['end'], 66.0)
        self.check(cues)
        self.assertLessEqual(cues[0]['end'], self.CUT)

    def test_full_lead_when_the_cut_is_further_back(self):
        cues = captions.build(self.words(65.5), [self.CUT], 42)
        q = next(c for c in cues if c['text'].startswith('What does'))
        self.assertEqual(q['start'], 65.45)
        self.check(cues)

    def test_cue_exactly_on_the_cut(self):
        cues = captions.build(self.words(self.CUT), [self.CUT], 42)
        q = next(c for c in cues if c['text'].startswith('What does'))
        self.assertEqual(q['start'], self.CUT)
        self.check(cues)

    def test_cli_on_a_synthetic_words_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'words.json')
            save(self.words(65.07), p)
            r = run([sys.executable, os.path.join(ENGINE, 'captions.py'), p, d, '--cuts', '9.33,%s' % self.CUT, '--strict'])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            cues = load(os.path.join(d, 'cues.json'))
            self.check(cues)
            with open(os.path.join(d, 'captions.vtt'), encoding='utf-8') as f:
                self.assertIn('00:01:05.040 --> ', f.read())


class DisplayMapTests(unittest.TestCase):
    def test_word_boundaries_only(self):
        cues = [{'text': 'someone said one thing, oneness'}]
        captions.apply_display(cues, {'one': '1'})
        self.assertEqual(cues[0]['text'], 'someone said 1 thing, oneness')

    def test_single_pass_longest_first(self):
        cues = [{'text': 'from the eighth to October ninth'}]
        captions.apply_display(cues, {'from the eighth': 'from October 8', 'October': 'Oct', 'eighth': '8th'})
        self.assertEqual(cues[0]['text'], 'from October 8 to Oct ninth')

    def test_punctuation_after_phrase(self):
        cues = [{'text': 'ninety-three percent, and'}]
        captions.apply_display(cues, {'ninety-three percent': '93%'})
        self.assertEqual(cues[0]['text'], '93%, and')

    def test_display_fn_is_the_same_rule_for_plain_text(self):
        fn = captions.display_fn({'Said versus Shown': 'Said vs. Shown', 'one': '1'})
        self.assertEqual(fn("That's Said versus Shown, someone said one."), "That's Said vs. Shown, someone said 1.")
        self.assertEqual(captions.display_fn({})('as is'), 'as is')
        self.assertEqual(captions.display_fn(None)('as is'), 'as is')


class ChunkingTests(unittest.TestCase):
    def test_balanced_split_of_a_long_clause(self):
        text = 'the quick brown fox jumps over the lazy dog and keeps running far away from here'
        ws = [w(t, i * 0.3, i * 0.3 + 0.25) for i, t in enumerate(text.split())]
        cues = captions.build(ws, [], 42)
        self.assertGreater(len(cues), 1)
        self.assertTrue(all(len(c['text']) <= 42 for c in cues))
        self.assertEqual(' '.join(c['text'] for c in cues), text)

    def test_single_overlong_word_does_not_crash(self):
        cues = captions.build([w('x' * 50, 0.0, 1.0)], [], 42)
        self.assertEqual(len(cues), 1)

    def test_timestamps_round_up_cleanly(self):
        self.assertEqual(captions.ts(1.9996, ','), '00:00:02,000')
        self.assertEqual(captions.ts(3725.5, '.'), '01:02:05.500')

    def test_cli_strict_fails_on_fast_cue(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'words.json')
            save([w('Extraordinarily', 0.0, 0.2), w('fast.', 0.2, 0.4), w('Then', 0.45, 0.5), w('more.', 0.5, 0.6)], p)
            cmd = [sys.executable, os.path.join(ENGINE, 'captions.py'), p, d, '--cuts', '']
            ok = run(cmd)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertTrue(os.path.exists(os.path.join(d, 'captions.vtt')))
            self.assertTrue(load(os.path.join(d, 'cues.json')))
            strict = run(cmd + ['--strict'])
            self.assertEqual(strict.returncode, 1)


if __name__ == '__main__':
    unittest.main()
