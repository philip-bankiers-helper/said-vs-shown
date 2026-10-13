"""The disclosure rule (companion / fill_scenes / new_episode / deliver), the one-thing question split,
deliver.py's transcript.md and the paths new_episode.py prints. Offline; standard library only."""
import io
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
        d = lambda E: companion.disclosure_of(E, warn_to=None)  # noqa: E731
        self.assertEqual(d({}), UNREVIEWED)
        self.assertEqual(d({'disclosure': UNREVIEWED, 'reviewed_by': 'Jane Doe'}),
                         'AI-produced · AI voice · every claim sourced · reviewed by Jane Doe')
        claimed = 'AI-produced · AI voice · every claim sourced · reviewed by Sam'
        self.assertEqual(d({'disclosure': claimed}), UNREVIEWED)
        self.assertEqual(d({'disclosure': claimed, 'reviewed_by': '  '}), UNREVIEWED)
        self.assertEqual(d({'disclosure': claimed, 'reviewed_by': None, 'editor': 'Sam'}), UNREVIEWED)

    def test_a_review_claim_anywhere_is_dropped(self):
        d = lambda E: companion.disclosure_of(E, warn_to=None)  # noqa: E731
        self.assertEqual(d({'disclosure': 'AI-produced · reviewed by Jane · every claim sourced'}), UNREVIEWED)
        self.assertEqual(d({'disclosure': 'reviewed by Jane'}), UNREVIEWED)
        self.assertEqual(d({'disclosure': 'Made by AI · Human-reviewed'}),
                         'AI-produced · AI voice · every claim sourced · Made by AI · not yet human-reviewed')

    # every way a free-text segment could claim a person checked the episode
    HUMAN_CHECK = ['fact-checked by Sam', 'Fact checked by the Desk', 'human-checked by Ana', 'checked by a human',
                   'approved by Sam', 'Approval: Legal', 'Reviewer: Jane', 'Reviewers: Jane, Sam', 'reviewed by Jane',
                   'peer-reviewed', 'Human-reviewed', 'verified by a human editor', 'Verified', 'human verified',
                   'editor: Sam', 'Editor Sam Lee', 'editorial review: Sam', 'Editorial team', 'edited by Sam',
                   'proofread by Sam', 'vetted by our newsroom', 'signed off by Sam', 'sign-off: Sam',
                   'audited by Sam', 'human oversight', 'supervised by Sam', 'validated by experts',
                   'confirmed by our staff', 'curated by people', 'a journalist looked at it', 'human in the loop',
                   'reviewed and approved', 'QA checked']

    def test_human_check_claims_are_dropped_with_a_warning(self):
        for claim in self.HUMAN_CHECK:
            for disclosure in (claim, 'AI-produced · AI voice · every claim sourced · ' + claim, claim + ' · AI voice'):
                with self.subTest(disclosure=disclosure):
                    err = io.StringIO()
                    self.assertEqual(companion.disclosure_of({'disclosure': disclosure}, warn_to=err), UNREVIEWED)
                    self.assertIn('warning', err.getvalue())
                    self.assertIn(repr(claim), err.getvalue())
                    err = io.StringIO()
                    self.assertEqual(companion.disclosure_of({'disclosure': disclosure, 'reviewed_by': 'Jane Doe'}, warn_to=err),
                                     'AI-produced · AI voice · every claim sourced · reviewed by Jane Doe')
                    self.assertIn(repr(claim), err.getvalue())

    def test_known_parts_always_and_harmless_user_parts_kept(self):
        d = lambda E: companion.disclosure_of(E, warn_to=None)  # noqa: E731
        self.assertEqual(d({'disclosure': 'every claim sourced'}), UNREVIEWED)  # known parts are never lost
        self.assertEqual(d({'disclosure': 'AI voice · music: CC0 loops · AI-produced'}),
                         'AI-produced · AI voice · every claim sourced · music: CC0 loops · not yet human-reviewed')
        self.assertEqual(d({'disclosure': 'Made by AI · ai voice'}),
                         'AI-produced · AI voice · every claim sourced · Made by AI · not yet human-reviewed')
        parts, dropped = companion.disclosure_parts({'disclosure': 'Thumbnail: illustration · approved by Sam'})
        self.assertEqual(parts, ['AI-produced', 'AI voice', 'every claim sourced', 'Thumbnail: illustration',
                                 'not yet human-reviewed'])
        self.assertEqual(dropped, ['approved by Sam'])
        self.assertEqual(sum(1 for p in parts if 'review' in p), 1)  # the single generated segment

    def test_the_tools_own_segment_round_trips_silently(self):
        for E in ({'disclosure': UNREVIEWED},
                  {'disclosure': 'AI-produced · AI voice · every claim sourced · reviewed by Jane Doe', 'reviewed_by': 'Jane Doe'},
                  {'disclosure': UNREVIEWED, 'reviewed_by': 'Jane Doe'}):
            err = io.StringIO()
            companion.disclosure_of(E, warn_to=err)
            self.assertEqual(err.getvalue(), '', E)
        err = io.StringIO()  # a different name than reviewed_by records is a claim, not the tools' own segment
        self.assertTrue(companion.disclosure_of({'disclosure': '… · reviewed by Sam', 'reviewed_by': 'Jane Doe'},
                                                warn_to=err).endswith('· reviewed by Jane Doe'))
        self.assertIn("'reviewed by Sam'", err.getvalue())

    def test_fill_scenes_close_uses_the_same_rule(self):
        with tempfile.TemporaryDirectory() as d:
            mini_episode(d, disclosure='AI-produced · AI voice · every claim sourced · reviewed by Sam', editor='Sam')
            ep = fill_scenes.Episode(d)
            self.assertEqual(ep.disclosure(), UNREVIEWED)
            self.assertTrue(any('reviewed_by' in n for n in ep.notes))
            self.assertTrue(any(n.startswith('warning:') and "'reviewed by Sam'" in n for n in ep.notes), ep.notes)
            cfg = fill_scenes.build_close(ep, fill_scenes.Words(None), fill_scenes.Beats('close'))
            self.assertEqual(cfg['receipt']['disclosure'], UNREVIEWED)
            ep.E['reviewed_by'] = 'Jane Doe'
            self.assertTrue(ep.disclosure().endswith(' · reviewed by Jane Doe'))

    def test_companion_page_drops_free_text_check_claims(self):
        with tempfile.TemporaryDirectory() as d:
            ep = mini_episode(os.path.join(d, 'ep'), disclosure='AI-produced · fact-checked by Sam · approved by Legal · '
                                                                  'verified by a human editor · Reviewer: Jane · music: CC0')
            out = os.path.join(d, 'page')
            r = run([sys.executable, os.path.join(ENGINE, 'companion.py'), ep, out])
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(os.path.join(out, 'index.html'), encoding='utf-8') as f:
                page = f.read()
            self.assertIn('AI-produced · AI voice · every claim sourced · music: CC0 · not yet human-reviewed', page)
            for claim in ('fact-checked', 'approved', 'verified', 'Reviewer'):
                self.assertNotIn(claim, page)
                self.assertIn(claim, r.stderr)

    def test_companion_page_never_claims_an_unrecorded_review(self):
        with tempfile.TemporaryDirectory() as d:
            ep = mini_episode(os.path.join(d, 'ep'), disclosure='AI-produced · AI voice · every claim sourced · reviewed by Sam',
                              editor='Sam')
            out = os.path.join(d, 'page')
            r = run([sys.executable, os.path.join(ENGINE, 'companion.py'), ep, out])
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("warning: disclosure segment 'reviewed by Sam' dropped", r.stderr)
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
