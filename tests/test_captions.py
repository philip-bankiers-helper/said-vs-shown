import itertools
import os
import random
import sys
import tempfile
import time
import unittest

from helpers import ENGINE, ROOT, example, load, run, save, worked_example

import align
import captions

CFG = load(os.path.join(ENGINE, 'config.json'))


def w(text, start, end):
    return {'text': text, 'start': start, 'end': end}


def even(text, start, end):
    """Words of `text` spread evenly over [start, end]."""
    toks = text.split()
    d = (end - start) / len(toks)
    return [w(t, round(start + d * i, 3), round(start + d * (i + 1), 3)) for i, t in enumerate(toks)]


def gate_fails(cues):
    return [c for c in cues if c['cps'] > CFG['max_cps'] or len(c['text']) > CFG['max_chars']]


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
        cues = captions.build(self.words(65.5), [self.CUT], 42, max_cps=0)
        q = next(c for c in cues if c['text'].startswith('What does'))
        self.assertEqual(q['start'], 65.45)
        self.check(cues)
        # at 21.3 chars/s the question borrows a little more lead from the pause before it, still after the cut
        cues = captions.build(self.words(65.5), [self.CUT], 42)
        q = next(c for c in cues if c['text'].startswith('What does'))
        self.assertTrue(65.5 - captions.BORROW_LEAD <= q['start'] < 65.45, q)
        self.assertLessEqual(q['cps'], 21)
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


class ReliefTests(unittest.TestCase):
    """A cue over max_cps borrows what its neighbours can spare, so a tenth or two of ASR jitter cannot fail the
    reading-speed gate (Whisper put 'Here's what it proves,' at 22.2 chars/s; Parakeet, on the same audio, 19.6)."""

    def words(self, here_start=6.25):
        a = [w(t, 3.7 + 0.24 * i, 3.7 + 0.24 * (i + 1)) for i, t in enumerate('One of them passed a test you can check.'.split())]
        b = [w(t, here_start + 0.245 * i, here_start + 0.245 * (i + 1)) for i, t in enumerate("Here's what it proves,".split())]
        c = [w(t, 7.24 + 0.3 * i, 7.24 + 0.3 * (i + 1)) for i, t in enumerate('and where the evidence stops.'.split())]
        return a + b + c

    def test_jitter_is_absorbed_by_neighbours(self):
        plain = captions.build(self.words(), [], 42, max_cps=0)  # 0: no relief
        self.assertGreater(plain[1]['cps'], 21)
        cues = captions.build(self.words(), [], 42, max_cps=21)
        self.assertEqual([c['text'] for c in cues], [c['text'] for c in plain])
        for c in cues:
            self.assertLessEqual(c['cps'], 21, c)
        here = cues[1]
        self.assertGreaterEqual(here['start'], 6.25 - captions.BORROW_LEAD - 1e-9)  # at most 0.3 s before its first word
        self.assertLess(here['start'], plain[1]['start'])
        self.assertLessEqual(cues[0]['end'], here['start'])  # it took the pause first, the previous cue kept its time
        self.assertEqual(cues[2]['start'], plain[2]['start'])  # the lead was enough: the next cue is untouched
        for a, b in zip(cues, cues[1:]):
            self.assertLessEqual(a['end'], b['start'] + 1e-9)

    def test_never_across_its_own_cut_and_a_short_lag_only(self):
        cut = 6.2  # the scene opens just before 'Here's': no lead available
        cues = captions.build(self.words(), [cut], 42, max_cps=21)
        here = cues[1]
        self.assertEqual(here['start'], cut)
        self.assertLessEqual(cues[0]['end'], cut)
        self.assertLessEqual(cues[2]['start'], 7.24 + captions.BORROW_LAG + 1e-9)  # the next cue lags its word <= 0.1 s
        self.assertLessEqual(here['cps'], 21.0)

    def test_genuinely_fast_speech_still_fails(self):
        fast = [w("Here's", 6.0, 6.1), w('what', 6.1, 6.2), w('it', 6.2, 6.3), w('proves,', 6.3, 6.4)] + \
               [w(t, 6.4 + 0.1 * i, 6.5 + 0.1 * i) for i, t in enumerate('and where the evidence stops right here.'.split())]
        cues = captions.build(fast, [], 42, max_cps=21)
        self.assertTrue(any(c['cps'] > 21 for c in cues))

    def test_no_op_without_violations(self):
        script, transcript, timeline = example()
        words, _ = align.align(script, transcript, timeline)
        self.assertEqual(captions.build(words, timeline['cuts'], 42, script['display'], 21),
                         captions.build(words, timeline['cuts'], 42, script['display'], 0))


