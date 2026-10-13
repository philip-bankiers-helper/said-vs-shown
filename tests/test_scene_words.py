import os
import sys
import tempfile
import unittest

from helpers import ENGINE, example, load, run, save

import align
import scene_words


class SceneWordsExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script, transcript, cls.timeline = example()
        cls.words, _ = align.align(cls.script, transcript, cls.timeline)
        cls.out = scene_words.slice_words(cls.script, cls.timeline, cls.words, hold=0.12)

    def test_scene_ids_from_script_in_order(self):
        self.assertEqual(list(self.out), [L['scene'] for L in self.script['lines']])

    def test_bounds_follow_cuts_and_hold(self):
        cuts = self.timeline['cuts']
        starts = [v['global_start'] for v in self.out.values()]
        self.assertEqual(starts, [0.0] + cuts)
        total = sum(v['duration'] for v in self.out.values())
        self.assertAlmostEqual(total, self.timeline['total'] + 0.12, delta=0.03)
        self.assertEqual(self.out['close']['duration'], 12.43)

    def test_words_are_local_and_complete(self):
        self.assertEqual(sum(len(v['words']) for v in self.out.values()), 423)
        for sc, v in self.out.items():
            self.assertEqual(set(v['words'][0]), {'t', 's', 'e'})
            self.assertGreaterEqual(v['words'][0]['s'], 0.0, sc)
            self.assertLess(v['words'][0]['s'], 1.0, sc)
            self.assertLessEqual(v['words'][-1]['s'], v['duration'], sc)
        first = self.out['math-receipt']['words'][0]
        self.assertEqual(first['t'], 'First,')
        self.assertAlmostEqual(first['s'], 0.19, places=2)


class SceneWordsRulesTests(unittest.TestCase):
    script = {'lines': [{'id': 'L1', 'scene': 'a', 'text': 'One two.'},
                        {'id': 'L2', 'scene': 'a', 'text': 'Three.'},
                        {'id': 'L3', 'scene': 'b', 'text': 'Four five.'}]}
    words = [{'line': 'L1', 'text': 'One', 'start': 0.4, 'end': 0.6},
             {'line': 'L1', 'text': 'two.', 'start': 0.6, 'end': 0.9},
             {'line': 'L2', 'text': 'Three.', 'start': 1.6, 'end': 2.0},
             {'line': 'L3', 'text': 'Four', 'start': 2.9, 'end': 3.1},
             {'line': 'L3', 'text': 'five.', 'start': 3.1, 'end': 3.5}]

    def test_consecutive_lines_share_a_scene(self):
        out = scene_words.slice_words(self.script, {'cuts': [2.5], 'total': 4.0}, self.words, hold=0.0)
        self.assertEqual(list(out), ['a', 'b'])
        self.assertEqual([x['t'] for x in out['a']['words']], ['One', 'two.', 'Three.'])
        self.assertEqual(out['b'], {'global_start': 2.5, 'duration': 1.5,
                                    'words': [{'t': 'Four', 's': 0.4, 'e': 0.6}, {'t': 'five.', 's': 0.6, 'e': 1.0}]})

    def test_word_goes_to_its_lines_scene_even_before_the_cut(self):
        words = [dict(x) for x in self.words]
        words[3]['start'] = 2.45  # ASR put "Four" a hair before the cut
        out = scene_words.slice_words(self.script, {'cuts': [2.5], 'total': 4.0}, words, hold=0.0)
        self.assertEqual(out['b']['words'][0], {'t': 'Four', 's': -0.05, 'e': 0.6})

    def test_scene_cut_count_mismatch(self):
        with self.assertRaises(ValueError):
            scene_words.slice_words(self.script, {'cuts': [1.2, 2.5], 'total': 4.0}, self.words)

    def test_reappearing_scene_is_rejected(self):
        script = {'lines': self.script['lines'] + [{'id': 'L4', 'scene': 'a', 'text': 'Six.'}]}
        with self.assertRaises(ValueError):
            scene_words.slice_words(script, {'cuts': [2.5, 3.6], 'total': 4.5}, self.words)

    def test_cli_reads_hold_from_scenes_json_and_exits_1_on_desync(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, 'audio'))
            save(self.script, os.path.join(d, 'audio', 'script.json'))
            save(self.words, os.path.join(d, 'audio', 'words.json'))
            save({'cuts': [2.5], 'total': 4.0, 'lines': []}, os.path.join(d, 'audio', 'timeline.json'))
            save({'hold': 0.5, 'scenes': []}, os.path.join(d, 'scenes.json'))
            r = run([sys.executable, os.path.join(ENGINE, 'scene_words.py'), d])
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(load(os.path.join(d, 'audio', 'scene-words.json'))['b']['duration'], 2.0)
            save({'cuts': [], 'total': 4.0, 'lines': []}, os.path.join(d, 'audio', 'timeline.json'))
            r = run([sys.executable, os.path.join(ENGINE, 'scene_words.py'), d])
            self.assertEqual(r.returncode, 1)
            self.assertIn('scenes', r.stderr)


if __name__ == '__main__':
    unittest.main()
