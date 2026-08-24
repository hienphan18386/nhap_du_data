"""Fill the clinical sections of EXISTING Medinet KSKD18 records from the KSK workbook.

Scope, deliberately narrow: this tool never creates, deletes or re-files a record.
It looks each student up by CCCD among the exam dates the user asks for, opens the
record that is already on file, and completes four sections of it:

    1. Tiền sử bản thân   (KSKD18_TTHC_TienSu)     -- tiền sử + khám thể lực
    2. Đánh giá tâm thần  (KSKD18_TAB_DANHGIATAMTHAN, both sub-tabs)
    3. Khám lâm sàng      (KSKD18_ThongTinKham)    -- nhi khoa, mắt, TMH, RHM
    4. Kết luận           (KSKD18_KetLuanKham)

Each section is saved before the next one is opened, because Medinet routes each
section to its own form and navigating away discards anything unsaved.

A student whose CCCD is not found in the requested date window is skipped and
recorded in the error log -- never created.

Usage:
    python3 -m app.clinical --file "data/MAU AI NHAP LIEU  KSK.xlsx"
    python3 -m app.clinical --file <xlsx> --from 01/07/2026 --to 08/08/2026
    python3 -m app.clinical --file <xlsx> --limit 1          # trial on one student
    python3 -m app.clinical --file <xlsx> --dry-run          # fill, never save
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

try:
    from app import ksk_workbook as wb
    from app.importer import AppleScriptImporter, js_string
except ImportError:  # frozen / loose script
    import ksk_workbook as wb
    from importer import AppleScriptImporter, js_string

SITE = "https://quanlyskcd.medinet.org.vn"
NAV = f"{SITE}/nav_group/kskdk_thongtinkhamduoi18/app/main"
GRID_URL = f"{SITE}/app/main/dynamicreport/report/viewer-utility/KSKDK_DanhSach_KSK_M12"

FORM_TIEN_SU = "dynamicform/viewer/KSKD18_TTHC_TienSu"
FORM_TAM_THAN = "dynamicviewer/tabpanel/KSKD18_TAB_DANHGIATAMTHAN"
FORM_LAM_SANG = "dynamicform/viewer/KSKD18_ThongTinKham"
FORM_KET_LUAN = "dynamicform/viewer/KSKD18_KetLuanKham"

RESULTS_FILE = os.environ.get("CLINICAL_RESULTS_FILE", "clinical_results.json")

# Gap between two vaccination picks, in milliseconds. The grids re-bind after each
# one; too small and they come back empty, saving nothing. 120ms held over the whole
# 38-dose schedule while Medinet was responsive, but a loaded server re-binds slower
# than that, so ticks land mid-rebind and the schedule times out half-finished --
# that is how a run leaves "19 dòng chưa đặt được". Raise it only with a
# save-and-reload check to prove every dose still persists.
VACCINE_TICK_MS = 250

# Prefix for a message that describes the source data rather than a failure to enter
# it. The workbook sometimes answers a Có/Không question with a sentence; the answer
# is entered correctly and the extra wording simply has nowhere to go on the form.
# Such a message must still reach the operator, but counting it as a defect marks a
# fully entered section "lưu thiếu", which in turn keeps the student in the retry
# queue for ever.
NOTE_PREFIX = "ghi chú: "

# How long a vaccination pass may make no progress at all before it is written off.
# A rebind on a loaded server can hide every row for seconds on end, and a pass that
# gives up during one reports rows as unset that nothing was ever wrong with.
VACCINE_STALL_S = 25

# Hard ceiling for one vaccination pass. The pass ends as soon as the schedule is
# complete, so this only bounds a server that has stopped answering.
VACCINE_BUDGET_S = 300

# The six nhi-khoa blocks of Khám lâm sàng: workbook key -> (checkbox class, ICD class).
# "Thần kinh" really is wired to NoiTiet_* in Medinet's own markup -- not a typo here.
NHI_KHOA = [
    ("tuan_hoan", "TuanHoan_ChuaPhatHienBatThuong", "TuanHoan_ChanDoanSoBo_ICD"),
    ("ho_hap", "HoHap_ChuaPhatHienBatThuong", "HoHap_ChanDoanSoBo_ICD"),
    ("tieu_hoa", "TieuHoa_ChuaPhatHienBatThuong", "TieuHoa_ChanDoanSoBo_ICD"),
    ("than_tiet_nieu", "ThanTietNieu_ChuaPhatHienBatThuong", "ThanTietNieu_ChanDoanSoBo_ICD"),
    ("than_kinh", "NoiTiet_ChuaPhatHienBatThuong", "NoiTiet_ChanDoanSoBo_ICD"),
    ("tam_than", "TamThan_ChuaPhatHienBatThuong", "TamThan_ChanDoanSoBo_ICD"),
]

# Kết luận -> mục 3. Đề nghị. Which radio to tick is decided by what Medinet itself
# computed into "2. Bệnh, tật cần lưu ý, theo dõi", not by the workbook.
DE_NGHI_BINH_THUONG = "Bình thường, hẹn khám định kỳ lần sau"
DE_NGHI_NGUY_CO = "Có yếu tố nguy cơ, cần theo dõi thêm"

# Shared JS helpers, (re)installed on every page load. Everything the filler does to a
# DevExtreme widget goes through these: assigning .value alone never reaches the Angular
# model, and a plain .click() does not drive a DevExtreme radio/checkbox either.
# The backend stopped accepting the session cookie on its own -- it now answers
# "Current user did not login to the application!" to anything without the app's own
# Bearer header, which is why api_lookup() started coming back empty-handed and
# children with no exam date looked like they had no record at all. The token is not
# readable from script: localStorage keeps it encrypted, and the app runs in the page
# world where a script sent over Apple Events cannot see its variables. But a <script>
# tag injected into the page does run there, so this one wraps XMLHttpRequest before
# the app makes its next call and parks the header it used in a hidden node, which the
# controlling script can read back like any other bit of DOM.
TOKEN_TAP_JS = r"""
(function(){
  if (document.getElementById('__mxtok')) return 'already';
  var out = document.createElement('div');
  out.id = '__mxtok';
  out.style.display = 'none';
  document.body.appendChild(out);
  var s = document.createElement('script');
  s.textContent = "(function(){var S=XMLHttpRequest.prototype.setRequestHeader;" +
    "XMLHttpRequest.prototype.setRequestHeader=function(k,v){try{" +
    "if(String(k).toLowerCase()==='authorization'){var n=document.getElementById('__mxtok');" +
    "if(n)n.textContent=String(v);}}catch(e){}return S.apply(this,arguments);};" +
    "var F=window.fetch;window.fetch=function(a,b){try{var h=b&&b.headers;" +
    "var v=h?(h.Authorization||h.authorization||(h.get&&h.get('Authorization'))):null;" +
    "if(v){var n=document.getElementById('__mxtok');if(n)n.textContent=String(v);}}catch(e){}" +
    "return F.apply(this,arguments);};})();";
  document.documentElement.appendChild(s);
  s.remove();
  return 'tapped';
})()
"""

HELPERS_JS = r"""
(function(){
  /* Medinet gives a successful save no visible acknowledgement at all: no toast, no
     banner, no URL change -- and it leaves the "Vui lòng nhập ..." validation nodes
     from the initial empty render lying in the DOM, so reading those reports failure
     on a save that worked. The write itself is the only honest signal, so the two
     network transports are tapped once per page and every save request is recorded. */
  if (!window.__mxNet) {
    window.__mxNet = {calls: [], armed: 0};
    var isSave = function(url, method){
      return (method || 'GET').toUpperCase() !== 'GET' && /medinet|\/api\/|\/app\//i.test(url || '');
    };
    var origFetch = window.fetch;
    if (origFetch) {
      window.fetch = function(input, init){
        var url = (typeof input === 'string') ? input : (input && input.url) || '';
        var method = (init && init.method) || (input && input.method) || 'GET';
        var p = origFetch.apply(this, arguments);
        if (isSave(url, method)) {
          p.then(function(res){
            window.__mxNet.calls.push({url: url, status: res.status, ok: res.ok, at: Date.now()});
          }).catch(function(e){
            window.__mxNet.calls.push({url: url, status: 0, ok: false, err: String(e), at: Date.now()});
          });
        }
        return p;
      };
    }
    var origOpen = XMLHttpRequest.prototype.open;
    var origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function(method, url){
      this.__mxMethod = method; this.__mxUrl = url;
      return origOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function(){
      var xhr = this;
      if (isSave(xhr.__mxUrl, xhr.__mxMethod)) {
        xhr.addEventListener('loadend', function(){
          window.__mxNet.calls.push({
            url: xhr.__mxUrl, status: xhr.status,
            ok: xhr.status >= 200 && xhr.status < 300,
            body: String(xhr.responseText || '').slice(0, 300), at: Date.now()});
        });
      }
      return origSend.apply(this, arguments);
    };
  }

  /* Medinet's Angular stores whatever any postMessage carries into KhamRangJSON --
     it checks neither e.origin nor the shape of e.data. Every browser extension that
     broadcasts on window therefore overwrites the dental chart. A deny-list of known
     offenders is not enough: it listed react-devtools, redux and webpack, and
     Wappalyzer walked straight past it and put 1995 bytes of its own inventory into
     the field, which is why teeth marked "Sâu" came back "Bình thường".

     So this is an allow-list instead. The dental iframe posts an Array of tooth
     records; nothing else is a legitimate message for this page, and anything else is
     stopped before Angular's own listener runs. */
  if (!window.__mxMessageGuard) {
    window.__mxMessageGuard = true;
    window.addEventListener('message', function(e) {
      if (!e) return;
      var d = e.data;
      if (Array.isArray(d)) return;                       // the dental chart itself
      if (d && typeof d === 'object' && d.action === 'INIT_DATA') return;
      e.stopImmediatePropagation();                       // everything else is noise
    }, true);
  }

  window.__mx = {
    /* An element counts as live only if no ancestor is an aria-hidden tab pane --
       the tâm thần tabpanel keeps the unselected sub-tab mounted and full-height. */
    live: function(el){
      if (!el) return false;
      for (var n = el; n; n = n.parentElement) {
        if (n.getAttribute && n.getAttribute('aria-hidden') === 'true') return false;
      }
      return el.offsetHeight > 0 || el.offsetWidth > 0;
    },
    field: function(cls){
      var all = Array.from(document.querySelectorAll('.' + cls));
      return all.find(window.__mx.live) || null;
    },
    click: function(el){
      if (!el) return false;
      var r = el.getBoundingClientRect();
      if (r.top < 0 || r.left < 0 || r.bottom > window.innerHeight || r.right > window.innerWidth) {
        el.scrollIntoView({block: 'center', inline: 'center'});
        r = el.getBoundingClientRect();
      }
      var o = {bubbles:true, cancelable:true, view:window, pointerId:1, pointerType:'mouse',
               isPrimary:true, button:0, buttons:1,
               clientX:r.left + r.width/2, clientY:r.top + r.height/2};
      el.dispatchEvent(new PointerEvent('pointerdown', o));
      el.dispatchEvent(new MouseEvent('mousedown', o));
      el.dispatchEvent(new FocusEvent('focusin', {bubbles:true}));
      el.dispatchEvent(new FocusEvent('focus', {bubbles:true}));
      el.dispatchEvent(new PointerEvent('pointerup', Object.assign({}, o, {buttons:0})));
      el.dispatchEvent(new MouseEvent('mouseup', Object.assign({}, o, {buttons:0})));
      el.dispatchEvent(new MouseEvent('click', Object.assign({}, o, {buttons:0})));
      return true;
    },
    /* Types into a DevExtreme editor and deliberately LEAVES THE FIELD FOCUSED.
       Do not end this with blur/focusout, and do not swap el.focus() for synthetic
       focus events: the server-backed lookups (ICD tag boxes, the grid's CCCD and
       date search) only render their drop-down while the input really holds focus,
       and blurring cancels the pending search. A version that dispatched focus
       events instead of focusing, then blurred at the end, closed the list the
       instant it was typed into -- 424 ICD codes across one 270-student run were
       reported as "không chọn được", with the drop-down never showing a single
       option. Callers that DO want the value committed on blur (set_number,
       set_text) dispatch their own blur right after calling this. */
    type: function(el, text){
      if (!el) return false;
      el.focus();
      el.value = '';
      el.dispatchEvent(new Event('input', {bubbles:true}));
      for (var i = 0; i < text.length; i++) {
        var ch = text[i];
        el.dispatchEvent(new KeyboardEvent('keydown', {key:ch, bubbles:true}));
        el.dispatchEvent(new KeyboardEvent('keypress', {key:ch, bubbles:true}));
        el.value += ch;
        el.dispatchEvent(new Event('input', {bubbles:true}));
        el.dispatchEvent(new KeyboardEvent('keyup', {key:ch, bubbles:true}));
      }
      el.dispatchEvent(new Event('change', {bubbles:true}));
      return el.value;
    },
    /* Types into a plain editor (number box, text box) and commits the value.

       This is the sequence that DevExtreme number boxes actually accept, kept
       separate from type() on purpose. The two cannot share one implementation:
       a lookup must stay focused so its server-backed drop-down survives, while a
       number box only hands its text to the model on focusout. Using the lookup
       sequence here left every measurement box holding text the model never saw and
       Medinet refused the save with "Vui lòng nhập chiều cao (cm)"; using this
       sequence for a lookup closed the drop-down before any option could load. */
    typeField: function(el, text){
      if (!el) return false;
      el.dispatchEvent(new FocusEvent('focusin', {bubbles:true}));
      el.dispatchEvent(new FocusEvent('focus', {bubbles:true}));
      el.value = '';
      el.dispatchEvent(new Event('input', {bubbles:true}));
      for (var i = 0; i < text.length; i++) {
        var ch = text[i];
        el.dispatchEvent(new KeyboardEvent('keydown', {key:ch, bubbles:true}));
        el.dispatchEvent(new KeyboardEvent('keypress', {key:ch, bubbles:true}));
        el.value += ch;
        el.dispatchEvent(new Event('input', {bubbles:true}));
        el.dispatchEvent(new KeyboardEvent('keyup', {key:ch, bubbles:true}));
      }
      el.dispatchEvent(new Event('change', {bubbles:true}));
      el.dispatchEvent(new FocusEvent('focusout', {bubbles:true}));
      el.dispatchEvent(new FocusEvent('blur', {bubbles:true}));
      return el.value;
    },
    nfc: function(s){ return (s || '').normalize('NFC').replace(/\s+/g, ' ').trim(); },
    /* Compare an option's visible text with a workbook answer. Case is deliberately
       ignored: the ADHD questionnaire offers "Thỉnh thoảng" while the workbook column
       says "thỉnh thoảng", and an exact match silently left every such question blank. */
    same: function(a, b){
      return window.__mx.nfc(a).toLowerCase() === window.__mx.nfc(b).toLowerCase();
    },
    /* Pick a dxList row. When the list carries radio/checkbox decorators the row
       itself ignores synthetic clicks -- only the decorator commits the selection. */
    pickItem: function(li){
      var deco = li.querySelector('.dx-list-select-radiobutton, .dx-list-select-checkbox');
      return window.__mx.click(deco || li);
    }
  };
  return 'helpers-ready';
})()
"""


def nfc(text) -> str:
    return wb.nfc(text)


TOOTH_CONDITION_ALIASES = {
    # Quy ước nhập liệu: file của người nhập dùng nhãn cũ/ngắn, trong khi
    # biểu đồ răng M2 hiện tại của Medinet chỉ còn nhãn này.
    "trám sâu": "Trám sâu lại",
}


def medinet_san_khoa(text) -> str:
    value = nfc(text).strip()
    if not value:
        return ""
    val_lower = value.lower()
    if val_lower in ("bình thường", "binh thuong", "thường", "thuong", "đẻ thường", "de thuong"):
        return "Bình thường"
    return "Không bình thường"


def medinet_tooth_condition(text) -> str:
    value = nfc(text)
    return TOOTH_CONDITION_ALIASES.get(value.casefold(), value)


def is_no(text) -> bool:
    """Whether a workbook answer means "no".

    Only the plain negatives count. Anything else -- including a cell that names a
    condition instead of answering the question -- is a yes, because a Có/Không radio
    has no third state to put it in.
    """
    return nfc(text).lower().strip(" .:;") in ("không", "khong", "không có", "khong co", "0")


class ClinicalFiller:
    """Drives one Medinet record through the four clinical sections."""

    def __init__(self, driver, exam_from: str, exam_to: str, dry_run: bool = False):
        self.d = driver
        self.exam_from = exam_from
        self.exam_to = exam_to
        self.dry_run = dry_run
        self._token: Optional[str] = None

    # --- transport ----------------------------------------------------------

    def js(self, code: str):
        return self.d.run_js(code)

    def install_helpers(self) -> None:
        self.js(HELPERS_JS)
        self.js(TOKEN_TAP_JS)

    def goto(self, url: str, ready_class: Optional[str] = None, timeout_s: int = 40) -> bool:
        """Navigate and wait until the target form has actually rendered.

        A fixed sleep is not enough: these forms are server-rendered dynamic layouts
        and a slow one still shows the previous section's widgets, which is exactly
        how data ends up filed under the wrong heading.
        """
        self.d.goto(url)
        deadline = time.time() + timeout_s
        blank_since = None
        blank_reloaded = False
        while time.time() < deadline:
            time.sleep(1.0)
            # Chrome occasionally finishes location.assign() on a completely blank
            # document while keeping the requested Medinet URL.  readyState is then
            # already "complete", so waiting longer can never make a form marker
            # appear.  A real reload recovers the app without losing the login or
            # the marked tab.  Require several consecutive blank observations so a
            # normal document swap is never reloaded mid-navigation.
            page_state = self.js("""
                (function(){
                    var body = document.body;
                    return {
                        ready: document.readyState,
                        chars: body ? (body.innerText || '').trim().length : 0,
                        elements: body ? body.querySelectorAll('*').length : 0,
                        appElements: (body && body.querySelector('app-root'))
                            ? body.querySelector('app-root').querySelectorAll('*').length
                            : -1
                    };
                })()
            """) or {}
            is_blank_complete = (page_state.get("ready") == "complete" and
                                 page_state.get("chars", 0) < 20 and
                                 (page_state.get("appElements") == 0 or
                                  page_state.get("elements", 0) < 5))
            if is_blank_complete and not blank_reloaded:
                blank_since = blank_since or time.time()
                if time.time() - blank_since >= 5.0:
                    hard_goto = getattr(self.d, "hard_goto", None)
                    if hard_goto:
                        hard_goto(url)
                    else:
                        self.js("location.reload(); true")
                    blank_reloaded = True
                    blank_since = None
                    time.sleep(1.0)
                    continue
            elif not is_blank_complete:
                blank_since = None
            self.install_helpers()
            if ready_class is None:
                if self.js("document.readyState") == "complete":
                    return True
            elif self.js(f"""
                (function(){{
                    if (window.__mx && window.__mx.field({js_string(ready_class)})) return true;
                    var el = document.querySelector('.' + {js_string(ready_class)});
                    if (el && (el.offsetHeight > 0 || el.offsetWidth > 0 || el.querySelector('input, .dx-texteditor-input'))) return true;
                    return false;
                }})()
            """):
                return True
        return False

    # --- widget primitives --------------------------------------------------

    def wait_field(self, cls: str, timeout_s: float = 20.0) -> bool:
        """Wait for one widget to exist, for blocks that render after the form is 'ready'.

        A section is declared ready by a single marker widget, but these forms build
        their groups progressively, so a later group can still be missing when filling
        starts. Waiting costs nothing once the widget is there and only runs its clock
        when something really is absent.
        """
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self.js(f"!!(window.__mx && window.__mx.field({js_string(cls)}))"):
                return True
            time.sleep(0.5)
        return False

    def set_number(self, cls: str, value) -> bool:
        text = wb.number(value)
        if text is None:
            return True
        return bool(self.js(f"""
            (function(){{
                var f = window.__mx.field({js_string(cls)});
                if (!f) return false;
                var i = f.querySelector('input.dx-texteditor-input');
                if (!i) return false;
                var valNum = parseFloat({js_string(text)}.replace(',', '.'));
                try {{
                    var nb = f.querySelector('.dx-numberbox') || i.closest('.dx-numberbox');
                    if (nb && window.DevExpress && window.DevExpress.ui && window.DevExpress.ui.dxNumberBox) {{
                        var inst = window.DevExpress.ui.dxNumberBox.getInstance(nb);
                        if (inst) inst.option('value', valNum);
                    }}
                }} catch(e) {{}}
                window.__mx.typeField(i, {js_string(text)});
                i.dispatchEvent(new Event('blur', {{bubbles:true}}));
                return true;
            }})()
        """))

    def set_text(self, cls: str, value) -> bool:
        """Type into a text/number box, or into a rich-text editor.

        "Đề nghị (ghi rõ)" is a DevExtreme HtmlEditor: its <textarea> is only the hidden
        submit element, and writing to it changes nothing. The visible surface is Quill's
        contenteditable, which commits through a real editing command.
        """
        text = nfc(value).replace("\n", " ")
        if not text:
            return True
        ok = bool(self.js(f"""
            (function(){{
                var f = window.__mx.field({js_string(cls)});
                if (!f) return false;

                var ql = f.querySelector('.ql-editor[contenteditable], [contenteditable="true"]');
                if (ql) {{
                    try {{
                        if (window.DevExpress && window.DevExpress.ui && window.DevExpress.ui.dxHtmlEditor) {{
                            var he = f.querySelector('.dx-htmleditor') || f;
                            var heInst = window.DevExpress.ui.dxHtmlEditor.getInstance(he);
                            if (heInst) {{
                                heInst.option('value', {js_string(text)});
                                return true;
                            }}
                        }}
                    }} catch(e) {{}}
                    ql.innerText = {js_string(text)};
                    ql.dispatchEvent(new InputEvent('input', {{bubbles:true, inputType:'insertText'}}));
                    ql.dispatchEvent(new Event('change', {{bubbles:true}}));
                    ql.dispatchEvent(new Event('blur', {{bubbles:true}}));
                    return true;
                }}

                var i = f.querySelector('textarea, input.dx-texteditor-input');
                if (!i) return false;
                window.__mx.typeField(i, {js_string(text)});
                i.dispatchEvent(new Event('blur', {{bubbles:true}}));
                return true;
            }})()
        """))
        if ok:
            # Quill pushes into the hidden submit element asynchronously; saving before
            # it lands stores an empty value.
            self._wait(lambda: bool(self.field_text(cls)), 5, 0.4)
        return ok

    def field_text(self, cls: str) -> str:
        """The plain text a field currently holds, rich-text markup stripped."""
        return nfc(self.js(f"""
            (function(){{
                var f = window.__mx.field({js_string(cls)});
                if (!f) return '';
                var ql = f.querySelector('.ql-editor[contenteditable], [contenteditable="true"]');
                if (ql) return window.__mx.nfc(ql.textContent);
                var i = f.querySelector('input.dx-texteditor-input, textarea');
                return i ? window.__mx.nfc(i.value) : '';
            }})()
        """))

    def pick_radio(self, cls: str, label: str, attempts: int = 4) -> bool:
        """Tick an option, waiting for it to exist first.

        The field wrapper renders before the options inside it do, so a pick attempted
        the instant the form appears finds nothing to click and silently leaves the
        question blank.
        """
        for attempt in range(attempts):
            if self._pick_radio_once(cls, label):
                return True
            time.sleep(1.5 if attempt else 0.5)
        return False

    def _pick_radio_once(self, cls: str, label: str) -> bool:
        """Tick the option whose visible text equals label, and confirm it stuck.

        Medinet builds single-choice fields two different ways: a real dxRadioGroup
        (a) Sản khoa, c) Tiền sử bệnh) whose label sits inside the radio, and a dxList
        with radio decorators (3. Đề nghị) whose label is a sibling of an empty radio.
        Both are handled here so callers do not have to know which one they got.
        """
        return bool(self.js(f"""
            (function(){{
                var f = window.__mx.field({js_string(cls)});
                if (!f) return false;
                var want = {js_string(label)};

                function matchOpt(txt, w) {{
                    if (!txt || !w) return false;
                    var t = window.__mx.nfc(txt).toLowerCase().trim();
                    var wt = window.__mx.nfc(w).toLowerCase().trim();
                    if (t === wt) return true;
                    if (t.indexOf(wt) !== -1 || wt.indexOf(t) !== -1) return true;
                    if ((wt.indexOf('can thiệp') !== -1 || wt.indexOf('ngạt') !== -1) && (t.indexOf('can thiệp') !== -1 || t.indexOf('ngạt') !== -1)) return true;
                    if ((wt.indexOf('bình thường') !== -1 || wt.indexOf('thường') !== -1) && (t.indexOf('bình thường') !== -1 || t.indexOf('thường') !== -1)) return true;
                    if ((wt.indexOf('thiếu tháng') !== -1 || wt.indexOf('non') !== -1) && (t.indexOf('thiếu tháng') !== -1 || t.indexOf('non') !== -1)) return true;
                    if (wt.indexOf('mổ') !== -1 && t.indexOf('mổ') !== -1) return true;
                    return false;
                }}

                var items = Array.from(f.querySelectorAll('.dx-list-item'));
                var li = items.find(function(e){{ return matchOpt(e.textContent, want); }});
                if (li) {{
                    if (li.classList.contains('dx-list-item-selected')) return true;
                    window.__mx.pickItem(li);
                    return true;
                }}

                var rg = f.querySelector('.dx-radiogroup') || f;
                try {{
                    if (window.DevExpress && window.DevExpress.ui && window.DevExpress.ui.dxRadioGroup) {{
                        var inst = window.DevExpress.ui.dxRadioGroup.getInstance(rg);
                        if (inst) {{
                            var rItems = inst.option('items') || [];
                            var foundItem = rItems.find(function(it){{
                                var txt = typeof it === 'object' ? (it.text || it.name || it.label || '') : String(it);
                                return matchOpt(txt, want);
                            }});
                            if (foundItem) {{
                                var val = typeof foundItem === 'object' ? (foundItem.value !== undefined ? foundItem.value : (foundItem.id !== undefined ? foundItem.id : foundItem)) : foundItem;
                                inst.option('value', val);
                            }}
                        }}
                    }}
                }} catch(e) {{}}

                var hit = Array.from(f.querySelectorAll('.dx-radiobutton')).find(function(b){{
                    var c = b.querySelector('.dx-item-content');
                    return matchOpt(c ? c.textContent : b.textContent, want);
                }});
                if (!hit) return false;
                if (hit.classList.contains('dx-radiobutton-checked')) return true;
                window.__mx.click(hit);
                return true;
            }})()
        """))

    def radio_checked(self, cls: str, label: str) -> bool:
        return bool(self.js(f"""
            (function(){{
                var f = window.__mx.field({js_string(cls)});
                if (!f) return false;
                var want = {js_string(label)};

                function matchOpt(txt, w) {{
                    if (!txt || !w) return false;
                    var t = window.__mx.nfc(txt).toLowerCase().trim();
                    var wt = window.__mx.nfc(w).toLowerCase().trim();
                    if (t === wt) return true;
                    if (t.indexOf(wt) !== -1 || wt.indexOf(t) !== -1) return true;
                    if ((wt.indexOf('can thiệp') !== -1 || wt.indexOf('ngạt') !== -1) && (t.indexOf('can thiệp') !== -1 || t.indexOf('ngạt') !== -1)) return true;
                    if ((wt.indexOf('bình thường') !== -1 || wt.indexOf('thường') !== -1) && (t.indexOf('bình thường') !== -1 || t.indexOf('thường') !== -1)) return true;
                    if ((wt.indexOf('thiếu tháng') !== -1 || wt.indexOf('non') !== -1) && (t.indexOf('thiếu tháng') !== -1 || t.indexOf('non') !== -1)) return true;
                    if (wt.indexOf('mổ') !== -1 && t.indexOf('mổ') !== -1) return true;
                    return false;
                }}

                var li = Array.from(f.querySelectorAll('.dx-list-item')).find(function(e){{
                    return matchOpt(e.textContent, want);
                }});
                if (li) return li.classList.contains('dx-list-item-selected');

                var rg = f.querySelector('.dx-radiogroup') || f;
                try {{
                    if (window.DevExpress && window.DevExpress.ui && window.DevExpress.ui.dxRadioGroup) {{
                        var inst = window.DevExpress.ui.dxRadioGroup.getInstance(rg);
                        if (inst && inst.option('value') !== undefined && inst.option('value') !== null) {{
                            var val = inst.option('value');
                            var rItems = inst.option('items') || [];
                            var curItem = rItems.find(function(it){{
                                var itVal = typeof it === 'object' ? (it.value !== undefined ? it.value : (it.id !== undefined ? it.id : it)) : it;
                                return itVal === val;
                            }});
                            if (curItem) {{
                                var txt = typeof curItem === 'object' ? (curItem.text || curItem.name || curItem.label || '') : String(curItem);
                                if (matchOpt(txt, want)) return true;
                            }}
                        }}
                    }}
                }} catch(e) {{}}

                return Array.from(f.querySelectorAll('.dx-radiobutton')).some(function(b){{
                    var c = b.querySelector('.dx-item-content');
                    return matchOpt(c ? c.textContent : b.textContent, want)
                        && b.classList.contains('dx-radiobutton-checked');
                }});
            }})()
        """))

    def set_checkbox(self, cls: str, on: bool = True) -> bool:
        """Tick or untick the single checkbox inside a field, idempotently."""
        return bool(self.js(f"""
            (function(){{
                var f = window.__mx.field({js_string(cls)});
                if (!f) return false;
                var cb = f.querySelector('.dx-checkbox');
                if (!cb) return false;
                var isOn = cb.classList.contains('dx-checkbox-checked');
                if (isOn === {str(bool(on)).lower()}) return true;
                window.__mx.click(cb);
                return true;
            }})()
        """))

    def checkbox_state(self, cls: str) -> Optional[bool]:
        return self.js(f"""
            (function(){{
                var f = window.__mx.field({js_string(cls)});
                if (!f) return null;
                var cb = f.querySelector('.dx-checkbox');
                return cb ? cb.classList.contains('dx-checkbox-checked') : null;
            }})()
        """)

    def pick_list_answer(self, cls: str, row_index: int, label: str) -> bool:
        """Answer one questionnaire row.

        Each answer cell is a DevExtreme List of selectable items rather than a radio
        group, so the pick is a click on the item carrying the wanted text.

        A row whose options do not include the wanted answer counts as a failure. It
        used to be reported as success, which is how every "thỉnh thoảng" answer went
        missing without a single complaint in the log.
        """
        return self.js(f"""
            (function(){{
                var f = window.__mx.field({js_string(cls)});
                if (!f) return false;
                var rows = Array.from(f.querySelectorAll('tr')).filter(function(tr){{
                    return tr.querySelector('.dx-list-item');
                }});
                var tr = rows[{row_index}];
                if (!tr) return false;
                var items = Array.from(tr.querySelectorAll('.dx-list-item'));
                var hit = items.find(function(li){{
                    return window.__mx.same(li.textContent, {js_string(label)});
                }});
                if (!hit) return false;
                if (hit.classList.contains('dx-list-item-selected')) return true;
                window.__mx.pickItem(hit);
                return true;
            }})()
        """) is True

    def question_rows(self, cls: str = "DanhGiaTamThan_ChiTiet") -> int:
        return self.js(f"""
            (function(){{
                var f = window.__mx.field({js_string(cls)});
                if (!f) return 0;
                return Array.from(f.querySelectorAll('tr')).filter(function(tr){{
                    return tr.querySelector('.dx-list-item');
                }}).length;
            }})()
        """) or 0

    def answered_rows(self, cls: str) -> int:
        return self.js(f"""
            (function(){{
                var f = window.__mx.field({js_string(cls)});
                if (!f) return 0;
                return Array.from(f.querySelectorAll('tr')).filter(function(tr){{
                    return tr.querySelector('.dx-list-item-selected');
                }}).length;
            }})()
        """) or 0

    def select_icd(self, cls: str, codes: List[str], timeout_s: int = 40) -> List[str]:
        """Add each ICD code to a diagnosis tag box. Returns the codes that failed.

        The list is server-backed: the option only exists after the search round-trips,
        so each code is typed, awaited, then clicked -- one at a time.
        """
        failed: List[str] = []
        self.icd_choices: Dict[str, List[str]] = {}
        # Why each failure happened, so a silent drop-down never again hides behind the
        # same message as a code Medinet genuinely does not carry.
        self.icd_why: Dict[str, str] = {}
        for code in codes:
            if self.icd_has(cls, code):
                continue
            typed = self.js(f"""
                (function(){{
                    var f = window.__mx.field({js_string(cls)});
                    if (!f) return 'no-field';
                    var i = f.querySelector('input.dx-texteditor-input');
                    if (!i) return 'no-input';
                    window.__mx.type(i, {js_string(code)});
                    return 'typed';
                }})()
            """)
            if typed != 'typed':
                self.icd_why[code] = ('không tìm thấy ô nhập mã ICD trên form'
                                      if typed == 'no-field' else
                                      'ô mã ICD không có chỗ gõ')
                failed.append(code)
                continue
            saw_items = False
            picked = False
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                time.sleep(0.6)
                got = self.js(f"""
                    (function(){{
                        var want = {js_string(code.upper())};
                        var items = Array.from(document.querySelectorAll('.dx-overlay-content .dx-list-item'))
                            .filter(window.__mx.live);
                        if (!items.length) return 'waiting';
                        var hit = items.find(function(li){{
                            var t = window.__mx.nfc(li.textContent).toUpperCase();
                            return t === want || t.indexOf(want + ' ') === 0 || t.indexOf(want + '-') === 0;
                        }});
                        if (!hit) return 'no-match:' + items.length;
                        window.__mx.click(hit);
                        return 'picked';
                    }})()
                """)
                if got == "picked":
                    saw_items = True
                    picked = True
                    break
                if isinstance(got, str) and got.startswith("no-match"):
                    saw_items = True
                    # The catalogue offers something, just not this exact code -- almost
                    # always because the workbook names a category (F90) where Medinet
                    # only carries its leaves (F90.0, F90.1, ...). Which leaf applies is
                    # a clinical decision, so record the choices and let a human pick.
                    self.icd_choices[code] = self.js("""
                        (function(){
                            return Array.from(document.querySelectorAll(
                                '.dx-overlay-content .dx-list-item'))
                              .filter(window.__mx.live)
                              .map(function(li){ return window.__mx.nfc(li.textContent); })
                              .slice(0, 8);
                        })()
                    """) or []
                    break
            # Close the drop-down and clear the leftover search text either way.
            self.js(f"""
                (function(){{
                    var f = window.__mx.field({js_string(cls)});
                    if (!f) return false;
                    var i = f.querySelector('input.dx-texteditor-input');
                    if (i) {{
                        i.value = '';
                        i.dispatchEvent(new Event('input', {{bubbles:true}}));
                        i.dispatchEvent(new KeyboardEvent('keydown', {{key:'Escape', bubbles:true}}));
                        i.blur();
                    }}
                    return true;
                }})()
            """)
            time.sleep(0.5)
            if not (picked and self.icd_has(cls, code)):
                if not saw_items:
                    # Nothing was ever offered. The catalogue is server-backed, so this
                    # means the search never ran or its drop-down was closed again --
                    # not that the code is missing from Medinet.
                    self.icd_why[code] = (f"gõ {code} nhưng danh sách gợi ý không hiện ra "
                                          f"sau {timeout_s}s")
                elif picked:
                    self.icd_why[code] = "chọn xong nhưng mã không bám vào ô"
                failed.append(code)
        return failed

    def icd_has(self, cls: str, code: str) -> bool:
        return bool(self.js(f"""
            (function(){{
                var f = window.__mx.field({js_string(cls)});
                if (!f) return false;
                return Array.from(f.querySelectorAll('.dx-tag-content')).some(function(t){{
                    return window.__mx.nfc(t.textContent).toUpperCase()
                        .indexOf({js_string(code.upper())}) === 0;
                }});
            }})()
        """))

    def set_datebox(self, cls: str, ddmmyyyy: str) -> bool:
        """Set a DevExtreme DateBox through its calendar.

        Typing into a DateBox only repaints the display; the bound value keeps its old
        date and that is what gets saved. Driving the calendar commits the real value.
        """
        current = self.js(f"""
            (function(){{
                var f = window.__mx.field({js_string(cls)});
                if (!f) return null;
                var i = f.querySelector('input.dx-texteditor-input');
                return i ? i.value.trim() : null;
            }})()
        """)
        if current == ddmmyyyy:
            return True
        parts = (ddmmyyyy or "").split("/")
        if len(parts) != 3:
            # An empty or malformed date reaches here when the record's own exam date
            # could not be read; refuse it rather than crashing the whole student.
            return False
        day, month, year = parts
        target = f"{year}/{month}/{day}"

        opened = self.js(f"""
            (function(){{
                var f = window.__mx.field({js_string(cls)});
                if (!f) return false;
                var b = f.querySelector('.dx-dropdowneditor-button');
                if (!b) return false;
                window.__mx.click(b);
                return true;
            }})()
        """)
        if not opened:
            return False

        for _ in range(30):
            time.sleep(0.4)
            got = self.js(f"""
                (function(){{
                    var cells = Array.from(document.querySelectorAll('.dx-calendar-cell'))
                        .filter(window.__mx.live);
                    if (!cells.length) return 'no-calendar';
                    var hit = cells.find(function(c){{
                        return c.getAttribute('data-value') === {js_string(target)};
                    }});
                    if (hit) {{ window.__mx.click(hit); return 'picked'; }}
                    var first = cells[0].getAttribute('data-value') || '';
                    var last = cells[cells.length - 1].getAttribute('data-value') || '';
                    var dir = ({js_string(target)} < first) ? 'previous' : (({js_string(target)} > last) ? 'next' : null);
                    if (!dir) return 'not-in-view';
                    var nav = document.querySelector('.dx-calendar-navigator-' + dir + '-view');
                    if (!nav) return 'no-nav';
                    window.__mx.click(nav);
                    return 'moved-' + dir;
                }})()
            """)
            if got == "picked":
                break
            if got in ("not-in-view", "no-nav"):
                return False
        time.sleep(0.8)
        return self.js(f"""
            (function(){{
                var f = window.__mx.field({js_string(cls)});
                if (!f) return null;
                var i = f.querySelector('input.dx-texteditor-input');
                return i ? i.value.trim() : null;
            }})()
        """) == ddmmyyyy

    # --- saving -------------------------------------------------------------

    def validation_messages(self) -> List[str]:
        """Validation text that reflects the form's current state.

        DevExtreme keeps a message node per editor and does not always remove it
        once the editor becomes valid again, so reading the text alone reports
        failures that are not happening. A saved Tiền sử section was rejected this
        way -- all six measurements present and correct, no editor carrying
        dx-invalid, yet twelve "Vui lòng nhập ..." nodes still in the page. The
        editors themselves are the authority: while nothing is marked dx-invalid,
        those nodes are leftovers. Toasts are different -- they carry server
        replies, which no field state reflects -- so they always count.
        """
        return self.js("""
            (function(){
                var text = function(sel){
                    return Array.from(document.querySelectorAll(sel))
                      .filter(window.__mx.live)
                      .map(function(e){ return window.__mx.nfc(e.textContent); })
                      .filter(function(t){ return t; });
                };
                var out = text('.dx-toast-message');
                if (document.querySelectorAll('.dx-invalid').length) {
                    out = out.concat(
                        text('.dx-validationsummary-item, .dx-invalid-message-content'));
                }
                return out;
            })()
        """) or []

    def save(self, label: str, settle_s: float = 1.5) -> Tuple[bool, List[str]]:
        """Press a section's save button."""
        if self.dry_run:
            return True, ["dry-run: không bấm lưu"]

        before = set(self.validation_messages())
        clicked = self.js(f"""
            (function(){{
                var want = window.__mx.nfc({js_string(label)});
                var btns = Array.from(document.querySelectorAll('.dx-button, button'))
                    .filter(window.__mx.live)
                    .filter(function(b){{ return window.__mx.nfc(b.textContent) === want; }});
                if (!btns.length) return false;
                window.__mx.click(btns[0]);
                return true;
            }})()
        """)
        if not clicked:
            return False, [f"không tìm thấy nút {label!r}"]

        time.sleep(settle_s)
        new_errors = [m for m in self.validation_messages() if m not in before]
        if new_errors:
            return False, new_errors
        return True, []

    # --- sections -----------------------------------------------------------

    def fill_tien_su(self, r: Dict) -> List[str]:
        """Section 1: tiền sử bản thân + khám thể lực."""
        problems = []

        # Tiền sử gia đình. "Không" means no disease is ticked, which is the form's
        # own default -- only a cell naming diseases would need any clicking, and the
        # workbook has never carried one, so anything else is flagged, not guessed.
        family = nfc(r["ts_gia_dinh"])
        if family and family.lower() not in ("không", "khong", "không có"):
            problems.append(f"tiền sử gia đình {family!r} chưa có quy tắc -- bỏ trống")

        san_khoa = medinet_san_khoa(r["ts_san_khoa"])
        if san_khoa and not self.pick_radio("TS_BanThan_SanKhoa", san_khoa):
            problems.append(f"không chọn được sản khoa {san_khoa!r}")

        tiem_chung = nfc(r["ts_tiem_chung"])
        if tiem_chung:
            missed = self.set_all_vaccines(tiem_chung)
            if missed:
                problems.append(f"tiêm chủng: {missed} dòng chưa đặt được {tiem_chung!r}")

        # "c) Tiền sử bệnh" is a bare Có/Không radio -- there is no box beside it for the
        # name of the illness. The column is mostly "Không", but a row that names a
        # condition ("ĐÃ điều trị hen suyễn dự phòng") is still answering yes, so it is
        # filed as Có and the wording is reported back: it has nowhere to live on this
        # form, and "d) Hiện tại có đang điều trị" is a different question with its own
        # answer in the workbook, so it must not be written there.
        benh_tat = nfc(r["ts_benh_tat"])
        if benh_tat:
            answer = "Không" if is_no(benh_tat) else "Có"
            if not self.pick_radio("TS_BanThan_MacBenh", answer):
                problems.append(f"không chọn được tiền sử bệnh {answer!r}")
            elif answer == "Có" and nfc(benh_tat).lower() != "có":
                problems.append(
                    NOTE_PREFIX +
                    f"tiền sử bệnh ghi {benh_tat!r} -- form chỉ có Có/Không nên đã chọn "
                    f"'Có'; phần chữ này không có ô để nhập")

        if not self.set_text("TS_BanThan_DangDieuTriBenh", r["ts_dang_dieu_tri"]):
            problems.append("không nhập được mục d) đang điều trị")

        # Khám thể lực sits below Tiền sử on the same form and renders later, while
        # the section is declared ready as soon as TS_BanThan_SanKhoa exists. On a
        # loaded server the six measurement boxes are still absent at that point, so
        # every one of them silently fails to take a value and Medinet rejects the
        # save with "Vui lòng nhập chiều cao (cm)". Wait for the block itself.
        if not self.wait_field("TheLuc_ChieuCao"):
            problems.append("khối Khám thể lực không hiện ra để nhập số đo")
        for cls, key in (("TheLuc_ChieuCao", "chieu_cao"),
                         ("TheLuc_CanNang", "can_nang"),
                         ("TheLuc_Mach", "mach"),
                         ("TheLuc_HuyetApTamThu", "huyet_ap_tt"),
                         ("TheLuc_HuyetApTamTruong", "huyet_ap_ttr"),
                         ("NhipTho", "nhip_tho")):
            if not self.set_number(cls, r[key]):
                problems.append(f"không nhập được {key}")
        return problems

    def set_all_vaccines(self, answer: str) -> int:
        """Set every vaccination row to the same answer. Returns the rows left unset.

        The workbook records tiêm chủng as one verdict for the whole schedule, and the
        form asks it per dose, so the single answer is applied to all of them.

        The doses live in two DevExtreme grids that re-bind after every pick, so
        clicking them all in one synchronous pass leaves both grids empty and saves
        nothing. They still have to go one at a time -- but the pacing runs inside the
        page on a timer instead of over AppleScript, which turns ~38 round-trips of
        half a second each into a handful of polls. Each tick re-finds the next
        unanswered row from scratch, so a re-bind between ticks is harmless.
        """
        if not self._wait(lambda: self.vaccine_state()["groups"] > 0, 30):
            return -1

        self.js(f"""
            (function(){{
                var want = {js_string(answer)};
                var st = window.__mxVac = {{done: 0, total: 0, misses: 0, running: true}};
                var tick = function(){{
                    /* The stop flag is checked here, at the top of every tick, so the
                       controller can actually end this pass. Without it setting
                       st.running = false did nothing: the setTimeout chain kept
                       clicking vaccination rows while the next steps typed the six
                       measurement boxes, and every click re-bound the grid and reset
                       the form model underneath them -- the save then failed with
                       "Vui lòng nhập chiều cao (cm)" even though the values had just
                       been entered. */
                    if (!st.running) return;
                    var f = window.__mx.field('KSKD18_TiemChung_Json');
                    var groups = f ? Array.from(f.querySelectorAll('.dx-radiogroup')) : [];
                    st.total = groups.length || st.total;
                    st.done = groups.filter(function(g){{
                        return g.querySelector('.dx-radiobutton-checked'); }}).length;
                    var next = groups.find(function(g){{
                        return !g.querySelector('.dx-radiobutton-checked'); }});
                    if (groups.length && !next) {{ st.running = false; return; }}
                    var hit = next && Array.from(next.querySelectorAll('.dx-radiobutton'))
                        .find(function(b){{
                            var c = b.querySelector('.dx-item-content');
                            return window.__mx.same(c ? c.textContent : b.textContent, want);
                        }});
                    if (hit) {{ window.__mx.click(hit); st.misses = 0; }}
                    else {{ st.misses++; }}
                    if (st.misses > {int(VACCINE_STALL_S * 1000 / VACCINE_TICK_MS)}) {{
                        st.running = false; return; }}
                    setTimeout(tick, {VACCINE_TICK_MS});
                }};
                setTimeout(tick, 0);
                return true;
            }})()
        """)

        # A flat timeout here is what silently truncated the schedule on a loaded
        # server: the pass was still working through the doses when the clock ran
        # out, and the rows it had not reached yet got reported as unset. Wait on
        # progress instead -- the deadline only advances the run when nothing at all
        # is happening, so a slow server finishes and a dead one still gives up.
        deadline = time.time() + VACCINE_BUDGET_S
        stall_until = time.time() + VACCINE_STALL_S
        best = -1
        while time.time() < min(deadline, stall_until):
            if not self.js("!!window.__mxVac && window.__mxVac.running"):
                break
            done = self.vaccine_state()["done"]
            if done > best:
                best = done
                stall_until = time.time() + VACCINE_STALL_S
            time.sleep(1.0)
        # Stop the in-page pass and give any tick already scheduled time to see the
        # flag and return, so nothing is still clicking when the next field is typed.
        self.js("(function(){ if (window.__mxVac) window.__mxVac.running = false; return 1; })()")
        time.sleep(VACCINE_TICK_MS / 1000.0 + 0.3)
        final = self.vaccine_state()
        return max(0, final["groups"] - final["done"])

    def vaccine_state(self) -> Dict[str, int]:
        return self.js("""
            (function(){
                var f = window.__mx.field('KSKD18_TiemChung_Json');
                if (!f) return {groups: 0, done: 0};
                var groups = Array.from(f.querySelectorAll('.dx-radiogroup'));
                return {groups: groups.length,
                        done: groups.filter(function(g){
                            return g.querySelector('.dx-radiobutton-checked'); }).length};
            })()
        """) or {"groups": 0, "done": 0}

    def fill_tam_than(self, r: Dict, answers: List[str], exam_date: str) -> List[str]:
        """One sub-tab of section 2: the evaluation date plus every question."""
        problems = []
        wanted = len([a for a in answers if nfc(a)])
        if not self._wait(lambda: self.question_rows() >= wanted, 90):
            problems.append(f"bảng câu hỏi chỉ nạp được {self.question_rows()}/{wanted} dòng")

        if not self.set_datebox("NgayDanhGia", exam_date):
            problems.append(f"không đặt được ngày đánh giá {exam_date}")

        ans_clean = [nfc(a) for a in answers]
        missing = self.js(f"""
            (function(){{
                var f = window.__mx.field('DanhGiaTamThan_ChiTiet');
                if (!f) return [];
                var answers = {json.dumps(ans_clean, ensure_ascii=False)};
                var rows = Array.from(f.querySelectorAll('tr')).filter(function(tr){{
                    return tr.querySelector('.dx-list-item');
                }});
                var miss = [];
                answers.forEach(function(ans, i){{
                    if (!ans) return;
                    var tr = rows[i];
                    if (!tr) {{ miss.push(i); return; }}
                    var items = Array.from(tr.querySelectorAll('.dx-list-item'));
                    var hit = items.find(function(li){{ return window.__mx.same(li.textContent, ans); }});
                    if (!hit) {{ miss.push(i); return; }}
                    if (!hit.classList.contains('dx-list-item-selected')) {{
                        window.__mx.pickItem(hit);
                    }}
                }});
                return miss;
            }})()
        """) or []

        for i in missing:
            problems.append(f"câu {i + 1}: không chọn được {answers[i]!r}")
        answered = self.answered_rows("DanhGiaTamThan_ChiTiet")
        if answered < wanted:
            problems.append(f"mới trả lời {answered}/{wanted} câu")
        return problems

    def fill_lam_sang(self, r: Dict) -> List[str]:
        """Section 3: nhi khoa, mắt, tai-mũi-họng, răng-hàm-mặt."""
        problems = []

        for key, cb_cls, icd_cls in NHI_KHOA:
            problems += self.fill_diagnosis(r[key], cb_cls, icd_cls, key)

        if not self.set_text("KhamLamSangKhac", r["kham_lam_sang_khac"]):
            problems.append("không nhập được khám lâm sàng khác")

        for cls, key in (("Mat_KhongKinh_MP", "mat_khong_kinh_mp"),
                         ("Mat_KhongKinh_MT", "mat_khong_kinh_mt"),
                         ("Mat_CoKinh_MP", "mat_co_kinh_mp"),
                         ("Mat_CoKinh_MT", "mat_co_kinh_mt")):
            score = wb.vision_score(r[key])
            if score is not None and not self.set_number(cls, score):
                problems.append(f"không nhập được thị lực {key}")
        problems += self.fill_diagnosis(r["mat_benh"], "Mat_ChuaPhatHienBatThuong",
                                        "Mat_ChanDoanSoBo_ICD", "mắt")

        for cls, key in (("TMH_TaiTrai_NoiThuong", "tai_trai_noi_thuong"),
                         ("TMH_TaiTrai_NoiTham", "tai_trai_noi_tham"),
                         ("TMH_TaiPhai_NoiThuong", "tai_phai_noi_thuong"),
                         ("TMH_TaiPhai_NoiTham", "tai_phai_noi_tham")):
            if not self.set_number(cls, r[key]):
                problems.append(f"không nhập được thính lực {key}")
        problems += self.fill_diagnosis(r["tmh_benh"], "TMH_ChuaPhatHienBatThuong",
                                        "TMH_ChanDoanSoBo_ICD", "tai-mũi-họng")

        problems += self.fill_teeth(r)
        problems += self.fill_diagnosis(r["rhm_benh"], "RHM_ChuaPhatHienBatThuong",
                                        "RHM_ChanDoanSoBo_ICD", "răng-hàm-mặt")
        return problems

    def fill_diagnosis(self, cell, cb_cls: str, icd_cls: str, what: str) -> List[str]:
        """One clinical block: either 'chưa phát hiện bất thường' or a set of ICD codes."""
        text = nfc(cell)
        if not text:
            return []
        if wb.is_no_finding(text):
            return [] if self.set_checkbox(cb_cls, True) else [f"{what}: không tích được ô bình thường"]
        codes = wb.icd_codes(text)
        if not codes:
            return [f"{what}: không đọc được mã ICD trong {text!r}"]
        self.set_checkbox(cb_cls, False)
        failed = self.select_icd(icd_cls, codes)
        if not failed:
            return []
        notes = []
        for code in failed:
            choices = getattr(self, "icd_choices", {}).get(code)
            if choices:
                notes.append(f"{what}: Medinet không có mã {code} -- chọn tay một trong: "
                             + " | ".join(choices))
            else:
                why = getattr(self, "icd_why", {}).get(code)
                notes.append(f"{what}: không chọn được mã ICD {code}"
                             + (f" -- {why}" if why else ""))
        return notes

    def fill_teeth(self, r: Dict) -> List[str]:
        """Mark each decayed tooth 'Sâu' through its own popup form.

        Only teeth the workbook actually lists are touched; every other tooth keeps
        whatever Medinet already holds.
        """
        condition = medinet_tooth_condition(r["tinh_trang_rang"])
        teeth = wb.tooth_numbers(r["cac_rang_sau"])
        if not condition or condition.lower() in ("bình thường", "binh thuong"):
            return []
        if not teeth:
            return [f"tình trạng răng {condition!r} nhưng không có danh sách răng"]

        # 1. Trigger iframe chart render via native INIT_DATA postMessage if unrendered
        self.js("""
            (function(){
                var frame = document.querySelector('iframe[src*="ksk_kham_rang_m2"]');
                if (frame && frame.contentWindow && frame.contentDocument && !frame.contentDocument.querySelector('.tooth-card')) {
                    frame.contentWindow.postMessage({action: "INIT_DATA", payload: []}, "*");
                }
            })()
        """)
        time.sleep(0.5)

        # 2. Select bulk status, click tooth cards, and apply
        res = self.js(f"""
            (function(){{
                var frame = document.querySelector('iframe[src*="ksk_kham_rang_m2"]');
                if (!frame || !frame.contentDocument) return 'no frame';
                var doc = frame.contentDocument;
                var win = frame.contentWindow;

                // Ensure cards exist
                if (!doc.querySelector('.tooth-card')) {{
                    try {{
                        win.postMessage({{action: "INIT_DATA", payload: []}}, "*");
                    }} catch(e) {{}}
                }}

                // Find status ID for condition
                var wantCond = window.__mx ? window.__mx.nfc({js_string(condition)}) : {js_string(condition)};
                var bulkSel = doc.getElementById('bulkStatusSelect');
                var hitStatusId = '192'; // default Sâu
                if (bulkSel) {{
                    var hitOpt = Array.from(bulkSel.options).find(function(o){{
                        var t = window.__mx ? window.__mx.nfc(o.textContent) : (o.textContent||'').trim();
                        return t.toLowerCase() === wantCond.toLowerCase();
                    }});
                    if (hitOpt) {{
                        hitStatusId = hitOpt.value;
                        bulkSel.value = hitStatusId;
                        bulkSel.dispatchEvent(new Event('change', {{bubbles:true}}));
                    }}
                }}

                // Click target tooth cards to select them
                var teethList = {json.dumps(teeth)};
                var missingTeeth = [];
                teethList.forEach(function(tooth){{
                    var card = doc.getElementById('tooth-card-' + tooth);
                    if (card) {{
                        if (!card.classList.contains('is-selected')) {{
                            card.click();
                        }}
                    }} else {{
                        missingTeeth.push(tooth);
                    }}
                }});

                // Click Áp dụng button
                var applyBtn = doc.getElementById('applyBulkStatusBtn');
                if (applyBtn) {{
                    applyBtn.disabled = false;
                    applyBtn.click();
                }}

                // Fallback: also ensure each select is explicitly set and change dispatched
                teethList.forEach(function(tooth){{
                    var sel = doc.querySelector('select.tooth-select[data-tooth="' + tooth + '"]');
                    if (sel && sel.value !== hitStatusId) {{
                        sel.value = hitStatusId;
                        sel.dispatchEvent(new Event('input', {{bubbles:true}}));
                        sel.dispatchEvent(new Event('change', {{bubbles:true}}));
                    }}
                }});

                if (typeof win.buildDentalJSON === 'function') {{
                    win.buildDentalJSON();
                }}

                return JSON.stringify({{
                    appliedCount: doc.querySelectorAll('.tooth-card[data-status-id="' + hitStatusId + '"]').length,
                    missingTeeth: missingTeeth
                }});
            }})()
        """)

        problems = []
        if isinstance(res, str):
            try:
                data = json.loads(res)
                for mt in data.get("missingTeeth", []):
                    problems.append(f"răng {mt}: không tìm thấy thẻ răng")
            except Exception:
                if res != "ok":
                    problems.append(f"lỗi nhập răng: {res}")
        return problems

    def set_one_tooth(self, tooth: str, condition: str, timeout_s: int = 30) -> Tuple[bool, str]:
        condition = medinet_tooth_condition(condition)

        opened = self.js(f"""
            (function(){{
                // New M2 forms render the dental chart in a same-origin iframe and
                // use a native select per tooth. Run this in Chrome's page world so
                // the iframe's own change handler posts the JSON back to Angular.
                var frame = document.querySelector('iframe[src*="ksk_kham_rang_m2"]');
                if (frame) {{
                    var doc = null;
                    try {{ doc = frame.contentDocument; }} catch (e) {{}}
                    if (!doc) return 'iframe-inaccessible';
                    var sel = doc.querySelector('select.tooth-select[data-tooth="' + {js_string(tooth)} + '"]');
                    if (!sel) {{
                        try {{
                            var win = frame.contentWindow;
                            if (typeof win.renderDentalChart !== 'function') {{
                                var scriptTag = doc.querySelector('script:not([src])');
                                if (scriptTag) win.eval(scriptTag.innerHTML);
                            }}
                            if (typeof win.renderDentalChart === 'function') {{
                                win.renderDentalChart();
                                win.initializeBulkToolbar();
                            }}
                        }} catch(e) {{}}
                        sel = doc.querySelector('select.tooth-select[data-tooth="' + {js_string(tooth)} + '"]');
                    }}
                    if (!sel) return 'no-tooth';
                    var want = window.__mx.nfc({js_string(condition)});
                    var hit = Array.from(sel.options).find(function(o){{
                        return window.__mx.nfc(o.textContent) === want;
                    }});
                    if (!hit) return 'no-condition';
                    if (sel.value !== hit.value) {{
                        sel.value = hit.value;
                        var EventCtor = (frame.contentWindow && frame.contentWindow.Event) || Event;
                        sel.dispatchEvent(new EventCtor('input', {{bubbles:true}}));
                        sel.dispatchEvent(new EventCtor('change', {{bubbles:true}}));
                        try {{
                            if (frame.contentWindow && typeof frame.contentWindow.buildDentalJSON === 'function') {{
                                frame.contentWindow.buildDentalJSON();
                            }}
                        }} catch(e) {{}}
                    }}
                    return sel.value === hit.value ? 'iframe-ok' : 'iframe-not-set';
                }}

                // Legacy forms used a popup chart in the main document.  Do not
                // bind to its old generated dynamicreportNNNN id.
                var teeth = Array.from(document.querySelectorAll('.tooth'))
                  .filter(window.__mx.live);
                if (!teeth.length) return 'no-chart';
                var t = teeth.find(function(d){{
                    var n = d.querySelector('.toothNumber');
                    return n && n.textContent.trim() === {js_string(tooth)};
                }});
                if (!t) return 'no-tooth';
                var img = t.querySelector('img');
                if (!img) return 'no-image';
                window.__mx.click(img);
                return 'ok';
            }})()
        """)

        if opened == "iframe-ok":
            time.sleep(0.4)
            return True, ""
        if opened != "ok":
            return False, str(opened)

        if not self._wait(lambda: self.js("""
            (function(){
                return Array.from(document.querySelectorAll('.dx-overlay-content'))
                  .filter(window.__mx.live)
                  .some(function(p){ return p.innerText.indexOf('TÌNH TRẠNG RĂNG') >= 0; });
            })()
        """), timeout_s):
            return False, "popup không mở"

        # Confirm the popup really is this tooth before changing anything.
        shown = self.js("""
            (function(){
                var f = window.__mx.field('ViTriRang');
                if (!f) return null;
                var i = f.querySelector('input.dx-texteditor-input');
                return i ? i.value.trim() : null;
            })()
        """)
        if shown != tooth:
            self.close_tooth_popup()
            return False, f"popup mở nhầm răng {shown!r}"

        picked = self.pick_select("TinhTrangId", condition)
        if not picked:
            self.close_tooth_popup()
            return False, f"không chọn được tình trạng {condition!r}"

        if self.dry_run:
            self.close_tooth_popup()
            return True, "dry-run"

        ok, messages = self.save("Lưu", settle_s=6)
        self._wait(lambda: not self.js("""
            (function(){
                return Array.from(document.querySelectorAll('.dx-overlay-content'))
                  .filter(window.__mx.live)
                  .some(function(p){ return p.innerText.indexOf('TÌNH TRẠNG RĂNG') >= 0; });
            })()
        """), 15)
        self.close_tooth_popup()
        return (True, "") if ok else (False, "; ".join(messages) or "lưu thất bại")

    def close_tooth_popup(self) -> None:
        self.js("""
            (function(){
                var p = Array.from(document.querySelectorAll('.dx-overlay-content'))
                  .filter(window.__mx.live)
                  .find(function(e){ return e.innerText.indexOf('TÌNH TRẠNG RĂNG') >= 0; });
                if (!p) return true;
                var b = Array.from(p.querySelectorAll('.dx-button, button'))
                  .find(function(e){ return window.__mx.nfc(e.textContent) === 'Quay lại'; });
                if (b) window.__mx.click(b);
                return true;
            })()
        """)
        time.sleep(1.2)

    def pick_select(self, cls: str, option: str, timeout_s: int = 15) -> bool:
        """Choose an option in a plain (non-searchable) DevExtreme select box."""
        if self.js(f"""
            (function(){{
                var f = window.__mx.field({js_string(cls)});
                if (!f) return false;
                var i = f.querySelector('input.dx-texteditor-input');
                return !!i && window.__mx.nfc(i.value) === window.__mx.nfc({js_string(option)});
            }})()
        """):
            return True
        self.js(f"""
            (function(){{
                var f = window.__mx.field({js_string(cls)});
                if (!f) return false;
                var b = f.querySelector('.dx-dropdowneditor-button');
                if (!b) return false;
                window.__mx.click(b);
                return true;
            }})()
        """)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            time.sleep(0.5)
            got = self.js(f"""
                (function(){{
                    var want = window.__mx.nfc({js_string(option)});
                    var items = Array.from(document.querySelectorAll('.dx-overlay-content .dx-list-item'))
                        .filter(window.__mx.live);
                    if (!items.length) return 'waiting';
                    var hit = items.find(function(li){{ return window.__mx.nfc(li.textContent) === want; }});
                    if (!hit) return 'no-match';
                    window.__mx.click(hit);
                    return 'picked';
                }})()
            """)
            if got == "picked":
                break
            if got == "no-match":
                return False
        time.sleep(0.6)
        return bool(self.js(f"""
            (function(){{
                var f = window.__mx.field({js_string(cls)});
                if (!f) return false;
                var i = f.querySelector('input.dx-texteditor-input');
                return !!i && window.__mx.nfc(i.value) === window.__mx.nfc({js_string(option)});
            }})()
        """))

    def fill_ket_luan(self, r: Dict) -> List[str]:
        """Section 4. Which "3. Đề nghị" applies is read off Medinet's own summary of
        "2. Bệnh, tật cần lưu ý, theo dõi" -- that box is computed from the diagnoses
        just saved in Khám lâm sàng, so it, not the workbook, decides."""
        problems = []
        followup = self.benh_tat_can_luu_y()
        if not (followup or "").strip():
            return ["không đọc được mục 2. Bệnh, tật cần lưu ý"]

        clean = followup.lower().strip(" .:;")
        healthy = clean in ("không có", "khong co")
        wanted = DE_NGHI_BINH_THUONG if healthy else DE_NGHI_NGUY_CO

        self.pick_radio("DeNghi", wanted)
        time.sleep(0.5)
        if not self.radio_checked("DeNghi", wanted):
            problems.append(f"không chọn được đề nghị {wanted!r}")

        if not healthy and not self.set_text("KetLuan_DeNghi", r["de_nghi"]):
            problems.append("không nhập được ô Đề nghị (ghi rõ)")
        return problems

    def benh_tat_can_luu_y(self, timeout_s: float = 20.0) -> Optional[str]:
        """The text Medinet computed into '2. Bệnh, tật cần lưu ý, theo dõi:'.

        The box is filled in after the rest of the form paints, and until then it reads
        as either a missing heading or an empty body -- an empty body being the same
        thing a healthy child produces once loaded. Reading it too early is therefore
        not a harmless miss: it decides "3. Đề nghị" the wrong way round and leaves the
        Đề nghị text unwritten. A loaded box always says something ("Không có" for a
        healthy child), so waiting for non-empty text separates the two.
        """
        deadline = time.time() + timeout_s
        text = self._benh_tat_raw()
        while not (text or "").strip() and time.time() < deadline:
            time.sleep(1.0)
            text = self._benh_tat_raw()
        return text

    def _benh_tat_raw(self) -> Optional[str]:
        return self.js("""
            (function(){
                var blocks = Array.from(document.querySelectorAll('div'))
                  .filter(window.__mx.live)
                  .filter(function(d){
                      return d.children.length === 0
                          && d.textContent.indexOf('Bệnh, tật cần lưu ý') >= 0;
                  });
                if (!blocks.length) return null;
                var head = blocks[0];
                var box = head.parentElement;
                if (!box) return null;
                var kids = Array.from(box.children);
                var i = kids.indexOf(head);
                var body = kids[i + 1];
                return body ? window.__mx.nfc(body.textContent) : '';
            })()
        """)

    # --- read-back verification ---------------------------------------------
    # Each of these runs against a freshly reloaded section, so what it reads is what
    # Medinet actually stored -- the only trustworthy proof that a save took effect.

    def field_value(self, cls: str) -> Optional[str]:
        return self.js(f"""
            (function(){{
                var f = window.__mx.field({js_string(cls)});
                if (!f) return null;
                var i = f.querySelector('input.dx-texteditor-input, textarea');
                return i ? i.value.trim() : null;
            }})()
        """)

    def verify_tien_su(self, r: Dict, exam_date: str) -> List[str]:
        bad = []
        for cls, key, label in (("TheLuc_ChieuCao", "chieu_cao", "chiều cao"),
                                ("TheLuc_CanNang", "can_nang", "cân nặng"),
                                ("TheLuc_Mach", "mach", "mạch"),
                                ("TheLuc_HuyetApTamThu", "huyet_ap_tt", "huyết áp TT"),
                                ("TheLuc_HuyetApTamTruong", "huyet_ap_ttr", "huyết áp TTr"),
                                ("NhipTho", "nhip_tho", "nhịp thở")):
            want = wb.number(r[key])
            if want is None:
                continue
            got = self.field_value(cls)
            if got is None or not got:
                bad.append(f"{label} lưu là {got!r}, cần {want!r}")
                continue
            got_clean = got.replace(",", ".").strip()
            want_clean = want.replace(",", ".").strip()
            try:
                if float(got_clean) != float(want_clean):
                    bad.append(f"{label} lưu là {got!r}, cần {want!r}")
            except ValueError:
                if got_clean != want_clean:
                    bad.append(f"{label} lưu là {got!r}, cần {want!r}")

        san_khoa = medinet_san_khoa(r["ts_san_khoa"])
        if san_khoa and not self.radio_checked("TS_BanThan_SanKhoa", san_khoa):
            bad.append(f"sản khoa không giữ {san_khoa!r}")
        benh_tat = nfc(r["ts_benh_tat"])
        if benh_tat:
            want_bt = "Không" if is_no(benh_tat) else "Có"
            if not self.radio_checked("TS_BanThan_MacBenh", want_bt):
                bad.append(f"tiền sử bệnh không giữ {want_bt!r}")

        want_dt = nfc(r["ts_dang_dieu_tri"]).replace("\n", " ")
        if want_dt and self.field_value("TS_BanThan_DangDieuTriBenh") != want_dt:
            bad.append("mục d) đang điều trị không lưu")

        if nfc(r["ts_tiem_chung"]):
            state = self.vaccine_state()
            if state["groups"] and state["done"] < state["groups"]:
                bad.append(f"tiêm chủng chỉ lưu {state['done']}/{state['groups']} dòng")
        return bad

    def verify_tam_than(self, answers: List[str], exam_date: str) -> List[str]:
        bad = []
        wanted = len([a for a in answers if nfc(a)])
        self._wait(lambda: self.question_rows() >= wanted, 45)
        got_date = self.field_value("NgayDanhGia")
        if exam_date and got_date != exam_date:
            bad.append(f"ngày đánh giá lưu là {got_date!r}, cần {exam_date!r}")
        answered = self.answered_rows("DanhGiaTamThan_ChiTiet")
        if answered < wanted:
            bad.append(f"chỉ lưu {answered}/{wanted} câu trả lời")
        return bad

    def verify_lam_sang(self, r: Dict) -> List[str]:
        bad = []
        blocks = [(r[key], cb, icd, key) for key, cb, icd in NHI_KHOA]
        blocks += [(r["mat_benh"], "Mat_ChuaPhatHienBatThuong", "Mat_ChanDoanSoBo_ICD", "mắt"),
                   (r["tmh_benh"], "TMH_ChuaPhatHienBatThuong", "TMH_ChanDoanSoBo_ICD", "tai-mũi-họng"),
                   (r["rhm_benh"], "RHM_ChuaPhatHienBatThuong", "RHM_ChanDoanSoBo_ICD", "răng-hàm-mặt")]
        for cell, cb_cls, icd_cls, what in blocks:
            if not nfc(cell):
                continue
            if wb.is_no_finding(cell):
                if self.checkbox_state(cb_cls) is not True:
                    bad.append(f"{what}: ô 'chưa phát hiện bất thường' không lưu")
                continue
            missing = [c for c in wb.icd_codes(cell) if not self.icd_has(icd_cls, c)]
            if missing:
                bad.append(f"{what}: thiếu mã ICD {missing}")

        for cls, key, label in (("Mat_KhongKinh_MP", "mat_khong_kinh_mp", "thị lực không kính MP"),
                                ("Mat_KhongKinh_MT", "mat_khong_kinh_mt", "thị lực không kính MT"),
                                ("Mat_CoKinh_MP", "mat_co_kinh_mp", "thị lực có kính MP"),
                                ("Mat_CoKinh_MT", "mat_co_kinh_mt", "thị lực có kính MT")):
            want = wb.vision_score(r[key])
            got = self.field_value(cls) if want else None
            if want and got != want:
                bad.append(f"{label} lưu là {got!r}, cần {want!r}")

        for cls, key, label in (("TMH_TaiTrai_NoiThuong", "tai_trai_noi_thuong", "tai trái nói thường"),
                                ("TMH_TaiTrai_NoiTham", "tai_trai_noi_tham", "tai trái nói thầm"),
                                ("TMH_TaiPhai_NoiThuong", "tai_phai_noi_thuong", "tai phải nói thường"),
                                ("TMH_TaiPhai_NoiTham", "tai_phai_noi_tham", "tai phải nói thầm")):
            want = wb.number(r[key])
            got = self.field_value(cls) if want else None
            if want and got != want:
                bad.append(f"{label} lưu là {got!r}, cần {want!r}")

        bad += self.verify_teeth(r)
        return bad

    def verify_teeth(self, r: Dict) -> List[str]:
        """Confirm each decayed tooth kept its condition.

        The chart itself is no evidence: every tooth renders the same positional
        t<N>.png whatever condition is stored. The value only appears inside the
        tooth's own popup, so each listed tooth is reopened and read.
        """
        condition = medinet_tooth_condition(r["tinh_trang_rang"])
        teeth = wb.tooth_numbers(r["cac_rang_sau"])
        if not teeth or condition.lower() in ("bình thường", "binh thuong"):
            return []

        wrong = []
        for tooth in teeth:
            got = self.read_tooth_condition(tooth)
            if medinet_tooth_condition(got).casefold() != condition.casefold():
                wrong.append(f"{tooth}={got!r}")
        return [f"răng chưa lưu đúng {condition!r}: {', '.join(wrong)}"] if wrong else []

    def read_tooth_condition(self, tooth: str, timeout_s: int = 25) -> Optional[str]:
        """Open a tooth's popup, read its stored condition, close it again."""
        # Retry loop: iframe tooth selects may still be rendering
        iframe_retry_deadline = time.time() + 15
        while True:
            opened = self.js(f"""
                (function(){{
                    var frame = document.querySelector('iframe[src*="ksk_kham_rang_m2"]');
                    if (frame) {{
                        var doc = null;
                        try {{ doc = frame.contentDocument; }} catch (e) {{}}
                        if (!doc) return 'iframe-error:inaccessible';
                        var sel = doc.querySelector('select.tooth-select[data-tooth="' + {js_string(tooth)} + '"]');
                        if (!sel) {{
                            try {{
                                if (frame.contentWindow) {{
                                    frame.contentWindow.postMessage({{action: "INIT_DATA", payload: []}}, "*");
                                }}
                            }} catch(e) {{}}
                            sel = doc.querySelector('select.tooth-select[data-tooth="' + {js_string(tooth)} + '"]');
                        }}
                        if (!sel) return 'iframe-error:no-tooth';
                        var opt = sel.options[sel.selectedIndex];
                        return 'iframe-value:' + (opt ? opt.textContent.trim() : '');
                    }}
                    var teeth = Array.from(document.querySelectorAll('.tooth'))
                      .filter(window.__mx.live);
                    if (!teeth.length) return 'no-chart';
                    var t = teeth.find(function(d){{
                        var e = d.querySelector('.toothNumber');
                        return e && e.textContent.trim() === {js_string(tooth)}; }});
                    var img = t && t.querySelector('img');
                    if (!img) return 'no-tooth';
                    window.__mx.click(img);
                    return 'ok';
                }})()
            """)
            if isinstance(opened, str) and opened in ('iframe-error:no-tooth', 'iframe-error:inaccessible') and time.time() < iframe_retry_deadline:
                time.sleep(1.0)
                continue
            break
        if isinstance(opened, str) and opened.startswith("iframe-value:"):
            return opened.split(":", 1)[1]
        if isinstance(opened, str) and opened.startswith("iframe-error:"):
            return f"<{opened}>"
        if opened != "ok":
            return f"<{opened}>"
        if not self._wait(lambda: self.field_value("ViTriRang") == tooth, timeout_s):
            self.close_tooth_popup()
            return "<popup không mở>"
        value = self.field_value("TinhTrangId")
        self.close_tooth_popup()
        return value

    def verify_ket_luan(self, r: Dict) -> List[str]:
        bad = []
        followup = self.benh_tat_can_luu_y()
        if not (followup or "").strip():
            return ["không đọc được mục 2. Bệnh, tật cần lưu ý để đối chiếu"]
        healthy = followup.lower().strip(" .:;") in ("không có", "khong co")
        wanted = DE_NGHI_BINH_THUONG if healthy else DE_NGHI_NGUY_CO
        if not self.radio_checked("DeNghi", wanted):
            bad.append(f"mục 3. Đề nghị không giữ {wanted!r}")
        if not healthy:
            want_text = nfc(r["de_nghi"]).replace("\n", " ")
            got = self.field_text("KetLuan_DeNghi")
            # Rich-text fields collapse repeated spaces in HTML. Compare their
            # visible wording after the same whitespace normalization so a value
            # such as "Khám  TMH" is not reported missing after Medinet stores it
            # as "Khám TMH".
            want_compare = " ".join(want_text.split())
            got_compare = " ".join(got.split())
            if want_compare and want_compare not in got_compare:
                bad.append(f"ô Đề nghị (ghi rõ) lưu là {got!r}, cần {want_text!r}")
        return bad

    # --- record orchestration ----------------------------------------------

    def date_in_window(self, ddmmyyyy: str) -> bool:
        """True when a DD/MM/YYYY exam date falls inside the requested range.

        An unparseable date is treated as outside: the caller uses this to decide
        whether writing into a record is safe, and a date it cannot read is not a
        date it may act on.
        """
        def parse(v):
            try:
                return datetime.strptime(nfc(v).strip(), "%d/%m/%Y").date()
            except (ValueError, AttributeError):
                return None
        got, lo, hi = parse(ddmmyyyy), parse(self.exam_from), parse(self.exam_to)
        if not got or not lo or not hi:
            return False
        return lo <= got <= hi

    @staticmethod
    def _wait(condition, timeout_s: float, interval_s: float = 0.5) -> bool:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if condition():
                return True
            time.sleep(interval_s)
        return False

    # --- backend lookup ------------------------------------------------------
    # The M12 list report marks Ngày khám as a required filter, so the screen cannot
    # show a record that has no exam date -- and a child registered as "không đi học"
    # often has none. The stored procedure behind the report has no such requirement,
    # and the backend accepts the browser's own session cookie, so the same report can
    # be asked for one CCCD with no date at all. That is how those children are found.

    API_BASE = "https://be-qlskcd.medinet.org.vn/api/services/app"
    M12_REPORT_CODE = "KSKDK_DanhSach_KSK_M12"

    def auth_token(self) -> Optional[str]:
        """The Authorization header the app itself is using, caught by TOKEN_TAP_JS.

        Read fresh rather than cached: the tap re-arms on every page, and a token that
        has been rotated is worse than none at all.
        """
        self.js(TOKEN_TAP_JS)
        got = self.js("""
            (function(){
                var n = document.getElementById('__mxtok');
                return n && n.textContent ? n.textContent : '';
            })()
        """)
        return got or self._token

    def api(self, path: str, method: str = "GET", body=None, timeout_s: int = 30):
        """Call the Medinet backend from the signed-in tab and return the parsed JSON."""
        url = self.API_BASE + path
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        token = self.auth_token()
        if token:
            self._token = token
            headers["Authorization"] = token
        init = {"method": method, "credentials": "include", "headers": headers}
        if body is not None:
            init["body"] = json.dumps(body, ensure_ascii=False)
        self.js(
            "(function(){window.__mxApi=null;"
            f"fetch({js_string(url)},{json.dumps(init, ensure_ascii=False)})"
            ".then(function(r){return r.text().then(function(t){"
            "window.__mxApi={status:r.status, body:t};});})"
            ".catch(function(e){window.__mxApi={status:0, err:String(e)};});return 1;})()"
        )
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            time.sleep(0.5)
            res = self.js("window.__mxApi")
            if res:
                try:
                    return json.loads(res.get("body") or "")
                except (ValueError, TypeError):
                    return {"_status": res.get("status"), "_err": res.get("err")}
        return None

    def m12_report_id(self) -> Optional[Tuple[int, int]]:
        """(reportId, sessionSiteId) for the M12 list report, resolved once per run."""
        if getattr(self, "_m12_ids", None):
            return self._m12_ids
        site = self.api(f"/User/GetSessionSiteByViewCode?viewType=report"
                        f"&viewCode={self.M12_REPORT_CODE}")
        ssid = (((site or {}).get("result") or {}).get("data")) or 130
        got = self.api(f"/DRReport/GetIdByCode?code={self.M12_REPORT_CODE}&SessionSiteId={ssid}")
        rows = ((got or {}).get("result") or {}).get("data") or []
        if not rows or not rows[0].get("id"):
            return None
        self._m12_ids = (rows[0]["id"], ssid)
        return self._m12_ids

    def api_lookup(self, cccd: str) -> Optional[Dict]:
        """Find a record by CCCD through the backend, ignoring the exam-date filter."""
        ids = self.m12_report_id()
        if not ids:
            return None
        report_id, ssid = ids
        path = (f"/DRViewer/PostDataWithDataOutput?id={report_id}&SessionSiteId={ssid}"
                f"&UrlPage=%2Fapp%2Fmain%2Fdynamicreport%2Freport%2Fviewer-utility"
                f"%2F{self.M12_REPORT_CODE}&ispopup=false&istab=false")
        # "varible" is the backend's own spelling of the parameter field -- not a typo here.
        got = self.api(path, "POST", [{"varible": "KSKDK_DinhDanhCaNhan", "value": cccd}])
        rows = ((got or {}).get("result") or {}).get("data") or []
        for row in rows:
            if str(row.get("DinhDanhCaNhan") or "").strip() != cccd:
                continue
            if not row.get("phieukhamId") or not row.get("cdId"):
                continue
            return {"phieukhamId": str(row["phieukhamId"]), "cdId": str(row["cdId"]),
                    "name": row.get("HoTen"), "exam": row.get("NgayKham"),
                    "code": row.get("MaPhieu")}
        return None

    def find_record(self, cccd: str, attempts: int = 3) -> Tuple[str, Optional[Dict]]:
        """Look the student up in the M2 grid inside the requested exam-date window.

        Returns ('match', row) | ('empty', None) | ('unknown', None).

        The third answer matters more than it looks. A grid that never responds is not
        the same as a grid that says "no such child": treating the two alike is how a
        student who does have a record gets written off as missing and quietly skipped.
        Only 'empty' -- Medinet's own "Không có dữ liệu" -- means absent.
        """
        for attempt in range(1, attempts + 1):
            state, row = self.search_grid(cccd)
            if state in ("match", "empty"):
                return state, row
            print(f"      lưới chưa trả lời dứt khoát ({state}), thử lại {attempt}/{attempts}",
                  flush=True)
        return "unknown", None

    def search_grid(self, cccd: str, timeout_s: int = 40) -> Tuple[str, Optional[Dict]]:
        """One search. Reloads the grid so no stale result can be mistaken for this one."""
        self.goto(GRID_URL, None, 40)
        # A no-op location.assign (already on the grid) leaves the previous student's
        # result on screen, so force the page to rebuild every time.
        self.d.run_js("location.reload()")
        time.sleep(2.0)
        if not self._wait(lambda: bool(self.js(
                "!!document.querySelector('input[id$=\"_KSKDK_DinhDanhCaNhan\"]')")), 60):
            return "no-filters", None
        self.install_helpers()

        date_range = f"{self.exam_from} - {self.exam_to}"
        typed = self.js(f"""
            (function(){{
                var cc = document.querySelector('input[id$="_KSKDK_DinhDanhCaNhan"]');
                var dt = document.querySelector('input[id$="_KSKDK_NgayKham"]');
                var nm = document.querySelector('input[id$="_KSKDK_HoVaTen"]');
                if (!cc || !dt) return false;
                if (nm) window.__mx.type(nm, '');
                window.__mx.type(dt, {js_string(date_range)});
                window.__mx.type(cc, {js_string(cccd)});
                cc.dispatchEvent(new Event('blur', {{bubbles:true}}));
                return cc.value === {js_string(cccd)};
            }})()
        """)
        if not typed:
            return "no-filters", None

        if not self.run_search(cccd):
            return "no-xem", None

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            time.sleep(1.0)
            state = self.js(f"""
                (function(){{
                    var grid = Array.from(document.querySelectorAll('.dx-datagrid'))
                        .filter(window.__mx.live)
                        .find(function(g){{ return g.innerText.indexOf('ĐỊNH DANH CÁ NHÂN') >= 0; }});
                    if (!grid) return {{s:'no-grid'}};
                    var busy = Array.from(document.querySelectorAll(
                        '.dx-loadpanel .dx-overlay-content, .dx-loadindicator'))
                        .some(function(e){{ return e.offsetHeight > 0; }});
                    if (busy) return {{s:'busy'}};
                    var rows = Array.from(grid.querySelectorAll('.dx-data-row'));
                    for (var i = 0; i < rows.length; i++) {{
                        var cells = Array.from(rows[i].querySelectorAll('td'))
                            .map(function(td){{ return td.innerText.trim(); }});
                        if (cells.indexOf({js_string(cccd)}) >= 0) {{
                            return {{s:'match', name: cells[3], exam: cells[8], code: cells[7]}};
                        }}
                    }}
                    var nodata = grid.querySelector('.dx-datagrid-nodata');
                    var m = grid.innerText.match(/Có (\\d+) kết quả/);
                    var count = m ? parseInt(m[1], 10) : null;
                    if (count === 0 || (nodata && nodata.offsetHeight > 0)) return {{s:'empty'}};
                    // Rows on screen but not this child's: the filter has not landed yet,
                    // or worse, this is the previous student's result still showing.
                    return {{s: rows.length ? 'stale-rows' : 'no-rows', count: count}};
                }})()
            """) or {"s": "unknown"}
            if state.get("s") == "match":
                return "match", state
            if state.get("s") == "empty":
                return "empty", None

        return state.get("s", "unknown"), None

    def run_search(self, cccd: str, attempts: int = 4) -> bool:
        """Press 'Xem' and make sure the grid really re-queried.

        Two failure modes to close off. Clicking too soon -- while the grid is still
        loading and DevExtreme has the button disabled -- is swallowed silently. And
        this report restores the previous search's rows on load, so a swallowed click
        leaves the *last student's* record on screen, which reads as a confident wrong
        answer rather than an error. So: wait for the button, click, and require the
        grid's contents to actually change before believing the search ran.
        """
        for _ in range(attempts):
            self._wait(self.grid_idle, 30)
            before = self.grid_signature()
            clicked = self.js("""
                (function(){
                    var b = Array.from(document.querySelectorAll('.dx-button'))
                        .filter(window.__mx.live)
                        .filter(function(e){ return window.__mx.nfc(e.textContent) === 'Xem'; })
                        .find(function(e){ return !e.classList.contains('dx-state-disabled'); });
                    if (!b) return false;
                    window.__mx.click(b);
                    return true;
                })()
            """)
            if not clicked:
                time.sleep(1.5)
                continue
            if self._wait(lambda: self.grid_signature() != before, 20, 0.5):
                return True
            # The grid is unchanged. If it already holds exactly this child, the search
            # did run -- the result simply looks the same as what was there.
            if self.js(f"""
                (function(){{
                    var g = Array.from(document.querySelectorAll('.dx-datagrid'))
                        .filter(window.__mx.live)
                        .find(function(x){{ return x.innerText.indexOf('ĐỊNH DANH CÁ NHÂN') >= 0; }});
                    return !!g && g.innerText.indexOf({js_string(cccd)}) >= 0;
                }})()
            """):
                return True
        return False

    def grid_idle(self) -> bool:
        return not self.js("""
            (function(){
                return Array.from(document.querySelectorAll(
                    '.dx-loadpanel .dx-overlay-content, .dx-loadindicator'))
                  .some(function(e){ return e.offsetHeight > 0; });
            })()
        """)

    def grid_signature(self) -> str:
        """A cheap fingerprint of what the result grid is currently showing."""
        return str(self.js("""
            (function(){
                var g = Array.from(document.querySelectorAll('.dx-datagrid'))
                    .filter(window.__mx.live)
                    .find(function(x){ return x.innerText.indexOf('ĐỊNH DANH CÁ NHÂN') >= 0; });
                if (!g) return 'no-grid';
                return window.__mx.nfc(g.innerText).slice(0, 400);
            })()
        """))

    def open_record(self, cccd: str, timeout_s: int = 60) -> Optional[Dict]:
        """Click the row's edit pen and read the ids Medinet puts in the URL."""
        clicked = self.js(f"""
            (function(){{
                var grid = Array.from(document.querySelectorAll('.dx-datagrid'))
                    .filter(window.__mx.live)
                    .find(function(g){{ return g.innerText.indexOf('ĐỊNH DANH CÁ NHÂN') >= 0; }});
                if (!grid) return 'no-grid';
                var rows = Array.from(grid.querySelectorAll('.dx-data-row'));
                for (var i = 0; i < rows.length; i++) {{
                    if (rows[i].innerText.indexOf({js_string(cccd)}) < 0) continue;
                    var pen = rows[i].querySelector('i.fa-pen, .fa-pen');
                    if (!pen) return 'no-pen';
                    window.__mx.click(pen);
                    return 'ok';
                }}
                return 'row-not-found';
            }})()
        """)
        if clicked != "ok":
            return None

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            time.sleep(1.0)
            url = self.js("location.href") or ""
            if "phieukhamId=" in url and "KSKD18_TTHC" in url:
                ids = dict(part.split("=", 1) for part in url.split("?", 1)[1].split("&")
                           if "=" in part)
                if ids.get("phieukhamId") and ids.get("cdId"):
                    return {"phieukhamId": ids["phieukhamId"], "cdId": ids["cdId"]}
        return None

    def section_url(self, form: str, ids: Dict, sub_tab: Optional[int] = None) -> str:
        pid, cdid = ids["phieukhamId"], ids["cdId"]
        path = f"{NAV}/{form}"
        if sub_tab is not None:
            path = f"{path}/{sub_tab}"
        return f"{path}/{pid}?cdId={cdid}&phieukhamId={pid}&MauKham=mauphieukskd18"

    def open_by_ids(self, cccd: str, ids: Dict) -> Tuple[bool, str]:
        """Open a record straight from its ids and prove it is the right student.

        For a child filed as "không đi học" there is no exam date, so no list report
        will show them and there is no edit pen to click -- but the record is still
        reachable by URL if someone can supply the ids. Filling clinical data into the
        wrong child's record would be far worse than not filling it at all, so the
        CCCD on the loaded form is checked before anything is typed.
        """
        if not self.goto(self.section_url("dynamicform/viewer/KSKD18_TTHC", ids),
                         "DinhDanhCaNhan"):
            return False, "không mở được hồ sơ theo ID đã cho"
        got = self.field_value("DinhDanhCaNhan")
        if got != cccd:
            return False, f"hồ sơ mở ra có CCCD {got!r}, không phải {cccd!r} -- không nhập"
        return True, self.field_value("NgayKham") or ""

    def fill_missing_home_ward(self, ward: str) -> Tuple[bool, List[str]]:
        """Fill "Phường/Xã" of the home address when the record has none.

        Some administrative records were created without it -- typically a child whose
        address is in another province -- and it is required, so the form refuses to
        save anything at all, including the exam date. Only an empty field is touched:
        an address already on file is somebody's real record, not ours to correct.
        """
        current = self.field_value("DiaChiHienTai_XaPhuong") or ""
        if current.strip():
            return False, []
        if not self.d.select_searchable_dropdown(".DiaChiHienTai_XaPhuong", ward):
            return False, [f"không chọn được phường/xã {ward!r}"]
        print(f"      phường/xã nơi ở đã điền -> {ward}", flush=True)
        return True, []

    def ensure_exam_date(self, ids: Dict, wanted: str, force: bool = False,
                         home_ward: Optional[str] = None) -> Tuple[str, List[str]]:
        """Give a record its Ngày khám on the Thông tin hành chính form.

        A child filed as "không đi học" can end up with no exam date at all, and the
        M12 list report filters on that date -- so the record exists but no list will
        ever show it, and it cannot be found or edited through the normal screens.
        Writing the date is what makes it reachable again.

        An exam date that is already set is left alone unless force is given: it is
        somebody's real record of when they were seen, not a field to overwrite.
        """
        if not self.goto(self.section_url("dynamicform/viewer/KSKD18_TTHC", ids),
                         "DinhDanhCaNhan"):
            return "", ["không mở được Thông tin hành chính để đặt ngày khám"]

        current = self.field_value("NgayKham") or ""
        ward_filled, problems = (self.fill_missing_home_ward(home_ward)
                                 if home_ward else (False, []))
        if current == wanted and not ward_filled:
            return current, problems
        if current and current != wanted and not force:
            return current, problems + [
                f"hồ sơ đã có ngày khám {current!r}, giữ nguyên "
                f"(dùng --force-exam-date nếu thực sự muốn đổi)"]

        if current != wanted and not self.set_datebox("NgayKham", wanted):
            return current, problems + [f"không đặt được ngày khám {wanted}"]
        ok, messages = self.save("Lưu thay đổi")
        if not ok:
            return current, problems + [f"lưu ngày khám thất bại: {'; '.join(messages)}"]

        if not self.goto(self.section_url("dynamicform/viewer/KSKD18_TTHC", ids),
                         "DinhDanhCaNhan"):
            return wanted, ["đã lưu ngày khám nhưng không mở lại được để đối chiếu"]
        got = self.field_value("NgayKham") or ""
        if got != wanted:
            return got, [f"ngày khám sau lưu là {got!r}, cần {wanted!r}"]
        print(f"      ngày khám đã đặt -> {wanted}", flush=True)
        return got, []

    def process(self, r: Dict, ids: Optional[Dict] = None,
                set_exam_date: Optional[str] = None, force_date: bool = False,
                home_ward: Optional[str] = None) -> Dict:
        """Run one student end to end. Never creates a record."""
        cccd, name = r["cccd"], r["name"]
        result = {"cccd": cccd, "name": name, "stt": r["stt"], "row": r["row"],
                  "sections": {}, "problems": [], "status": "unknown"}

        if ids:
            ok, info = self.open_by_ids(cccd, ids)
            if not ok:
                result["status"] = "open_failed"
                result["problems"].append(info)
                return result
            result["ids"] = ids
            exam_date = info
            if set_exam_date:
                exam_date, date_problems = self.ensure_exam_date(
                    ids, set_exam_date, force_date, home_ward)
                result["problems"] += date_problems
            result["exam_date"] = exam_date
            if not exam_date:
                result["status"] = "no_exam_date"
                result["problems"].append(
                    "hồ sơ chưa có ngày khám -- dùng --exam-date để đặt trước khi nhập")
                return result
            return self.fill_sections(r, ids, exam_date, result)

        state, found = self.find_record(cccd)
        if state == "empty":
            # The screen cannot show a record with no exam date. Ask the backend before
            # writing the child off, or a child who does have a record gets skipped.
            via_api = self.api_lookup(cccd)
            if via_api:
                print(f"      lưới không có, tra qua API: phieukhamId={via_api['phieukhamId']}"
                      f" ngày khám={via_api['exam'] or 'trống'}", flush=True)
                # The API fallback exists for a child whose record carries NO exam date,
                # because the M12 screen cannot list one. A record that does carry a date
                # outside the requested window is a different thing entirely -- an older
                # round, usually a previous year -- and filling this year's examination
                # into it would overwrite another visit's record. Refuse it.
                if via_api["exam"] and not self.date_in_window(via_api["exam"]):
                    result["status"] = "khac_dot_kham"
                    result["problems"].append(
                        f"API tìm thấy hồ sơ ngày khám {via_api['exam']}, ngoài khoảng "
                        f"{self.exam_from} - {self.exam_to} -- gần như chắc chắn là phiếu "
                        f"của đợt khám khác, KHÔNG nhập để khỏi ghi đè hồ sơ cũ")
                    return result
                api_ids = {"phieukhamId": via_api["phieukhamId"], "cdId": via_api["cdId"]}
                ok, info = self.open_by_ids(cccd, api_ids)
                if not ok:
                    result["status"] = "open_failed"
                    result["problems"].append(info)
                    return result
                result["ids"] = api_ids
                exam_date = info
                if set_exam_date:
                    exam_date, date_problems = self.ensure_exam_date(
                        api_ids, set_exam_date, force_date, home_ward)
                    result["problems"] += date_problems
                result["exam_date"] = exam_date
                if not exam_date:
                    result["status"] = "no_exam_date"
                    result["problems"].append(
                        "hồ sơ chưa có ngày khám -- thêm --exam-date để đặt trước khi nhập")
                    return result
                return self.fill_sections(r, api_ids, exam_date, result)

            result["status"] = "not_found"
            result["problems"].append(
                f"không tìm thấy CCCD trong khoảng khám {self.exam_from} - {self.exam_to} "
                f"(tra cả qua API cũng không có)")
            return result
        if state != "match" or not found:
            # Not the same thing as absent: the grid never gave a usable answer, so
            # this student still has to be looked at rather than written off.
            result["status"] = "search_failed"
            result["problems"].append(
                f"lưới không trả lời được khi tìm CCCD ({state}) -- cần chạy lại em này")
            return result

        result["medinet_name"] = found.get("name")
        result["exam_date"] = found.get("exam")
        result["ma_phieu"] = found.get("code")
        exam_date = found.get("exam") or ""

        ids = self.open_record(cccd)
        if not ids:
            result["status"] = "open_failed"
            result["problems"].append("không mở được hồ sơ từ lưới")
            return result
        result["ids"] = ids
        if set_exam_date:
            exam_date, date_problems = self.ensure_exam_date(
                ids, set_exam_date, force_date, home_ward)
            result["problems"] += date_problems
            result["exam_date"] = exam_date
        if not exam_date:
            # Without a date there is nothing to stamp the tâm thần evaluations with,
            # and filling the rest would leave the record half-done and hard to spot.
            result["status"] = "no_exam_date"
            result["problems"].append(
                "không đọc được ngày khám của hồ sơ -- chạy lại em này")
            return result
        return self.fill_sections(r, ids, exam_date, result)

    def fill_sections(self, r: Dict, ids: Dict, exam_date: str, result: Dict) -> Dict:
        """Fill and save the available clinical sections of an already-open record."""
        self._current_ids = ids  # stored for fill_teeth iframe-reload fallback
        # Kết luận runs last on purpose: its "2. Bệnh, tật cần lưu ý, theo dõi" box is
        # computed by Medinet from the diagnoses already stored, so it only shows the
        # right thing once Khám lâm sàng has been saved and the page reloaded.
        autism_title = "Đánh giá tâm thần - Phổ tự kỷ"
        plan = [
            ("Tiền sử bản thân", FORM_TIEN_SU, None, "TS_BanThan_SanKhoa",
             lambda: self.fill_tien_su(r), "Lưu thay đổi",
             lambda: self.verify_tien_su(r, exam_date)),
            ("Đánh giá tâm thần - Giảm chú ý/Tăng động", FORM_TAM_THAN, 1,
             "DanhGiaTamThan_ChiTiet",
             lambda: self.fill_tam_than(r, r["adhd"], exam_date), "Lưu",
             lambda: self.verify_tam_than(r["adhd"], exam_date)),
        ]
        if r.get("autism_available", True):
            plan.append((autism_title, FORM_TAM_THAN, 2,
             "DanhGiaTamThan_ChiTiet",
             lambda: self.fill_tam_than(r, r["autism"], exam_date), "Lưu",
             lambda: self.verify_tam_than(r["autism"], exam_date)))
        else:
            # A shortened source workbook has no autism answers at all. Leave the
            # existing Medinet tab untouched rather than inventing medical data or
            # overwriting a prior assessment with an empty one.
            result["sections"][autism_title] = "bỏ qua (file không có dữ liệu)"
        plan.extend([
            ("Khám lâm sàng", FORM_LAM_SANG, None, "TuanHoan_ChuaPhatHienBatThuong",
             lambda: self.fill_lam_sang(r), "Lưu thay đổi",
             lambda: self.verify_lam_sang(r)),
            ("Kết luận", FORM_KET_LUAN, None, "DeNghi",
             lambda: self.fill_ket_luan(r), "Lưu thay đổi",
             lambda: self.verify_ket_luan(r)),
        ])

        for title, form, sub_tab, ready, fill, save_label, verify in plan:
            print(f"    - {title} ...", flush=True)
            url = self.section_url(form, ids, sub_tab)
            if not self.goto(url, ready):
                result["sections"][title] = "không mở được"
                result["problems"].append(f"{title}: không mở được form")
                continue

            problems = fill() or []
            ok, messages = self.save(save_label)

            if not ok and self.dry_run:
                result["sections"][title] = f"lưu thất bại: {'; '.join(messages)}"
                result["problems"] += [f"{title}: {p}" for p in problems]
                result["problems"].append(f"{title}: {'; '.join(messages)}")
                print(f"      {result['sections'][title]}", flush=True)
                continue

            if self.dry_run:
                result["sections"][title] = "đã điền (dry-run)"
            else:
                # Reload and read it back: a save that did nothing looks identical to
                # one that worked until the stored values are seen again. That cuts both
                # ways -- a save that worked also looks like one that failed, because the
                # form rebinds to an empty state afterwards and its required fields start
                # complaining again. So the complaints only get believed if the reload
                # shows the data really is missing. Dropping this step is what turned a
                # working Tiền sử save into "Vui lòng nhập chiều cao (cm)": the save-time
                # message became the only judge, and it lies in both directions.
                if not self.goto(url, ready):
                    result["sections"][title] = "đã lưu (không mở lại được để đối chiếu)"
                    if not ok:
                        result["sections"][title] = f"lưu thất bại: {'; '.join(messages)}"
                        result["problems"].append(f"{title}: {'; '.join(messages)}")
                else:
                    left = verify() or []
                    problems += left
                    if left and not ok:
                        problems.append("báo lỗi khi lưu: " + "; ".join(messages))
                    # Notes describe the workbook, not a failed entry, so they must not
                    # hold a finished section open.
                    blocking = [p for p in problems if not p.startswith(NOTE_PREFIX)]
                    result["sections"][title] = "đã lưu" if not blocking else "lưu thiếu"

            if problems:
                result["problems"] += [f"{title}: {p}" for p in problems]
            print(f"      {result['sections'][title]}", flush=True)

        good = sum(1 for v in result["sections"].values()
                   if v in ("đã lưu", "đã điền (dry-run)"))
        result["status"] = ("done" if good == len(plan)
                            else "partial" if good else "failed")
        return result


