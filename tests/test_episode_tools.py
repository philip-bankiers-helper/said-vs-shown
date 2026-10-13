"""The disclosure rule, reviewed_by names and credits (companion / fill_scenes / close template / new_episode / deliver), the
"credit" footer switch, the one-thing question split,
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


# Free text that tried to sit next to "not yet human-reviewed": 33 phrasings the earlier blocklist dropped, then the 51
# a verifier found that it kept (other verbs, other languages, homoglyphs, spacing), 82 distinct, and 3 harmless ones.
SMUGGLED = [
    'fact-checked by Sam', 'Fact checked by the Desk', 'human-checked by Ana', 'checked by a human', 'approved by Sam',
    'Approval: Legal', 'Reviewer: Jane', 'Reviewers: Jane, Sam', 'reviewed by Jane', 'peer-reviewed', 'Human-reviewed',
    'verified by a human editor', 'Verified', 'human verified', 'editor: Sam', 'Editor Sam Lee', 'editorial review: Sam',
    'Editorial team', 'edited by Sam', 'proofread by Sam', 'vetted by our newsroom', 'signed off by Sam', 'sign-off: Sam',
    'audited by Sam', 'human oversight', 'supervised by Sam', 'validated by experts', 'confirmed by our staff',
    'curated by people', 'a journalist looked at it', 'human in the loop', 'reviewed and approved', 'QA checked',
    "QA'd by Sam", 'QA: Sam', 'QC passed', 'quality-controlled by Sam', 'looked over by Sam', 'proofed by Sam',
    'corrected by Sam', 'Legal OK', "OK'd by Legal", 'greenlit by Legal', 'passed legal', 'assessed by Dr. Lee',
    'evaluated by experts', 'examined by an expert', 'screened by Legal', 'tested by Sam', 'eyeballed by Sam',
    'corroborated by Sam', 'cross-referenced by our desk', 'read by a lawyer', 'seen by Sam before release',
    'revisado por Sam', 'vérifié par Sam', 'geprüft von Sam', 'überprüft von Sam', 'relu par Sam',
    'reviеwed by Sam (cyrillic e)', 'chеcked by Sam (cyrillic e)', 'Rev. by Sam', "rev'd by Sam",
    'researched and written by Sam Lee', 'produced by our newsroom', 'a human was in the loop', 'expert-led',
    'accuracy guaranteed', 'fact-checked', 'signed off by Legal', 'with notes from Dr. Lee', 'Sam stands behind every claim',
    'second pair of eyes: Sam', 'double-sourced and cleared', 'by the Said vs Shown team', 'curated by Sam',
    'reviewing: Sam', 'R E V I E W E D by Sam', 'peer-reviewed', 'f-a-c-t c-h-e-c-k-e-d', 'factchecked',
    'audited by Legal', 'editor: Sam', 'corrections by Sam',
    # harmless text is not let in either: it belongs in "credits"
    'music: CC0 loops', 'Made by AI', 'Thumbnail: illustration']
REVIEWED = 'AI-produced · AI voice · every claim sourced · reviewed by Jane Doe'


class DisclosureTests(unittest.TestCase):
    """The disclosure line is generated: the fixed parts, then "reviewed by <reviewed_by>" or "not yet human-reviewed".
    No text from episode.json enters it; third-party credits print on their own "Credits" line."""

    def test_fixed_parts_and_the_generated_review_segment(self):
        d = lambda E: companion.disclosure_of(E, warn_to=None)  # noqa: E731
        self.assertEqual(d({}), UNREVIEWED)
        self.assertEqual(d({'reviewed_by': 'Jane Doe'}), REVIEWED)
        self.assertEqual(d({'reviewed_by': '  Jane   Doe '}), REVIEWED)
        self.assertEqual(d({'reviewed_by': '  '}), UNREVIEWED)
        self.assertEqual(d({'reviewed_by': None, 'editor': 'Sam'}), UNREVIEWED)  # an editor is not a review
        self.assertEqual(companion.disclosure_parts({}), ['AI-produced', 'AI voice', 'every claim sourced',
                                                          'not yet human-reviewed'])

    def test_no_free_text_reaches_the_line(self):
        self.assertEqual(len(set(SMUGGLED)), 85)
        for phrase in SMUGGLED:
            if companion.CREDIT.fullmatch(phrase):  # an allowlisted credit moves to the Credits line (test below)
                continue
            for disclosure in (phrase, 'AI-produced · AI voice · every claim sourced · ' + phrase, phrase + ' · AI voice',
                               'AI-produced · ' + phrase + ' · music: CC0', 'AI-produced • ' + phrase + ' | music: CC0',
                               UNREVIEWED + ' · ' + phrase):
                with self.subTest(disclosure=disclosure):
                    for E, want in (({'disclosure': disclosure}, UNREVIEWED),
                                    ({'disclosure': disclosure, 'reviewed_by': 'Jane Doe'}, REVIEWED)):
                        err = io.StringIO()
                        self.assertEqual(companion.disclosure_of(E, warn_to=err), want)
                        self.assertIn('ignored', err.getvalue())
                        self.assertIn('"credits"', err.getvalue())  # the warning points to the new field

    def test_the_tools_own_line_round_trips_silently(self):
        for E in ({'disclosure': UNREVIEWED}, {'disclosure': 'AI-produced · AI voice'},
                  {'disclosure': REVIEWED, 'reviewed_by': 'Jane Doe'}, {'disclosure': UNREVIEWED, 'reviewed_by': 'Jane Doe'},
                  {'disclosure': ''}, {'disclosure': None}):
            err = io.StringIO()
            companion.disclosure_of(E, warn_to=err)
            self.assertEqual(err.getvalue(), '', E)
        err = io.StringIO()  # a name reviewed_by does not record is free text, not the tools' own segment
        self.assertEqual(companion.disclosure_of({'disclosure': '… · reviewed by Sam', 'reviewed_by': 'Jane Doe'},
                                                 warn_to=err), REVIEWED)
        self.assertIn('reviewed by Sam', err.getvalue())

    def test_reviewed_by_must_be_a_name(self):
        for name in ('Jane Doe', 'Dr. Lee', "Mary-Ann O'Neil", 'José Núñez', 'J. R. R. Tolkien', 'Ana de la Cruz',
                     'Ludwig van Beethoven', 'Omar al-Hassan', 'Philip Bankier', 'Zoë Ångström', 'Łukasz Żółć',
                     'Nguyễn Văn An', 'Søren Kierkegaard', 'Kaʻiulani Cleghorn'):
            with self.subTest(name=name):
                self.assertEqual(companion.disclosure_of({'reviewed_by': name}, warn_to=None),
                                 'AI-produced · AI voice · every claim sourced · reviewed by ' + name)
        for bad in ('Sam · fact-checked by Legal · approved by the board', 'Sam, fact-checked by Legal and approved by the board',
                    'Sam fact checked by Legal', 'Sam and the legal desk', 'Sam (Legal)', 'Sam | Legal', 'R2D2',
                    'the newsroom', 'Sam\nfact-checked', 'A' * 61, 'One Two Three Four Five Six', 'Sam <b>Legal</b>',
                    '李小龙'):
            with self.subTest(bad=bad):
                err = io.StringIO()
                self.assertEqual(companion.disclosure_of({'reviewed_by': bad}, warn_to=err), UNREVIEWED)
                self.assertIn('reviewed_by', err.getvalue())
                self.assertIsNone(companion.reviewer_of({'reviewed_by': bad}))

    def test_reviewed_by_latin_letters_only(self):
        """Letters that read as a separator (U+A78F ꞏ, U+318D ㆍ, U+1427 ᐧ, U+01C0 ǀ, U+01C3 ǃ, U+02D0 ː, U+02D1 ˑ, and
        ǁ ǂ) and letters of any other script are refused: "not yet human-reviewed" plus a warning. They used to pass,
        so "Sam ꞏ Fact-Checked ꞏ Legal-Approved" printed as "reviewed by Sam ꞏ Fact-Checked ꞏ Legal-Approved"."""
        for ch in '\ua78f\u318d\u1427\u01c0\u01c3\u02d0\u02d1\u01c1\u01c2':
            for bad in ('Sam %s Fact-Checked %s Legal-Approved' % (ch, ch), 'Sam%sLegal' % ch, 'Sam Lee%s' % ch):
                with self.subTest(ch='U+%04X' % ord(ch), bad=bad):
                    self.assertFalse(companion.is_name(bad))
                    err = io.StringIO()
                    self.assertEqual(companion.disclosure_of({'reviewed_by': bad}, warn_to=err), UNREVIEWED)
                    self.assertIn('reviewed_by', err.getvalue())
        for bad in ('李小龙', 'محمد علي', 'Иван Петров', 'Σωκράτης', 'S\u0430m Lee',  # Cyrillic a in a Latin name
                    'ＳＡＭ Lee', 'Sam \u02bb\u02bbLee', 'Sam\u034f Lee'):
            with self.subTest(bad=bad):
                self.assertIsNone(companion.reviewer_of({'reviewed_by': bad}))
        # diacritics in either Unicode form; the line carries the composed (NFC) name
        nfd = 'Jose\u0301 Nu\u0301n\u0303ez'
        self.assertEqual(companion.reviewer_of({'reviewed_by': nfd}), 'José Núñez')
        self.assertEqual(companion.disclosure_of({'reviewed_by': nfd}, warn_to=None),
                         'AI-produced · AI voice · every claim sourced · reviewed by José Núñez')

    def test_legacy_disclosure_credit_is_migrated(self):
        E = {'disclosure': 'AI-produced · AI voice · Music: CC0 loops by Kevin MacLeod · fact-checked by Legal · data: Epoch AI',
             'credits': ['data: Epoch AI']}
        err = io.StringIO()
        self.assertEqual(companion.disclosure_of(E, warn_to=err), UNREVIEWED)
        self.assertIn("'fact-checked by Legal' ignored", err.getvalue())
        self.assertNotIn('Kevin MacLeod', err.getvalue())  # not "ignored": it moves to the Credits line
        err = io.StringIO()
        self.assertEqual(companion.credits_of(E, warn_to=err),
                         ['data: Epoch AI', 'music: CC0 loops by Kevin MacLeod'])  # migrated once, no duplicate
        self.assertIn('moved to the Credits line', err.getvalue())
        self.assertIn('Music: CC0 loops by Kevin MacLeod', err.getvalue())

    def test_credit_switch_holding_credits_is_read_as_credits(self):
        """"credit" is the footer switch; credits text written there by mistake used to vanish (only the footer showed).
        It is read as "credits" with a loud warning, and the footer stays on."""
        for raw, want in ((['music: CC0 loops by Kevin MacLeod', 'images: NASA'], ['music: CC0 loops by Kevin MacLeod', 'images: NASA']),
                          ('music: CC0 loops by Kevin MacLeod', ['music: CC0 loops by Kevin MacLeod'])):
            with self.subTest(raw=raw):
                E = {'credit': raw, 'credits': ['data: Epoch AI']}
                err = io.StringIO()
                self.assertEqual(companion.credits_of(E, warn_to=err), ['data: Epoch AI'] + want)
                self.assertIn('"credit" HOLDS', err.getvalue())
                self.assertIn('rename the field to "credits"', err.getvalue())
                err = io.StringIO()
                self.assertTrue(companion.credit_footer(E, False, err))
                self.assertEqual(err.getvalue(), '')  # warned once, by credits_of
        for raw, want in ((True, True), (False, False), (None, 'default'), ('false', False), ('No', False), (0, False),
                          ('true', True), (1, True)):
            with self.subTest(raw=raw):
                err = io.StringIO()
                self.assertEqual(companion.credit_footer({'credit': raw}, 'default', err), want)
                self.assertEqual(bool(err.getvalue()), not isinstance(raw, (bool, type(None))))
                self.assertEqual(companion.credits_of({'credit': raw}, warn_to=None), [])
        with tempfile.TemporaryDirectory() as d:  # the close card and the page
            mini_episode(d, credit=['music: CC0 loops'])
            ep = fill_scenes.Episode(d)
            cfg = fill_scenes.build_close(ep, fill_scenes.Words(None), fill_scenes.Beats('close'))
            self.assertEqual((cfg['receipt']['credits'], cfg['receipt']['credit']), (['music: CC0 loops'], True))
            self.assertTrue(any('"credit" HOLDS' in n for n in ep.notes), ep.notes)
            out = os.path.join(d, 'page')
            r = run([sys.executable, os.path.join(ENGINE, 'companion.py'), d, out])
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('"credit" HOLDS', r.stderr)
            with open(os.path.join(out, 'index.html'), encoding='utf-8') as f:
                page = f.read()
            self.assertEqual(re.findall(r'<p class="credits">([^<]*)</p>', page), ['Credits: music: CC0 loops'])
            self.assertIn('<footer class="credit">', page)

    def test_credit_that_claims_a_review_warns_and_still_prints(self):
        claims = ['data: fact-checked by Reuters', 'translation: verified by Dr. Lee', 'footage: approved by Legal',
                  'data: reviewed by Sam', 'images: peer-reviewed set', 'data: double-checked by our desk',
                  'music: vetted by Legal', 'data: Census, confirmed by the bureau', 'sfx: proofread by Sam']
        for c in claims:
            with self.subTest(credit=c):
                err = io.StringIO()
                self.assertEqual(companion.credits_of({'credits': [c]}, warn_to=err), [c])
                self.assertIn('mentions a review, fact-check, approval or verification', err.getvalue())
        for c in ('music: CC0 loops by Kevin MacLeod', 'images: Wikimedia Commons (CC BY-SA)', 'footage: NASA preview reel',
                  'data: Epoch AI, CC-BY 4.0', 'translation: Ana de la Cruz'):
            with self.subTest(credit=c):
                err = io.StringIO()
                self.assertEqual(companion.credits_of({'credits': [c]}, warn_to=err), [c])
                self.assertEqual(err.getvalue(), '')
        err = io.StringIO()  # a separator-like letter in a value counts as a separator
        self.assertEqual(companion.credits_of({'credits': ['data: Census \ua78f fact-checked by Legal']}, warn_to=err), [])
        self.assertIn('dropped', err.getvalue())

    def test_close_card_prints_at_most_three_credits(self):
        """The receipt never runs off the frame: at most 3 credits of at most 64 characters, then "+N more"; the page
        prints them all (and so does SOURCES.md, from the same credits_of)."""
        long = 'images: Wikimedia Commons contributors, CC BY-SA 4.0, edited and colour graded'
        credits = ['music: CC0 loops by Kevin MacLeod', long, 'sfx: freesound.org/s/123', 'data: Epoch AI', 'footage: NASA']
        with tempfile.TemporaryDirectory() as d:
            mini_episode(d, credits=credits)
            ep = fill_scenes.Episode(d)
            R = fill_scenes.build_close(ep, fill_scenes.Words(None), fill_scenes.Beats('close'))['receipt']
            self.assertEqual(R['credits'], ['music: CC0 loops by Kevin MacLeod',
                                            'images: Wikimedia Commons contributors, CC BY-SA 4.0, edited…',
                                            'sfx: freesound.org/s/123'])
            self.assertEqual(R['credits_more'], 2)
            self.assertTrue(all(len(c) <= companion.CLOSE_CREDIT_CHARS for c in R['credits']))
            self.assertTrue(any(n.startswith('close: 5 credits') and 'SOURCES.md' in n for n in ep.notes), ep.notes)
            self.assertTrue(any('prints as' in n and 'in full' in n for n in ep.notes), ep.notes)
            out = os.path.join(d, 'page')
            self.assertEqual(run([sys.executable, os.path.join(ENGINE, 'companion.py'), d, out]).returncode, 0)
            with open(os.path.join(out, 'index.html'), encoding='utf-8') as f:
                self.assertEqual(re.findall(r'<p class="credits">([^<]*)</p>', f.read()),
                                 ['Credits: ' + ' · '.join(credits)])
        with tempfile.TemporaryDirectory() as d:  # three or fewer: all of them, nothing more
            mini_episode(d, credits=credits[:3])
            R = fill_scenes.build_close(fill_scenes.Episode(d), fill_scenes.Words(None), fill_scenes.Beats('close'))['receipt']
            self.assertEqual((len(R['credits']), R['credits_more']), (3, 0))

    def test_credits_allowlist(self):
        err = io.StringIO()
        E = {'credits': ['music: CC0 loops by Kevin MacLeod', 'SFX : freesound.org/s/123', 'Data:Epoch AI, CC-BY 4.0',
                         'images: Wikimedia Commons (CC BY-SA)', 'footage: NASA', 'translation: Ana de la Cruz',
                         'fact-checked by Legal', 'editor: Sam', 'reviewed by: Sam', 'music: CC0 · reviewed by Sam',
                         'music: CC0 | approved', 'music: a; b', 'music: <b>x</b>', 'music:', 'sfx: ' + 'x' * 81, 7]}
        self.assertEqual(companion.credits_of(E, warn_to=err),
                         ['music: CC0 loops by Kevin MacLeod', 'sfx: freesound.org/s/123', 'data: Epoch AI, CC-BY 4.0',
                          'images: Wikimedia Commons (CC BY-SA)', 'footage: NASA', 'translation: Ana de la Cruz'])
        self.assertEqual(err.getvalue().count('dropped'), 10, err.getvalue())
        self.assertEqual(companion.credits_line(['music: CC0', 'data: Epoch AI']), 'Credits: music: CC0 · data: Epoch AI')
        self.assertEqual(companion.credits_line([]), '')
        self.assertEqual(companion.credits_of({}), [])
        self.assertEqual(companion.credits_of({'credits': 'music: CC0'}, warn_to=None), ['music: CC0'])
        err = io.StringIO()
        self.assertEqual(companion.credits_of({'credits': {'music': 'CC0'}}, warn_to=err), [])
        self.assertIn('credits', err.getvalue())
        # credits never change the disclosure line
        self.assertEqual(companion.disclosure_of(dict(E, reviewed_by='Jane Doe'), warn_to=None), REVIEWED)

    def test_fill_scenes_close_uses_the_same_rule(self):
        with tempfile.TemporaryDirectory() as d:
            mini_episode(d, disclosure='AI-produced · AI voice · every claim sourced · reviewed by Sam · music: CC0',
                         editor='Sam', credits=['music: CC0 loops', 'approved by Legal'])
            ep = fill_scenes.Episode(d)
            self.assertEqual(ep.disclosure(), UNREVIEWED)
            self.assertTrue(any('reviewed_by' in n for n in ep.notes))
            self.assertTrue(any(n.startswith('warning:') and 'reviewed by Sam' in n and '"credits"' in n for n in ep.notes),
                            ep.notes)
            cfg = fill_scenes.build_close(ep, fill_scenes.Words(None), fill_scenes.Beats('close'))
            self.assertEqual(cfg['receipt']['disclosure'], UNREVIEWED)
            # "music: CC0" from the legacy disclosure is migrated to the credits, with a warning
            self.assertEqual(cfg['receipt']['credits'], ['music: CC0 loops', 'music: CC0'])
            self.assertTrue(any(n.startswith('warning:') and 'moved to the Credits line' in n for n in ep.notes), ep.notes)
            self.assertTrue(any(n.startswith('warning:') and "'approved by Legal'" in n for n in ep.notes), ep.notes)
            ep.E['reviewed_by'] = 'Jane Doe'
            self.assertEqual(ep.disclosure(), REVIEWED)

    def test_close_template_prints_credits_on_their_own_line(self):
        with open(os.path.join(ENGINE, '..', 'templates', 'scenes', 'close.html'), encoding='utf-8') as f:
            src = f.read()
        self.assertIn('credits: [],', src)
        self.assertIn('credits_more: 0,', src)
        self.assertRegex(src, r'line\("cl-credits", "Credits: " \+ R\.credits\.join')
        self.assertRegex(src, r'R\.credits_more > 0 \? "\\u00a0· \+" \+ R\.credits_more \+ " more"')
        self.assertLess(src.index('line("cl-disc"'), src.index('line("cl-credits"'))

    def test_companion_page_generates_the_line_and_prints_credits_apart(self):
        with tempfile.TemporaryDirectory() as d:
            ep = mini_episode(os.path.join(d, 'ep'), disclosure="AI-produced · QA'd by Sam · looked over by Legal · "
                                                                  "OK'd by the client · music: CC0",
                              credits=['music: CC0 loops by Kevin MacLeod', 'fact-checked by Legal'])
            out = os.path.join(d, 'page')
            r = run([sys.executable, os.path.join(ENGINE, 'companion.py'), ep, out])
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(os.path.join(out, 'index.html'), encoding='utf-8') as f:
                page = f.read()
            self.assertEqual(re.findall(r'<p class="disc">([^<]*)</p>', page), [UNREVIEWED])
            self.assertEqual(re.findall(r'<p class="credits">([^<]*)</p>', page),
                             ['Credits: music: CC0 loops by Kevin MacLeod · music: CC0'])  # the last one migrated
            for claim in ("QA'd", 'looked over', "OK&#x27;d", 'fact-checked'):
                self.assertNotIn(claim, page)
            self.assertIn('"credits"', r.stderr)
            self.assertIn("'fact-checked by Legal' dropped", r.stderr)
            E = load(os.path.join(ep, 'edit', 'episode.json'))
            E['reviewed_by'] = 'Jane Doe'
            save(E, os.path.join(ep, 'edit', 'episode.json'))
            self.assertEqual(run([sys.executable, os.path.join(ENGINE, 'companion.py'), ep, out]).returncode, 0)
            with open(os.path.join(out, 'index.html'), encoding='utf-8') as f:
                page = f.read()
            self.assertEqual(re.findall(r'<p class="disc">([^<]*)</p>', page), [REVIEWED])
            self.assertNotIn('not yet human-reviewed', page)

    def test_new_episode_starter_has_credits_and_no_disclosure_text(self):
        with tempfile.TemporaryDirectory() as d:
            r = run([sys.executable, os.path.join(ENGINE, 'new_episode.py'), d, '2026-10-13', 'ai', '--editor', 'Jane Editor'])
            self.assertEqual(r.returncode, 0, r.stderr)
            E = load(os.path.join(d, '2026-10-13_ai', 'edit', 'episode.json'))
            self.assertEqual(E['editor'], 'Jane Editor')
            self.assertEqual(E['credits'], [])
            self.assertNotIn('disclosure', E)
            self.assertFalse(E.get('reviewed_by'))
            self.assertEqual(companion.disclosure_of(E, warn_to=None), UNREVIEWED)

    @unittest.skipUnless(have('ffmpeg') and have('ffprobe'), 'ffmpeg not installed')
    def test_deliver_refuses_unreviewed_without_flag(self):
        with tempfile.TemporaryDirectory() as d:
            master = os.path.join(d, 'master.mp4')
            with open(master, 'wb') as f:
                f.write(b'\0')
            for i, extra in enumerate(({}, {'reviewed_by': 'Sam, fact-checked by Legal'})):
                ep = mini_episode(os.path.join(d, 'ep%d' % i), disclosure='… · reviewed by Sam', editor='Sam', **extra)
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
