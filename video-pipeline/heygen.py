"""HeyGen API v2: find Liam's avatar + cloned voice, render a 9:16 talking video.

Env: HEYGEN_API_KEY
"""
import os
import time
import unicodedata

import requests

API = "https://api.heygen.com"


def _h():
    return {"X-Api-Key": os.environ["HEYGEN_API_KEY"], "Accept": "application/json"}


def _norm(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def _get(path, **params):
    r = requests.get(f"{API}{path}", headers=_h(), params=params, timeout=60)
    r.raise_for_status()
    return r.json().get("data") or {}


def find_avatar(name):
    """Returns ("avatar"|"talking_photo", id). Exact (normalized) name match wins over substring."""
    want, cands = _norm(name), []
    data = _get("/v2/avatars")
    for a in data.get("avatars", []):
        cands.append(("avatar", a["avatar_id"], a.get("avatar_name", "")))
    for p in data.get("talking_photos", []):
        cands.append(("talking_photo", p["talking_photo_id"], p.get("talking_photo_name", "")))
    try:  # custom / photo avatars live in avatar groups
        for g in _get("/v2/avatar_group.list", include_public="false").get("avatar_group_list", []):
            for a in _get(f"/v2/avatar_group/{g['id']}/avatars").get("avatar_list", []):
                kind = "talking_photo" if a.get("type") == "photo" else "avatar"
                cands.append((kind, a["id"], a.get("name") or g.get("name", "")))
    except requests.HTTPError:
        pass
    exact = [c for c in cands if _norm(c[2]) == want]
    loose = [c for c in cands if want in _norm(c[2])]
    hit = (exact or loose or [None])[0]
    if not hit:
        raise SystemExit(f"Không thấy avatar '{name}' trên HeyGen. Có: {sorted({c[2] for c in cands})[:40]}")
    return hit[0], hit[1]


def find_voice(name):
    want = _norm(name)
    voices = _get("/v2/voices").get("voices", [])
    exact = [v for v in voices if _norm(v.get("name")) == want]
    loose = [v for v in voices if want in _norm(v.get("name"))]
    hit = (exact or loose or [None])[0]
    if not hit:
        raise SystemExit(f"Không thấy voice '{name}' trên HeyGen.")
    return hit["voice_id"]


def generate(text, avatar_name, voice_name, width=1080, height=1920, speed=1.0, title="Nava video"):
    kind, avatar_id = find_avatar(avatar_name)
    voice_id = find_voice(voice_name)
    character = ({"type": "avatar", "avatar_id": avatar_id, "avatar_style": "normal"} if kind == "avatar"
                 else {"type": "talking_photo", "talking_photo_id": avatar_id})
    body = {
        "title": title,
        "caption": False,
        "dimension": {"width": width, "height": height},
        "video_inputs": [{
            "character": character,
            "voice": {"type": "text", "input_text": text, "voice_id": voice_id, "speed": speed},
        }],
    }
    r = requests.post(f"{API}/v2/video/generate", headers=_h(), json=body, timeout=60)
    if r.status_code >= 400:
        raise SystemExit(f"HeyGen từ chối: {r.status_code} {r.text[:500]}")
    return r.json()["data"]["video_id"]


def wait(video_id, timeout=3600, every=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        d = _get("/v1/video_status.get", video_id=video_id)
        st = d.get("status")
        if st == "completed":
            return d
        if st == "failed":
            raise SystemExit(f"HeyGen render lỗi: {d.get('error')}")
        time.sleep(every)
    raise SystemExit("HeyGen render quá thời gian chờ.")


def download(url, dest):
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return dest
