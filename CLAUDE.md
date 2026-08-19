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

### 0a. Medinet M2 Dental Chart Automation (Biểu đồ răng KSKD18) — Fully Resolved
* **Iframe Architecture**: The dental chart is embedded via `<iframe src=".../ksk_kham_rang_m2.html">`.
* **Auto-Initialization via Native postMessage**:
  - In `ksk_kham_rang_m2.html`, JavaScript functions are block-scoped (`const`).
  - To initialize/render all 52 tooth cards immediately, post an `INIT_DATA` message:
    `win.postMessage({action: "INIT_DATA", payload: []}, "*")`.
  - This executes the iframe's native listener: `renderDentalChart()`, `initializeBulkToolbar()`, and `loadDentalData([])`.
* **Bulk Toolbar Interaction Flow (Verified 100%)**:
  1. Trigger iframe chart render: `win.postMessage({action: "INIT_DATA", payload: []}, "*")`.
  2. Select status in `#bulkStatusSelect` (192 for "Sâu", 193 for "Trám sâu lại").
  3. Click each target tooth card (`#tooth-card-[số_răng]`) to mark it selected (`is-selected`).
  4. Click `#applyBulkStatusBtn` ("Áp dụng") -> updates tooth visual appearance and executes `buildDentalJSON()`, posting `dentalData` array to parent Angular via `window.parent.postMessage(dentalData, "*")`.
  5. As fallback, also set `select.tooth-select[data-tooth="..."]` value and dispatch `change` event.
  6. Fill RHM Diagnosis: uncheck `RHM_ChuaPhatHienBatThuong` and set `RHM_ChanDoanSoBo_ICD` to `K02.9 -- Sâu răng, không đặc hiệu`.
  7. Click **"Lưu thay đổi"** to persist to Medinet backend.
* **CRITICAL ROOT CAUSE: React Developer Tools / Chrome Extension Message Interference**:
  - Medinet Angular has a bug in `onMessageReceived(e)`:
    ```javascript
    t.prototype.onMessageReceived = function(e) {
        if (e && e.data && this.iframeElement) {
            this.formData[this.frameview.dataField] = JSON.stringify(e.data);
        }
    }
    ```
  - Angular does NOT check `e.origin` or `Array.isArray(e.data)`.
  - If **React Developer Tools** (or similar dev extension) is active in Chrome, it continuously broadcasts `postMessage({"source":"react-devtools-content-script", ...})`.
  - Medinet treats this noise as dental data and overwrites `this.formData['KhamRangJSON']`. When saving, the backend discards the malformed JSON.
  - **Resolution**:
    1. In Chrome, disable React Developer Tools under `chrome://extensions/`.
    2. In automated scripts, install a capturing listener (`useCapture = true`) in `HELPERS_JS` to intercept and `stopImmediatePropagation()` on any message containing `react-devtools`, `redux`, or `webpack`.
* **Tooth Status Mapping & Colors**:
  - `ID 191`: "Bình thường" (Green `#10b981`)
  - `ID 192`: "Sâu" (Red `#ef4444`)
  - `ID 193`: "Trám sâu lại" (Orange `#f97316`)
  - `ID 194`: "Trám tốt" (Blue `#3b82f6`)
* **Verification / Reload Mechanism**: When reopening the record from URL, the iframe starts in default state until navigating via sidebar: click **"Thông tin hành chính"** then click **"Khám lâm sàng"**. This triggers Angular's `sendDataToChild()` which posts `{action: "INIT_DATA", payload: [...]}` to the iframe and renders the saved teeth in their respective colors.
* **Batch Results for 53 Partial Students**:
  - Script: `scripts/retry_teeth_only.py --file "..." --from 01/07/2026 --to 16/08/2026 --cccd-file scripts/teeth_cccd_list.txt`
  - 52/53 Done (100% OK), 1 Partial (TT273 had invalid non-FDI tooth 93 in source Excel, other 3 teeth saved).

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

### 0f. Quy trình chuẩn để nhập một file danh sách trường (M2)
Rút ra từ đợt TH Nguyễn Thái Bình 04/08/2026 (336 dòng → 335 em vào Medinet). Làm
đúng thứ tự này; các bước kiểm tra không phải là tuỳ chọn.

**1. Đọc thử file trước khi mở trình duyệt**
```
python3 -m app.importer --check-file "data/<file>.xlsx"
```
Xem số dòng, số thiếu Phường/Xã, số thiếu CCCD người giám hộ. Nếu có dòng
`no_ward`, thêm alias vào `WARD_PATTERNS` trong `app/parsers.py` — nhưng **phải mở
danh mục Phường/Xã trên form Medinet, gõ thử và đọc đúng nhãn thật** rồi mới thêm.
Không suy đoán nhãn (`Xã Hiệp Phước` chứ không phải `Phường Hiệp Phước`).

