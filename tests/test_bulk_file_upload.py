import tempfile
import unittest
from unittest.mock import patch

from app.importer import AppleScriptImporter


class BulkFileUploadTests(unittest.TestCase):
    def test_real_chrome_upload_attaches_file_without_finder(self):
        importer = AppleScriptImporter(age_group="M2")
        responses = [True, True, True, {"started": True, "error": ""}]

        with tempfile.NamedTemporaryFile(suffix=".xlsx") as workbook:
            workbook.write(b"xlsx")
            workbook.flush()
            with patch.object(importer, "run_js", side_effect=responses) as run:
                importer._attach_bulk_file(workbook.name)

        scripts = [call.args[0] for call in run.call_args_list]
        self.assertTrue(any("DataTransfer" in script for script in scripts))
        self.assertTrue(any("input.dispatchEvent" in script for script in scripts))
        self.assertFalse(any("System Events" in script for script in scripts))

    def test_upload_returns_medinet_result_without_row_by_row_import(self):
        importer = AppleScriptImporter(age_group="M2")
        importer._bulk_import_ready = lambda: True
        importer._attach_bulk_file = lambda path: None
        importer._bulk_import_result = lambda: {
            "message": "Thành công (Số dòng 39/119) Vui lòng kiểm tra File lỗi",
            "success": True,
            "error": False,
        }

        with tempfile.NamedTemporaryFile(suffix=".xlsx") as workbook:
            result = importer.upload_excel_file(workbook.name, timeout_s=1)

        self.assertTrue(result["success"])
        self.assertIn("39/119", result["message"])


if __name__ == "__main__":
    unittest.main()
