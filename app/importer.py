"""Import the MN12 health-check list into quanlyskcd.medinet.org.vn using Firefox.

A Playwright port of import_health_check.py, which drove Chrome over AppleScript.
The page interaction (selectors, DevExtreme pointer-event clicks) is unchanged; only
the transport differs -- run_js() now goes through page.evaluate() instead of osascript.

This script only ever ADDS records. It searches each child's CCCD first and skips
anyone already present; it never edits or deletes an existing record.

The Firefox profile is persisted in .playwright-firefox-profile/ so the medinet
login survives between runs.

It drives the user's own everyday browser, existing medinet login included:
  - Chrome on macOS: over AppleScript, in their real profile (Chrome 136+ blocks
    CDP automation of the default profile, so AppleScript is the only route).
  - Firefox everywhere: over Marionette in their default profile (Firefox must be
    closed when the tool starts).
  - --separate-profile switches to an isolated profile beside the app instead
    (Playwright for Chrome/Edge -- also the Chrome path on Windows/Linux, where
    the real profile cannot be automated at all).
Nothing is downloaded onto the target machine; it only needs Chrome or Firefox.

Usage (source):
    python3 -m app.importer                      # Chrome, your real profile (macOS)
    python3 -m app.importer --browser firefox    # Firefox, your real profile
    python3 -m app.importer --separate-profile   # isolated profile, log in once
    python3 -m app.importer --dry-run            # fill forms but never save
    python3 -m app.importer --limit 3            # first 3 eligible records

Packaged (double-click the executable) it does the same, reading children.json from
beside the executable and writing import_results.json there.
"""

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from typing import Dict, List, Optional

# Playwright is imported lazily inside the Chrome path so the Firefox path (pure
# stdlib Marionette) works even where Playwright is not installed.
try:
    from app.marionette import DEFAULT_HOST, DEFAULT_PORT, Marionette, MarionetteError
    from app import parsers
except ImportError:  # frozen / run as a loose script, no package parent
    from marionette import DEFAULT_HOST, DEFAULT_PORT, Marionette, MarionetteError
    import parsers

ROOT_URL = "https://quanlyskcd.medinet.org.vn/"

# Keep the nav_group prefix. Without it the report only renders while the app already
# happens to be in the trẻ em dưới 6 group, and the app drifts to other groups on its
# own -- from the root it lands on BenhTruyenNhiem_BenhAn.
LIST_URL = "https://quanlyskcd.medinet.org.vn/nav_group/ksk_treemduoi6/app/main/dynamicreport/report/viewer-utility/KSK_KSKTE_TreEmDuoi24_ThongTinHanhChinh"


