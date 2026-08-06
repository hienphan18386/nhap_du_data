import unittest

from app.parsers import (
    _excel_header_candidates,
    _excel_row_values,
    _fill_unique_school_name,
    _finish_record,
)


class ExcelSchoolMappingTests(unittest.TestCase):
    def test_duplicate_school_headers_use_the_populated_column(self):
        headers = [
            "Nơi đang theo học/Nơi làm việc",
            "Địa chỉ nơi học/Nơi làm việc",
            "Nơi học/Nơi làm việc",
        ]
        mapping = _excel_header_candidates(headers)
        raw = _excel_row_values(
            [None, "76 Tôn Thất Thuyết, Phường Xóm Chiếu", "Trường THCS Mẫu"],
            mapping,
        )

        self.assertEqual(raw["school_name"], "Trường THCS Mẫu")
        self.assertEqual(
            raw["school_address"],
            "76 Tôn Thất Thuyết, Phường Xóm Chiếu",
        )

    def test_school_ward_is_inferred_from_school_address(self):
        record = _finish_record(
            {
                "child_name": "Nguyễn Văn A",
                "gender": "Nam",
                "dob": "01/01/2014",
                "child_cccd": "079214000001",
                "school_name": "Trường THCS Mẫu",
                "school_address": "76 Tôn Thất Thuyết, Phường Xóm Chiếu",
            },
            tt_fallback=1,
        )

        self.assertEqual(record["school_name"], "Trường THCS Mẫu")
        self.assertEqual(record["school_ward"], "Phường Xóm Chiếu")

    def test_one_school_workbook_fills_isolated_blank_names(self):
        records = [
            {"school_name": "Trường THCS Mẫu"},
            {"school_name": ""},
        ]

        _fill_unique_school_name(records)

        self.assertEqual(records[1]["school_name"], "Trường THCS Mẫu")


if __name__ == "__main__":
    unittest.main()
