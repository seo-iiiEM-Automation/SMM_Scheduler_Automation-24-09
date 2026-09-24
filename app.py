"""Streamlit UI: upload image/video, write caption + hashtags, pick platforms and time.
Run:  streamlit run app.py      (and keep  python scheduler.py  running in another terminal)
"""
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import streamlit as st
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

import db  # noqa: E402
import meta_api  # noqa: E402

st.set_page_config(page_title="Post Scheduler", page_icon="📅", layout="wide")
db.init_db()

MEDIA_DIR = "media"
os.makedirs(MEDIA_DIR, exist_ok=True)
TZ = ZoneInfo(os.getenv("TIMEZONE", "Asia/Kolkata"))
TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN", "")
PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "")
IG_ID = os.getenv("INSTAGRAM_USER_ID", "")

IG_CAPTION_LIMIT = 2200
IG_HASHTAG_LIMIT = 30
VIDEO_EXT = {".mp4", ".mov"}

if "form_id" not in st.session_state:
    st.session_state.form_id = 0


# ---------------- helpers ----------------
def normalize_hashtags(raw: str) -> list[str]:
    tags, seen = [], set()
    for t in re.split(r"[\s,]+", raw or ""):
        t = t.strip().lstrip("#")
        t = re.sub(r"[^\w]", "", t)
        if t and t.lower() not in seen:
            seen.add(t.lower())
            tags.append("#" + t)
    return tags


def local_str(utc_iso: str) -> str:
    return datetime.fromisoformat(utc_iso).astimezone(TZ).strftime("%d %b %Y, %I:%M %p")


def save_upload(uploaded) -> tuple[str, str]:
    """Save to ./media. Images become JPEG because Instagram only accepts JPEG."""
    ext = os.path.splitext(uploaded.name)[1].lower()
    name = uuid.uuid4().hex
    if ext in VIDEO_EXT:
        path = os.path.join(MEDIA_DIR, name + ext)
        with open(path, "wb") as f:
            f.write(uploaded.getbuffer())
        return path, "video"
    img = Image.open(uploaded)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    path = os.path.join(MEDIA_DIR, name + ".jpg")
    img.save(path, "JPEG", quality=92)
    return path, "image"


def show_thumb(post):
    if post["media_type"] == "image" and os.path.exists(post["media_path"]):
        st.image(post["media_path"], width=110)
    else:
        st.markdown("🎬 Video")


def when_picker(key_prefix, default_dt):
    c1, c2 = st.columns(2)
    d = c1.date_input("Date", value=default_dt.date(), min_value=datetime.now(TZ).date(), key=f"{key_prefix}_d")
    t = c2.time_input("Time", value=default_dt.time().replace(second=0, microsecond=0), step=60, key=f"{key_prefix}_t")
    return datetime.combine(d, t).replace(tzinfo=TZ)


# ---------------- sidebar ----------------
with st.sidebar:
    st.header("Accounts")
    if not TOKEN:
        st.error("Add your Meta token and IDs to the .env file, then restart.")
    if st.button("Test connection", use_container_width=True, disabled=not TOKEN):
        try:
            st.success(f"Facebook Page: {meta_api.check_page(PAGE_ID, TOKEN)}")
        except Exception as e:
            st.error(f"Facebook: {e}")
        try:
            st.success(f"Instagram: @{meta_api.check_instagram(IG_ID, TOKEN)}")
        except Exception as e:
            st.error(f"Instagram: {e}")
    st.caption(f"Times are in **{TZ.key}**.")
    st.info("Posts go out only while `python scheduler.py` is running.")

st.title("📅 Instagram & Facebook scheduler")
tab_new, tab_queue, tab_history = st.tabs(["New post", "Scheduled", "History"])