def _base_dir() -> str:
    """Where the user's own files live -- read and written here.

    Frozen (PyInstaller): the folder holding the executable, so children.json,
    the results file and the Firefox profile sit beside the app the user runs --
    not inside the read-only one-file bundle, which is wiped each launch.
    Running from source: the project root.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _bundle_dir() -> str:
    """Where PyInstaller unpacks bundled, read-only data. Source run: project root."""
    return getattr(sys, "_MEIPASS", _base_dir())


BASE_DIR = _base_dir()
DATA_FILE = os.path.join(BASE_DIR, "children.json")
RESULTS_FILE = os.path.join(BASE_DIR, "import_results.json")
# A dedicated profile per browser, kept beside the app so the login persists.
CHROME_PROFILE_DIR = os.path.join(BASE_DIR, "chrome-profile")
FIREFOX_PROFILE_DIR = os.path.join(BASE_DIR, "firefox-profile")
# A copy shipped inside the bundle, seeded next to the executable on first run.
BUNDLED_SAMPLE = os.path.join(_bundle_dir(), "data", "children.json")

NGUOI_KHAM = "Nguyễn Ngọc Thành"

# Marker element that only exists while the add/edit form is open.
FORM_MARKER = ".TienSu_TX_NguoiBenhLao"

# The one form this script may ever type into. The app sometimes drifts to a different
# dynamic form (a stall, a stray click), and every form here looks alike -- same widgets,
# same Lưu button -- so filling the wrong one would quietly file a child's data against
# the wrong record type. The URL is what actually names the form.
FORM_URL_MARKER = "KSK_TreEmDuoi6_ThongTinHanhChinh_MC"


def js_string(value: str) -> str:
    """Embed a Python string into a JS source literal safely (names contain quotes/diacritics)."""
    return json.dumps(value, ensure_ascii=False)


def valid_bhyt(value: str) -> str:
    """Drop a BHYT number the form will not accept.

    The BHYT editor is masked to the full 15-character number. A partial one (most of
    the parsed PDF rows only carry the trailing 10 digits) leaves the mask incomplete:
    it reads back as empty, blocks the save and only says so in a toast. Better to file
    the child with no BHYT than not at all.
    """
    value = (value or "").strip()
    return value if len(value) == 15 else ""


def clean_school_name(school_name: str) -> str:
    name = school_name.strip()
    if name.startswith("Trường "):
        name = name[7:].strip()
    elif name.startswith("Trường"):
        name = name[6:].strip()
    return name


class Importer:
    """Drives the import over a Playwright page. Firefox uses the subclass below."""

    def __init__(self, page=None, dry_run: bool = False):
        self.page = page
        self.dry_run = dry_run

    def run_js(self, code: str):
        return self.page.evaluate(f"() => {{ return ({code}); }}")

    def goto(self, url: str) -> None:
        self.page.goto(url, wait_until="domcontentloaded")

    # --- login / navigation -------------------------------------------------

    def wait_for_login(self, timeout_s: int = 600) -> bool:
        """Block until the report grid is reachable, prompting for a manual login if needed."""
        print(f"Opening {LIST_URL}")
        if self.open_list():
            print("Grid is loaded and ready.")
            return True

        deadline = time.time() + timeout_s
        prompted = False
        while time.time() < deadline:
            if self.has_them_moi():
                print("Grid is loaded and ready.")
                return True
            if not prompted:
                print("\n" + "=" * 68)
                print("  Please log in to quanlyskcd.medinet.org.vn in the browser window.")
                print("  Navigate to: Khám sức khỏe trẻ em -> Thông tin hành chính")
                print("  The import starts automatically once the grid appears.")
                print("=" * 68 + "\n")
                prompted = True
            time.sleep(2.0)
        return False

    def open_list(self, timeout_s: int = 60) -> bool:
        """Open the report grid, booting the app from its root first if it needs it.

        A cold deep link into the report renders a blank page -- the Angular app only
        boots from the root, and until it has, the report URL produces an empty body
        that is indistinguishable from a slow-loading grid.
        """
        self.goto(LIST_URL)
        if self.wait_for_grid(20):
            return True

        print("  report came up blank -- booting the app from its root, then retrying")
        self.goto(ROOT_URL)
        for _ in range(30):
            time.sleep(1.0)
            if (self.run_js("document.body.innerText.trim().length") or 0) > 50:
                break
        self.goto(LIST_URL)
        return self.wait_for_grid(timeout_s)

    def wait_for_grid(self, timeout_s: int = 60) -> bool:
        """Wait for the report to render. It takes ~12s from a cold navigation."""
        for _ in range(timeout_s):
            time.sleep(1.0)
            if self.has_them_moi():
                return True
        return False

    def has_them_moi(self) -> bool:
        return self.run_js("""
            (function() {
                const xpath = "//span[contains(text(), 'Thêm mới')]";
                const r = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                return !!r.singleNodeValue;
            })()
        """)

    def is_form_open(self) -> bool:
        return self.run_js(f"!!document.querySelector({js_string(FORM_MARKER)})")

    def on_expected_form(self) -> bool:
        """True only on the Thông tin hành chính form this script is written for."""
        return FORM_URL_MARKER in self.run_js("location.href")

    def form_matches_record(self, r: Dict[str, str]) -> bool:
        """Check the form is still the right one and still holds this child's data.

        Guards the moment before saving: if the app has drifted to another form, or the
        fields no longer read back what was typed, saving would write this child's data
        somewhere it does not belong.
        """
        if not self.on_expected_form():
            print(f"  ABORT: not on {FORM_URL_MARKER} any more -- not saving")
            return False

        actual = self.run_js("""
            (function() {
                const read = sel => {
                    const el = document.querySelector(sel + ' input.dx-texteditor-input');
                    return el ? el.value.trim() : null;
                };
                return {hoTen: read('.HoTen'), maDinhDanh: read('.MaDinhDanh')};
            })()
        """)
        expected_name = r["child_name"].upper().strip()
        if (actual.get("hoTen") or "").upper() != expected_name:
            print(f"  ABORT: form shows {actual.get('hoTen')!r}, expected {expected_name!r} -- not saving")
            return False
        if (actual.get("maDinhDanh") or "") != r["child_cccd"]:
            print(f"  ABORT: form shows CCCD {actual.get('maDinhDanh')!r}, expected {r['child_cccd']!r} -- not saving")
            return False
        return True

    def current_record_id(self) -> Optional[str]:
        """The phieukhamId the form is bound to, or None while it is still a blank one.

        Saving does not close the form: the app routes to .../<id>?phieukhamId=<id> and
        reveals the rest of the exam sections, leaving FORM_MARKER in the DOM. So the id
        appearing -- not the form vanishing -- is what says the record was created.
        """
        match = re.search(r"phieukhamId=(\d+)", self.run_js("location.href"))
        return match.group(1) if match else None

    def open_new_form(self, timeout_s: int = 60) -> bool:
        """Go back to the grid and open a blank form.

        Always routing through the grid is what keeps this an add-only script: a form
        already bound to a phieukhamId would otherwise be filled in and saved over,
        editing somebody else's record.
        """
        if not self.open_list(timeout_s):
            print("  ERROR: grid not ready, 'Thêm mới' missing")
            return False

        self.run_js("""
            (function() {
                const xpath = "//span[contains(text(), 'Thêm mới')]";
                const r = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                if (r.singleNodeValue) r.singleNodeValue.click();
                return true;
            })()
        """)
        for _ in range(timeout_s):
            time.sleep(1.0)
            if self.is_form_open():
                if self.current_record_id():
                    print("  ERROR: opened an existing record, not a blank form")
                    return False
                if not self.on_expected_form():
                    print(f"  ERROR: opened a different form, expected {FORM_URL_MARKER}")
                    return False
                return True
        print("  ERROR: form did not open")
        return False

    def click_save(self) -> None:
        self.run_js("""
            (function() {
                const xpath = "//span[text()='Lưu']";
                const r = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                if (r.singleNodeValue) { r.singleNodeValue.click(); return true; }
                const btns = Array.from(document.querySelectorAll('button, span, div'))
                    .filter(el => el.innerText.trim() === 'Lưu');
                if (btns.length) { btns[0].click(); return true; }
                return false;
            })()
        """)

    def validation_messages(self) -> List[str]:
        """Whatever the form is complaining about -- toasts included, they fade fast."""
        return self.run_js("""
            (function() {
                const sel = '.dx-invalid-message-content, .dx-validationsummary-item, .dx-toast-message';
                return Array.from(document.querySelectorAll(sel))
                    .map(el => el.innerText.trim()).filter(Boolean).slice(0, 8);
            })()
        """)

    # --- duplicate check ----------------------------------------------------

    def type_search_cccd(self, cccd: str) -> None:
        """Put the CCCD in the grid's search box.

        Assigning .value only updates the DOM: the DevExtreme widget keeps its own
        value, so 'Xem' re-runs the previous query and the grid answers about the
        previous child. Drivers that can type for real should override this.
        """
        self.run_js(f"""
            (function() {{
                const input = document.querySelector('input[id$="_MaDinhDanh"]');
                if (!input) return false;
                input.value = {js_string(cccd)};
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }})()
        """)

    def click_search(self) -> None:
        """Press 'Xem' to run the grid search.

        Must be a click that blurs the search box first: DevExtreme only commits a typed
        value on blur, and without it the search runs with an empty filter and returns
        every child rather than the one being looked up.
        """
        self.run_js("""
            (function() {
                const xemBtn = Array.from(document.querySelectorAll('button, span, div'))
                    .find(el => el.innerText.trim() === 'Xem');
                if (xemBtn) xemBtn.click();
                return true;
            })()
        """)

    def check_already_imported(self, cccd: str, timeout_s: int = 15,
                               attempts: int = 3) -> Optional[bool]:
        """Search the grid by CCCD. True if the child already has a record.

        Returns None when the grid never gives a trustworthy answer, which the caller
        must treat as "ask a human" rather than either yes or no: a wrong yes drops a
        child silently, a wrong no files them twice.
        """
        for attempt in range(1, attempts + 1):
            answer, state = self.search_grid(cccd, timeout_s)
            if answer is not None:
                return answer
            print(f"  search attempt {attempt}/{attempts} inconclusive (grid: {state!r})")
            self.open_list()

        print(f"  WARNING: grid never confirmed the search for {cccd}")
        return None

    def search_grid(self, cccd: str, timeout_s: int) -> tuple:
        """Run one CCCD search. Returns (True | False | None, last_grid_state).

        Match on the CCCD, which the grid shows in its own column, never on the name:
        the search is asynchronous, and a grid read before the filter lands still lists
        every child alphabetically -- a page on which the name being looked for is quite
        likely to appear, belonging to somebody else. The CCCD is proof either way.
        """
        self.run_js("""
            (function() {
                const ngayTaoEl = document.querySelector('input[id$="_NgayTao"]');
                if (ngayTaoEl) {
                    ngayTaoEl.focus();
                    ngayTaoEl.value = '';
                    ngayTaoEl.dispatchEvent(new Event('input', { bubbles: true }));
                    ngayTaoEl.dispatchEvent(new Event('change', { bubbles: true }));
                }
                return true;
            })()
        """)
        self.type_search_cccd(cccd)
        self.click_search()

        state = "unknown"
        for _ in range(timeout_s):
            time.sleep(1.0)
            state = self.run_js(f"""
                (function() {{
                    const grid = Array.from(document.querySelectorAll('.dx-datagrid'))
                        .find(g => g.offsetHeight > 0 && g.innerText.includes('MẪU PHIẾU KHÁM'));
                    if (!grid) return 'no-grid';
                    const busy = Array.from(document.querySelectorAll('.dx-loadpanel .dx-overlay-content, .dx-loadindicator'))
                        .some(el => el.offsetHeight > 0);
                    if (busy) return 'busy';
                    if (grid.innerText.includes({js_string(cccd)})) return 'match';
                    const noData = grid.querySelector('.dx-datagrid-nodata');
                    if (noData && noData.offsetHeight > 0) return 'empty';
                    const rows = grid.querySelectorAll('.dx-datagrid-content-fixed .dx-data-row');
                    if (!rows.length) return 'no-rows';
                    // Rows, but not this child's: the filter has not landed yet.
                    return rows.length >= 10 ? 'unfiltered' : 'stale';
                }})()
            """)
            if state == "match":
                return True, state
            if state == "empty":
                return False, state

        return None, state

    # --- form widgets -------------------------------------------------------

    def select_searchable_dropdown(self, selector: str, option_text: str, is_school: bool = False) -> bool:
        print(f"  dropdown {selector} -> {option_text}")
        self.run_js(f"""
            (function() {{
                const btn = document.querySelector({js_string(selector + ' .dx-dropdowneditor-button')});
                if (btn) btn.click();
                return true;
            }})()
        """)
        time.sleep(0.5)

        search_text = clean_school_name(option_text) if is_school else option_text
        self.run_js(f"""
            (function() {{
                const input = document.querySelector({js_string(selector + ' input.dx-texteditor-input')});
                if (!input) return false;
                input.value = {js_string(search_text)};
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                return true;
            }})()
        """)

        needle = search_text.lower()
        for attempt in range(5):
            time.sleep(0.6)
            res = self.run_js(f"""
                (function() {{
                    const needle = {js_string(needle)};
                    const items = Array.from(document.querySelectorAll('.dx-list-item-content'))
                        .filter(el => el.offsetHeight > 0);
                    const matched = items.find(el => {{
                        const text = el.innerText.trim().toLowerCase();
                        return {"text.includes(needle)" if is_school else "text === needle"};
                    }});
                    if (matched) {{ matched.click(); return 'Selected'; }}
                    return 'Not found (items: ' + items.length + ')';
                }})()
            """)
            if res == "Selected":
                return True
        print(f"  FAILED to select {option_text!r} in {selector}")
        self.run_js(f"""
            (function() {{
                const btn = document.querySelector({js_string(selector + ' .dx-dropdowneditor-button')});
                if (btn) btn.click();
                return true;
            }})()
        """)
        return False

    def fill_text_fields(self, fields: Dict[str, str]) -> None:
        """Fill DevExtreme text editors by simulating per-character keyboard input."""
        self.run_js(f"""
            (function() {{
                const fields = {json.dumps(fields, ensure_ascii=False)};
                function typeVal(selector, val) {{
                    const el = document.querySelector(selector + ' textarea.dx-texteditor-input') ||
                               document.querySelector(selector + ' input.dx-texteditor-input') ||
                               document.querySelector(selector + ' textarea') ||
                               document.querySelector(selector + ' input');
                    if (!el) return;
                    el.focus();
                    el.value = '';
                    for (const char of val) {{
                        el.dispatchEvent(new KeyboardEvent('keydown', {{ key: char, bubbles: true }}));
                        el.dispatchEvent(new KeyboardEvent('keypress', {{ key: char, bubbles: true }}));
                        el.value += char;
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new KeyboardEvent('keyup', {{ key: char, bubbles: true }}));
                    }}
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                }}
                for (const [selector, val] of Object.entries(fields)) typeVal(selector, val);
                return true;
            }})()
        """)

    def set_choices(self, gender: str) -> None:
        """Tick the fixed checkbox/radio answers. DevExtreme ignores a bare .click()."""
        self.run_js(f"""
            (function() {{
                function clickDx(el) {{
                    if (!el) return;
                    el.dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, cancelable: true }}));
                    el.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true, cancelable: true }}));
                    if (typeof el.focus === 'function') el.focus();
                    el.dispatchEvent(new PointerEvent('pointerup', {{ bubbles: true, cancelable: true }}));
                    el.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true, cancelable: true }}));
                    el.click();
                }}
                function pickRadio(groupSelector, label) {{
                    const el = Array.from(document.querySelectorAll(groupSelector + ' .dx-radiobutton'))
                        .find(e => e.innerText.trim() === label);
                    if (el && !el.classList.contains('dx-radiobutton-checked')) clickDx(el);
                }}
                function pickListItem(groupSelector, labelPart) {{
                    const item = Array.from(document.querySelectorAll(groupSelector + ' .dx-list-item'))
                        .find(e => e.innerText.trim().includes(labelPart));
                    if (!item) return;
                    const dot = item.querySelector('.dx-radiobutton') || item;
                    if (dot && dot.getAttribute('aria-checked') !== 'true') clickDx(dot);
                }}

                const kb = document.querySelector('.TuoiThai_KB .dx-checkbox');
                if (kb && !kb.classList.contains('dx-checkbox-checked')) clickDx(kb);

                pickRadio('.TreCoDiHoc', 'Có');
                pickRadio('.SinhNon', 'Không');
                pickRadio('.GioiTinh', {js_string(gender)});
                pickRadio('.TienSuBanThanCokhong', 'Không');
                pickRadio('.TienSuGiaDinhCoKhong', 'Không');
                pickRadio('.TienSu_TX_NguoiBenhLao', 'Không');

                pickListItem('.NguoiDiCung_QuanHe', 'Mẹ');
                pickListItem('.HinhThucKham', 'Ngân sách thành phố hỗ trợ');
                pickListItem('.DiaDiemKham', 'Trường học');
                return true;
            }})()
        """)

    def click_back(self) -> None:
        self.run_js("""
            (function() {
                const btn = document.querySelector('dx-button[aria-label="Quay lại"]');
                if (btn) { btn.click(); return true; }
                const alt = Array.from(document.querySelectorAll('span, button, div'))
                    .find(el => el.innerText.trim() === 'Quay lại');
                if (alt) { alt.click(); return true; }
                return false;
            })()
        """)
        time.sleep(1.5)

    # --- one record ---------------------------------------------------------

    def fill_form(self, r: Dict[str, str]) -> None:
        """Fill an open blank form with one child's details. Does not save."""
        bhyt = valid_bhyt(r.get("bhyt"))
        if r.get("bhyt") and not bhyt:
            print(f"  BHYT {r['bhyt']!r} is not a full 15-char number -- filing without it")

        self.fill_text_fields({
            ".NguoiKham": NGUOI_KHAM,
            ".HoTen": r["child_name"].upper(),
            ".NgaySinh": r["dob"],
            ".MaDinhDanh": r["child_cccd"],
            ".BHYT": bhyt,
            ".DiaChiHienTai": r["address"],
            ".ChaMe_HoTen_24TT": r["mother_name"],
            ".ChaMe_CCCD_24TT": r["mother_cccd"],
            ".ChaMe_SDT_24TT": r["phone"],
            ".NguoiDiCung_HoTen": r["mother_name"],
            ".SoDienThoaiNguoiDiCung": r["phone"],
            ".textarea6030": "Định kỳ",
        })
        time.sleep(1.0)

        self.select_searchable_dropdown(".DoiTuong", "Trẻ dưới 6 tuổi đi học (trẻ đang học mầm non)")
        self.select_searchable_dropdown(".WardIdSauSapNhap", r["ward"])

        self.set_choices("Nam" if r["gender"] == "Nam" else "Nữ")
        time.sleep(1.0)

        self.select_searchable_dropdown(".SchoolWardId", r["school_ward"])
        self.select_searchable_dropdown(".TruongId", r["school_name"], is_school=True)
        self.fill_text_fields({
            ".DiaChiTruong": r["school_address"],
            ".Lop": r["lop"],
        })
        time.sleep(1.5)

    def enter_child_record(self, r: Dict[str, str]) -> str:
        """Fill and save one child. Returns 'success' | 'duplicate' | 'failed'."""
        print(f"--- entering {r['child_name']} ({r['child_cccd']})")

        if not self.open_new_form():
            return "failed"

        self.fill_form(r)

        if not self.form_matches_record(r):
            return "failed"

        if self.dry_run:
            print("  DRY RUN: form filled, not saving. Reverting.")
            self.click_back()
            return "dry-run"

        self.click_save()

        for attempt in range(45):
            time.sleep(1.0)
            record_id = self.current_record_id()
            if record_id:
                print(f"  saved (phieukhamId={record_id})")
                return "success"

            is_duplicate = self.run_js("""
                (function() {
                    const title = document.querySelector('.dx-popup-title');
                    if (!title) return false;
                    const txt = title.innerText.toUpperCase();
                    if (txt.includes('TRÙNG') || txt.includes('TỒN TẠI') || txt.includes('ĐÃ CÓ') || txt.includes('CCCD')) {
                        const x = document.querySelector('.dx-popup-cancel-button, .dx-close-button, [aria-label="Close"], .dx-popup-title .dx-button');
                        if (x) x.click();
                        return true;
                    }
                    return false;
                })()
            """)
            if is_duplicate:
                print("  duplicate popup -> already in system elsewhere")
                self.click_back()
                return "duplicate"

        print("  WARNING: no phieukhamId after 45s -- not saved.")
        for message in self.validation_messages():
            print(f"    form says: {message}")
        return "failed"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--browser",
        choices=["chrome", "firefox"],
        default="chrome",
        help="which installed browser to drive (default: chrome)",
    )
    parser.add_argument(
        "--file",
        help="children list to import: .xlsx, .pdf or .json (default: children.json beside the app)",
    )
    parser.add_argument(
        "--make-template",
        action="store_true",
        help="write mau_danh_sach.xlsx beside the app and exit",
    )
    parser.add_argument("--dry-run", action="store_true", help="fill forms but never save")
    parser.add_argument("--limit", type=int, help="only process the first N eligible records")
    parser.add_argument(
        "--separate-profile",
        action="store_true",
        help="use an isolated browser profile beside the app instead of your real one",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="check the packaging and installed browsers without opening any window",
    )
    return parser.parse_args()


