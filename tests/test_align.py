import os
import sys
import tempfile
import unittest

from helpers import ENGINE, EXAMPLE_AUDIO, example, load, run

import align


class CanonTests(unittest.TestCase):
    def toks(self, text):
        return [t for t, _ in align.canon(text.split())]

    def test_spoken_and_written_numbers_meet(self):
        pairs = [
            ('five hundred and twenty-two', '522'),
            ('ninety-three percent,', '93%,'),
            ('Nineteen AI', '19 AI'),
            ('October fifth to eighth.', 'October 5th to 8th.'),
            ('the twenty-first', 'the 21st'),
            ('two thousand five hundred', '2,500'),
            ('fifty-three point six percent', '53.6%'),
            ('sixteen other leads', '16 other leads'),
            ('one hundred', '100'),
            ('hundreds of tasks', '100s of tasks'),
            ('the eleventh', 'the 11th'),
            ('ninety-nine', '99'),
        ]
        for spoken, written in pairs:
            with self.subTest(spoken=spoken):
                self.assertEqual(self.toks(spoken), self.toks(written))

    def test_separate_numbers_stay_separate(self):
        self.assertEqual(self.toks('one two three'), ['1', '2', '3'])
        self.assertEqual(self.toks('five twenty'), ['5', '20'])
        self.assertEqual(self.toks('a hundred and'), ['a', '100', 'and'])

    def test_word_spans(self):
        self.assertEqual(align.canon('Sense: five hundred and twenty-two image'.split()),
                         [('sense', (0, 0)), ('522', (1, 4)), ('image', (5, 5))])
        self.assertEqual(align.canon(['93%,']), [('93', (0, 0)), ('percent', (0, 0))])

    def test_plain_words(self):
        self.assertEqual(self.toks("OpenAI's GPT-6, side-by-side"), ["openai's", 'gpt', '6', 'side', 'by', 'side'])
        self.assertEqual(self.toks('“quoted” — dash'), ['quoted', 'dash'])

    def test_ordinals(self):
        self.assertEqual([align.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 101, 111)],
                         ['1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '22nd', '101st', '111th'])


class LineEndClampTests(unittest.TestCase):
    """A line's last word may not end after the line's audio (timeline start + dur): an ASR end deep in the
    following silence kept the last caption on screen through the close hold."""
    script = {'lines': [{'id': 'L1', 'scene': 'a', 'text': 'Every source is on the page.'},
                        {'id': 'L2', 'scene': 'b', 'text': 'See you next week.'}]}
    timeline = {'lines': [{'id': 'L1', 'start': 0.35, 'dur': 2.0}, {'id': 'L2', 'start': 3.5, 'dur': 1.5}],
                'cuts': [3.14], 'total': 12.0}
    transcript = [{'text': 'Every', 'start': 0.4, 'end': 0.7}, {'text': 'source', 'start': 0.7, 'end': 1.1},
                  {'text': 'is', 'start': 1.1, 'end': 1.25}, {'text': 'on', 'start': 1.25, 'end': 1.4},
                  {'text': 'the', 'start': 1.4, 'end': 1.55}, {'text': 'page.', 'start': 1.6, 'end': 3.3},
                  {'text': 'See', 'start': 3.55, 'end': 3.8}, {'text': 'you', 'start': 3.8, 'end': 4.0},
                  {'text': 'next', 'start': 4.0, 'end': 4.3}, {'text': 'week.', 'start': 4.3, 'end': 11.6}]

    def test_word_end_clamped_to_line_audio_end(self):
        words, _ = align.align(self.script, self.transcript, self.timeline)
        by = {(x['line'], x['text']): x for x in words}
        self.assertEqual(by[('L1', 'page.')]['end'], 2.35)   # ASR said 3.3
        self.assertEqual(by[('L2', 'week.')]['end'], 5.0)    # ASR said 11.6 (deep in the close hold)
        self.assertEqual(by[('L1', 'the')]['end'], 1.55)     # inside the line: untouched
        for x in words:
            self.assertGreater(x['end'], x['start'], x)

    def test_last_caption_leaves_with_the_voice(self):
        import captions
        words, _ = align.align(self.script, self.transcript, self.timeline)
        cues = captions.build(words, self.timeline['cuts'], 42)
        self.assertEqual(cues[-1]['text'], 'See you next week.')
        self.assertLessEqual(cues[-1]['end'], 5.0 + 0.25 + 1e-6)

    def test_word_starting_at_the_line_end_keeps_a_minimum_length(self):
        tr = [dict(x) for x in self.transcript]
        tr[5] = {'text': 'page.', 'start': 2.33, 'end': 3.0}
        words, _ = align.align(self.script, tr, self.timeline)
        page = next(x for x in words if x['text'] == 'page.')
        self.assertEqual((page['start'], page['end']), (2.33, 2.41))


class AlignExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script, cls.transcript, cls.timeline = example()
        cls.words, cls.report = align.align(cls.script, cls.transcript, cls.timeline)
        cls.asr = {round(w['start'], 2): w for w in cls.transcript}

    def test_every_script_word_once_in_order(self):
        expected = [t for L in self.script['lines'] for t in L['text'].split()]
        self.assertEqual([w['text'] for w in self.words], expected)
        self.assertEqual(len(self.words), 423)

    def test_times_monotonic_and_positive(self):
        for a, b in zip(self.words, self.words[1:]):
            self.assertLessEqual(a['start'], b['start'] + 1e-6, (a, b))
        for w in self.words:
            self.assertGreater(w['end'], w['start'])

    def test_low_wer(self):
        for r in self.report:
            self.assertLessEqual(r['wer'], 0.15, r)
        self.assertEqual(sum(r['unmatched'] for r in self.report), 9)

    def test_digits_from_asr_land_on_spoken_words(self):
        by_text = {}
        for w in self.words:
            by_text.setdefault(w['text'], w)
        nineteen = by_text['Nineteen']
        self.assertEqual((nineteen['start'], nineteen['end']), (0.32, 0.96))  # ASR "19"
        fifth = by_text['fifth']
        self.assertEqual((fifth['start'], fifth['end']), (2.72, 3.12))  # ASR "5th"

    def test_multiword_number_shares_one_asr_span(self):
        i = next(k for k, w in enumerate(self.words) if w['text'] == 'five')
        run_ = self.words[i:i + 4]
        self.assertEqual([w['text'] for w in run_], ['five', 'hundred', 'and', 'twenty-two'])
        self.assertAlmostEqual(run_[0]['start'], 94.87, places=2)  # ASR "522" 94.87-96.23
        self.assertAlmostEqual(run_[-1]['end'], 96.23, places=2)
        for a, b in zip(run_, run_[1:]):
            self.assertAlmostEqual(a['end'], b['start'], places=2)
        pct = next(k for k, w in enumerate(self.words) if w['text'] == 'ninety-three')
        self.assertEqual(self.words[pct + 1]['text'], 'percent,')
        self.assertAlmostEqual(self.words[pct]['end'], self.words[pct + 1]['start'], places=2)

    def test_line_mismatch_is_an_error(self):
        tl = dict(self.timeline, lines=self.timeline['lines'][:-1])
        with self.assertRaises(SystemExit):
            align.align(self.script, self.transcript, tl)

    def test_cli_writes_utf8_words(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, 'words.json')
            r = run([sys.executable, os.path.join(ENGINE, 'align.py'), os.path.join(EXAMPLE_AUDIO, 'script.json'),
                     os.path.join(EXAMPLE_AUDIO, 'transcript.json'), os.path.join(EXAMPLE_AUDIO, 'timeline.json'), out])
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(len(load(out)), 423)


if __name__ == '__main__':
    unittest.main()