def fast_clause(second):
    """One clause longer than 42 characters, spoken fast, between a slow line and a scene cut (4.85-4.9 s)."""
    return (even('Every source is on the page today,', 0.3, 2.6) + even('and that the statement', 3.0, 3.95) +
            even(second, 4.0, 4.75) + even('Next scene starts here.', 5.0, 6.5))


class ChainReliefTests(unittest.TestCase):
    """A fast cue next to another fast cue: the slack of the slow cue before them reaches the second one through the
    first (which starts earlier itself), and as a last resort a cue may start up to LAST_LEAD before its first word."""

    def check(self, cues, words, cuts):
        firsts = {}
        for c in cues:
            first = next(x for x in words if c['text'].split()[0] == x['text'] and x['start'] >= c['start'] - 1.0)
            firsts[c['text']] = first['start']
            self.assertGreaterEqual(c['start'], first['start'] - captions.LAST_LEAD - 1e-9, c)
            for cut in cuts:
                self.assertFalse(c['start'] < cut - 1e-6 < c['end'] - 2e-6, (c, cut))
        for a, b in zip(cues, cues[1:]):
            self.assertLessEqual(a['end'], b['start'] + 1e-9, (a, b))
        return firsts

    def test_slack_passes_through_a_fast_neighbour(self):
        words, cuts = fast_clause('matches the paper claim.'), [4.9]
        cues = captions.build(words, cuts, 42)
        self.assertEqual(gate_fails(cues), [])
        firsts = self.check(cues, words, cuts)
        for c in cues:  # the usual 0.3 s lead was enough: no last resort
            self.assertGreaterEqual(c['start'], firsts[c['text']] - captions.BORROW_LEAD - 1e-9, c)
        self.assertLess(cues[1]['start'], 3.0 - captions.LEAD - 1e-6)  # the first fast cue moved to make room
        relieve = captions.relieve
        try:  # relief limited to direct neighbours (the earlier rule) leaves the second fast cue over the gate
            captions.relieve = lambda *a, **k: relieve(*a, depth=0)
            self.assertTrue(gate_fails(captions.build(words, cuts, 42)))
        finally:
            captions.relieve = relieve

    def test_last_resort_lead_is_bounded(self):
        words, cuts = fast_clause("matches the paper's claim."), [4.85]
        cues = captions.build(words, cuts, 42)
        self.assertEqual(gate_fails(cues), [])
        firsts = self.check(cues, words, cuts)
        self.assertTrue(any(c['start'] < firsts[c['text']] - captions.BORROW_LEAD - 1e-6 for c in cues), cues)
        last = captions.LAST_LEAD
        try:
            captions.LAST_LEAD = captions.BORROW_LEAD
            self.assertTrue(gate_fails(captions.build(words, cuts, 42)))
        finally:
            captions.LAST_LEAD = last


class ReadingSpeedSplitTests(unittest.TestCase):
    """Chunking aims at max_cps - 2: words spoken faster than that, which relief could not bring to it, become up to
    4 cues with their boundaries placed by reading speed, never a cue under MIN_PART."""

    def test_boundary_placed_by_reading_speed(self):
        words = fast_clause("matches the paper's claim.")
        texts = [c['text'] for c in captions.build(words, [4.85], 42)]
        self.assertEqual(texts, ['Every source is on the page today,', 'and that the statement matches',
                                 "the paper's claim.", 'Next scene starts here.'])
        plain = captions.build(words, [4.85], 42, target_cps=0)  # 0: the usual character-balanced split only
        self.assertEqual([c['text'] for c in plain][1:3], ['and that the statement', "matches the paper's claim."])

    def test_no_change_when_relief_reaches_the_target(self):
        for s, tr, tl in (example(), worked_example('parakeet'), worked_example('whisper')):
            words, _ = align.align(s, tr, tl)
            self.assertEqual([c['text'] for c in captions.build(words, tl['cuts'], 42, s['display'])],
                             [c['text'] for c in captions.build(words, tl['cuts'], 42, s['display'], target_cps=0)])

    def test_fast_split_parts(self):
        c = even('one two three four five six seven eight nine ten', 0.0, 1.6)  # 48 chars in 1.6 s
        parts = captions.fast_split(c, [c[:5], c[5:]], 42, 19, -0.3, 1.7)
        self.assertTrue(2 <= len(parts) <= captions.MAX_SPLIT, parts)
        self.assertEqual([x for p in parts for x in p], c)
        for p, d in zip(parts, captions.predicted(parts)):
            self.assertLessEqual(len(captions.text(p)), 42)
            self.assertGreaterEqual(d, captions.MIN_PART)
        slow = even('one two three four five', 0.0, 3.0)
        self.assertIs(captions.fast_split(slow, [slow], 42, 19, -0.3, 3.2)[0], slow)  # relief reaches 19: unchanged