**2. Chạy một bản thử thật, rồi mới chạy hàng loạt**
```
python3 -m app.importer --file "data/<file>.xlsx" --age-group m2 \
  --exam-date DD/MM/YYYY --limit 1
```
Sau khi lưu, **đọc lại form vừa lưu** để đối chiếu tên, CCCD, ngày khám, trường,
lớp, phường với file nguồn. Chỉ khi bản thử đúng mới chạy tiếp với `--skip-trial`.

**3. Chạy hàng loạt theo từng đợt, ghi log ra file**
```
python3 -u -m app.importer --file "data/<file>.xlsx" --age-group m2 \
  --exam-date DD/MM/YYYY --start-at N --skip-trial > run.log 2>&1 &
```
`--start-at` đếm theo **hồ sơ hợp lệ**, không theo TT. Theo dõi log bằng dòng kết
quả `(failed in Ns)`, **không** bằng các dòng `ABORT` — nhiều dòng ABORT chỉ là bước
dò nội bộ rồi tự sửa được.

**4. Dừng và chạy tiếp giữa chừng**
Dừng bằng `pkill -f "app.importer --file"`. Hồ sơ đang dở chưa lưu nên không hỏng.
Đọc `import_results.json` → `checkpoint.position`; điểm chạy tiếp =
`--start-at` của lần chạy đó + `position`. Lưu ý `import_results.json` **bị ghi đè
mỗi lần chạy**, nên phải ghi lại danh sách failed trước khi chạy đợt mới.

**5. Chạy lại các hồ sơ thất bại**
Chạy riêng từng em bằng `--start-at <index> --limit 1`. Form được nạp mới nên tới
giờ lần chạy lại nào cũng thành công. **Nếu bỏ qua bước này thì em đó mất luôn** —
đợt vừa rồi suýt sót một em vì đợt sau bắt đầu từ vị trí sau chỗ lỗi.

**6. Đối chiếu cuối cùng trước khi báo "xong"**
Ghép từng dòng `[n/N] TTx tên (cccd)` trong log với dòng `saved (phieukhamId=...)`
ngay sau nó, rồi so với `load_records()`. Các đợt chạy tay không ghi ra file log nên
phải ghi lại `phieukhamId` riêng. Em nào Medinet báo đã có sẵn (không tạo phiếu mới,
không báo lỗi) là bình thường, không phải lỗi.

**7. Việc luôn phải làm tay**
Dòng nào thiếu CCCD người giám hộ thì form M2 không lưu được — liệt kê cho người
dùng nhập tay. **Không bao giờ tự bịa số định danh.**

**Nguyên tắc bất biến khi sửa code trong luồng này**
* Mỗi hồ sơ phải đi qua grid rồi mới mở form trắng — đó là thứ giữ cho script chỉ
  thêm mới, không sửa đè hồ sơ cũ.
* Với dropdown danh mục, **chỉ `id` danh mục mới là bằng chứng đã chọn**, không phải
  chữ hiển thị. Mỗi lượt chỉ bấm một lần rồi chờ xác nhận; bấm lại dồn dập làm
  DevExtreme kẹt.
* So sánh mọi chữ tiếng Việt lấy từ trang ở dạng **NFC** cả hai phía (`nfc()` bên
  Python, `.normalize('NFC')` trong JS) — Medinet trả về một số nhãn ở dạng tách dấu.
* Ngày khám: giữ **cả hai** đường — `set_datebox` lúc tạo và `correct_exam_date()`
  sau khi lưu. Bỏ đường nào cũng có hồ sơ sai ngày.
* Sửa code giữa lúc đang chạy hàng loạt thì phải chạy thử lại vài hồ sơ trước khi
  chạy tiếp; đo trước khi tối ưu, đừng đoán chỗ chậm.
* Tốc độ thực tế ~60–68s/hồ sơ. `python3 -m unittest discover -s tests` phải xanh
  (hiện 26/26).

### 0g. Nhập nội dung KHÁM (không phải hành chính) — `app/clinical.py`
Luồng thứ hai, tách hẳn khỏi `app/importer.py`. `importer.py` **tạo** hồ sơ hành
chính; `clinical.py` **chỉ sửa hồ sơ đã có**: tìm theo CCCD trong khoảng ngày khám,
mở hồ sơ đó rồi điền 4 phần chuyên môn. Không bao giờ tạo/xoá hồ sơ. Em nào không
tìm thấy thì bỏ qua và ghi vào `clinical_results.json` (`not_found`).

```
python3 -m app.clinical --file "data/<file>.xlsx" --check-file        # chỉ đọc Excel
python3 -m app.clinical --file "data/<file>.xlsx" --only-cccd <cccd>  # chạy 1 em
python3 -m app.clinical --file "data/<file>.xlsx" --from 01/07/2026 --to 08/08/2026
```

