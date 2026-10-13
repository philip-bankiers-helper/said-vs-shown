"""The disclosure rule (companion / fill_scenes / new_episode / deliver), the one-thing question split,
deliver.py's transcript.md and the paths new_episode.py prints. Offline; standard library only."""
import os
import re
import sys
import tempfile
import unittest

from helpers import ENGINE, have, load, run, save

import companion
import deliver
import fill_scenes

UNREVIEWED = 'AI-produced · AI voice · every claim sourced · not yet human-reviewed'


def mini_episode(d, **episode):
    """The smallest episode companion.py builds a page from."""
    E = {'show': 'Said vs. Shown', 'edition': 'AI', 'date': '2026-10-08', 'title': 'Test', 'credit': False,
         'stories': [], 'one_thing': 'Ask one question: which test did it pass?'}
    E.update(episode)
    for sub in ('edit', 'ledger', os.path.join('video', 'audio')):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    save(E, os.path.join(d, 'edit', 'episode.json'))
    save({'lines': [{'id': 'L1', 'start': 0.35, 'dur': 2.0}], 'cuts': [], 'total': 3.0},
         os.path.join(d, 'video', 'audio', 'timeline.json'))
    save([{'text': 'Said vs. Shown.', 'start': 0.3, 'end': 1.4}], os.path.join(d, 'video', 'audio', 'cues.json'))
    save({'hold': 0.12, 'scenes': [{'id': 'close', 'src': 'compositions/01-close.html'}]}, os.path.join(d, 'video', 'scenes.json'))
    return d


class DisclosureTests(unittest.TestCase):
    def test_review_follows_reviewed_by_only(self):
        d = companion.disclosure_of
        self.assertEqual(d({}), UNREVIEWED)
        self.assertEqual(d({'disclosure': UNREVIEWED, 'reviewed_by': 'Jane Doe'}),
                         'AI-produced · AI voice · every claim sourced · reviewed by Jane Doe')
        claimed = 'AI-produced · AI voice · every claim sourced · reviewed by Sam'
        self.assertEqual(d({'disclosure': claimed}), UNREVIEWED)
        self.assertEqual(d({'disclosure': claimed, 'reviewed_by': '  '}), UNREVIEWED)
        self.assertEqual(d({'disclosure': claimed, 'reviewed_by': None, 'editor': 'Sam'}), UNREVIEWED)

    def test_a_review_claim_anywhere_is_dropped(self):
        d = companion.disclosure_of
        self.assertEqual(d({'disclosure': 'AI-produced · reviewed by Jane · every claim sourced'}),
                         'AI-produced · every claim sourced · not yet human-reviewed')
        self.assertEqual(d({'disclosure': 'reviewed by Jane'}), UNREVIEWED)
        self.assertEqual(d({'disclosure': 'Made by AI · Human-reviewed'}), 'Made by AI · not yet human-reviewed')

    def test_fill_scenes_close_uses_the_same_rule(self):
        with tempfile.TemporaryDirectory() as d:
            mini_episode(d, disclosure='AI-produced · AI voice · every claim sourced · reviewed by Sam', editor='Sam')
            ep = fill_scenes.Episode(d)
            self.assertEqual(ep.disclosure(), UNREVIEWED)
            self.assertTrue(any('reviewed_by' in n for n in ep.notes))
            cfg = fill_scenes.build_close(ep, fill_scenes.Words(None), fill_scenes.Beats('close'))
            self.assertEqual(cfg['receipt']['disclosure'], UNREVIEWED)
            ep.E['reviewed_by'] = 'Jane Doe'
            self.assertTrue(ep.disclosure().endswith(' · reviewed by Jane Doe'))

    def test_companion_page_never_claims_an_unrecorded_review(self):
        with tempfile.TemporaryDirectory() as d:
            ep = mini_episode(os.path.join(d, 'ep'), disclosure='AI-produced · AI voice · every claim sourced · reviewed by Sam',
                              editor='Sam')
            out = os.path.join(d, 'page')
            r = run([sys.executable, os.path.join(ENGINE, 'companion.py'), ep, out])
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(os.path.join(out, 'index.html'), encoding='utf-8') as f:
                page = f.read()
            self.assertIn('not yet human-reviewed', page)
            self.assertNotIn('reviewed by', page)
            E = load(os.path.join(ep, 'edit', 'episode.json'))
            E['reviewed_by'] = 'Jane Doe'
            save(E, os.path.join(ep, 'edit', 'episode.json'))
            self.assertEqual(run([sys.executable, os.path.join(ENGINE, 'companion.py'), ep, out]).returncode, 0)
            with open(os.path.join(out, 'index.html'), encoding='utf-8') as f:
                page = f.read()
            self.assertIn('reviewed by Jane Doe', page)
            self.assertNotIn('not yet human-reviewed', page)

    def test_new_episode_never_prewrites_a_review(self):
        with tempfile.TemporaryDirectory() as d:
            r = run([sys.executable, os.path.join(ENGINE, 'new_episode.py'), d, '2026-10-13', 'ai', '--editor', 'Jane Editor'])
            self.assertEqual(r.returncode, 0, r.stderr)
            E = load(os.path.join(d, '2026-10-13_ai', 'edit', 'episode.json'))
            self.assertEqual(E['editor'], 'Jane Editor')
            self.assertEqual(E['disclosure'], UNREVIEWED)
            self.assertFalse(E.get('reviewed_by'))
            self.assertNotIn('reviewed by', E['disclosure'])

    @unittest.skipUnless(have('ffmpeg') and have('ffprobe'), 'ffmpeg not installed')
    def test_deliver_refuses_unreviewed_without_flag(self):
        with tempfile.TemporaryDirectory() as d:
            ep = mini_episode(os.path.join(d, 'ep'), disclosure='… · reviewed by Sam', editor='Sam')
            master = os.path.join(d, 'master.mp4')
            with open(master, 'wb') as f:
                f.write(b'\0')
            r = run([sys.executable, os.path.join(ENGINE, 'deliver.py'), ep, '--master', master])
            self.assertEqual(r.returncode, 1)
            self.assertIn('reviewed_by', r.stderr)


