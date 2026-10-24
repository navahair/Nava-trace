"""One video, end to end:  plan.json -> HeyGen -> pick unused factory clips -> edit -> Drive.

  python run.py plans/NH-20261025-HG1.json            # full run
  python run.py plan.json --avatar my_heygen.mp4      # skip HeyGen, use a rendered avatar file
  python run.py plan.json --local-broll DIR --no-drive  # offline test render

Clips used are written to the ledger sheet and moved to 3_ĐANG KHOÁ/Mở lại <date>
for `cooldown_days`; release.py moves them back when the date comes.
"""
import argparse
import datetime as dt
import glob
import json
import math
import os
import random
import subprocess

import edit
from align import duration

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
MAX_PIECE = 3.6   # longest single cutaway, seconds
MIN_PIECE = 1.4


def full_text(plan):
    return " ".join(s["text"].strip() for s in plan["segments"])


def get_avatar(plan, work, given):
    if given:
        return given
    import heygen
    dest = os.path.join(work, "avatar.mp4")
    state = os.path.join(work, "heygen.json")
    if os.path.exists(dest):
        return dest
    vid = json.load(open(state))["video_id"] if os.path.exists(state) else None
    if not vid:
        h = CFG["heygen"]
        vid = heygen.generate(full_text(plan), h["avatar_name"], h["voice_name"], h["width"], h["height"],
                              h.get("voice_speed", 1.0), title=plan["id"])
        json.dump({"video_id": vid}, open(state, "w"))
        print("HeyGen video_id:", vid)
    info = heygen.wait(vid)
    return heygen.download(info["video_url"], dest)


def locked_ids(rows, today):
    return {r["file_id"] for r in rows if r.get("trang_thai") == "KHOA" and r.get("ngay_mo_lai", "") > today}


def candidate_stages(seg):
    b = seg["broll"]
    order = [b["stage"]] + b.get("alt", []) + CFG["fallback_stages"]
    seen = []
    for s in order:
        if s not in seen:
            seen.append(s)
    return seen


def pick_pieces(plan, prep, pool, work):
    """pool(stage) -> list of clip dicts {id,name,path?,dur,stage}. Returns timeline pieces + used clips."""
    pieces, used, notes = [], {}, []
    for i, seg in enumerate(plan["segments"]):
        if not seg.get("broll"):
            continue
        a, b = prep["windows"][i]
        span = b - a
        if span < MIN_PIECE:
            continue
        n = max(1, math.ceil(span / MAX_PIECE))
        d = span / n
        for p in range(n):
            clip = None
            for st in candidate_stages(seg):
                for c in pool(st):
                    if c["id"] not in used and (c.get("dur") or 0) >= d + 0.4:
                        clip = c
                        break
                if clip:
                    break
            if not clip:
                notes.append(f"seg {i}: hết clip phù hợp cho công đoạn {seg['broll']['stage']} — giữ avatar")
                break
            used[clip["id"]] = clip
            cd = clip["dur"]
            src = min(max(0.3, (cd - d) * 0.35), cd - d - 0.1)
            pieces.append({"path": clip["path"], "src_start": src, "at": a + p * d, "dur": d,
                           "clip_id": clip["id"], "stage": clip["stage"], "seg": i})
    return pieces, used, notes


