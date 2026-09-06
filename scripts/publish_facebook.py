"""Publish the daily caption and screenshots as a multi-photo Facebook Page post."""

import json
import mimetypes
import os
import uuid
from pathlib import Path
from urllib import error, parse, request


CAPTION_FILE = Path("output/facebook_caption.txt")
# The capture phase stores full README captures in ``raw`` and the 1080x1350
# social-media assets in ``final``. Only the portrait-ready images are posted.
SCREENSHOTS_DIR = Path("output/screenshots/final")
GRAPH_API_VERSION = "v20.0"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def require_environment(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set.")
    return value


def api_error_message(body):
    """Extract Graph API's useful error details without exposing credentials."""
    try:
        payload = json.loads(body)
        api_error = payload.get("error", {})
        if api_error:
            details = api_error.get("message", "Unknown Graph API error")
            code = api_error.get("code")
            return f"{details}" + (f" (code {code})" if code is not None else "")
    except json.JSONDecodeError:
        pass
    return body or "No response body returned."


def send_request(url, data, headers):
    http_request = request.Request(url, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(http_request, timeout=60) as response:
            return json.load(response)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Facebook Graph API request failed ({exc.code}): {api_error_message(body)}"
        ) from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach Facebook Graph API: {exc.reason}") from exc


def multipart_photo_data(image_path, access_token):
    boundary = f"----github-daily-agent-{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    image_bytes = image_path.read_bytes()
    fields = [
        ("published", "false"),
        ("access_token", access_token),
    ]

    body = bytearray()
    for name, value in fields:
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(value.encode("utf-8"))
        body.extend(b"\r\n")

    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="source"; filename="{image_path.name}"\r\n'.encode()
    )
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
    body.extend(image_bytes)
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    return bytes(body), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def upload_photo(page_id, access_token, image_path):
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/photos"
    data, headers = multipart_photo_data(image_path, access_token)
    response = send_request(url, data, headers)
    photo_id = response.get("id")
    if not photo_id:
        raise RuntimeError(f"Facebook did not return a photo ID for {image_path.name}.")
    return photo_id


def publish_post(page_id, access_token, caption, photo_ids):
    form_data = {"message": caption, "access_token": access_token}
    for index, photo_id in enumerate(photo_ids):
        form_data[f"attached_media[{index}]"] = json.dumps({"media_fbid": photo_id})

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/feed"
    response = send_request(
        url,
        parse.urlencode(form_data).encode("utf-8"),
        {"Content-Type": "application/x-www-form-urlencoded"},
    )
    post_id = response.get("id")
    if not post_id:
        raise RuntimeError("Facebook did not return a post ID after publishing.")
    return post_id


def main():
    if not CAPTION_FILE.is_file():
        raise RuntimeError(f"Missing {CAPTION_FILE}. Run the caption-generation phase first.")
    if not SCREENSHOTS_DIR.is_dir():
        raise RuntimeError(
            f"Missing {SCREENSHOTS_DIR}. Run the screenshot phase first."
        )

    caption = CAPTION_FILE.read_text(encoding="utf-8").strip()
    if not caption:
        raise RuntimeError(f"{CAPTION_FILE} is empty.")

    images = sorted(
        path for path in SCREENSHOTS_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    if not images:
        raise RuntimeError(
            f"No PNG or JPG images found in {SCREENSHOTS_DIR}. "
            "The screenshot phase may not have produced any final images."
        )

    access_token = require_environment("META_PAGE_ACCESS_TOKEN")
    page_id = require_environment("META_PAGE_ID")

    print(f"Uploading {len(images)} unpublished Facebook Page photo(s)...")
    photo_ids = []
    for image_path in images:
        print(f"  Uploading {image_path.name}")
        photo_ids.append(upload_photo(page_id, access_token, image_path))

    print("Publishing combined Facebook Page post...")
    post_id = publish_post(page_id, access_token, caption, photo_ids)
    print(f"Published Facebook Post ID: {post_id}")


if __name__ == "__main__":
    main()