def load_records(limit: Optional[int] = None, dry_run: bool = False,
                 path: Optional[str] = None):
    """Load the children list (xlsx/pdf/json) and split off rows missing a ward."""
    if path is None:
        if not os.path.exists(DATA_FILE) and os.path.exists(BUNDLED_SAMPLE):
            shutil.copyfile(BUNDLED_SAMPLE, DATA_FILE)
            print(f"Đã tạo {DATA_FILE} từ dữ liệu mẫu -- sửa lại theo danh sách của bạn.")
        if not os.path.exists(DATA_FILE):
            raise SystemExit(f"ERROR: không thấy file dữ liệu {DATA_FILE}.")
        path = DATA_FILE

    print(f"Đọc danh sách từ: {path}")
    data: List[Dict] = parsers.load_any(path)

    no_ward = [r for r in data if not r.get("ward")]
    eligible = [r for r in data if r.get("ward")]
    if limit:
        eligible = eligible[:limit]

    print(f"Đọc được {len(data)} hồ sơ: {len(eligible)} sẽ xử lý, {len(no_ward)} bỏ qua (thiếu Phường/Xã).")
    if dry_run:
        print("*** CHẠY THỬ: sẽ không lưu gì ***")
    return eligible, no_ward


def run_import(importer: "Importer", eligible: List[Dict]) -> Dict[str, List[str]]:
    """Walk the eligible records, skipping anyone already in the system."""
    results: Dict[str, List[str]] = {
        "success": [], "skipped_existing": [], "duplicate": [], "failed": [], "dry-run": [],
        "unverified": [],
    }

    for idx, r in enumerate(eligible, 1):
        label = f"{r['child_name']} ({r['child_cccd']})"
        print(f"\n[{idx}/{len(eligible)}] TT{r['tt']} {label}")

        already = importer.check_already_imported(r["child_cccd"])
        if already is None:
            # Neither answer is safe to assume: guessing wrong either duplicates the
            # child or drops them silently. Leave this one for a human.
            print("  cannot tell if already imported -> skipping, enter by hand")
            results["unverified"].append(label)
            continue
        if already:
            print("  already imported -> skip")
            results["skipped_existing"].append(label)
            continue

        status = importer.enter_child_record(r)
        results[status].append(label)
        time.sleep(2.0)

    return results