class ShortCueMergeTests(unittest.TestCase):
    def test_a_cue_under_half_a_second_merges(self):
        words = [w('Quick.', 0.0, 0.2)] + even('Then more follows.', 0.3, 1.0)
        cues = captions.build(words, [], 42)
        self.assertEqual([c['text'] for c in cues], ['Quick. Then more follows.'])
        self.assertGreaterEqual(cues[0]['end'] - cues[0]['start'], captions.MIN_CUE)

    def test_never_across_a_cut(self):
        words = [w('Quick.', 0.0, 0.2)] + even('Then more follows.', 0.3, 1.0)
        cues = captions.build(words, [0.28], 42)
        self.assertEqual([c['text'] for c in cues], ['Quick.', 'Then more follows.'])
        self.assertLessEqual(cues[0]['end'], 0.28)


class ShortCueLengthenTests(unittest.TestCase):
    """A one-word scene ("Five." spoken 2.3-2.6 s between cuts at 1.94 and next line - 0.36): its cue cannot merge
    across either cut, so it starts earlier, back to its own scene cut and at most LAST_LEAD before its word, until it
    lasts 0.5 s; a scene too short for that keeps the cue at the whole scene. It used to stay at 0.29 s (gap 0.3)."""

    def build(self, gap):
        nxt = 2.6 + gap
        cuts = [1.94, round(nxt - 0.36, 2)]
        words = [w('That', 0.35, 0.7), w('ships', 0.7, 1.1), w('today.', 1.1, 1.6), w('Five.', 2.3, 2.6),
                 w('Next', nxt, nxt + 0.3), w('scene', nxt + 0.3, nxt + 0.6), w('here.', nxt + 0.6, nxt + 1.0)]
        cues = captions.build(words, cuts, 42)
        for a, b in zip(cues, cues[1:]):
            self.assertLessEqual(a['end'], b['start'] + 1e-9, (a, b))
        for c in cues:
            for x in cuts:
                self.assertFalse(c['start'] < x - 1e-6 < c['end'] - 2e-6, (c, x))
        return next(c for c in cues if c['text'] == 'Five.'), cuts

    def test_starts_earlier_to_reach_half_a_second(self):
        for gap in (0.3, 0.5):
            five, cuts = self.build(gap)
            self.assertGreaterEqual(round(five['end'] - five['start'], 3), captions.MIN_PART, (gap, five))
            self.assertGreaterEqual(five['start'], cuts[0])  # never before its own scene cut
            self.assertGreaterEqual(five['start'], 2.3 - captions.LAST_LEAD - 1e-9)
            self.assertLessEqual(five['end'], cuts[1])
            self.assertEqual(five['cps'], round(5 / (five['end'] - five['start']), 1))

    def test_a_scene_too_short_keeps_what_it_gives(self):
        five, cuts = self.build(0.1)  # the scene lasts 0.4 s: the cue is the whole scene
        self.assertEqual((five['start'], five['end']), (cuts[0], cuts[1]))

    def test_no_change_without_short_cues(self):
        lengthen = captions.lengthen
        for s, tr, tl in (example(), worked_example('whisper')):
            words, _ = align.align(s, tr, tl)
            cues = captions.build(words, tl['cuts'], 42, s['display'])
            try:
                captions.lengthen = lambda cues, *a, **k: cues
                self.assertEqual(captions.build(words, tl['cuts'], 42, s['display']), cues)
            finally:
                captions.lengthen = lengthen

    def test_docs_say_where_the_scene_allows(self):
        self.assertIn('≥0.5 s where the scene allows', captions.__doc__)
        with open(os.path.join(ROOT, 'skills', 'said-vs-shown', 'references', 'editorial.md'), encoding='utf-8') as f:
            self.assertIn('≥0.5 s where the scene allows', f.read())


