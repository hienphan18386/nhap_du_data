"""Read-only live API probe for record ambiguity, forms, ICDs and tooth statuses."""
import argparse
import json
import pathlib
import sys
import unicodedata
import warnings

warnings.filterwarnings("ignore")
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app import ksk_workbook as wb
import build_tamthan as mental
import check_tamthan as mental_check
import medapi


def fold(value):
    text = unicodedata.normalize("NFKD", wb.nfc(value)).lower()
    return " ".join("".join(ch for ch in text if not unicodedata.combining(ch)).split())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("file")
    p.add_argument("--stt", type=int, action="append", default=[])
    p.add_argument("--icd", action="append", default=[])
    args = p.parse_args()

    records = {int(r["stt"]): r for r in wb.load_records(args.file)}
    result = {"records": [], "icd": {}}
    for stt in args.stt:
        r = records[stt]
        candidates = medapi.find_records(r["cccd"])
        item = {"stt": stt, "candidate_count": len(candidates),
                "candidates": []}
        for who in candidates:
            pid, cd = who["phieukhamId"], who["cdId"]
            stored = medapi.read("lam_sang", pid, cd)
            tooth_map = {}
            try:
                chart = json.loads(stored.get("KhamRangJSON") or "[]")
                tooth_map = {str(x.get("statusName")): x.get("statusId") for x in chart
                             if isinstance(x, dict) and x.get("statusName")}
            except (TypeError, ValueError):
                pass
            tabs = {}
            for tab in ("adhd", "autism"):
                cfg = mental.TABS[tab]
                rows = mental_check.read_rows(pid, cd, cfg["code"], cfg["form_id"])
                head = mental.read_head(cfg["form_id"], cfg["code"], pid, cd)
                tabs[tab] = {"question_rows": len(rows), "header_id": head.get("ID"),
                             "evaluation_date": head.get("NgayDanhGia")}
            item["candidates"].append({
                "name_matches": fold(who.get("name")) == fold(r.get("name")),
                "exam": who.get("exam"), "mental": tabs, "tooth_statuses": tooth_map})
        result["records"].append(item)

    for code in args.icd:
        response = medapi._curl(
            f"{medapi.BASE}/DRReportService/HF_ExecuteServiceWithParam"
            f"?serviceId=1000291&SessionSiteId=130",
            [{"Varible": "SearchValue", "Value": code}])
        data = ((response.get("result") or {}).get("data") or [])
        result["icd"][code] = [
            {"Id": row.get("Id"), "Name": row.get("Name")} for row in data[:10]]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