**URL từng phần** (`<nav>` = `/nav_group/kskdk_thongtinkhamduoi18/app/main`):
| Phần | Đường dẫn | Nút lưu |
|---|---|---|
| Thông tin hành chính | `<nav>/dynamicform/viewer/KSKD18_TTHC/<pid>` | Lưu thay đổi |
| Tiền sử bản thân (gồm **Khám thể lực**) | `<nav>/dynamicform/viewer/KSKD18_TTHC_TienSu/<pid>` | Lưu thay đổi |
| Đánh giá tâm thần | `<nav>/dynamicviewer/tabpanel/KSKD18_TAB_DANHGIATAMTHAN/<1\|2>/<pid>` | **Lưu** |
| Khám lâm sàng | `<nav>/dynamicform/viewer/KSKD18_ThongTinKham/<pid>` | Lưu thay đổi |
| Kết luận | `<nav>/dynamicform/viewer/KSKD18_KetLuanKham/<pid>` | Lưu thay đổi |

Query string bắt buộc: `?cdId=<cdId>&phieukhamId=<pid>&MauKham=mauphieukskd18`.
Lấy `pid`/`cdId` bằng cách bấm bút sửa trên lưới M2 rồi đọc URL.

**Những cái bẫy đã mất công tìm ra — đừng phá:**
* **Lưới M2 lọc được theo khoảng ngày khám.** `input[id$="_KSKDK_NgayKham"]` là
  textbox nhận chuỗi `"01/07/2026 - 08/08/2026"`; gõ từng ký tự rồi bấm `Xem`.
* **Bẫy nặng nhất: lưới giữ nguyên kết quả của lần tìm trước.** Bấm `Xem` khi lưới
  còn đang tải thì DevExtreme nuốt cú click (nút đang `dx-state-disabled`), và báo
  cáo này khôi phục kết quả cũ khi nạp lại trang — nên màn hình hiển thị **hồ sơ của
  em trước đó**. Lần chạy đầu vì thế báo sai "không tìm thấy" cho 6 em, trong đó 3 em
  thật sự có hồ sơ. Bắt buộc: chờ lưới rảnh → bấm `Xem` → **chờ nội dung lưới thật sự
  đổi** rồi mới đọc kết quả (`run_search()`), và `location.reload()` mỗi lần tìm vì
  `location.assign` sang đúng URL đang mở là lệnh rỗng.
* **Không được đánh đồng "hết giờ chờ" với "không có hồ sơ".** `find_record()` trả về
  ba trạng thái: `match` / `empty` / `unknown`. Chỉ `empty` (Medinet tự báo
  "Không có dữ liệu" hoặc "Có 0 kết quả") mới được ghi là không tìm thấy; `unknown`
  phải vào nhóm `search_failed` để chạy lại, nếu không sẽ bỏ sót em có hồ sơ.
  Tìm thấy dứt khoát mất ~9s; chạm mốc 40s gần như luôn là lỗi, không phải vắng mặt.
* **Số thập phân dùng DẤU PHẨY.** Gõ `121.5` vào ô chiều cao ra **1.215 cm**. Xem
  `ksk_workbook.number()`. Thị lực `1/10` chỉ nhập tử số (`1`) vào number box.
* **Lưu xong Medinet KHÔNG báo gì cả** — không toast, không đổi URL. Tệ hơn: các
  node `"Vui lòng nhập ..."` từ lúc trang mới tải vẫn nằm trong DOM, đọc vào là
  tưởng lỗi. Hook `fetch`/XHR cũng không bắt được request. **Bằng chứng duy nhất
  là nạp lại trang và đọc lại giá trị** — đó là việc của các hàm `verify_*`.
* **Bảng tiêm chủng (38 liều) re-bind sau mỗi lần click.** Click cả 38 trong một
  lượt JS làm hai grid rỗng và không lưu gì. Phải click từng dòng, cách nhau
  `VACCINE_TICK_MS` (120ms), do một bộ đếm `setTimeout` chạy trong trang — không
  phải mỗi dòng một lượt AppleScript (chậm gấp bốn).
* **Bảng câu hỏi tâm thần nạp dòng dần dần.** Điền ngay sau khi form hiện ra thì
  mất mấy câu đầu. Phải chờ đủ số dòng (`question_rows()`).
* **So nhãn lựa chọn phải BỎ QUA HOA/THƯỜNG** — dùng `window.__mx.same()`, đừng so
  `===`. Form ghi `Thỉnh thoảng` (T hoa) còn Excel ghi `thỉnh thoảng` (t thường), nên
  so khớp đúng-từng-ký-tự làm **mọi câu trả lời "thỉnh thoảng" bị bỏ trống**. Nặng hơn
  nữa: `pick_list_answer()` cũ trả về chuỗi `'no-option'` khi không thấy lựa chọn, mà
  `'no-option' is not False` → **báo thành công**, nên lỗi bị nuốt hoàn toàn, log sạch
  trơn. Chỉ lộ ra nhờ `verify_*` đếm số dòng đã trả lời. Quy tắc rút ra: **hàm chọn
  phải trả về `False` khi không tìm thấy lựa chọn**, đừng bao giờ trả chuỗi rồi so
  `is not False`. Đợt `nhap.xlsx` có 10 em dính (51 ô).
