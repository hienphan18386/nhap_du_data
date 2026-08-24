"""Direct Medinet API access: read a record, write it, read it back.

The UI path drives DevExtreme widgets and loses data to races -- an ICD drop-down
that never opened, a tooth chart that saved "Bình thường". The same records are
reachable through the API the UI itself calls, where a value is just a value.

Field names are identical to the CSS classes app/clinical.py already uses
(TheLuc_ChieuCao, Mat_ChanDoanSoBo_ICD, ...), so the mapping the project already
knows carries over unchanged.
"""
import json, subprocess, pathlib, time

BASE = "https://be-qlskcd.medinet.org.vn/api/services/app"
HERE = pathlib.Path(__file__).parent

SECTIONS = {
    "lam_sang": dict(get="KSKD18_ThongTinKham_Get", set="KSKD18_ThongTinKham_Set",
                     labelactionId=1001333, guid_field="KSKD18_ThongTinKham_guid"),
    "tien_su":  dict(get="KSKD18_TTHC_TienSu_Get", set="KSKD18_TTHC_TienSu_Set",
                     labelactionId=1001330, guid_field="KSKD18_TTHC_TienSu_guid"),
    "ket_luan": dict(get="KSKDK_KetLuanKham_Get", set="KSKDK_KetLuanKham_Set",
                     labelactionId=1001336, guid_field="KSKD18_KetLuanKham_guid"),
}


def token() -> str:
    return (HERE / "token.txt").read_text().strip()


class Unauthorized(Exception):
    """The session token is no longer accepted.

    This must never be allowed to look like an empty result. The backend answers an
    expired token with a normal 200 whose body says "Current user did not login",
    so a caller that only checks for rows reads it as "this child has no record" and
    writes off every student in the run. Raising here keeps the two apart.
    """


def _check_auth(r):
    if isinstance(r, dict) and r.get("unAuthorizedRequest"):
        raise Unauthorized((r.get("error") or {}).get("message") or "token het han")
    return r


def refresh_token():
    """Re-capture the app's own Authorization header from the signed-in tab."""
    import runjs
    tap = pathlib.Path(__file__).parent / "token_tap.js"
    runjs.run_js(tap.read_text())
    # any API call from the page re-arms the header
    runjs.run_js("(function(){location.reload(); return 1;})()")
    time.sleep(16)
    runjs.run_js(tap.read_text())
    time.sleep(4)
    tok = runjs.run_js("(function(){var n=document.getElementById('__mxtok');"
                       "return n?n.textContent:'';})()")
    if tok and tok.startswith("Bearer "):
        (pathlib.Path(__file__).parent / "token.txt").write_text(tok)
        return True
    return False


# The headers the app itself sends. SessionSiteId as a *header* is load-bearing:
# FormViewer/FormToDataBaseUpdate answers "Object reference not set to an instance of
# an object." without it, and it does so even when the exact body the browser just sent
# successfully is replayed -- which made the failure look like a body problem for a
# long time. Passing SessionSiteId only in the query string is not enough.
APP_HEADERS = {"Content-Type": "application/json", "Accept": "text/plain",
               "X-Requested-With": "XMLHttpRequest", "SessionSiteId": "130",
               "displaymode": "0"}


def _headers():
    h = ["-H", "Authorization: " + token()]
    for k, v in APP_HEADERS.items():
        h += ["-H", f"{k}: {v}"]
    return h


def _curl(url, body):
    p = subprocess.run(
        ["curl", "-s", "-m", "90", "-X", "POST", url] + _headers()
        + ["-d", json.dumps(body, ensure_ascii=False)],
        capture_output=True, text=True)
    try:
        return _check_auth(json.loads(p.stdout))
    except json.JSONDecodeError:
        return {"_raw": p.stdout[:400]}


def read(section: str, pid: str, cd: str) -> dict:
    """Current stored values for one section of one record."""
    s = SECTIONS[section]
    r = _curl(f"{BASE}/DRViewer/ExecuteStoreWithParamAndDatasource"
              f"?dataSourceId=97&store={s['get']}",
              [{"Varible": "phieukhamId", "Value": str(pid)},
               {"Varible": "cdId", "Value": str(cd)}])
    res = r.get("result")
    rows = res if isinstance(res, list) else (res or {}).get("data") or []
    return rows[0] if rows else {}


