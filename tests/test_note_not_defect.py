"""A note about the workbook must not mark a fully entered section as incomplete.

TT2 of TH Bạch Đằng answers a Có/Không question with a sentence. The answer is
entered correctly and only the extra wording has nowhere to go, but that message
used to mark the section "lưu thiếu", which made the student permanently "partial" --
so every resumed run entered them again from the start and the final reconciliation
counted a correct record as broken.
"""
import unittest

from app.clinical import NOTE_PREFIX


def section_state(problems):
    """The status rule from fill_sections, isolated for test."""
    blocking = [p for p in problems if not p.startswith(NOTE_PREFIX)]
    return "lưu thiếu" if blocking else "đã lưu"


class NoteIsNotADefect(unittest.TestCase):
    def test_note_alone_leaves_section_saved(self):
        self.assertEqual(section_state([NOTE_PREFIX + "tiền sử bệnh ghi ..."]), "đã lưu")

    def test_real_problem_still_marks_section_short(self):
        self.assertEqual(section_state(["không nhập được can_nang"]), "lưu thiếu")

    def test_real_problem_wins_when_mixed_with_a_note(self):
        self.assertEqual(
            section_state([NOTE_PREFIX + "tiền sử bệnh ghi ...",
                           "không nhập được can_nang"]),
            "lưu thiếu")

    def test_no_problems_is_saved(self):
        self.assertEqual(section_state([]), "đã lưu")


if __name__ == "__main__":
    unittest.main()
