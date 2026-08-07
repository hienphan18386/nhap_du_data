import unicodedata
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

    def test_m2_form_accepts_decomposed_vietnamese_echoed_by_medinet(self):
        # Medinet renders some catalogue labels decomposed -- "Mỹ" as "My" plus a
        # combining tilde. It looks identical to the precomposed source text and
        # compares unequal, which silently rejected every ward spelled that way.
        record = dict(self.record, ward=unicodedata.normalize("NFC", "Phường Tân Mỹ"))
        importer = self.importer_with_form_state(
            phuongCuTru=unicodedata.normalize("NFD", "Phường Tân Mỹ"),
            hoTen=unicodedata.normalize("NFD", "NGUYỄN VĂN A"),
        )

        self.assertTrue(importer.form_matches_record(record))

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

    @staticmethod
    def _recording_importer(stdout):
        """An importer whose osascript is stubbed, returning `scripts` it was given."""
        importer = AppleScriptImporter(age_group="M2")
        scripts = []

        def fake(script):
            scripts.append(script)
            value = stdout(len(scripts)) if callable(stdout) else stdout
            return SimpleNamespace(stdout=value, stderr="")

        importer._osascript = fake
        return importer, scripts

    def test_applescript_js_targets_only_the_marked_medinet_tab(self):
        importer, scripts = self._recording_importer('1:3:"ok"')

        self.assertEqual(importer.run_js("'ok'"), "ok")
        # The marker is checked inside the evaluated expression itself, so a tab
        # that is not this importer's answers __wrong_tab__ and is skipped.
        self.assertIn("codex-medinet-manual-import", scripts[0])
        self.assertIn("__wrong_tab__", scripts[0])

    def test_applescript_reuses_the_tab_it_already_found(self):
        importer, scripts = self._recording_importer('1:3:"ok"')
        importer.run_js("'ok'")

        importer._osascript = lambda script: scripts.append(script) or SimpleNamespace(
            stdout='"ok"', stderr=""
        )
        self.assertEqual(importer.run_js("'ok'"), "ok")

        # The second call addresses the remembered tab directly instead of walking
        # every window and tab again -- the bulk of the cost of importing a child.
        self.assertIn("tab 3 of window 1", scripts[1])
        self.assertNotIn("repeat with w in windows", scripts[1])

    def test_applescript_researches_when_the_remembered_tab_moved(self):
        importer, scripts = self._recording_importer(
            lambda call: '1:3:"ok"' if call != 2 else "__wrong_tab__"
        )
        importer.run_js("'ok'")

        # A user opening or closing tabs shifts the indices; the stale reference is
        # dropped and the marked tab is searched for again rather than trusted.
        self.assertEqual(importer.run_js("'ok'"), "ok")
        self.assertIn("tab 3 of window 1", scripts[1])
        self.assertIn("repeat with w in windows", scripts[2])


if __name__ == "__main__":
    unittest.main()