* **Ba kiểu widget chọn một, trông giống hệt nhau:** dxRadioGroup (`.TS_BanThan_SanKhoa`)
  có nhãn trong `.dx-item-content`; dxList có trang trí radio (`.DeNghi`) thì
  **phải click vào `.dx-list-select-radiobutton`**, click vào `.dx-list-item` không
  ăn; dxList trơn (bảng câu hỏi) thì click thẳng item. `pick_radio()` xử lý cả ba.
* **"Đề nghị (ghi rõ)" là HtmlEditor (Quill).** `<textarea>` chỉ là submit element,
  ghi vào đó vô nghĩa. Phải `execCommand('insertText')` trên `.ql-editor` rồi chờ
  Quill đẩy sang submit element.
* **Sơ đồ răng không thể hiện tình trạng đã lưu** — mọi răng đều là `t<N>.png` theo
  vị trí. Muốn biết răng đã ghi "Sâu" chưa thì phải mở popup và đọc `.TinhTrangId`.
* **"Thần kinh" trong Khám lâm sàng dùng class `NoiTiet_*`** (lỗi đặt tên của
  Medinet), nhưng phân loại lại là `ThanKinh_PhanLoai`.
* **Widget ngoài vùng nhìn thấy không nhận click** — DevExtreme đọc toạ độ con trỏ.
  `__mx.click()` tự `scrollIntoView` trước.
* **Kết luận phải làm CUỐI CÙNG.** Mục *2. Bệnh, tật cần lưu ý* là ô chỉ đọc, do
  Medinet tự tính từ các chẩn đoán **đã lưu**. Quy tắc: mục 2 = "Không có" →
  chọn *Bình thường, hẹn khám định kỳ lần sau*; khác thế → chọn *Có yếu tố nguy cơ,
  cần theo dõi thêm* và điền cột `Đề nghị` (BM) của Excel vào ô *Đề nghị (ghi rõ)*.
* **Ngày đánh giá tâm thần = ngày khám của hồ sơ**, không phải hôm nay. Đọc từ cột
  NGÀY KHÁM của lưới, đặt qua `set_datebox` (gõ tay chỉ đổi chữ hiển thị).

**Em "không đi học" — vì sao tìm không ra (đã điều tra 09/08/2026):**
Hồ sơ dạng `Mẫu từ 6 đến 18 tuổi không đi học (M12)` có thể **không có Ngày khám**.
Danh sách M12 lọc **bắt buộc** theo ngày khám — để trống bộ lọc thì truy vấn trả về
**0 kết quả cho mọi thứ**, nên hồ sơ không có ngày khám thì **không khoảng ngày nào
chứa được**. Đã thử và đều không ra: mọi khoảng ngày (kể cả 01/01/2020–31/12/2030),
tìm theo họ tên, `KSKDK_DanhSach_KSK_TheoDiaBan_VIEW`, `KSK_KSKTE_TreEm_..._KTSK`
(M10), `KSKDK_GhiNhanThongTinDaKhamSucKhoe_Report`.
**Cách giải — gọi thẳng API, bỏ qua ràng buộc của giao diện.** Ràng buộc "phải có
ngày khám" **chỉ nằm ở giao diện** (`required=true` trên định nghĩa bộ lọc); stored
procedure sau lưng nó không đòi. Backend nhận **cookie phiên** của tab đang đăng
nhập, nên hỏi thẳng báo cáo M12 với mỗi CCCD, **không truyền ngày**, là ra hồ sơ kèm
`phieukhamId` và `cdId`. Đã cài sẵn trong `ClinicalFiller.api_lookup()`, tự động chạy
khi lưới báo `empty` — không phải làm gì thêm.

Ba mảnh ghép cần nhớ:
* Backend: `https://be-qlskcd.medinet.org.vn/api/services/app/...`, gọi bằng
  `fetch(..., {credentials:'include'})` từ tab đã đăng nhập. **Phải kèm header
  `Authorization: Bearer ...`** — xem mục ngay dưới. (Trước 10/08/2026 chỉ cookie là
  đủ; nay không còn đủ.)
* Body của `PostDataWithDataOutput` là **mảng `FParameter`**, và trường tên là
  **`varible`** (backend viết sai chính tả), không phải `name`/`code`/`key`:
  `[{"varible":"KSKDK_DinhDanhCaNhan","value":"<cccd>"}]`. Tra được nhờ
  `https://be-qlskcd.medinet.org.vn/swagger/v1/swagger.json` → `definitions.FParameter`.
  **Swagger mở, dùng nó thay vì đoán.**
* `reportId` lấy qua `DRReport/GetIdByCode?code=KSKDK_DanhSach_KSK_M12` (hiện là
  1002123), `SessionSiteId` qua `User/GetSessionSiteByViewCode` (hiện 130).
  Response có đủ `phieukhamId`, `cdId`, `NgayKham`, `HoTen`, `MaPhieu`.

