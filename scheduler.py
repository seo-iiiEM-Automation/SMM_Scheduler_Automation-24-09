"""Background worker: publishes due posts. Run in its own terminal:  python scheduler.py"""
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

import db  # noqa: E402
import meta_api  # noqa: E402
from media_host import get_public_url  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger("scheduler")

TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN")
PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
IG_ID = os.getenv("INSTAGRAM_USER_ID")
POLL = int(os.getenv("SCHEDULER_POLL_SECONDS", "30"))


def build_caption(caption, hashtags):
    caption, hashtags = (caption or "").strip(), (hashtags or "").strip()
    return f"{caption}\n\n{hashtags}".strip() if hashtags else caption


def publish_post(post):
    results = json.loads(post.get("results") or "{}")
    results.pop("_note", None)
    text = build_caption(post["caption"], post["hashtags"])
    is_image = post["media_type"] == "image"
    public_url = None

    for platform in post["platforms"].split(","):
        if results.get(platform, {}).get("ok"):
            continue  # already posted there (e.g. on a retry) - don't duplicate
        try:
            if platform == "facebook":
                pid = (meta_api.fb_post_photo if is_image else meta_api.fb_post_video)(
                    PAGE_ID, TOKEN, post["media_path"], text)
            elif platform == "instagram":
                public_url = public_url or get_public_url(post["media_path"], post["media_type"])
                pid = (meta_api.ig_post_image if is_image else meta_api.ig_post_reel)(
                    IG_ID, TOKEN, public_url, text)
            else:
                raise ValueError(f"Unknown platform {platform}")
            results[platform] = {"ok": True, "id": pid,
                                 "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            log.info("Post #%s published to %s (%s)", post["id"], platform, pid)
        except Exception as e:  # keep going with the other platform
            results[platform] = {"ok": False, "error": str(e)}
            log.error("Post #%s failed on %s: %s", post["id"], platform, e)

    oks = [results[p]["ok"] for p in post["platforms"].split(",")]
    status = "published" if all(oks) else ("partial" if any(oks) else "failed")
    db.set_result(post["id"], status, results)


def run_once():
    for post in db.claim_due_posts():
        publish_post(post)


def main():
    if not TOKEN:
        sys.exit("META_PAGE_ACCESS_TOKEN is missing in .env")
    db.init_db()
    stuck = db.fail_stuck_posts()
    if stuck:
        log.warning("%s post(s) were interrupted last time and marked failed.", stuck)
    log.info("Scheduler running. Checking every %ss. Ctrl+C to stop.", POLL)
    while True:
        try:
            run_once()
        except Exception:
            log.exception("Unexpected error in scheduler loop")
        if "--once" in sys.argv:
            break
        time.sleep(POLL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Stopped.")