def parse_args() -> argparse.Namespace:
    today = datetime.now().strftime("%d/%m/%Y")
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--file", required=True, help="Đường dẫn file Excel KSK")
    p.add_argument("--from", dest="exam_from", default="01/07/2026",
                   help="Ngày khám từ (DD/MM/YYYY)")
    p.add_argument("--to", dest="exam_to", default=today,
                   help="Ngày khám đến (DD/MM/YYYY), mặc định hôm nay")
    p.add_argument("--limit", type=int, default=None, help="Chỉ xử lý N em đầu tiên")
    p.add_argument("--start-at", type=int, default=1, help="Bắt đầu từ em thứ N")
    p.add_argument("--only-cccd", default=None, help="Chỉ xử lý đúng một CCCD")
    p.add_argument("--record-url", default=None,
                   help="Dán URL hồ sơ (chứa phieukhamId và cdId) để nhập thẳng, "
                        "bỏ qua bước tìm trên lưới. Dùng cho em không có ngày khám "
                        "nên danh sách M12 không liệt kê. Phải kèm --only-cccd.")
    p.add_argument("--exam-date", default=None,
                   help="Ghi Ngày khám (DD/MM/YYYY) vào hồ sơ nếu đang để trống. "
                        "Cần cho em 'không đi học': không có ngày khám thì danh sách "
                        "M12 không liệt kê nên không tìm và sửa được.")
    p.add_argument("--xa-phuong", dest="home_ward", default=None,
                   help="Điền Phường/Xã của địa chỉ nơi ở nếu hồ sơ đang để trống. "
                        "Ô này bắt buộc nên thiếu nó là form không lưu được gì cả, "
                        "kể cả ngày khám. Ô đã có sẵn thì giữ nguyên.")
    p.add_argument("--force-exam-date", action="store_true",
                   help="Ghi đè cả khi hồ sơ đã có ngày khám khác (mặc định: giữ nguyên)")
    p.add_argument("--separate-profile", action="store_true",
                   help="Dùng cửa sổ Chrome riêng biệt qua Playwright (không bao giờ cướp focus)")
    p.add_argument("--hide-browser", action="store_true", default=True,
                   help="Ẩn cửa sổ Chrome xuống nền để không bao giờ chiếm focus hay chuột")
    p.add_argument("--no-hide-browser", dest="hide_browser", action="store_false",
                   help="Không ẩn cửa sổ Chrome")
    p.add_argument("--dry-run", action="store_true", help="Điền nhưng không bấm lưu")
    p.add_argument("--check-file", action="store_true",
                   help="Chỉ đọc file Excel và in ra, không mở trình duyệt")
    return p.parse_args()


