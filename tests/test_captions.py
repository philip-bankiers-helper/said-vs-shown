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