def print_summary(results: Dict[str, List[str]], no_ward: List[Dict], dry_run: bool = False) -> None:
    print("\n=== FINISHED ===")
    print(f"Newly imported : {len(results['success'])}")
    print(f"Already present: {len(results['skipped_existing'])}")
    print(f"Duplicate popup: {len(results['duplicate'])}")
    print(f"Failed         : {len(results['failed'])}")
    print(f"Unverified     : {len(results['unverified'])}")
    if dry_run:
        print(f"Dry-run filled : {len(results['dry-run'])}")

    if results["failed"]:
        print("\nFailed records:")
        for label in results["failed"]:
            print(f"  {label}")

    if results["unverified"]:
        print("\nCould not confirm whether these are already in the system -- check by hand:")
        for label in results["unverified"]:
            print(f"  {label}")

    if no_ward:
        print(f"\nNot attempted -- no ward in the PDF, enter these {len(no_ward)} by hand:")
        for r in no_ward:
            print(f"  TT{r['tt']:>3} {r['child_name']:<28} {r['address']}")

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump({"results": results, "no_ward": no_ward}, f, ensure_ascii=False, indent=2)
    print(f"\nDetails written to {RESULTS_FILE}")


class MarionetteImporter(Importer):
    """The Importer with page.evaluate()/page.goto() swapped for Marionette calls."""

    def __init__(self, client: Marionette, dry_run: bool = False):
        super().__init__(page=None, dry_run=dry_run)
        self.client = client

    def run_js(self, code: str):
        return self.client.execute_script(f"return ({code});")

    def goto(self, url: str) -> None:
        self.client.navigate(url)

    def type_search_cccd(self, cccd: str) -> None:
        """Type the CCCD for real so the DevExtreme search widget picks up the value.

        The trailing Tab is what commits it: DevExtreme only takes the typed value on
        blur, and relying on the click of 'Xem' to provide that blur is fragile.
        """
        element_id = self.client.find_element('input[id$="_MaDinhDanh"]', using="css selector")
        if element_id is None:
            super().type_search_cccd(cccd)
            return
        self.client.element_clear(element_id)
        self.client.element_send_keys(element_id, cccd)
        self.client.element_send_keys(element_id, "")  # Tab keycode -> blur

    def real_click_button(self, label: str) -> bool:
        """Click a DevExtreme button by its label with a real, browser-synthesised click.

        JS-dispatched clicks are unreliable on these widgets -- 'Lưu' often fires no save
        request at all -- and a real click also blurs whatever field has focus, which is
        what makes DevExtreme commit a typed value.
        """
        xpath = f"//span[text()={js_string(label)}]"
        if not self.run_js(f"""
            (function() {{
                const r = document.evaluate({js_string(xpath)}, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                if (!r.singleNodeValue) return false;
                (r.singleNodeValue.closest('.dx-button') || r.singleNodeValue)
                    .scrollIntoView({{block: 'center'}});
                return true;
            }})()
        """):
            return False
        time.sleep(0.5)

        element_id = self.client.find_element(f"{xpath}/ancestor::*[contains(@class, 'dx-button')][1]")
        if element_id is None:
            element_id = self.client.find_element(xpath)
        if element_id is None:
            return False
        try:
            self.client.element_click(element_id)
            return True
        except MarionetteError as exc:
            print(f"  WARNING: real click on {label!r} failed: {exc}")
            return False

    def click_search(self) -> None:
        # The typed value is already committed by the Tab in type_search_cccd, so a
        # JS click is a safe fallback here when the real one gets intercepted.
        if not self.real_click_button("Xem"):
            super().click_search()

    def click_save(self) -> None:
        # No JS fallback: a JS click on Lưu tends to fire no save request at all, and
        # silently not saving is worse than reporting a failure.
        if not self.real_click_button("Lưu"):
            print("  ERROR: could not click Lưu")