# ---------------- new post ----------------
with tab_new:
    fid = st.session_state.form_id
    left, right = st.columns([3, 2], gap="large")

    with left:
        uploaded = st.file_uploader("Image or video", type=["jpg", "jpeg", "png", "mp4", "mov"], key=f"up_{fid}")
        caption = st.text_area("Caption", height=160, key=f"cap_{fid}")
        hashtags_raw = st.text_input("Hashtags", placeholder="#export #import training, business",
                                     help="Separate with spaces or commas. # is added automatically.", key=f"tags_{fid}")
        c1, c2 = st.columns(2)
        to_ig = c1.checkbox("Instagram", value=True, key=f"ig_{fid}")
        to_fb = c2.checkbox("Facebook", value=True, key=f"fb_{fid}")
        post_now = st.checkbox("Publish as soon as possible", key=f"now_{fid}")
        default_dt = (datetime.now(TZ) + timedelta(minutes=30))
        when = None if post_now else when_picker(f"new_{fid}", default_dt)

    tags = normalize_hashtags(hashtags_raw)
    full_caption = (caption.strip() + ("\n\n" + " ".join(tags) if tags else "")).strip()

    with right:
        st.subheader("Preview")
        if uploaded:
            if os.path.splitext(uploaded.name)[1].lower() in VIDEO_EXT:
                st.video(uploaded)
                if to_ig:
                    st.caption("Instagram posts videos as Reels (9:16, 3 s – 15 min works best).")
            else:
                img = Image.open(uploaded)
                st.image(img, use_container_width=True)
                ratio = img.width / img.height
                if to_ig and not (0.8 <= ratio <= 1.91):
                    st.warning(f"Aspect ratio {ratio:.2f} is outside Instagram's 4:5 – 1.91:1 range. Crop it first.")
                uploaded.seek(0)
        st.text(full_caption or "Your caption will appear here.")
        st.caption(f"{len(full_caption)}/{IG_CAPTION_LIMIT} characters · {len(tags)}/{IG_HASHTAG_LIMIT} hashtags")

    if st.button("Schedule post", type="primary"):
        errors = []
        platforms = [p for p, on in (("instagram", to_ig), ("facebook", to_fb)) if on]
        if not uploaded:
            errors.append("Upload an image or video.")
        if not platforms:
            errors.append("Pick at least one platform.")
        if to_ig and len(full_caption) > IG_CAPTION_LIMIT:
            errors.append(f"Instagram captions are limited to {IG_CAPTION_LIMIT} characters.")
        if to_ig and len(tags) > IG_HASHTAG_LIMIT:
            errors.append(f"Instagram allows at most {IG_HASHTAG_LIMIT} hashtags.")
        if when and when <= datetime.now(TZ):
            errors.append("Pick a time in the future.")
        if errors:
            for e in errors:
                st.error(e)
        else:
            path, mtype = save_upload(uploaded)
            run_at = when or datetime.now(TZ)
            pid = db.add_post(path, mtype, caption.strip(), " ".join(tags), platforms, run_at)
            st.session_state.flash = f"Scheduled post #{pid} for {run_at.strftime('%d %b %Y, %I:%M %p')}."
            st.session_state.form_id += 1  # clears the form
            st.rerun()

    if msg := st.session_state.pop("flash", None):
        st.success(msg)

# ---------------- scheduled queue ----------------
with tab_queue:
    queue = db.list_posts(["scheduled", "publishing"])
    if not queue:
        st.info("Nothing scheduled yet. Create a post in the New post tab.")
    for p in queue:
        with st.container(border=True):
            c1, c2, c3 = st.columns([1, 4, 2])
            with c1:
                show_thumb(p)
            with c2:
                st.markdown(f"**#{p['id']}** · {p['platforms'].replace(',', ' + ').title()}")
                st.write((p["caption"][:180] + "…") if len(p["caption"]) > 180 else p["caption"])
                if p["hashtags"]:
                    st.caption(p["hashtags"])
            with c3:
                if p["status"] == "publishing":
                    st.warning("Publishing now…")
                    continue
                st.markdown(f"🕒 **{local_str(p['scheduled_at'])}**")
                with st.popover("Change time"):
                    cur = datetime.fromisoformat(p["scheduled_at"]).astimezone(TZ)
                    new_when = when_picker(f"rs_{p['id']}", cur)
                    if st.button("Save time", key=f"rs_btn_{p['id']}"):
                        if new_when <= datetime.now(TZ):
                            st.error("Pick a time in the future.")
                        else:
                            db.reschedule(p["id"], new_when)
                            st.rerun()
                if st.button("Delete", key=f"del_{p['id']}"):
                    path = db.delete_post(p["id"])
                    if path and os.path.exists(path):
                        os.remove(path)
                    st.rerun()

# ---------------- history ----------------
with tab_history:
    history = list(reversed(db.list_posts(["published", "partial", "failed"])))
    if not history:
        st.info("Published and failed posts will show up here.")
    badge = {"published": "✅ Published", "partial": "⚠️ Partly published", "failed": "❌ Failed"}
    for p in history:
        results = json.loads(p["results"] or "{}")
        with st.container(border=True):
            c1, c2, c3 = st.columns([1, 4, 2])
            with c1:
                show_thumb(p)
            with c2:
                st.markdown(f"**#{p['id']}** · {badge[p['status']]} · {local_str(p['scheduled_at'])}")
                st.write((p["caption"][:140] + "…") if len(p["caption"]) > 140 else p["caption"])
                for plat in p["platforms"].split(","):
                    r = results.get(plat, {})
                    if r.get("ok"):
                        st.caption(f"{plat.title()}: posted (id {r.get('id')})")
                    elif r:
                        st.error(f"{plat.title()}: {r.get('error')}")
                if results.get("_note"):
                    st.warning(results["_note"])
            with c3:
                if p["status"] in ("failed", "partial"):
                    if st.button("Retry now", key=f"retry_{p['id']}",
                                 help="Only retries the platforms that failed."):
                        db.reschedule(p["id"], datetime.now(TZ))
                        st.rerun()
                if st.button("Remove", key=f"rm_{p['id']}"):
                    path = db.delete_post(p["id"])
                    if path and os.path.exists(path):
                        os.remove(path)
                    st.rerun()