def contact_sheet(pieces, out):
    if not pieces:
        return None
    frames = []
    for k, p in enumerate(pieces):
        f = out + f".{k}.jpg"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{p['src_start'] + p['dur'] / 2:.2f}", "-i", p["path"],
                        "-frames:v", "1", "-vf", "scale=270:480:force_original_aspect_ratio=increase,crop=270:480", f],
                       check=True)
        frames.append(f)
    cols = min(6, len(frames))
    rows = math.ceil(len(frames) / cols)
    inputs = sum((["-i", f] for f in frames), [])
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex",
                    "".join(f"[{i}:v]" for i in range(len(frames))) +
                    f"concat=n={len(frames)}:v=1:a=0,tile={cols}x{rows}", "-frames:v", "1", out], check=True)
    for f in frames:
        os.remove(f)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--avatar")
    ap.add_argument("--local-broll", help="offline: DIR/<stage>/*.mp4 instead of Drive")
    ap.add_argument("--music")
    ap.add_argument("--no-drive", action="store_true", help="do not touch Drive (no upload, no ledger)")
    args = ap.parse_args()

    plan = json.load(open(args.plan, encoding="utf-8"))
    work = os.path.join(HERE, "work", plan["id"])
    os.makedirs(os.path.join(work, "broll"), exist_ok=True)
    today = dt.date.today().isoformat()

    avatar = get_avatar(plan, work, args.avatar)
    prep = edit.prepare(plan, avatar, work)
    print(f"avatar {prep['total']:.1f}s, {len(prep['words'])} words")

    rows = []
    if args.local_broll:
        def pool(stage):
            out = []
            for f in sorted(glob.glob(os.path.join(args.local_broll, stage, "*.mp4"))):
                out.append({"id": f, "name": os.path.basename(f), "path": f, "dur": duration(f), "stage": stage})
            return out
    else:
        import drive
        rows = drive.read_ledger(CFG["drive"]["ledger_sheet"])
        locked = locked_ids(rows, today)
        cache = {}

        def pool(stage):
            if stage not in cache:
                files = [f for f in drive.list_children(CFG["stages"][stage]["id"], videos_only=True)
                         if f["id"] not in locked]
                for f in files:
                    f["stage"] = stage
                    ms = (f.get("videoMediaMetadata") or {}).get("durationMillis")
                    f["dur"] = int(ms) / 1000 if ms else None
                cache[stage] = files
            for f in cache[stage]:
                if not f.get("path"):
                    f["path"] = os.path.join(work, "broll", f["id"] + os.path.splitext(f["name"])[1].lower())
                    if not os.path.exists(f["path"]):
                        drive.download(f["id"], f["path"])
                    f["dur"] = duration(f["path"])
                yield f

    pieces, used, notes = pick_pieces(plan, prep, pool, work)
    for n in notes:
        print("!", n)
    sheet = contact_sheet(pieces, os.path.join(work, "broll_contact.jpg"))
    json.dump({"pieces": pieces, "windows": prep["windows"]}, open(os.path.join(work, "edl.json"), "w"), indent=1)

    music = args.music
    if not music and not args.local_broll and not args.no_drive:
        import drive
        tracks = drive.list_children(CFG["drive"]["nhac_nen"][plan.get("music_mood", "D")])
        tracks = [t for t in tracks if t["mimeType"].startswith("audio/")]
        if tracks:
            t = random.choice(tracks)
            music = drive.download(t["id"], os.path.join(work, "music" + os.path.splitext(t["name"])[1]))
            print("music:", t["name"])
    if not music:
        import music as synth
        music = synth.make(plan.get("music_mood", "D"), prep["total"] + 2, os.path.join(work, "music_synth.wav"))
        print("music: synth fallback")

    out = os.path.join(work, f"{plan['id']}.mp4")
    edit.render(plan, avatar, pieces, music, out, work, prep)
    print("rendered:", out, f"{duration(out):.1f}s")
    if sheet:
        print("contact sheet:", sheet)

    if args.no_drive or args.local_broll:
        return
    import drive
    folder = drive.ensure_folder(plan["id"], CFG["drive"]["thanh_pham"])
    up = drive.upload(out, f"{plan['id']}.mp4", folder)
    drive.upload_text(plan_doc(plan), f"{plan['id']} — kịch bản & caption", folder,
                      convert_to="application/vnd.google-apps.document")
    reopen = (dt.date.today() + dt.timedelta(days=CFG["cooldown_days"])).isoformat()
    lock_dir = drive.ensure_folder(f"Mở lại {reopen}", CFG["drive"]["dang_khoa"])
    for c in used.values():
        drive.move(c["id"], lock_dir)
        rows.append({"file_id": c["id"], "ten_file": c["name"], "cong_doan": c["stage"],
                     "folder_goc_id": CFG["stages"][c["stage"]]["id"], "video_thanh_pham": plan["id"],
                     "ngay_dung": today, "ngay_mo_lai": reopen, "trang_thai": "KHOA"})
    drive.write_ledger(CFG["drive"]["ledger_sheet"], rows)
    print("uploaded:", up.get("webViewLink"), f"| locked {len(used)} clips until {reopen}")


def plan_doc(plan):
    seg = "\n".join(f"{i + 1}. [{('B-roll ' + s['broll']['stage']) if s.get('broll') else 'Avatar'}] {s['text']}"
                    + (f"\n   VI: {s['vi']}" if s.get("vi") else "") for i, s in enumerate(plan["segments"]))
    return (f"{plan['id']} — {plan['title']}\n\nHook on-screen: {plan.get('on_screen_hook', '')}\n\n"
            f"KỊCH BẢN (EN + VI)\n{seg}\n\nCAPTION\n{plan.get('caption', '')}\n\nHASHTAGS\n{plan.get('hashtags', '')}\n\n"
            f"Nguồn trend: {plan.get('trend_sources', '')}\n")


if __name__ == "__main__":
    main()
