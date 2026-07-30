import unittest

from app.importer import is_duplicate_notice
from app.parsers import _finish_record
from app.workbook_repair import (
    _date_text,
    _normalize_filter_ref,
    _plain_number,
)


class WorkbookRepairTests(unittest.TestCase):
    def test_full_column_filter_uses_sheet_row_bounds(self):
        self.assertEqual(
            _normalize_filter_ref("C:E", "C1:E169"),
            "C1:E169",
        )
        self.assertIsNone(_normalize_filter_ref("C1:E169", "C1:E169"))

    def test_excel_serial_becomes_medinet_date_text(self):
        self.assertEqual(_date_text("43102", date1904=False), "02/01/2018")
        self.assertEqual(_date_text("2/1/2018", date1904=False), "02/01/2018")

    def test_numeric_identifier_is_written_without_decimal_suffix(self):
        self.assertEqual(_plain_number("7938354360.0"), "7938354360")

    def test_duplicate_messages_are_skipped(self):
        for message in (
            "Hồ sơ đã nhập trước đó",
            "Số CCCD đã tồn tại trong hệ thống",
            "Bị trùng dữ liệu",
            "Duplicate record",
        ):
            with self.subTest(message=message):
                self.assertTrue(is_duplicate_notice([message]))

        self.assertFalse(is_duplicate_notice(["Vui lòng nhập ngày sinh"]))

    def test_medinet_row_keeps_its_exam_date(self):
        record = _finish_record(
            {
                "child_name": "Nguyen Van A",
                "gender": "Nam",
                "dob": "02/01/2018",
                "exam_date": "29/07/2026",
                "child_cccd": "079218000001",
                "ward": "Phường Xóm Chiếu",
            },
            tt_fallback=1,
        )
        self.assertEqual(record["exam_date"], "29/07/2026")


if __name__ == "__main__":
    unittest.main()