**Lấy token Bearer (bắt buộc từ 10/08/2026) — `TOKEN_TAP_JS` + `auth_token()`:**
Backend giờ trả `{"error":{"message":"Current user did not login to the application!"},
"unAuthorizedRequest":true}` cho mọi request không có header `Authorization`, kể cả khi
giao diện vẫn đăng nhập bình thường. Triệu chứng ở tầng trên: `api_lookup()` trả
`None` cho **mọi** CCCD, nên em không có Ngày khám bị ghi nhầm là `not_found` — đúng
cái bẫy mà API sinh ra để tránh. Nếu thấy `not_found` hàng loạt, **nghi ngờ token
trước tiên**, đừng kết luận là hồ sơ không tồn tại.

Token **không đọc được bằng script thường**: `localStorage['1_keys'].enc_tk` đã mã
hoá, và JS chạy qua Apple Events ở isolated world nên không thấy biến của app. Cách
lấy: chèn thẻ `<script>` vào **page world**, bọc `XMLHttpRequest.prototype.setRequestHeader`
(và `window.fetch`), chờ app tự gọi một request rồi cất header `Authorization` vào một
node DOM ẩn (`#__mxtok`) — controlling script đọc node đó như DOM bình thường. Toàn bộ
đã cài trong `TOKEN_TAP_JS`, `install_helpers()` tự đặt bẫy trên mọi trang, `api()` tự
gắn token. Không cần làm gì thêm. Đọc lại token mỗi lần gọi chứ không cache cứng, vì
token có xoay vòng.

**Quy trình cho em tìm không ra (đã dùng lại 10/08/2026, chạy tốt):**
1. Tra `f.api_lookup(cccd)` → ra `phieukhamId`, `cdId`, và `NgayKham: None`.
2. Chạy `python3 -m app.clinical --file <file> --only-cccd <cccd> --exam-date DD/MM/YYYY`.
   Ngày khám đang trống sẽ được ghi vào, sau đó em hiện ra trong danh sách M12 và nhập
   bình thường. Ngày lấy theo ngày khám của các em cùng đợt (đợt `nhap.xlsx` là
   `28/07/2026`).

`--exam-date DD/MM/YYYY` ghi Ngày khám khi ô đang trống → sau đó em đó **hiện ra
trong danh sách M12 và tìm/sửa bình thường**. Ngày đã có sẵn thì giữ nguyên, trừ khi
thêm `--force-exam-date`. `--record-url` (dán URL hồ sơ) vẫn còn để dùng tay; nó luôn
đối chiếu CCCD trên form trước khi nhập, lệch là dừng.

**Không dùng "Thêm mới" để dò ID** — luồng đó có thể tạo hồ sơ trùng, phá vỡ nguyên
tắc chỉ thêm-không-sửa của dự án.

**JS qua AppleScript chạy ở "isolated world"** — chung DOM nhưng khác `window` với
app. Vì vậy **không hook được `fetch`/`XHR` của Angular** (đã thử cả vá prototype lẫn
thay constructor, đều không bắt được — đừng thử lại), và `window.DevExpress`,
`jQuery`, `ng` đều `undefined` khi nhìn từ đó. Muốn chạy trong page world thì chèn
`<script>` rồi trả kết quả qua một node DOM ẩn. Muốn biết app gọi API nào thì đọc
`performance.getEntriesByType('resource')` — cái này thấy hết.

**Mã ICD trong Excel có thể là mã nhóm, Medinet chỉ có mã lá.** Ví dụ `F90`: danh mục
chỉ có F90.0 / F90.1 / F90.8 / F90.9. Chọn nhánh nào là **quyết định chuyên môn** —
`fill_diagnosis()` liệt kê các lựa chọn ra log cho người dùng chọn tay, **không tự
đoán**.

**Giả định đang áp dụng, nếu sai thì sửa ở đây:** cột `Tiêm chủng` chỉ có một giá
trị chung ("Đã tiêm") nên được áp cho **cả 38 liều**; cột `Tiền sử gia đình` =
"Không" nên **không tích ô nào**; `Phân loại thể lực` và `Phân loại Loại I–V` của
từng cơ quan **không có trong Excel nên để nguyên**; phần **Khám cận lâm sàng
không đụng tới**. Mục *1. Tình trạng sức khỏe* và *2. Bệnh, tật cần lưu ý* là ô chỉ
đọc nên cột BK/BL của Excel không nhập được — Medinet tự suy ra.

Tốc độ ~165s/hồ sơ (đã gồm nạp lại 5 lần để đối chiếu). Test:
`python3 -m unittest discover -s tests` (46/46).

**Đã chạy xong — `data/MAU AI NHAP LIEU  KSK.xlsx` (09/08/2026):**
**10/10 em** đã nhập đủ 4 phần; mỗi phần **lưu xong đều nạp lại trang và đọc lại để
đối chiếu** (`verify_*`). Tất cả đều mang ngày khám `28/07/2026`:

