import json
import os
import random
import sys
import tempfile
import unittest

from helpers import ENGINE, EXAMPLE_AUDIO, ROOT, WORKED_AUDIO, example, load, run, worked_example

import align
import captions

CFG = load(os.path.join(ENGINE, 'config.json'))


def windows(timeline):
    """{line id: (lo, end)}: lo = start - LEAD, never before the previous line's audio end."""
    out, prev_end = {}, 0.0
    for T in timeline['lines']:
        end = T['start'] + T['dur']
        out[T['id']] = (min(T['start'], max(T['start'] - align.LEAD, prev_end, 0.0)), end)
        prev_end = end
    return out


def check_guarantees(tc, words, timeline):
    """What align() promises for any transcript, however wrong its times."""
    win = windows(timeline)
    order = [T['id'] for T in timeline['lines']]
    for a, b in zip(words, words[1:]):
        tc.assertLessEqual(a['start'], b['start'], (a, b))  # starts never decrease
    for w in words:
        lo, end = win[w['line']]
        tc.assertGreaterEqual(w['start'], lo - 1e-9, w)  # inside its own line's window
        tc.assertLessEqual(w['start'], end + 1e-9, w)
        tc.assertGreaterEqual(round(w['end'] - w['start'], 3), align.MIN_DUR, w)
        # an end after the line's audio only when the minimum length needs it
        tc.assertTrue(w['end'] <= end + 1e-9 or abs(w['end'] - w['start'] - align.MIN_DUR) < 2e-3, w)
        i = order.index(w['line'])
        if i + 1 < len(order):
            tc.assertLessEqual(w['end'], win[order[i + 1]][0] + 1e-9, w)  # never into the next line's window


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

    def test_guarantees(self):
        check_guarantees(self, self.words, self.timeline)

    def test_parakeet_fixture_unchanged_or_better(self):
        # words-per-line.json: this fixture aligned by the earlier per-line search (ASR words from start - 0.6 s)
        before = load(os.path.join(EXAMPLE_AUDIO, 'words-per-line.json'))
        self.assertEqual([b[0] for b in before], [w['text'] for w in self.words])
        moved = [(b, w) for b, w in zip(before, self.words) if (b[1], b[2]) != (w['start'], w['end'])]
        self.assertLessEqual(len(moved), 3, moved)
        for b, w in moved:
            # only a line's first word that Parakeet put more than LEAD before the line: moved to the window edge,
            # i.e. a hundredth of a second closer to the voice (each take starts speaking ~0.04 s in)
            line = next(T for T in self.timeline['lines'] if T['id'] == w['line'])
            self.assertEqual(w['start'], round(line['start'] - align.LEAD, 3), (b, w))
            self.assertGreater(w['start'], b[1])
            self.assertLessEqual(w['start'] - b[1], 0.0111)
            self.assertEqual(w['end'], b[2])

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


