# Project Info & Data Entry Automation Guide - COMPLETED

This file provides a summary of the data entry automation task, final statistics, and technical guidelines.

---

## Project Scope — Mandatory For This Session
* **Current and only project**: `NHAP_DATA_LONG`.
* **Canonical project root**:
  `/Users/hienphantrong/Desktop/Project/AI_PROJECT/NHAP_DATA_LONG`.
* Before reading, editing, testing, building, or starting an app, verify that the
  working directory and target files belong to this root.
* Do not reuse implementation context, file paths, running servers, UI work, or
  assumptions from `WEB_MANGA`, `IMPORT_DATA_LONG`, or any other repository.
* Do not edit another project unless the user explicitly names that project in a
  new request. A file mentioned from `Downloads` is input data, not a change of
  project.
* Project-specific Claude memory is under
  `/Users/hienphantrong/.claude/projects/-Users-hienphantrong-Desktop-Project-AI-PROJECT-NHAP-DATA-LONG/`.
  Do not read or update the memory directory of another project for this work.

---

## 📌 Context & Goals
* **Target Website**: [Health Check Report Viewer](https://quanlyskcd.medinet.org.vn/app/main/dynamicreport/report/viewer-utility/KSK_KSKTE_TreEmDuoi24_ThongTinHanhChinh) (requires active authenticated session in the user's Google Chrome).
* **Objective**: Automatically import children health check administrative records from the parsed OCR list into the database, skipping duplicates.
* **CRITICAL RULE**: Do NOT modify, edit, or delete any existing or previously imported records. Only insert new records.

---

## 📈 Final Progress (160 Children Total)
All 160 children records from `scripts/parsed_children_data.json` have been successfully processed, imported, or skipped:
* **Skipped (Already Imported)**: **120 children** were found in the database grid and skipped automatically.
* **Skipped (Duplicates at other units)**: **24 children** triggered the duplicate population database popup (already registered at another health center) and were skipped.
* **Newly Imported Successfully**: **16 children** were successfully saved into the Medinet database.
  * Note: `Vũ Hạo Thiên` (`079223008614`) had an empty phone number in the source parsed data. He was successfully imported using the fallback placeholder phone number `0909999999` so his record can be saved. The user can update it later.

No existing children records were modified or deleted.

---

## ⚙️ Key Technical Discoveries & Solutions

### 0. Latest Session Notes - MN12 Excel + Windows Build
* **Excel parser fixed for MN12 2026 file**:
  `app/parsers.py` now reads `/Users/hienphantrong/Downloads/MN12 _thong tin KHAM SUC KHOE NAM 2026.xlsx`.
  The source header uses variants such as `Họ và tên`, `Ngày tháng năm sinh`,
  `CCCD của mẹ/người giám hộ`, `Nơi đang theo học/Nơi làm việc`, and
  `Địa chỉ nơi học/Nơi làm việc`; these have been added to `_HEADER_TOKENS`.
* **Parsed result for that file**: 127 student records total; 120 records have a
  detected ward and are eligible for import; 7 records remain in `no_ward`
  because their address does not clearly include a ward/xã. One typo alias was
  added: `Vình Hội` -> `Phường Vĩnh Hội`.
* **Important parser behavior**: `parse_excel()` now skips numeric helper rows
  like the `1..17` row below the header, infers `school_ward` from
  `school_address`, and raises a clear error if zero student rows are parsed
  instead of silently continuing into browser automation.
* **Safe parser verification command**:
  `python3 -c "from app import parsers; p='/Users/hienphantrong/Downloads/MN12 _thong tin KHAM SUC KHOE NAM 2026.xlsx'; data=parsers.load_any(p); print(len(data), data[0])"`
  Avoid using `python3 -m app.importer --dry-run` just to test parsing, because
  after loading records it can still open/control the browser.
* **Windows build fix**: `packaging/importer.spec` no longer requires
  `app/data/children.json` during CI. That file is local sample/real data and is
  gitignored by `children.json`, so GitHub Actions previously failed on Windows
  with `Unable to find ... app\data\children.json`.
* **Windows artifact to download**: after GitHub Actions workflow
  `Build standalone importer` succeeds, download artifact
  `medinet-importer-windows`; it is a zip containing `medinet-importer.exe`.
  PyInstaller cannot cross-build Windows `.exe` from macOS.
* **Do not commit local data blindly**: avoid `git add -f app/data/children.json`
  unless the user explicitly confirms it is safe sample data, because it may
  contain real/personal records.

### 0b. M2 Flow (Trẻ 6–17 tuổi, KSKD18_TTHC) — Completed This Session
The importer now supports a second age group alongside M1 (Trẻ dưới 6 tuổi):
**M2 (TRẺ TỪ 6–17 TUỔI)**, chosen via the double-click menu or `--age-group m2`.
Everything below is implemented in `app/importer.py` and verified against the live
Medinet form, including successful M2 saves with the requested examination date.

* **M2 form fully reverse-engineered and wired up**. Selectors differ entirely from
  M1: CCCD trẻ = `.DinhDanhCaNhan` (not `.MaDinhDanh`); guardian = `.TreEm_NguoiGiamHo`
  / `.TreEm_CCCD_NguoiGiamHo` / `.TreEm_SDT_NguoiGiamHo`; relationship
  `.TreEm_MQH_NguoiGiamHo` = "Mẹ"; school block `.TreEm_XaPhuong` /
  `.TreEm_TruongHocId` / `.TreEm_DiaChiTruong` / `.TreEm_Lop`; đối tượng
  `.DoiTuong_M13`; địa điểm khám `.DoiTuongKham` = "Trường Học".
* **Save button is "Lưu thay đổi"** (M1 uses "Lưu"); add-new is "Thêm mới phiếu".
  Success signal is still `phieukhamId=<id>` in the URL.
* **Two hidden required payment fields** (only revealed by save-time validation
  "Vui lòng ... hình thức chi trả"): `.HinhThucChiTraKhamSK` = "Ngân sách thành phố
  hỗ trợ" and `.HinhThucChiTraKhamSK_ChiTiet` = "Khám theo hợp đồng". Handled in
  `set_choices_m2`.
* **School is a server-backed lookup** (`select_school_lookup`): search with only
  the distinctive core (for example, `Tăng Bạt Hổ`, not the full school + ward
  label), wait for the async result, then select the exact option.
* **Fixed examination date (Ngày khám)**: `.NgayKham` is a DevExtreme DateBox where
  **typing only changes the display, not the saved value** — an overnight run would
  otherwise file the next day's date. Fixed with `set_datebox()`, which drives the
  calendar (cells carry `data-value="yyyy/MM/dd"`; navigator
  `.dx-calendar-navigator-previous-view/next-view`) so the real model value commits.
  The exam date is captured once at run start (`Importer.exam_date`, or
  `--exam-date DD/MM/YYYY`) and stays constant across midnight. Calendar mechanism
  verified without saving (chose 18/07 same month, 05/06 prev month, held after blur)
  and later verified on saved Tăng Bạt Hổ records using `30/07/2026`.
* **Skip placeholder CCCD**: `is_importable_cccd()` drops records whose CCCD is blank
  or a single repeated digit (e.g. `999999999999`, `000000000000`).
* **Guardian CCCD is REQUIRED on M2** but 158/533 source rows have none →
  `load_records` now returns `(eligible, no_ward, no_guardian)`; for M2 those 158 are
  skipped and listed for manual entry. Latest MN12 file result: **533 hồ sơ → 375 sẽ
  xử lý, 0 thiếu Phường/Xã, 158 thiếu CCCD người giám hộ (bỏ qua)**.
* **No grid pre-check for M2** (`check_already_imported` returns False): the M2
  DevExtreme grid search cannot be driven via AppleScript/synthetic events (result
  count stays stuck). Instead we rely on medinet itself refusing a second record for
  an existing CCCD — verified no duplicate is created. A silent non-save with empty
  `validation_messages()` is classified as "duplicate/already on file".
* **M2 runs a "bản thử" first by default**: fills 1 student, shows the result, asks
  "Tiếp tục nhập hết? (y/n)". Controlled unattended runs may use `--skip-trial`
  after a live trial has already succeeded.
* **Batch is slow**: ~60–75s per M2 record over AppleScript (~9–11h for all 533).
  Run overnight or in chunks with `--limit`. Packaged app rebuilt with all of the
  above. Deeper detail lives in the `m2-form-quirks` memory file.

### 0c. TH Xóm Chiếu (24/07/2026) — Excel Fix + Chrome Focus Fix
* **Excel school name corrected**: The file
  `/Users/hienphantrong/Downloads/Danh sach truong xom chieu kham ngay 24.7.2026.xlsx`
  (441 students, classes 1/1–5/4) had column "Nơi đang theo học" set to
  `Trường TH Xóm Chiếu`. The Medinet lookup expects the exact option text
  `TH Xóm Chiếu - Phường Xóm Chiếu`. All 441 cells in column J (row 10+) were
  updated directly in the `.xlsx` file via openpyxl.
* **Parser verification**: `parsers.load_any()` successfully reads all 441 records
  with `school_name='TH Xóm Chiếu - Phường Xóm Chiếu'`,
  `school_ward='Phường Xóm Chiếu'`. 72 records have `ward=None` because their
  home addresses use old ward names (Phường 10, 14, 13, 15, 16) or other
  districts.
* **Chrome focus-stealing fixed** (`app/importer.py`,
  `AppleScriptImporter.goto()`): During batch import, every call to
  `open_new_form()` → `open_list()` → `goto(list_url)` previously brought
  Chrome to the foreground. The first navigation now finds or creates the Medinet
  tab without `activate`; subsequent navigations use JavaScript
  `location.assign(url)` via `run_js()`. School selection also no longer calls
  `System Events` or sends macOS keystrokes. The user can keep using the mouse and
  keyboard in another application while Medinet is controlled in the background.
* **Rebuilt packaged app**: `pyinstaller packaging/importer.spec` →
  `dist/medinet-importer` includes both fixes.

### 0d. Menu [3] — Upload Original Excel To Medinet (Latest)
* The double-click menu now includes **[3] Tự động tải file Excel gốc vào Medinet
  (M2)**. It uploads the exact workbook selected by the user through Medinet's
  **Nhập → Nhập file** flow. It does not create, require, or search for a
  `*_NHAP.xlsx` copy and does not fall back to row-by-row form entry.
* **File picker fix**: option [3] intentionally reuses `choose_file_dialog()` from
  option [1]. A separate Excel-only macOS picker made valid LibreOffice-generated
  `.xlsx` files appear disabled. After selection, option [3] explicitly accepts
  `.xlsx` and `.xlsm`; other extensions are rejected.
* **Original-file behavior**: option [3] normalizes the selected path, verifies the
  file still exists, prints the exact path, and sends that same file to Medinet.
  The separate `--repair-import-file` CLI remains available when a corrected copy
  is explicitly requested, but it is not part of menu option [3].
* **Do not use XML-level repair for option [3]**: calling
  `repair_medinet_workbook()` caused the live Medinet importer to process one row
  but hang indefinitely for files with 3+ rows. The verified path is only the
  openpyxl round-trip plus `fill_lookup_ids()`. Multi-row upload was verified with
  Medinet's result `Thành công (Số dòng N/N)`.
* **Chrome upload on macOS**: `AppleScriptImporter._attach_bulk_file()` reads the
  selected workbook in the app, transfers it to the signed-in Chrome tab in small
  base64 chunks, creates a browser `File`, assigns it through `DataTransfer`, and
  dispatches the file input's `change` event. This avoids Finder and Accessibility
  permission. Chrome still requires **View → Developer → Allow JavaScript from
  Apple Events**.
* If the existing Chrome tab cannot receive the file, the app automatically tries
  `upload_repaired_file_with_separate_chrome()` using a persistent Playwright
  Chrome/Edge profile. Option [3]'s automatic bulk upload is currently macOS-only;
  Firefox is not its primary path.
* The bulk result wait is up to **900 seconds**. A Medinet message mentioning a
  **file lỗi** means processing completed: valid rows were imported and rows that
  already existed or failed validation are available in Medinet's error workbook.
  The app must continue to preserve the rule of never modifying/deleting existing
  records.
* Optional CLI repair-only command:
  `medinet-importer --repair-import-file ds.xlsx`.
  It creates the `_NHAP` workbook and exits; menu option [3] does not call it.
* Relevant regression tests are `tests/test_workbook_repair.py` and
  `tests/test_bulk_file_upload.py`.

### 0e. THCS Tăng Bạt Hổ (30/07/2026) — Mapping + Safe Background Entry
* **Source and mapped workbook**:
  `data/Tang ban ho kham ngay 30_07_2026_da_bo_sung_phuong_long.xlsx` was mapped
  into
  `outputs/019fd1f5-1b32-7411-bca1-3646ea6d2f7b/NHAP_LIEU_HOC_SINH_TANG_BAT_HO_30_07_2026.xlsx`.
  The mapped file contains **1,023 students** and uses examination date
  `30/07/2026`, school ward `Phường Xóm Chiếu`, relationship `Mẹ`, payment
  `Ngân sách thành phố hỗ trợ`, and support type `Khám theo hợp đồng`.
* **Eligible rows**: **1,019** rows have the required guardian CCCD. Four rows
  cannot be saved through the M2 form because guardian CCCD is mandatory:
  TT465 Nguyễn Đình Đình (`079313024588`), TT480 Nguyễn Đức Phúc
  (`079213029564`), TT606 Nguyễn Hoàng Anh (`079213007407`), and TT628
  Nguyễn Ngọc Quyên (`079313044008`). Do not invent guardian identifiers.
* **School lookup rule**: query only `Tăng Bạt Hổ`, then select the exact live
  option `THCS Tăng Bạt Hổ - Phường Xóm Chiếu` (school ID `23372`, school-ward
  ID `22`). Do not search using the entire option text.
* **Pre-save safety guard**: `form_matches_record()` now verifies child name,
  child CCCD, and the visible school value. If the school does not contain
  `Tăng Bạt Hổ`, the record is not saved. The lookup may retry up to three times.
* **Date handling after save**: the importer waits for the SPA to rebind the saved
  form after `phieukhamId` appears, reads the visible `.NgayKham` value, and
  edits only the examination date when it differs from the requested value.
  `correct_exam_date()` uses the currently bound saved form before falling back
  to the grid.
* **Resume and repair CLI options**:
  `--start-at N` resumes from eligible row N, `--limit N` bounds a chunk,
  `--skip-trial` permits an already-verified unattended chunk, and
  `--repair-current-record` repairs only the currently open saved record after
  confirming its CCCD.
* **Verified live results so far**: the initial record was corrected to the exact
  Tăng Bạt Hổ school and retained date `30/07/2026`. A later 10-row chunk
  (eligible rows 4–13) completed with **6 newly saved, 4 already present, 0 failed**.
  Other trial records were either saved or safely classified as already present.
  This is progress only, not completion of all 1,023 source rows.
* **No-focus/background mode**: the old school lookup used `activate Chrome` plus
  `System Events` select-all/paste, which stole the foreground app, mouse, and
  keyboard. That path has been removed. `AppleScriptImporter.goto()` no longer
  activates Chrome, and `AppleScriptImporter.select_school_lookup()` only waits
  for the signed-in Chrome tab to receive the school selection from the background
  controller. No active importer process was left running after the foreground
  issue was reported.
* **Verification**: `python3 -m unittest discover -s tests` passes **7/7** after
  the background-navigation and school-selection changes.

### 1. Form Reset Behavior on Success
* **Discovery**: When clicking "Lưu" (Save), if the record is saved successfully, the web application resets all fields on the form to blank/empty values but keeps the form container open and active.
* **Impact**: The original importer script checked `is_form_still_open` using `.TienSu_TX_NguoiBenhLao`. Because the form stayed open (but was blank), it timed out after 15 seconds, concluding the save failed and creating duplicates during re-runs.
* **Solution**: The success check was updated to look at the child name input value (`.HoTen input.dx-texteditor-input`). If it is blank *and* there are no validation error messages (`.dx-invalid` or `.dx-validationsummary-item`), the save is confirmed as successful, and the script clicks the `Quay lại` button to navigate back to the list grid.

### 2. DevExtreme/Angular Model Sync
* Programmatic value assignments (`input.value = 'val'`) and standard `click()` events do not trigger state changes in Angular/DevExtreme.
* **Text inputs**: We simulate character-by-character keypress events (`KeyboardEvent` sequence: `keydown`, `keypress`, `input`, `keyup`) followed by `change` and `blur` events.
* **Radio buttons & Checkboxes**: We dispatch a pointer sequence (`pointerdown`, `mousedown`, `focus`, `pointerup`, `mouseup`, `click`) to trigger widget model binding.

---

## 🛠️ Execution & Diagnostic Scripts

* **`python3 scripts/import_health_check.py`**:
  Main bulk importer. Reads `parsed_children_data.json`, checks if child's CCCD exists in the grid, skips if present, fills details, and saves.
* **`python3 scripts/test_specific_child.py "<child name>"`**:
  Fills out and saves a specific child's form by name, dumping DOM errors if the save fails. Handles empty phone fallbacks.
* **`python3 scripts/search_cccd_any_date.py <cccd>`**:
  Queries a specific CCCD on the grid list for any date to check if they exist.
* **`python3 scripts/close_modal.py`**:
  Closes any open form/popups and returns the browser state to the list grid.
* **`python3 scripts/capture_chrome.py`**:
  Saves a screenshot of Google Chrome.