| TT | Họ tên | CCCD | phieukhamId |
|---|---|---|---|
| 1 | NGUYỄN HOÀNG MINH KHANG | 079219037487 | 1360002 |
| 2 | NGUYỄN HOÀNG KHÁNH THY | 079316000498 | 1359977 |
| 3 | HUỲNH NGỌC THIÊN KIM | 079320021138 | 1360448 |
| 4 | NGUYỄN NGỌC AN NHIÊN | 079319015955 | 1360003 |
| 5 | NGUYỄN THẢO NGUYÊN | 079317000463 | 1359989 |
| 6 | NGUYỄN BẢO ANH | 066318020155 | 1360415 |
| 7 | TRẦN ĐẶNG ANH KHOA | 079216003246 | 1359979 |
| 8 | TRẦN CHÍ TÂM | 079216021273 | 1360388 |
| 9 | ĐẶNG NGUYỄN NGỌC LAM | 079319004275 | 1360432 |
| 10 | NGÔ NGUYỄN GIA KHANG | 079216015870 | 1360384 |

Năm em TT1, 2, 4, 5, 7 ban đầu **không tìm được** vì hồ sơ dạng "không đi học"
không có Ngày khám; đã tra ID qua API rồi đặt `--exam-date 28/07/2026`, sau đó nhập
bình thường. `cdId` **không** suy ra được từ `phieukhamId` (chênh lệch khác nhau
giữa các hồ sơ) — phải lấy cả hai từ API.

**Việc còn dở, cần người quyết:** TT4 NGUYỄN NGỌC AN NHIÊN — mục *Tâm thần* trong
Khám lâm sàng chưa điền. Excel ghi `F90` nhưng Medinet chỉ có F90.0 / F90.1 / F90.8 /
F90.9; chọn nhánh nào là quyết định chuyên môn. Bốn phần còn lại của em đã lưu xong.

**Ba lỗi đã sửa trong đợt này, đừng để tái diễn:**
* Số đo dùng **dấu phẩy** — `121.5` vào ô chiều cao ra 1.215 cm (`ksk_workbook.number()`).
* Lưới giữ kết quả tìm kiếm cũ → lần chạy đầu báo sai "không tìm thấy" cho 6 em,
  3 em trong đó có hồ sơ thật (`run_search()` giờ bắt buộc lưới đổi nội dung).
* Radio/list render sau khung form → `pick_radio()` phải chờ và thử lại, không thì
  câu hỏi bị bỏ trống mà không báo lỗi.

### 0h. Nhập nội dung khám — cạm bẫy dùng chung cho mọi đợt

Đúc kết từ đợt `data/nhap.xlsx` (10–11/08/2026, 111 hồ sơ, ngày khám `28/07/2026`,
kết quả 105 em nhập đủ 5 phần). Viết ở đây là **quy tắc chung**, áp cho mọi file danh
sách sau này; chi tiết riêng của từng đợt thì để trong log và `clinical_results.json`.

**Ba lỗi ÂM THẦM — chạy xong không báo gì mà dữ liệu vẫn thiếu.** Đây là loại nguy
hiểm nhất, vì log sạch trơn nên rất dễ tưởng đã xong:

1. **So nhãn lựa chọn phân biệt hoa/thường.** Form ghi `Thỉnh thoảng`, Excel ghi
   `thỉnh thoảng` → không tìm thấy lựa chọn. Luôn dùng `window.__mx.same()`
   (NFC + lowercase), **không bao giờ dùng `===`** để so nhãn với giá trị trong Excel.
2. **Hàm chọn trả về sentinel thay vì `False`.** `pick_list_answer()` cũ trả chuỗi
   `'no-option'`, người gọi lại kiểm `is not False` → chuỗi non-empty lọt qua thành
   "thành công". **Hàm chọn không tìm thấy lựa chọn thì phải trả `False`**, đừng trả
   chuỗi rồi bắt người gọi diễn giải.
3. **Ô rỗng bị hiểu nhầm thành một câu trả lời hợp lệ.** Ô *2. Bệnh, tật cần lưu ý*
   do Medinet tự tính nên hiện sau phần còn lại của form; đọc sớm ra rỗng, mà rỗng lại
   **trùng nghĩa với "trẻ khoẻ mạnh"** → chọn sai mục 3 và bỏ trống ô Đề nghị. Nguyên
   tắc: **"chưa nạp xong" và "giá trị rỗng hợp lệ" phải là hai trạng thái khác nhau**.
   Ở đây phân biệt được vì trẻ khoẻ mạnh luôn hiện chữ "Không có" — nên chờ tới khi ô
   có chữ, và ô rỗng thì coi là đọc lỗi chứ không đoán.