class EqualStartTests(unittest.TestCase):
    """Two cues whose first words open just after one cut both clamp to that cut; the earlier rule gave the first one
    zero length. Cue starts now rise by at least 1 ms."""

    def test_cues_opening_on_one_cut(self):
        cues = [{'text': 'Twenty-four was the year;', 'start': 5.01, 'end': 5.02},
                {'text': 'five hundred and twenty-two', 'start': 5.02, 'end': 5.03},
                {'text': 'people said so.', 'start': 5.6, 'end': 6.0}]
        captions.time_cues(cues, [5.0])
        self.assertEqual([c['start'] for c in cues][:2], [5.0, 5.001])
        for c in cues:
            self.assertGreater(c['end'], c['start'], c)


class JitterRegressionTests(unittest.TestCase):
    """The round-3 verifier's jitter model (each ASR word's start + N(0, sigma), its length + N(0, sigma / 2)), seeded:
    the caption gate holds on the worked example's Whisper transcript at sigma 0.05 and 0.1 s and on its Parakeet
    transcript at 0.2 s, and on episode 1's Parakeet transcript at 0.2 s (it failed 15 %, 26.5 %, 6.5 % and 20.5 % of
    200 trials before chain relief, the last-resort lead, the reading-speed split and the collapse spread)."""

    def run_trials(self, data, sigma, n):
        s, tr, tl = data
        rnd, fails = random.Random(42), []
        for trial in range(n):
            noisy = [dict(a) for a in tr]
            for a in noisy:
                d = a['end'] - a['start']
                a['start'] += rnd.gauss(0, sigma)
                a['end'] = a['start'] + max(0.0, d + rnd.gauss(0, sigma / 2))
            words, _ = align.align(s, noisy, tl)
            cues = captions.build(words, tl['cuts'], CFG['max_chars'], s['display'], CFG['max_cps'])
            for c in cues:
                self.assertGreaterEqual(c['end'] - c['start'], captions.MIN_PART - 1e-9, (trial, c))
            for a, b in zip(cues, cues[1:]):
                self.assertLessEqual(a['end'], b['start'] + 1e-9, (trial, a, b))
            if gate_fails(cues):
                fails.append((trial, gate_fails(cues)))
        return fails

    def test_whisper_up_to_a_tenth_of_a_second(self):
        for sigma in (0.05, 0.1):
            self.assertEqual(self.run_trials(worked_example('whisper'), sigma, 100), [], sigma)

    def test_parakeet_at_two_tenths(self):
        self.assertEqual(self.run_trials(worked_example('parakeet'), 0.2, 100), [])
        self.assertLessEqual(len(self.run_trials(example(), 0.2, 60)), 1)


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

    def test_balanced_is_the_exhaustive_optimum(self):
        """The dynamic-programming split gives exactly what trying every split gave (the earlier rule): the shortest
        longest part + 8 per stranded function word, earliest cuts on a tie."""
        def exhaustive(ws, n):
            best = None
            for cut in itertools.combinations(range(1, len(ws)), n - 1):
                parts = [ws[i:j] for i, j in zip((0,) + cut, cut + (len(ws),))]
                m = max(len(captions.text(p)) for p in parts) + 8 * sum(captions.stranded(p) for p in parts[:-1])
                if best is None or m < best[0]:
                    best = (m, parts)
            return best[1]
        rnd = random.Random(5)
        vocab = ['the', 'a', 'of', 'to', 'and', 'at', 'it', 'model', 'proof', 'Lean,', 'benchmark', 'x', 'GPT-6', '93%']
        for trial in range(250):
            ws = [w(rnd.choice(vocab) if rnd.random() < 0.7 else 'w' * rnd.randint(1, 12), 0, 0)
                  for _ in range(rnd.randint(1, 10))]
            for n in range(1, len(ws) + 1):
                self.assertEqual(captions.balanced(ws, n), exhaustive(ws, n), (trial, n, captions.text(ws)))

    def test_long_unpunctuated_clause_is_fast(self):
        """45 words took 90 s and 50 more than 200 s (every split tried); voice.py looked hung."""
        vocab = ('the model passed a test that anyone can check because the proof is written in a formal language '
                 'and the checker accepts it').split()
        for n in (45, 60):
            text = ' '.join(vocab[i % len(vocab)] for i in range(n)) + '.'
            ws = even(text, 0.35, 0.35 + (len(text) + 1) / 15.0)
            t0 = time.perf_counter()
            cues = captions.build(ws, [], 42)
            self.assertLess(time.perf_counter() - t0, 1.0, n)
            self.assertEqual(' '.join(c['text'] for c in cues), text)
            self.assertTrue(all(len(c['text']) <= 42 for c in cues))
            self.assertEqual(gate_fails(cues), [])

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