class AppleScriptJSDisabled(RuntimeError):
    """Chrome refused to run JS: 'Allow JavaScript from Apple Events' is off."""


class AppleScriptImporter(Importer):
    """Drives the user's real, everyday Chrome on macOS over AppleScript.

    This is the only way to automate the real Chrome profile (with its existing
    medinet login): Chrome 136+ refuses CDP/Playwright automation of the default
    profile, but still honours 'execute javascript' from Apple Events once the
    user enables View > Developer > Allow JavaScript from Apple Events.
    """

    SITE = "quanlyskcd.medinet.org.vn"

    def __init__(self, dry_run: bool = False):
        super().__init__(page=None, dry_run=dry_run)
        self._prompted_js_setting = False

    @staticmethod
    def _osascript(script: str) -> "subprocess.CompletedProcess":
        return subprocess.run(
            ["osascript", "-"], input=script, capture_output=True, text=True
        )

    @staticmethod
    def _as_string(value: str) -> str:
        """Escape a Python string into an AppleScript string literal."""
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'

    def goto(self, url: str) -> None:
        """Point the medinet tab (or a new tab) at url in the user's own Chrome."""
        self._osascript(f"""
tell application "Google Chrome"
    activate
    if (count of windows) = 0 then make new window
    set found to false
    repeat with w in windows
        repeat with t in tabs of w
            if URL of t contains "{self.SITE}" then
                set URL of t to {self._as_string(url)}
                set found to true
                exit repeat
            end if
        end repeat
        if found then exit repeat
    end repeat
    if not found then
        tell front window to make new tab with properties {{URL:{self._as_string(url)}}}
    end if
end tell
""")

    def run_js(self, code: str):
        """Evaluate a JS expression in the medinet tab and JSON-decode the result.

        Everything goes through JSON.stringify so dicts/bools/numbers come back as
        real Python values, matching what page.evaluate() gives the shared Importer.
        """
        js = f"JSON.stringify(( {code} ))"
        script = f"""
tell application "Google Chrome"
    repeat with w in windows
        repeat with t in tabs of w
            if URL of t contains "{self.SITE}" then
                return execute t javascript {self._as_string(js)}
            end if
        end repeat
    end repeat
    return "__no_tab__"
end tell
"""
        proc = self._osascript(script)
        err = (proc.stderr or "").strip()
        if err and ("javascript" in err.lower() and ("turned off" in err.lower() or "apple events" in err.lower())):
            raise AppleScriptJSDisabled(err)
        out = (proc.stdout or "").strip()
        if out in ("", "__no_tab__", "missing value", "undefined"):
            return None
        try:
            return json.loads(out)
        except ValueError:
            return out

    def wait_for_js_permission(self, timeout_s: int = 600) -> bool:
        """Poll until Chrome lets Apple Events run JS, guiding the user to enable it."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                self.run_js("1 + 1")
                return True
            except AppleScriptJSDisabled:
                if not self._prompted_js_setting:
                    print("\n" + "=" * 68)
                    print("  Chrome đang chặn điều khiển tự động. Bật một lần như sau:")
                    print("  Trên thanh menu Chrome: View > Developer >")
                    print("      'Allow JavaScript from Apple Events'")
                    print("  Bật xong công cụ sẽ tự chạy tiếp.")
                    print("=" * 68 + "\n")
                    self._prompted_js_setting = True
                time.sleep(3.0)
        return False


def run_with_chrome_applescript(args: argparse.Namespace, eligible: List[Dict]) -> Optional[Dict]:
    """macOS: drive the user's real Chrome (their normal profile and login)."""
    importer = AppleScriptImporter(dry_run=args.dry_run)
    importer.goto(LIST_URL)  # also starts Chrome if it is not running
    if not importer.wait_for_js_permission():
        print("ERROR: Chrome never allowed JavaScript from Apple Events. Nothing imported.")
        return None
    if not importer.wait_for_login():
        print("ERROR: timed out waiting for the grid. Nothing imported.")
        return None
    return run_import(importer, eligible)


