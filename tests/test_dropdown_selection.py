import unittest
from unittest.mock import patch

from app.importer import Importer


class SearchableDropdownSelectionTests(unittest.TestCase):
    @patch("app.importer.time.sleep", return_value=None)
    def test_accepts_catalogue_item_selected_in_controlled_list(self, _sleep):
        importer = Importer.__new__(Importer)
        responses = iter([
            True,
            True,
            "Selected",
            {
                "text": "",
                "id": "",
                "selectedText": "trẻ từ đủ 6 tuổi đến 18 tuổi đi học (lớp 1 đến lớp 12)",
            },
        ])
        importer.run_js = lambda _script: next(responses)

        selected = importer.select_searchable_dropdown(
            ".DoiTuong_M13",
            "Trẻ từ đủ 6 tuổi đến 18 tuổi đi học (lớp 1 đến lớp 12)",
        )

        self.assertTrue(selected)


class M2DuplicatePrecheckTests(unittest.TestCase):
    def test_positive_cccd_match_skips_existing_record(self):
        importer = Importer.__new__(Importer)
        importer.age_group = "M2"
        importer.search_grid = lambda _cccd, _timeout: (True, "match")

        self.assertTrue(importer.check_already_imported("012345678901"))

    def test_inconclusive_m2_search_proceeds_to_safe_form_save(self):
        importer = Importer.__new__(Importer)
        importer.age_group = "M2"
        importer.search_grid = lambda _cccd, _timeout: (None, "unfiltered")

        self.assertFalse(importer.check_already_imported("012345678901"))


class TextFieldCommitTests(unittest.TestCase):
    def test_uses_native_value_setter_to_commit_devextreme_text(self):
        importer = Importer.__new__(Importer)
        scripts = []
        importer.run_js = lambda script: scripts.append(script)

        importer.fill_text_fields({".TreEm_DiaChiTruong": "Số 1 đường Mẫu"})

        script = scripts[0]
        self.assertIn("HTMLInputElement.prototype", script)
        self.assertIn("HTMLTextAreaElement.prototype", script)
        self.assertIn("new InputEvent('input'", script)


if __name__ == "__main__":
    unittest.main()