def ids_from_url(url: str) -> Dict:
    """Pull phieukhamId and cdId out of a Medinet record URL."""
    query = url.split("?", 1)[1] if "?" in url else ""
    parts = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
    ids = {k: parts.get(k) for k in ("phieukhamId", "cdId")}
    missing = [k for k, v in ids.items() if not v]
    if missing:
        raise ValueError(f"URL thiếu {', '.join(missing)}: {url}")
    return ids


def print_record(r: Dict) -> None:
    codes = {k: wb.icd_codes(r[k]) for k in
             ("tuan_hoan", "ho_hap", "tieu_hoa", "than_tiet_nieu", "than_kinh",
              "tam_than", "mat_benh", "tmh_benh", "rhm_benh")}
    codes = {k: v for k, v in codes.items() if v}
    print(f"  {r['stt']:>3}. {r['cccd']}  {r['name']}")
    print(f"       thể lực: cao {r['chieu_cao']} nặng {r['can_nang']} mạch {r['mach']} "
          f"HA {r['huyet_ap_tt']}/{r['huyet_ap_ttr']} thở {r['nhip_tho']}")
    print(f"       tâm thần: {len(r['adhd'])} câu ADHD, {len(r['autism'])} câu tự kỷ")
    print(f"       chẩn đoán: {codes or 'không có'}")
    teeth = wb.tooth_numbers(r["cac_rang_sau"])
    print(f"       răng: {nfc(r['tinh_trang_rang']) or '-'}"
          + (f" {teeth}" if teeth else ""))
    print(f"       đề nghị: {nfc(r['de_nghi']) or '-'}")


