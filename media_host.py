"""Turns a local file into a public URL (Instagram's API only accepts URLs)."""
import os


def get_public_url(local_path, media_type):
    if os.getenv("CLOUDINARY_URL"):
        import cloudinary.uploader  # reads CLOUDINARY_URL from env
        res = cloudinary.uploader.upload(
            local_path,
            resource_type="video" if media_type == "video" else "image",
            folder="social_scheduler",
        )
        return res["secure_url"]

    base = os.getenv("PUBLIC_MEDIA_BASE_URL")
    if base:
        return f"{base.rstrip('/')}/{os.path.basename(local_path)}"

    raise RuntimeError("Instagram needs a public media URL. Set CLOUDINARY_URL or PUBLIC_MEDIA_BASE_URL in .env")