class WhisperWorkedExampleTests(unittest.TestCase):
    """The worked example (references/example) through Whisper small.en, the ASR a fresh install uses (Parakeet only
    after setup.sh --with-parakeet). Whisper puts a line's first words up to ~1 s early and the close's last words
    ~1.7 s late. The per-line search (ASR words from start - 0.6 s) failed voice.py's caption gate 7 times here: a
    cue that ended before it started ('One' 35.901 -> 35.44), a 49.5 chars/s cue ('So the next time an AI'), and
    ASR jitter on cues Parakeet already puts at ~20 chars/s."""

    @classmethod
    def setUpClass(cls):
        cls.script, cls.transcript, cls.timeline = worked_example('whisper')
        cls.words, cls.report = align.align(cls.script, cls.transcript, cls.timeline)
        cls.cues = captions.build(cls.words, cls.timeline['cuts'], CFG['max_chars'], cls.script['display'], CFG['max_cps'])

    def test_fixture_is_the_shipped_example(self):
        shipped = load(os.path.join(ROOT, 'skills', 'said-vs-shown', 'references', 'example', 'video', 'audio', 'script.json'))
        self.assertEqual(self.script, shipped, 'the example script changed: re-voice it and regenerate tests/fixtures/worked-example')
        self.assertEqual([T['id'] for T in self.timeline['lines']], [L['id'] for L in shipped['lines']])

    def test_every_script_word_once_and_matched(self):
        self.assertEqual([w['text'] for w in self.words], [t for L in self.script['lines'] for t in L['text'].split()])
        self.assertEqual(sum(r['unmatched'] for r in self.report), 0)  # the per-line search missed 4
        self.assertEqual(sum(r['asr_words'] for r in self.report), len(self.transcript))

    def test_guarantees(self):
        check_guarantees(self, self.words, self.timeline)

    def test_passes_the_caption_gate(self):
        for c in self.cues:
            self.assertGreater(c['end'], c['start'], c)
            self.assertLessEqual(len(c['text']), CFG['max_chars'], c)
            self.assertLessEqual(c['cps'], CFG['max_cps'], c)
        texts = [c['text'] for c in self.cues]
        self.assertIn('One result, one kind of test.', texts)  # not 'One' / 'result,' split across a scene cut
        self.assertIn('So the next time an AI', texts)

    def test_early_and_late_lines_are_refitted(self):
        refit = {r['line']: r['refit'] for r in self.report}
        self.assertGreater(refit['L4-payoff'][0], 0.9)    # Whisper: 'One' at 34.88, the line starts at 35.951
        self.assertGreater(refit['L5-onething'][0], 0.8)  # 'So' at 44.00, the line starts at 44.836
        self.assertLess(refit['L6-close'][1], -1.5)       # 'page.' at 58.19, the line's audio ends at 56.964
        self.assertEqual(refit['L1-squeeze'], [0.0, 0.0])
        first = {}
        for w in self.words:
            first.setdefault(w['line'], w)
        for T in self.timeline['lines']:
            self.assertGreaterEqual(first[T['id']]['start'], T['start'] - align.LEAD, first[T['id']])

    def test_agrees_with_parakeet_on_the_same_audio(self):
        s, tr, tl = worked_example('parakeet')
        pk, _ = align.align(s, tr, tl)
        diffs = [abs(a['start'] - b['start']) for a, b in zip(self.words, pk)]
        self.assertLess(sum(diffs) / len(diffs), 0.25)  # raw Whisper vs Parakeet: up to 1.76 s apart
        firsts = [(a, b) for a, b, prev in zip(self.words[1:], pk[1:], self.words) if a['line'] != prev['line']]
        for a, b in firsts:
            self.assertLess(abs(a['start'] - b['start']), 0.35, (a, b))

    def test_cli_gate_exits_0(self):
        # what voice.py runs: align.py, then captions.py with the config limits (voice.py fails on any violation)
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, 'words.json')
            r = run([sys.executable, os.path.join(ENGINE, 'align.py'), os.path.join(WORKED_AUDIO, 'script.json'),
                     os.path.join(WORKED_AUDIO, 'transcript-whisper.json'), os.path.join(WORKED_AUDIO, 'timeline.json'), out])
            self.assertEqual(r.returncode, 0, r.stderr)
            r = run([sys.executable, os.path.join(ENGINE, 'captions.py'), out, d, '--strict',
                     '--cuts', ','.join(map(str, self.timeline['cuts'])), '--display', os.path.join(WORKED_AUDIO, 'script.json')])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(json.loads(r.stdout)['violations'], [])


def synth(texts, gap=0.8, rate=0.3, lead_in=0.35):
    """A script, its timeline and a perfect transcript: every word lasts `rate` seconds, lines `gap` apart."""
    script = {'lines': [{'id': 'L%d' % (i + 1), 'scene': 's%d' % i, 'text': t} for i, t in enumerate(texts)]}
    tl, tr, t = {'lines': [], 'cuts': []}, [], lead_in
    for L in script['lines']:
        toks = L['text'].split()
        tl['lines'].append({'id': L['id'], 'start': round(t, 3), 'dur': round(rate * len(toks), 3)})
        for k, tok in enumerate(toks):
            tr.append({'text': tok, 'start': round(t + rate * k, 3), 'end': round(t + rate * (k + 1), 3)})
        t += rate * len(toks) + gap
    tl['cuts'] = [round(T['start'] - 0.36, 2) for T in tl['lines'][1:]]
    return script, tr, tl


