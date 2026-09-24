"""Minimal Meta Graph API client for Facebook Page + Instagram publishing."""
import os
import time

import requests

VERSION = os.getenv("GRAPH_API_VERSION", "v23.0")
GRAPH = f"https://graph.facebook.com/{VERSION}"
GRAPH_VIDEO = f"https://graph-video.facebook.com/{VERSION}"


class MetaAPIError(Exception):
    pass


def _check(resp):
    try:
        data = resp.json()
    except ValueError:
        raise MetaAPIError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    if resp.status_code >= 400 or "error" in data:
        e = data.get("error", {})
        raise MetaAPIError(f"{e.get('type', 'Error')} {e.get('code', '')}: {e.get('message', resp.text[:300])}")
    return data


# ---------------- Connection checks ----------------
def check_page(page_id, token):
    return _check(requests.get(f"{GRAPH}/{page_id}", params={"fields": "name", "access_token": token}, timeout=30))["name"]


def check_instagram(ig_user_id, token):
    return _check(requests.get(f"{GRAPH}/{ig_user_id}", params={"fields": "username", "access_token": token}, timeout=30))["username"]


# ---------------- Facebook Page (direct file upload) ----------------
def fb_post_photo(page_id, token, path, caption):
    with open(path, "rb") as f:
        r = requests.post(f"{GRAPH}/{page_id}/photos",
                          data={"caption": caption, "access_token": token},
                          files={"source": f}, timeout=180)
    d = _check(r)
    return d.get("post_id") or d["id"]


def fb_post_video(page_id, token, path, description):
    with open(path, "rb") as f:
        r = requests.post(f"{GRAPH_VIDEO}/{page_id}/videos",
                          data={"description": description, "access_token": token},
                          files={"source": f}, timeout=900)
    return _check(r)["id"]


# ---------------- Instagram (needs a PUBLIC media URL) ----------------
def _wait_until_ready(container_id, token, timeout_s):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        d = _check(requests.get(f"{GRAPH}/{container_id}",
                                params={"fields": "status_code,status", "access_token": token}, timeout=30))
        code = d.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise MetaAPIError(f"Instagram couldn't process the media: {d.get('status', code)}")
        time.sleep(5)
    raise MetaAPIError("Instagram took too long to process the media. Try again later.")


def _publish(ig_user_id, token, container_id):
    r = requests.post(f"{GRAPH}/{ig_user_id}/media_publish",
                      data={"creation_id": container_id, "access_token": token}, timeout=60)
    return _check(r)["id"]


def ig_post_image(ig_user_id, token, image_url, caption):
    r = requests.post(f"{GRAPH}/{ig_user_id}/media",
                      data={"image_url": image_url, "caption": caption, "access_token": token}, timeout=60)
    cid = _check(r)["id"]
    _wait_until_ready(cid, token, 120)
    return _publish(ig_user_id, token, cid)


def ig_post_reel(ig_user_id, token, video_url, caption, share_to_feed=True):
    r = requests.post(f"{GRAPH}/{ig_user_id}/media",
                      data={"media_type": "REELS", "video_url": video_url, "caption": caption,
                            "share_to_feed": "true" if share_to_feed else "false", "access_token": token},
                      timeout=60)
    cid = _check(r)["id"]
    _wait_until_ready(cid, token, 900)
    return _publish(ig_user_id, token, cid)
