"""Edge cases for the reviewer name and the "Made with" footer switch."""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'skills', 'said-vs-shown', 'engine'))
import companion  # noqa: E402


class ReviewerNameCasedLatinTests(unittest.TestCase):
    def test_caseless_lookalike_separators_are_refused(self):
        for name in ['Sam ꟷ Fact-Checked ꟷ Legal-Approved', 'Sam ʔ Approved']:
            self.assertFalse(companion.is_name(name), name)

    def test_real_names_still_pass(self):
        for name in ['Philip Bankier', 'José García', "Mary-Ann O'Neil", 'Dr. Lee', 'Ana de la Cruz']:
            self.assertTrue(companion.is_name(name), name)


class CreditSwitchEmptyTests(unittest.TestCase):
    def test_empty_or_none_values_turn_the_footer_off(self):
        for value in ['none', 'null', '', [], {}, False]:
            self.assertFalse(companion.credit_footer({'credit': value}, True, warn_to=io.StringIO()), repr(value))

    def test_true_values_keep_it_on(self):
        for value in [True, 'yes', 'true', 1]:
            self.assertTrue(companion.credit_footer({'credit': value}, False, warn_to=io.StringIO()), repr(value))


if __name__ == '__main__':
    unittest.main()
