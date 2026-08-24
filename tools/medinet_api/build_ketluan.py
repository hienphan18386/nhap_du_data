"""Kết luận: the "3. Đề nghị" choice plus its free-text box.

Sections 1 and 2 of this form (tình trạng sức khoẻ, bệnh tật cần lưu ý) are read-only:
Medinet derives them from the diagnoses stored in Khám lâm sàng, so the workbook's
ket_luan_icd column has nowhere to go and is deliberately not written.

Which choice applies follows from the same diagnoses: a child with any finding is
"có yếu tố nguy cơ", one with none is "bình thường". Verified against records Medinet
itself filled -- healthy children carry 5172 with an empty box, children with findings
carry 5173 and the Đề nghị text.
"""
import sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '/Users/hienphantrong/Desktop/Project/AI_PROJECT/NHAP_DATA_LONG')
from app import ksk_workbook as wb

BINH_THUONG = 5172
CO_NGUY_CO = 5173
BLOCKS = ('mat_benh', 'tmh_benh', 'rhm_benh', 'tam_than',
          'tuan_hoan', 'ho_hap', 'tieu_hoa', 'than_tiet_nieu', 'than_kinh')


def has_finding(r):
    for f in BLOCKS:
        t = wb.nfc(r.get(f) or '')
        if t and not wb.is_no_finding(t):
            return True
    return False


def advice(r):
    """The workbook's own recommendation, or "" when it says none."""
    from app.clinical import is_no
    text = wb.nfc(r.get('de_nghi') or '')
    return "" if (not text or is_no(text)) else text


def want(r):
    """(DeNghi id, KetLuan_DeNghi html) the record should end up with.

    A finding in a clinical block is not the only thing that makes a child one to watch:
    the examiner may record a real recommendation ("béo phì, tăng vận động") with the
    condition itself written in the free-text Khám lâm sàng khác column, which Medinet
    does not treat as a diagnosis. Judging by the clinical blocks alone concluded
    "bình thường" for 38 students of TH Tăng Bạt Hổ who plainly were not, and left their
    recommendation unwritten. Either signal is enough.
    """
    text = advice(r)
    if not has_finding(r) and not text:
        return BINH_THUONG, None
    return CO_NGUY_CO, (f"<p>{text}</p>" if text else None)


def build(r, current):
    out = dict(current)
    out.pop('__label_action_code', None)
    dn, html = want(r)
    out['DeNghi'] = dn
    if html is not None:
        out['KetLuan_DeNghi'] = html
    return out, []


def strip_html(s):
    import re
    return wb.nfc(re.sub(r'<[^>]+>', ' ', str(s or ''))).strip()


def check(r, stored):
    bad = []
    dn, html = want(r)
    if int(stored.get('DeNghi') or 0) != dn:
        bad.append(f"Đề nghị: lưu {stored.get('DeNghi')}, cần {dn}")
    if html is not None:
        got, wantt = strip_html(stored.get('KetLuan_DeNghi')), strip_html(html)
        if got.lower() != wantt.lower():
            bad.append(f"ô Đề nghị (ghi rõ): lưu {got!r}, cần {wantt!r}")
    return bad