def write(section: str, pid: str, cd: str, values: dict) -> dict:
    """Send the whole field set for a section. Returns the API's own verdict."""
    s = SECTIONS[section]
    body = [{"Varible": k, "Value": v} for k, v in values.items()]
    r = _curl(f"{BASE}/DRViewerUtility/ActionWithParamIdAndReturnOutput"
              f"?Id={pid}&StoreName={s['set']}&dataSrcId=96"
              f"&labelactionId={s['labelactionId']}", body)
    res = r.get("result") or {}
    return {"ok": bool(r.get("success")) and bool(res.get("isSucceeded")),
            "message": res.get("message"), "error": r.get("error")}


def icd_id(code: str):
    table = json.loads((HERE / "icd_map.json").read_text())
    return table.get(code)


M12_CODE = "KSKDK_DanhSach_KSK_M12"


def _get(path):
    p = subprocess.run(["curl", "-s", "-m", "60", BASE + path] + _headers(),
                       capture_output=True, text=True)
    try:
        return _check_auth(json.loads(p.stdout))
    except json.JSONDecodeError:
        return {}


_M12 = {}


def m12_ids():
    """(reportId, sessionSiteId) for the M12 list report."""
    if _M12:
        return _M12["v"]
    site = _get(f"/User/GetSessionSiteByViewCode?viewType=report&viewCode={M12_CODE}")
    ssid = ((site.get("result") or {}).get("data")) or 130
    got = _get(f"/DRReport/GetIdByCode?code={M12_CODE}&SessionSiteId={ssid}")
    rows = ((got.get("result") or {}).get("data")) or []
    _M12["v"] = (rows[0]["id"], ssid) if rows and rows[0].get("id") else None
    return _M12["v"]


def find_records(cccd: str):
    """All phieukhamId/cdId candidates for one CCCD, with no date filter.

    The M12 screen makes Ngày khám a required filter, so a record without one cannot be
    listed there; the stored procedure behind it has no such rule.
    """
    ids = m12_ids()
    if not ids:
        return []
    rid, ssid = ids
    got = _curl(f"{BASE}/DRViewer/PostDataWithDataOutput?id={rid}&SessionSiteId={ssid}",
                [{"varible": "KSKDK_DinhDanhCaNhan", "value": str(cccd)}])
    rows = ((got or {}).get("result") or {}).get("data") or []
    out = []
    for row in rows:
        if str(row.get("DinhDanhCaNhan") or "").strip() != str(cccd):
            continue
        if not row.get("phieukhamId") or not row.get("cdId"):
            continue
        out.append({"phieukhamId": str(row["phieukhamId"]), "cdId": str(row["cdId"]),
                    "name": row.get("HoTen"), "exam": row.get("NgayKham")})
    return out


def find_record(cccd: str):
    """First matching record, retained for compatibility with the older runners."""
    rows = find_records(cccd)
    return rows[0] if rows else None


FORM_IDS = {"tien_su": 1000103, "lam_sang": 1000104, "ket_luan": 1000105}


def read_form(form_id: int, pid: str, cd: str) -> dict:
    """Stored values for a dynamic form.

    The "..._Get" store is not a reader for every section -- for Tiền sử it is the
    formula trigger that recomputes BMI, and it answers with an empty template. The
    form viewer's own endpoint returns what is actually stored.
    """
    r = _curl(f"{BASE}/FormViewer/FormViewerDataByRecord"
              f"?form_id={form_id}&SessionSiteId=130&record_id={pid}",
              [{"Varible": "phieukhamId", "Value": str(pid)},
               {"Varible": "cdId", "Value": str(cd)},
               {"Varible": "recordid", "Value": str(pid)}])
    rows = (((r or {}).get("result") or {}).get("data") or {}).get("formData") or []
    return rows[0] if rows else {}