class RobustnessTests(unittest.TestCase):
    """Whatever the ASR gets wrong, every word stays in its own line's window, in order, and at least MIN_DUR long."""
    TEXTS = ['Three results, three different tests, and the evidence stops here.',
             'The result is new, or the result is checked, or the statement is the claim.',
             'That is the episode, and the sources are on the companion page.']

    def setUp(self):
        self.script, self.tr, self.tl = synth(self.TEXTS)

    def by_line(self, words):
        out = {}
        for w in words:
            out.setdefault(w['line'], []).append(w)
        return out

    def test_perfect_transcript_is_kept(self):
        words, rep = align.align(self.script, self.tr, self.tl)
        self.assertEqual([(w['start'], w['end']) for w in words], [(a['start'], a['end']) for a in self.tr])
        self.assertEqual([r['refit'] for r in rep], [[0.0, 0.0]] * 3)

    def test_early_line_starts_like_whisper(self):
        tr = [dict(a) for a in self.tr]
        for T in self.tl['lines'][1:]:  # the first 4 words of lines 2 and 3 start 0.9 s early, into the gap
            k = next(i for i, a in enumerate(tr) if a['start'] >= T['start'] - 1e-6)
            for a in tr[k:k + 4]:
                a['start'] = round(a['start'] - 0.9 + 0.2 * (a is not tr[k]), 3)
                a['end'] = round(a['end'] - 0.7, 3)
        words, rep = align.align(self.script, tr, self.tl)
        check_guarantees(self, words, self.tl)
        self.assertEqual(sum(r['unmatched'] for r in rep), 0)
        lines = self.by_line(words)
        for T in self.tl['lines'][1:]:
            self.assertAlmostEqual(lines[T['id']][0]['start'], T['start'], places=2)  # refitted onto the voice

    def test_late_line_end_stays_in_its_line(self):
        end1 = self.tl['lines'][0]['start'] + self.tl['lines'][0]['dur']
        for late in (0.7, 1.5):  # the last 3 words of line 1 drift late: past its audio, then past line 2's start
            tr = [dict(a) for a in self.tr]
            for a in tr:
                if end1 - 0.95 < a['start'] < end1:
                    a['start'], a['end'] = round(a['start'] + late, 3), round(a['end'] + late, 3)
            words, rep = align.align(self.script, tr, self.tl)
            check_guarantees(self, words, self.tl)
            self.assertEqual(self.by_line(words)['L1'][-1]['text'], 'here.')
            if late < 0.8:  # still before line 2's words: all matched, line 1 refitted onto its audio
                self.assertEqual(sum(r['unmatched'] for r in rep), 0)
                self.assertLess(rep[0]['refit'][1], -0.6)
            else:  # crossing line 2's first words: a monotonic alignment drops the crossing ones, they are spread
                self.assertLessEqual(sum(r['unmatched'] for r in rep), 3)

    def test_a_line_the_asr_missed_is_spread_over_its_own_audio(self):
        T = self.tl['lines'][1]
        tr = [a for a in self.tr if not T['start'] - 1e-6 <= a['start'] < T['start'] + T['dur']]
        words, rep = align.align(self.script, tr, self.tl)
        check_guarantees(self, words, self.tl)
        line2 = self.by_line(words)['L2']
        self.assertEqual(rep[1]['unmatched'], len(line2))
        self.assertAlmostEqual(line2[0]['start'], T['start'], places=3)
        self.assertAlmostEqual(line2[-1]['end'], T['start'] + T['dur'], places=3)
        self.assertEqual([(w['start'], w['end']) for w in self.by_line(words)['L3']],
                         [(a['start'], a['end']) for a in self.tr if a['start'] >= self.tl['lines'][2]['start'] - 1e-6])

    def test_unsorted_asr_with_a_hallucinated_word(self):
        tr = [dict(a) for a in self.tr] + [{'text': 'Subscribe!', 'start': 2.0, 'end': 2.2}]
        random.Random(7).shuffle(tr)
        words, _ = align.align(self.script, tr, self.tl)
        self.assertEqual(words, align.align(self.script, self.tr, self.tl)[0])

    def test_random_jitter_keeps_the_guarantees(self):
        rnd = random.Random(2026)
        expected = [t for s in self.TEXTS for t in s.split()]
        for trial in range(150):
            script, tr, tl = synth(self.TEXTS, gap=rnd.choice([0.0, 0.3, 0.5, 0.8]), rate=rnd.uniform(0.2, 0.4))
            noisy = []
            for a in tr:
                if rnd.random() < 0.1:
                    continue  # dropped
                s = a['start'] + rnd.uniform(-1.2, 1.2)
                noisy.append({'text': a['text'] if rnd.random() > 0.05 else 'uh', 'start': s,
                              'end': s + rnd.uniform(0.0, 0.6)})
            words, rep = align.align(script, noisy, tl)
            self.assertEqual([w['text'] for w in words], expected, trial)
            check_guarantees(self, words, tl)


if __name__ == '__main__':
    unittest.main()
