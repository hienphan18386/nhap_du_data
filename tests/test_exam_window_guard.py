"""The API fallback must not write into a record from a different examination round.

The fallback exists for a child whose record has no exam date at all, because the
M12 screen cannot list one. A record that does carry a date outside the requested
window belongs to another visit -- filling this year's examination into it would
overwrite a previous year's record, which is the one thing this project must never
do. TT266 of TH Bạch Đằng was written into a 22/07/2024 record that way.
"""
import unittest

from app.clinical import ClinicalFiller


def filler(lo="01/07/2026", hi="16/08/2026"):
    f = ClinicalFiller.__new__(ClinicalFiller)
    f.exam_from, f.exam_to = lo, hi
    return f


class ExamWindowGuard(unittest.TestCase):
    def test_date_inside_window_is_allowed(self):
        self.assertTrue(filler().date_in_window("15/07/2026"))

    def test_both_bounds_are_inclusive(self):
        self.assertTrue(filler().date_in_window("01/07/2026"))
        self.assertTrue(filler().date_in_window("16/08/2026"))

    def test_earlier_round_is_rejected(self):
        self.assertFalse(filler().date_in_window("22/07/2024"))

    def test_day_after_window_is_rejected(self):
        self.assertFalse(filler().date_in_window("17/08/2026"))

    def test_unreadable_date_is_rejected_not_assumed_safe(self):
        for bad in ("", None, "rác", "2026-07-15", "31/02/2026"):
            self.assertFalse(filler().date_in_window(bad), bad)


if __name__ == "__main__":
    unittest.main()