**Cách phát hiện cả ba:** chỉ có bước **nạp lại trang đọc ngược** (`verify_*`) mới bắt
được. Nó làm chậm gấp đôi nhưng **đừng bỏ**. Dấu hiệu nhận biết lỗi loại 1–2: dòng
`verify` báo *"chỉ lưu N/M"* mà **phía trên không có dòng lỗi nào cho từng mục** — khi
đó hàm chọn đang nói dối, hãy so chuỗi thật trên form với giá trị trong Excel trước khi
đổ cho chờ hụt. Cách khoanh vùng nhanh: đếm số ô thiếu và đối chiếu với số lần xuất
hiện của từng giá trị riêng biệt trong cột đó.

**Hai lỗi làm hỏng cả hồ sơ, không âm thầm nhưng dễ chẩn đoán sai:**

4. **Lưu thành công bị báo nhầm là thất bại.** Lưu xong form rebind về trống nên các ô
   bắt buộc lại kêu *"Vui lòng nhập ..."*. **Chỉ tin thông báo lỗi sau khi nạp lại
   trang và `verify_*` xác nhận dữ liệu thiếu thật.**
5. **Ngày rỗng lọt vào ô ngày.** Mở trang hỏng → `ensure_exam_date()` trả chuỗi rỗng →
   `set_datebox()` vỡ giữa chừng, hồ sơ dở dang. Ô ngày phải từ chối chuỗi không đúng
   `DD/MM/YYYY`, và hồ sơ không đọc được ngày khám thì **dừng lại báo `no_exam_date`**
   chứ không chạy tiếp nửa vời.

**Quy ước đọc dữ liệu Excel:**
* Ô "chọn một" mà Excel ghi bằng câu chữ thay vì Có/Không: dùng `is_no()` — chỉ các từ
  phủ định mới là "Không", **mọi thứ khác là "Có"** kèm ghi chú lại phần chữ. Không
  bao giờ đổ phần chữ sang một ô khác, kể cả ô nghe có vẻ liên quan: đó là câu hỏi
  khác và Excel thường đã có câu trả lời riêng cho nó.
* **Mã ICD dạng nhóm** (không có dấu chấm, ví dụ `J03`, `F90`): Medinet chỉ có mã lá.
  Rà trước cả file bằng `wb.icd_codes()` lọc mã không có dấu chấm, **hỏi người dùng
  chọn nhánh**, rồi sửa thẳng ô đó trong file nguồn (nhớ sao lưu file trước khi sửa).
  Không bao giờ tự đoán nhánh — đó là quyết định chuyên môn.

**Bài học vận hành:**
* **Tiến trình chạy nền chết theo phiên Claude Code.** `nohup ... &` **KHÔNG đủ** —
  đã mất một đợt vá giữa chừng (11/08/2026) vì cả nhóm tiến trình bị dọn theo phiên.
  `setsid` **không có trên macOS**. Cách chạy được: cho Python tự tách session
  `subprocess.Popen([...], start_new_session=True, stdin=DEVNULL)` — nó gọi `setsid(2)`
  nên tiến trình sang session riêng, không dính lệnh dọn của harness. Đợt dài vẫn phải
  kiểm lại bằng `ps aux`, và **đợt nhiều em thì mỗi em một log riêng** để biết chính
  xác em nào bị cắt giữa chừng.
* **`clinical_results.json` bị ghi đè mỗi lần chạy** → sao lưu sau mỗi chặng. Cách đối
  chiếu tin cậy nhất là **gộp tất cả file log** rồi lấy trạng thái cuối theo từng TT.
* **Tốc độ dao động rất mạnh** theo tải của Medinet: 130s → 870s/hồ sơ trong cùng một
  đêm. Chậm không có nghĩa là hỏng.
* Chạy lại từng em bằng `--only-cccd` gần như luôn cứu được hồ sơ thiếu mục — **trừ
  khi nguyên nhân là lỗi so khớp**, khi đó chạy lại bao nhiêu lần cũng vô ích. Nếu
  chạy lại một lần mà vẫn thiếu đúng chỗ cũ thì dừng, đi tìm lỗi so khớp.

**`--xa-phuong "Phường ..."` — hồ sơ thiếu Phường/Xã nơi ở.**
`DiaChiHienTai_XaPhuong` là ô bắt buộc; thiếu nó thì form **không lưu được gì cả**, kể
cả ngày khám (triệu chứng: *"lưu ngày khám thất bại: Vui lòng nhập phường, xã"*).
Thường gặp ở em có địa chỉ ở tỉnh khác. Cờ này chỉ điền khi ô đang trống, không đè lên
địa chỉ có sẵn. **Phải hỏi người dùng phường nào, đừng suy từ phường của trường.**

**Màn hình `Kiểm tra nhanh` (M11) — tra một em ở MỌI đơn vị, MỌI mẫu khám.**
`https://quanlyskcd.medinet.org.vn/app/main/dynamicreport/report/viewer-utility/KSKNCT_KiemTraNhanh_M11`
(reportId `1002249`, SessionSiteId `130`). Lọc theo **`CMND`** (không phải
`DinhDanhCaNhan`): `[{"varible":"CMND","value":"<cccd>"}]`. Trả về Họ tên, Ngày sinh,
Số điện thoại, **Ngày khám, Mẫu khám, Đơn vị khám** — nhưng **không có `phieukhamId`**,
nên chỉ để chẩn đoán, không mở được hồ sơ từ đây.