# --- browser launch ---------------------------------------------------------

def _port_is_open(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def find_firefox_binary() -> Optional[str]:
    """Locate the installed Firefox across macOS, Windows and Linux."""
    env = os.environ.get("FIREFOX_BINARY")
    if env and os.path.exists(env):
        return env

    if sys.platform == "darwin":
        candidates = [
            "/Applications/Firefox.app/Contents/MacOS/firefox",
            os.path.expanduser("~/Applications/Firefox.app/Contents/MacOS/firefox"),
        ]
    elif os.name == "nt":
        candidates = []
        for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(var)
            if base:
                candidates.append(os.path.join(base, "Mozilla Firefox", "firefox.exe"))
    else:
        candidates = [
            "/usr/bin/firefox", "/usr/bin/firefox-esr",
            "/usr/lib/firefox/firefox", "/snap/bin/firefox",
        ]

    for path in candidates:
        if path and os.path.exists(path):
            return path
    return shutil.which("firefox") or shutil.which("firefox-esr")


def _write_firefox_prefs(profile_dir: str) -> None:
    """Seed a dedicated profile's preferences before Firefox starts.

    The important one is security.enterprise_roots: medinet's certificate chains to
    a CA that lives in the operating-system trust store (which the user's normal
    browser uses) but not in Firefox's own built-in store, so a fresh profile would
    reject it as an unknown issuer. Turning this on makes Firefox trust the OS roots
    too, so the site loads exactly as it does in the user's day-to-day browser.
    Never applied to the user's real profile -- their settings are theirs.
    """
    prefs = [
        'user_pref("security.enterprise_roots.enabled", true);',
        'user_pref("browser.shell.checkDefaultBrowser", false);',
        'user_pref("datareporting.policy.dataSubmissionEnabled", false);',
        'user_pref("browser.aboutwelcome.enabled", false);',
    ]
    with open(os.path.join(profile_dir, "user.js"), "w", encoding="utf-8") as f:
        f.write("\n".join(prefs) + "\n")


def firefox_is_running() -> bool:
    """True if any Firefox instance is up (it would hold the default profile's lock)."""
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq firefox.exe"], capture_output=True, text=True
        )
        return "firefox.exe" in (result.stdout or "")
    # -f matches the full command line; the binary path always contains "firefox"
    # in lowercase on macOS and Linux (Linux pgrep has no -i flag).
    result = subprocess.run(["pgrep", "-f", "firefox"], capture_output=True, text=True)
    return result.returncode == 0 and bool(result.stdout.strip())


