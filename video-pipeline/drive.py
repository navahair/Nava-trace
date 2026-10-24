"""Google Drive access for the pipeline (OAuth refresh token of the Drive owner).

Env: GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REFRESH_TOKEN
"""
import csv
import io
import json
import os
import time

import requests

API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
FOLDER = "application/vnd.google-apps.folder"

_token = {"value": None, "exp": 0}


def _access_token():
    if _token["value"] and time.time() < _token["exp"] - 60:
        return _token["value"]
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["GOOGLE_OAUTH_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_OAUTH_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }, timeout=30)
    r.raise_for_status()
    data = r.json()
    _token["value"], _token["exp"] = data["access_token"], time.time() + data["expires_in"]
    return _token["value"]


def _h(extra=None):
    h = {"Authorization": f"Bearer {_access_token()}"}
    h.update(extra or {})
    return h


def list_children(folder_id, videos_only=False, folders_only=False):
    q = f"'{folder_id}' in parents and trashed = false"
    if videos_only:
        q += " and mimeType contains 'video/'"
    if folders_only:
        q += f" and mimeType = '{FOLDER}'"
    out, page = [], None
    while True:
        r = requests.get(f"{API}/files", headers=_h(), params={
            "q": q, "pageSize": 1000, "pageToken": page, "orderBy": "createdTime",
            "fields": "nextPageToken, files(id,name,mimeType,size,createdTime,parents,"
                      "videoMediaMetadata(durationMillis,width,height))",
        }, timeout=60)
        r.raise_for_status()
        data = r.json()
        out += data.get("files", [])
        page = data.get("nextPageToken")
        if not page:
            return out


def download(file_id, dest):
    with requests.get(f"{API}/files/{file_id}", headers=_h(), params={"alt": "media"},
                      stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return dest


def upload(path, name, parent_id, mime="video/mp4"):
    """Resumable upload; returns the created file resource."""
    meta = {"name": name, "parents": [parent_id]}
    r = requests.post(f"{UPLOAD}/files", params={"uploadType": "resumable", "fields": "id,name,webViewLink"},
                      headers=_h({"Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": mime}),
                      data=json.dumps(meta), timeout=60)
    r.raise_for_status()
    with open(path, "rb") as f:
        r2 = requests.put(r.headers["Location"], data=f, headers={"Content-Type": mime}, timeout=1800)
    r2.raise_for_status()
    return r2.json()


def upload_text(text, name, parent_id, mime="text/plain", convert_to=None):
    meta = {"name": name, "parents": [parent_id]}
    if convert_to:
        meta["mimeType"] = convert_to
    boundary = "navaboundary"
    body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n"
            f"--{boundary}\r\nContent-Type: {mime}; charset=UTF-8\r\n\r\n{text}\r\n--{boundary}--").encode()
    r = requests.post(f"{UPLOAD}/files", params={"uploadType": "multipart", "fields": "id,name,webViewLink"},
                      headers=_h({"Content-Type": f"multipart/related; boundary={boundary}"}), data=body, timeout=60)
    r.raise_for_status()
    return r.json()


def move(file_id, new_parent):
    r = requests.get(f"{API}/files/{file_id}", headers=_h(), params={"fields": "parents"}, timeout=30)
    r.raise_for_status()
    old = ",".join(r.json().get("parents", []))
    r = requests.patch(f"{API}/files/{file_id}", headers=_h(),
                       params={"addParents": new_parent, "removeParents": old, "fields": "id,parents"}, timeout=30)
    r.raise_for_status()


def ensure_folder(name, parent_id):
    for f in list_children(parent_id, folders_only=True):
        if f["name"] == name:
            return f["id"]
    r = requests.post(f"{API}/files", headers=_h({"Content-Type": "application/json"}),
                      data=json.dumps({"name": name, "mimeType": FOLDER, "parents": [parent_id]}), timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def trash(file_id):
    requests.patch(f"{API}/files/{file_id}", headers=_h({"Content-Type": "application/json"}),
                   data=json.dumps({"trashed": True}), timeout=30).raise_for_status()


# ---- ledger (Google Sheet "SỔ FOOTAGE ĐÃ DÙNG") ----
LEDGER_COLS = ["file_id", "ten_file", "cong_doan", "folder_goc_id", "video_thanh_pham",
               "ngay_dung", "ngay_mo_lai", "trang_thai"]


def read_ledger(sheet_id):
    r = requests.get(f"{API}/files/{sheet_id}/export", headers=_h(), params={"mimeType": "text/csv"}, timeout=60)
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8"))))
    return [row for row in rows if row.get("file_id")]


def write_ledger(sheet_id, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=LEDGER_COLS, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    r = requests.patch(f"{UPLOAD}/files/{sheet_id}", params={"uploadType": "media"},
                       headers=_h({"Content-Type": "text/csv"}), data=buf.getvalue().encode("utf-8"), timeout=60)
    r.raise_for_status()