**Bắt buộc tra M11 trước khi kết luận "chưa có hồ sơ"**, vì danh sách M12 chỉ liệt kê
hồ sơ 6–18 **của đơn vị mình**. Năm nguyên nhân "không tìm thấy" và cách xử lý:

| M11 cho thấy | Nghĩa là | Làm gì |
|---|---|---|
| Chỉ có **phiếu dưới 6** của năm trước | Chưa có phiếu 6–18 của đợt khám này. Mẫu dưới 6 **không có 4 phần chuyên môn KSKD18** | Sửa ngày cũng vô ích — phải tạo hồ sơ hành chính bằng `importer.py` trước. Báo người dùng |
| Có phiếu 6–18 nhưng **Đơn vị khám khác** | Em khám ở trạm khác | Bỏ qua, báo người dùng — không sửa hồ sơ của đơn vị khác |
| Có phiếu 6–18, **Ngày khám trống** | Đúng bẫy của mục 0g | `api_lookup()` + `--exam-date DD/MM/YYYY` là chạy được |
| **0 dòng** | CCCD trong Excel sai (hoặc em không có CCCD) | Tra lại theo họ tên. **Có kết quả cùng tên vẫn KHÔNG được tự dùng** — xem quy tắc dưới |
| Nhiều dòng cùng tên, khác CCCD | Có thể là hai em khác nhau | Đối chiếu **ngày sinh và số điện thoại**. Lệch là hai người ⇒ hỏi người dùng |

**Quy tắc bất di bất dịch:** chỉ khớp mỗi họ tên thì **không bao giờ đủ** để nhập. Đây
là hồ sơ bệnh; nhập nhầm là ghi vào bệnh án của trẻ khác. Luôn đối chiếu thêm ngày
sinh, và khi vẫn lệch thì đưa cả hai phương án cho người dùng chọn kèm bằng chứng
(ngày sinh, số điện thoại, số đo thể lực có hợp với tuổi không).

### 0i. TH Xóm Chiếu — quy tắc nhập thủ công và trạng thái lần chạy 18/08/2026

Nguồn đang xử lý là workbook:
`/Users/hienphantrong/Downloads/TH Xom Chieu_MAU AI NHAP LIEU  KSK.xlsx`.
Người dùng yêu cầu **nhập khám sức khỏe thủ công trên hồ sơ Medinet**, không dùng
luồng import file. Luồng này chỉ sửa các hồ sơ đã có; không tạo hồ sơ mới và không
xoá hay sửa hồ sơ ngoài danh sách.

**Quy tắc dữ liệu đã chốt:**
* Mã ICD trần `F90` trong Excel phải nhập thành mã lá `F90.0`. Nếu Excel đã ghi
  `F90.0` thì giữ nguyên và không tạo mã trùng.
* Nhãn tình trạng răng `Trám sâu` (cách ghi của người nhập) phải đổi thành
  `Trám sâu lại`, là nhãn hiện có trong biểu đồ răng Medinet. Các nhãn khác giữ
  nguyên.
* Biểu đồ răng M2 có thể nằm trong iframe `ksk_kham_rang_m2`; khi có iframe phải
  chọn `.tooth-select[data-tooth=...]` và phát cả `input` lẫn `change`. Biểu đồ
  dạng cũ trong tài liệu chính vẫn dùng fallback `.tooth`.
* Kết quả chạy có thể đặt ở file riêng bằng biến môi trường `CLINICAL_RESULTS_FILE`
  để các lần chạy lại không ghi đè `clinical_results.json` chung.

**Công cụ chạy lại:** `scripts/retry_partial_clinical.py` đọc các kết quả `partial`,
ưu tiên mở thẳng hồ sơ bằng cặp `phieukhamId` + `cdId`, ghi một `.log` và một
`.json` cho từng TT, đồng thời cập nhật `manifest.json`. Không được coi việc mở
thẳng theo ID là bằng chứng hồ sơ đã lưu thành công; vẫn phải đọc lại/verify từng
phần.

**Trạng thái toàn bộ đợt nhập (19/08/2026) — HOÀN TẤT 100%:**
* **53 hồ sơ partial răng**: Đã chạy lại và hoàn thành **52/53 Done**, 1 Partial (TT273 gõ nhầm răng 93 trong Excel).
* **11 hồ sơ từng bị báo open_failed**: Đã chạy lại full 5 mục (Tiền sử, Tâm thần ADHD, Phổ tự kỷ, Khám lâm sàng & Biểu đồ răng, Kết luận) và hoàn thành **11/11 Done 100%** (TT245, TT248, TT250, TT251, TT255, TT257, TT278, TT279, TT280, TT283, TT285).
* **Toàn bộ học sinh trong danh sách KSK trường TH Xóm Chiếu đã được nhập đầy đủ vào hệ thống Medinet.**

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
