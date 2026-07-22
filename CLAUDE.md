# Project Info & Data Entry Automation Guide - COMPLETED

This file provides a summary of the data entry automation task, final statistics, and technical guidelines.

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
medinet form (except final saved-date confirmation, which waits for new data).

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
* **School is a server-backed lookup** (`select_school_lookup`): option text is
  e.g. "TH Đinh Bộ Lĩnh - Phường Xóm Chiếu"; type the distinctive core, wait for
  the async result, then click it.
* **Fixed examination date (Ngày khám)**: `.NgayKham` is a DevExtreme DateBox where
  **typing only changes the display, not the saved value** — an overnight run would
  otherwise file the next day's date. Fixed with `set_datebox()`, which drives the
  calendar (cells carry `data-value="yyyy/MM/dd"`; navigator
  `.dx-calendar-navigator-previous-view/next-view`) so the real model value commits.
  The exam date is captured once at run start (`Importer.exam_date`, or
  `--exam-date DD/MM/YYYY`) and stays constant across midnight. Calendar mechanism
  verified without saving (chose 18/07 same month, 05/06 prev month, held after blur);
  the saved-date in DB will be confirmed on the first M2 trial when new data arrives.
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
* **M2 always runs a "bản thử" first**: fills 1 student, shows the result, asks
  "Tiếp tục nhập hết? (y/n)". This is a required checkpoint before bulk import.
* **Batch is slow**: ~60–75s per M2 record over AppleScript (~9–11h for all 533).
  Run overnight or in chunks with `--limit`. Packaged app rebuilt with all of the
  above. Deeper detail lives in the `m2-form-quirks` memory file.

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