def main() -> None:
    args = parse_args()
    records = wb.load_records(args.file)
    print(f"Đọc {len(records)} hồ sơ từ {os.path.basename(args.file)}")

    if args.only_cccd:
        records = [r for r in records if r["cccd"] == args.only_cccd]
    else:
        records = records[max(0, args.start_at - 1):]
    if args.limit:
        records = records[:args.limit]

    if args.check_file:
        for r in records:
            print_record(r)
        return

    ids = None
    if args.record_url:
        if not args.only_cccd:
            raise SystemExit("--record-url phải đi kèm --only-cccd để biết nhập cho em nào")
        if len(records) != 1:
            raise SystemExit(f"--only-cccd {args.only_cccd} khớp {len(records)} dòng, cần đúng 1")
        ids = ids_from_url(args.record_url)
        print(f"Mở thẳng hồ sơ theo URL: {ids}")

    print(f"Khoảng ngày khám: {args.exam_from} - {args.exam_to}")
    print(f"Sẽ xử lý {len(records)} hồ sơ" + ("  [DRY RUN]" if args.dry_run else ""))

    if args.separate_profile:
        from playwright.sync_api import sync_playwright
        from app.importer import CHROME_PROFILE_DIR, Importer
        os.makedirs(CHROME_PROFILE_DIR, exist_ok=True)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                CHROME_PROFILE_DIR,
                headless=False,
                channel="chrome",
                viewport=None,
            )
            page = context.pages[0] if context.pages else context.new_page()
            driver = Importer(page, age_group="M2")
            if not driver.wait_for_login():
                print("Hết thời gian chờ đăng nhập trên Chrome.")
                return
            filler = ClinicalFiller(driver, args.exam_from, args.exam_to, dry_run=args.dry_run)
            _run_batch(filler, records, ids, args)
        return

    if args.hide_browser:
        subprocess.run(["osascript", "-e", 'tell application "System Events" to set visible of process "Google Chrome" to false'], capture_output=True)

    driver = AppleScriptImporter(dry_run=args.dry_run, age_group="M2")
    filler = ClinicalFiller(driver, args.exam_from, args.exam_to, dry_run=args.dry_run)
    _run_batch(filler, records, ids, args)