def launch_firefox(binary: str, profile_dir: Optional[str] = None) -> subprocess.Popen:
    """Start the real Firefox with Marionette enabled and wait for its port.

    With no profile_dir Firefox opens the user's own default profile -- their
    existing medinet login and all. A profile_dir gives an isolated profile that
    can run alongside their normal Firefox.
    """
    command = [binary, "--marionette"]
    if profile_dir:
        os.makedirs(profile_dir, exist_ok=True)
        _write_firefox_prefs(profile_dir)
        command += ["--no-remote", "-profile", profile_dir]
        print(f"Launching Firefox with Marionette (profile riêng: {profile_dir})...")
    else:
        print("Launching Firefox with Marionette (profile thường của bạn)...")
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(60):
        if _port_is_open():
            print(f"Marionette is listening on {DEFAULT_HOST}:{DEFAULT_PORT}.")
            return process
        time.sleep(1.0)
    process.terminate()
    raise SystemExit(
        f"ERROR: Firefox started but never opened the Marionette port ({DEFAULT_PORT}). "
        "Nothing imported."
    )


def run_with_firefox(args: argparse.Namespace, eligible: List[Dict]) -> Optional[Dict]:
    binary = find_firefox_binary()
    if not binary:
        raise SystemExit(
            "ERROR: could not find Firefox. Install it, set the FIREFOX_BINARY "
            "environment variable, or run with --browser chrome."
        )
    if _port_is_open():
        raise SystemExit(
            f"ERROR: the Marionette port ({DEFAULT_PORT}) is already in use. Close any "
            "other automated Firefox instance and try again."
        )

    if args.separate_profile:
        launch_firefox(binary, FIREFOX_PROFILE_DIR)
    else:
        # The default profile: the user's own logins, bookmarks, everything. Firefox
        # must be fully closed first -- a running instance holds the profile lock and
        # ignores --marionette.
        if firefox_is_running():
            raise SystemExit(
                "ERROR: Firefox đang mở. Hãy thoát hẳn Firefox (Cmd+Q / đóng hết cửa sổ)\n"
                "       rồi chạy lại -- công cụ cần mở Firefox của bạn ở chế độ điều khiển.\n"
                "       (Hoặc chạy với --separate-profile để dùng hồ sơ riêng.)"
            )
        launch_firefox(binary)
    client = Marionette()
    try:
        client.connect()
        importer = MarionetteImporter(client, dry_run=args.dry_run)
        if not importer.wait_for_login():
            print("ERROR: timed out waiting for the grid. Nothing imported.")
            return None
        return run_import(importer, eligible)
    finally:
        client.close()
    # Firefox is left running so the user can review the result.


def run_with_chrome(args: argparse.Namespace, eligible: List[Dict]) -> Optional[Dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "ERROR: Playwright is not available for --browser chrome. "
            "Use --browser firefox instead."
        )

    os.makedirs(CHROME_PROFILE_DIR, exist_ok=True)
    with sync_playwright() as p:
        context = None
        last_error = None
        # channel picks the user's real installed browser rather than a download.
        for channel in ("chrome", "msedge", "chromium"):
            try:
                context = p.chromium.launch_persistent_context(
                    CHROME_PROFILE_DIR,
                    headless=False,
                    channel=channel,
                    viewport=None,
                    ignore_https_errors=True,
                    args=["--start-maximized"],
                    # Drop the default --enable-automation flag so Chrome does not
                    # show the "being controlled by automated test software" banner.
                    ignore_default_args=["--enable-automation"],
                )
                break
            except Exception as exc:  # noqa: BLE001 -- try the next channel
                last_error = exc
        if context is None:
            raise SystemExit(
                "ERROR: could not launch Chrome, Edge or Chromium. Install Google "
                f"Chrome or run with --browser firefox.\n  ({last_error})"
            )

        page = context.pages[0] if context.pages else context.new_page()
        importer = Importer(page, dry_run=args.dry_run)
        try:
            if not importer.wait_for_login():
                print("ERROR: timed out waiting for the grid. Nothing imported.")
                return None
            return run_import(importer, eligible)
        finally:
            context.close()


def run_selftest() -> bool:
    """Check the packaging and environment without opening any browser window."""
    print("Self-test (no browser window will open)\n")
    ok = True

    data_ok = os.path.exists(DATA_FILE) or os.path.exists(BUNDLED_SAMPLE)
    print(f"  data file        : {'OK' if data_ok else 'MISSING'} ({DATA_FILE})")
    ok = ok and data_ok

    for module, label in (("openpyxl", "đọc Excel"), ("pypdf", "đọc PDF")):
        try:
            __import__(module)
            print(f"  {module} ({label}): OK")
        except ImportError as exc:
            ok = False
            print(f"  {module} ({label}): FAILED -- {exc}")

    firefox = find_firefox_binary()
    print(f"  Firefox (--browser firefox): {firefox or 'not found'}")

    if sys.platform == "darwin":
        chrome_app = os.path.exists("/Applications/Google Chrome.app")
        print(f"  Chrome thật qua AppleScript (--browser chrome): "
              f"{'OK' if chrome_app else 'không thấy Google Chrome.app'}")

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            _ = p.chromium.name  # starts the node driver; reads its package.json
        print("  Playwright driver (chrome --separate-profile): OK")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"  Playwright driver (chrome --separate-profile): FAILED -- {exc}")

    if not firefox and not ok:
        print("\nNeither browser path is usable on this machine.")
    print("\nSelf-test:", "PASSED" if ok else "had problems (see above)")
    return ok


