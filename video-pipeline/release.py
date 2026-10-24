"""Daily: move clips whose lock expired back to their stage folder; mark ledger rows MO."""
import datetime as dt
import json
import os

import drive

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))


def main():
    today = dt.date.today().isoformat()
    rows = drive.read_ledger(CFG["drive"]["ledger_sheet"])
    freed = 0
    for r in rows:
        if r.get("trang_thai") == "KHOA" and r.get("ngay_mo_lai", "9999") <= today:
            drive.move(r["file_id"], r["folder_goc_id"])
            r["trang_thai"] = "MO"
            freed += 1
    if freed:
        drive.write_ledger(CFG["drive"]["ledger_sheet"], rows)
    for f in drive.list_children(CFG["drive"]["dang_khoa"], folders_only=True):
        if f["name"].startswith("Mở lại ") and f["name"][7:] <= today and not drive.list_children(f["id"]):
            drive.trash(f["id"])
    print(f"{today}: mở khoá {freed} clip")


if __name__ == "__main__":
    main()