def _run_batch(filler: ClinicalFiller, records: List[Dict], ids: Optional[Dict], args: argparse.Namespace) -> None:
    results, started = [], time.time()
    for i, r in enumerate(records, 1):
        print(f"\n[{i}/{len(records)}] TT{r['stt']} {r['name']} ({r['cccd']})", flush=True)
        t0 = time.time()
        try:
            res = filler.process(r, ids=ids, set_exam_date=args.exam_date,
                                 force_date=args.force_exam_date,
                                 home_ward=args.home_ward)
        except Exception as exc:  # keep the batch alive; the row is logged as failed
            res = {"cccd": r["cccd"], "name": r["name"], "stt": r["stt"], "row": r["row"],
                   "status": "error", "sections": {}, "problems": [f"lỗi: {exc!r}"]}
        res["seconds"] = round(time.time() - t0, 1)
        results.append(res)
        print(f"  => {res['status']} ({res['seconds']}s)", flush=True)
        for p in res["problems"]:
            print(f"     ! {p}", flush=True)
        write_results(results, args)

    summarise(results, time.time() - started)


def write_results(results: List[Dict], args: argparse.Namespace) -> None:
    payload = {
        "file": args.file,
        "exam_from": args.exam_from,
        "exam_to": args.exam_to,
        "dry_run": args.dry_run,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "done": [r for r in results if r["status"] == "done"],
        "partial": [r for r in results if r["status"] == "partial"],
        "not_found": [r for r in results if r["status"] == "not_found"],
        "search_failed": [r for r in results if r["status"] == "search_failed"],
        "no_exam_date": [r for r in results if r["status"] == "no_exam_date"],
        "failed": [r for r in results if r["status"] in ("failed", "error", "open_failed")],
    }
    with open(RESULTS_FILE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def summarise(results: List[Dict], seconds: float) -> None:
    buckets = {}
    for r in results:
        buckets.setdefault(r["status"], []).append(r)
    print("\n" + "=" * 64)
    print(f"Tổng: {len(results)} hồ sơ trong {seconds / 60:.1f} phút")
    for status, label in (("done", "Hoàn tất cả 4 phần"),
                          ("partial", "Lưu được một phần"),
                          ("not_found", "Không tìm thấy CCCD (đã bỏ qua)"),
                          ("search_failed", "LƯỚI KHÔNG TRẢ LỜI -- PHẢI CHẠY LẠI"),
                          ("no_exam_date", "Hồ sơ chưa có ngày khám"),
                          ("failed", "Thất bại"),
                          ("open_failed", "Không mở được hồ sơ"),
                          ("error", "Lỗi ngoại lệ")):
        rows = buckets.get(status, [])
        if not rows:
            continue
        print(f"\n{label}: {len(rows)}")
        for r in rows:
            print(f"  - TT{r.get('stt', '?')} {r['name']} ({r['cccd']})")
            for p in r["problems"]:
                print(f"      {p}")
    print(f"\nChi tiết đã ghi vào {RESULTS_FILE}")


if __name__ == "__main__":
    sys.exit(main())
