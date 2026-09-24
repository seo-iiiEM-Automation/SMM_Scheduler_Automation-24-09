# Instagram & Facebook post scheduler (Streamlit)

Upload an image or video, write a caption and hashtags, pick Instagram and/or Facebook,
choose your own date and time. A small background worker publishes it on time.

## Files
- `app.py` – Streamlit UI (new post, scheduled queue, history)
- `scheduler.py` – worker that publishes due posts (must keep running)
- `meta_api.py` – Facebook/Instagram Graph API calls
- `media_host.py` – gives Instagram a public URL for your file (Cloudinary or your own server)
- `db.py` – SQLite storage (`scheduler.db`)

## 1. Meta setup (one time)
1. Convert your Instagram account to **Business** or **Creator** and link it to your **Facebook Page**.
2. Create an app at developers.facebook.com (type: Business).
3. In Graph API Explorer, generate a user token with these permissions:
   `pages_show_list, pages_read_engagement, pages_manage_posts, instagram_basic, instagram_content_publish, business_management`
4. Exchange it for a long-lived token, then call `GET /me/accounts` - copy your Page's `access_token` (this is the Page token) and `id`.
5. Get the Instagram ID: `GET /{page-id}?fields=instagram_business_account`.

## 2. Install and configure
```bash
pip install -r requirements.txt
cp .env.example .env      # then fill in token, page id, instagram id, Cloudinary URL
```

## 3. Run (two terminals)
```bash
python scheduler.py       # terminal 1 – keeps publishing on time
streamlit run app.py      # terminal 2 – the UI
```
Use **Test connection** in the sidebar to confirm both accounts work.

## Good to know
- Instagram only accepts media from a public URL, so files are uploaded to Cloudinary at publish time. Facebook gets the file directly.
- PNGs are converted to JPEG automatically (Instagram requirement).
- Instagram videos are posted as Reels (also shared to feed). Image aspect ratio must be between 4:5 and 1.91:1.
- Limits: 2,200-character captions, 30 hashtags, and roughly 100 API posts per 24 h on Instagram.
- The worker must be running at the scheduled time. For 24/7 use, run `scheduler.py` on a server/VPS
  (e.g. with `systemd`, `pm2`, or `nohup`), or run `python scheduler.py --once` from cron every minute.
- Retrying a partly published post only re-sends to the platform that failed, so nothing is posted twice.