# --- double-click flow --------------------------------------------------------

def choose_file_dialog() -> Optional[str]:
    """Open the OS-native file picker for the children list. None if cancelled."""
    if sys.platform == "darwin":
        proc = subprocess.run(
            ["osascript", "-e",
             'POSIX path of (choose file with prompt '
             '"Chọn file danh sách trẻ (Excel/PDF/JSON)" '
             'of type {"xlsx", "pdf", "json"})'],
            capture_output=True, text=True,
        )
        path = (proc.stdout or "").strip()
        return path or None
    if os.name == "nt":
        script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "$f = New-Object System.Windows.Forms.OpenFileDialog;"
            "$f.Title = 'Chon file danh sach tre';"
            "$f.Filter = 'Danh sach (*.xlsx;*.pdf;*.json)|*.xlsx;*.pdf;*.json';"
            "if ($f.ShowDialog() -eq 'OK') { $f.FileName }"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", script],
            capture_output=True, text=True,
        )
        path = (proc.stdout or "").strip()
        return path or None
    # Linux: zenity where available, otherwise typed path.
    if shutil.which("zenity"):
        proc = subprocess.run(
            ["zenity", "--file-selection", "--title=Chọn file danh sách trẻ",
             "--file-filter=*.xlsx *.pdf *.json"],
            capture_output=True, text=True,
        )
        path = (proc.stdout or "").strip()
        return path or None
    typed = input("Nhập đường dẫn file danh sách (.xlsx/.pdf/.json): ").strip()
    return typed or None


def _ask(prompt: str, choices: Dict[str, str], default: str) -> str:
    """A tiny numbered console menu; Enter picks the default."""
    print(prompt)
    for key, label in choices.items():
        marker = " (Enter)" if key == default else ""
        print(f"  [{key}] {label}{marker}")
    while True:
        answer = input("Chọn: ").strip() or default
        if answer in choices:
            return answer
        print(f"  Không có lựa chọn {answer!r}, thử lại.")


def interactive_main() -> None:
    """What double-clicking the app runs: pick a file, pick a browser, go."""
    print("=" * 68)
    print("  NHẬP DANH SÁCH KHÁM SỨC KHỎE TRẺ EM -> medinet")
    print("  Chỉ THÊM MỚI, tự bỏ qua trẻ đã có. Không sửa/xóa hồ sơ nào.")
    print("=" * 68 + "\n")

    action = _ask("Bạn muốn làm gì?", {
        "1": "Nhập danh sách từ file (Excel / PDF / JSON)",
        "2": "Tạo file Excel mẫu để điền danh sách",
    }, default="1")
    if action == "2":
        target = os.path.join(BASE_DIR, "mau_danh_sach.xlsx")
        parsers.create_template(target)
        print(f"\nĐã tạo file mẫu: {target}")
        print("Mở file này, điền danh sách trẻ (mỗi dòng một bé), lưu lại,")
        print("rồi chạy công cụ lần nữa và chọn file đó.")
        return

    print("\nĐang mở hộp thoại chọn file...")
    path = choose_file_dialog()
    if not path:
        print("Không chọn file nào -- thoát.")
        return
    if not os.path.exists(path):
        raise SystemExit(f"Không thấy file: {path}")

    args = argparse.Namespace(
        browser="chrome", dry_run=False, limit=None,
        separate_profile=False, selftest=False, file=path, make_template=False,
    )

    browser = _ask("\nDùng trình duyệt nào?", {
        "1": "Chrome đang dùng của bạn" + (" (macOS)" if sys.platform == "darwin" else " -- hồ sơ riêng"),
        "2": "Firefox của bạn (phải thoát Firefox trước)",
        "3": "Cửa sổ riêng, đăng nhập 1 lần (Chrome/Edge)",
    }, default="1")
    if browser == "2":
        args.browser = "firefox"
    elif browser == "3":
        args.separate_profile = True

    mode = _ask("\nChế độ chạy?", {
        "1": "Nhập thật",
        "2": "Chạy thử -- điền form nhưng KHÔNG lưu",
    }, default="1")
    args.dry_run = mode == "2"

    print()
    run(args)


def run(args: argparse.Namespace) -> None:
    """Load the list and run the import with the chosen browser."""
    eligible, no_ward = load_records(args.limit, args.dry_run, path=args.file)

    if args.browser == "firefox":
        results = run_with_firefox(args, eligible)
    elif sys.platform == "darwin" and not args.separate_profile:
        results = run_with_chrome_applescript(args, eligible)
    else:
        results = run_with_chrome(args, eligible)

    if results is None:
        return
    print_summary(results, no_ward, args.dry_run)


def main() -> None:
    # No arguments (a double-click) -> the guided flow with the file picker.
    if len(sys.argv) <= 1:
        interactive_main()
        return

    args = parse_args()

    if args.selftest:
        run_selftest()
        return

    if args.make_template:
        target = os.path.join(BASE_DIR, "mau_danh_sach.xlsx")
        parsers.create_template(target)
        print(f"Đã tạo file mẫu: {target}")
        return

    run(args)


def _pause(message: str) -> None:
    """Wait for Enter so a double-clicked window stays readable. No-op without a console."""
    try:
        input(message)
    except EOFError:
        pass


def _run() -> None:
    """Entry point that keeps a double-clicked window open long enough to read."""
    frozen = getattr(sys, "frozen", False)
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        import traceback
        traceback.print_exc()
        if frozen:
            _pause("\nAn error occurred. Press Enter to close...")
        raise
    if frozen:
        _pause("\nDone. Press Enter to close...")


if __name__ == "__main__":
    _run()