class OneThingTests(unittest.TestCase):
    """build_one_thing: the question is line 1 + line 2 (mark + tail); the highlight must survive."""

    def build(self, question, highlight):
        with tempfile.TemporaryDirectory() as d:
            mini_episode(d, one_thing='When an AI claim crosses your desk, ask one question: ' + question,
                         one_thing_highlight=highlight)
            ep = fill_scenes.Episode(d)
        spoken = 'So when an AI claim crosses your desk, ask one question: ' + question
        W = fill_scenes.Words({'words': [{'t': t, 's': 0.3 + 0.35 * i, 'e': 0.6 + 0.35 * i} for i, t in enumerate(spoken.split())]})
        cfg = fill_scenes.build_one_thing(ep, W, fill_scenes.Beats('one-thing'))
        return cfg, ep.notes

    def test_highlight_inside_the_question_is_unchanged(self):
        cfg, notes = self.build('which test did it actually pass?', 'actually pass?')
        self.assertEqual((cfg['line1'], cfg['mark'], cfg['tail']), ('Which test did it', 'actually pass?', ''))
        self.assertFalse([n for n in notes if n.startswith('one-thing')])

    def test_whole_question_highlight_is_kept_on_line_2(self):
        cfg, notes = self.build('what does the release establish?', 'What does the release establish?')
        self.assertTrue(cfg['line1'])
        self.assertTrue(cfg['mark'])
        self.assertEqual(' '.join([cfg['line1'], cfg['mark']]) + cfg['tail'], 'What does the release establish?')
        self.assertNotIn(cfg['line1'].split()[-1].lower(), fill_scenes.STOP)
        self.assertTrue(any('starts the question' in n for n in notes), notes)
        b = cfg['beats']
        self.assertLess(b['line1'], b['line2'])
        self.assertGreaterEqual(b['highlight'], b['line2'])

    def test_leading_highlight_keeps_its_tail(self):
        cfg, notes = self.build('which test did it actually pass?', 'Which test')
        self.assertEqual((cfg['line1'], cfg['mark'], cfg['tail']), ('Which', 'test', ' did it actually pass?'))
        self.assertTrue(any('starts the question' in n for n in notes), notes)

    def test_one_word_leading_highlight_stays_marked(self):
        cfg, notes = self.build('why?', 'Why?')
        self.assertEqual((cfg['line1'], cfg['mark']), ('', 'Why?'))
        self.assertTrue(any('first word' in n for n in notes), notes)


