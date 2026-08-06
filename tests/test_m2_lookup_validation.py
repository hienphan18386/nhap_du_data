import unittest
from types import SimpleNamespace

from app.importer import AppleScriptImporter, Importer


class M2LookupValidationTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "child_name": "Nguyễn Văn A",
            "child_cccd": "079214000001",
            "ward": "Phường Xóm Chiếu",
            "school_ward": "Phường Xóm Chiếu",
            "school_name": "THCS Mẫu - Phường Xóm Chiếu",
            "school_address": "Số 1 đường Mẫu, Phường Xóm Chiếu",
            "lop": "6A1",
        }

    def importer_with_form_state(self, **overrides):
        state = {
            "hoTen": "NGUYỄN VĂN A",
            "maDinhDanh": "079214000001",
            "phuongCuTru": "Phường Xóm Chiếu",
            "phuongCuTruId": "22",
            "phuongTruong": "Phường Xóm Chiếu",
            "phuongTruongId": "22",
            "truong": "THCS Mẫu - Phường Xóm Chiếu",
            "truongId": "999",
            "diaChiTruong": "Số 1 đường Mẫu, Phường Xóm Chiếu",
            "lopTruong": "6A1",
        }
        state.update(overrides)
        importer = Importer(age_group="M2")
        importer.on_expected_form = lambda: True
        importer.run_js = lambda _code: state
        return importer

    def test_m2_form_requires_catalogue_ids_not_only_visible_text(self):
        importer = self.importer_with_form_state(
            phuongTruongId="",
            truongId="",
        )

        self.assertFalse(importer.form_matches_record(self.record))

    def test_m2_form_accepts_selected_ward_and_school_ids(self):
        importer = self.importer_with_form_state()

        self.assertTrue(importer.form_matches_record(self.record))

    def test_m2_form_rejects_visible_home_ward_without_catalogue_id(self):
        importer = self.importer_with_form_state(phuongCuTruId="")

        self.assertFalse(importer.form_matches_record(self.record))

    def test_m2_form_rejects_school_address_cleared_after_lookup(self):
        importer = self.importer_with_form_state(diaChiTruong="")

        self.assertFalse(importer.form_matches_record(self.record))

    def test_m2_form_accepts_catalogue_street_only_school_address(self):
        importer = self.importer_with_form_state(diaChiTruong="Số 1 đường Mẫu")

        self.assertTrue(importer.form_matches_record(self.record))

    def test_applescript_importer_uses_automatic_school_lookup(self):
        self.assertIs(
            AppleScriptImporter.select_school_lookup,
            Importer.select_school_lookup,
        )

    def test_applescript_js_targets_only_the_marked_medinet_tab(self):
        importer = AppleScriptImporter(age_group="M2")
        scripts = []
        importer._osascript = lambda script: scripts.append(script) or SimpleNamespace(
            stdout='"ok"', stderr=""
        )

        self.assertEqual(importer.run_js("'ok'"), "ok")
        self.assertIn("codex-medinet-manual-import", scripts[0])
        self.assertIn("isMarked", scripts[0])


if __name__ == "__main__":
    unittest.main()