class TranscriptTests(unittest.TestCase):
    def test_display_forms_on_word_boundaries(self):
        script = {'display': {'Said versus Shown': 'Said vs. Shown', 'sixteen other leads': '16 other leads', 'one': '1'},
                  'lines': [{'id': 'L1', 'text': "That's Said versus Shown. Every source, and the sixteen other leads."},
                            {'id': 'L2', 'text': 'Someone asked one question.'},
                            {'id': 'L3', 'text': 'Unvoiced line.'}]}
        tl = {'lines': [{'id': 'L1', 'start': 0.35}, {'id': 'L2', 'start': 65.5}]}
        md = deliver.transcript_md(script, tl, 'Said vs. Shown, AI')
        self.assertEqual(md.splitlines(), [
            '# Transcript — Said vs. Shown, AI', '',
            "**0:00** — That's Said vs. Shown. Every source, and the 16 other leads.", '',
            '**1:05** — Someone asked 1 question.', '',
            'Unvoiced line.'])
        self.assertTrue(md.endswith('Unvoiced line.\n'))
        self.assertNotIn('versus', md)
        self.assertNotIn('sixteen', md)

    def test_no_display_map(self):
        md = deliver.transcript_md({'lines': [{'id': 'L1', 'text': 'Said versus Shown.'}]}, {'lines': []}, 'X')
        self.assertIn('Said versus Shown.', md)


class NewEpisodePathTests(unittest.TestCase):
    def new(self, cwd, root, date):
        r = run([sys.executable, os.path.join(ENGINE, 'new_episode.py'), root, date, 'ai'], cwd=cwd)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_relative_inside_the_working_directory(self):
        with tempfile.TemporaryDirectory() as d:
            d = os.path.realpath(d)
            out = self.new(d, '.', '2026-10-13')
            self.assertTrue(out.startswith('Created 2026-10-13_ai '), out)
            self.assertIn('voice.py" 2026-10-13_ai/video\n', out)
            self.assertNotIn('..', re.sub(r'<[^>]*>', '', out))

    def test_absolute_outside_the_working_directory(self):
        with tempfile.TemporaryDirectory() as d:
            d = os.path.realpath(d)
            eps, cwd = os.path.join(d, 'episodes'), os.path.join(d, 'a', 'b', 'c')
            os.makedirs(eps)
            os.makedirs(cwd)
            out = self.new(cwd, os.path.relpath(eps, cwd), '2026-10-13')
            ep = os.path.join(eps, '2026-10-13_ai')
            self.assertTrue(out.startswith('Created %s ' % ep), out)
            self.assertIn('--master %s\n' % os.path.join(ep, 'video', 'renders', 'master.mp4'), out + '\n')
            self.assertNotIn('../', out)

    def test_paths_with_spaces_are_quoted(self):
        with tempfile.TemporaryDirectory() as d:
            d = os.path.realpath(d)
            eps = os.path.join(d, 'my episodes')
            os.makedirs(eps)
            out = self.new(d, eps, '2026-10-13')
            self.assertIn('fill_scenes.py" "%s"' % os.path.join('my episodes', '2026-10-13_ai'), out)


if __name__ == '__main__':
    unittest.main()
