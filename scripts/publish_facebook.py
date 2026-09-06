"""Prepare and publish one scheduled Facebook Page post for a daily slot."""

import argparse
import json
import mimetypes
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, parse, request


CAPTIONS_FILE = Path("output/captions.json")
SCREENSHOTS_DIR = Path("output/screenshots/final")
CONTENT_DIR = Path("content")
GRAPH_API_VERSION = "v20.0"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def require_environment(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set.")
    return value


def state_path():
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return CONTENT_DIR / date / "facebook_publish_state.json"


def api_error_message(body):
    try:
        payload = json.loads(body)
        api_error = payload.get("error", {})
        if api_error:
            message = api_error.get("message", "Unknown Graph API error")
            code = api_error.get("code")
            return f"{message}" + (f" (code {code})" if code is not None else "")
    except json.JSONDecodeError:
        pass
    return body or "No response body returned."


def send_request(url, data, headers):
    api_request = request.Request(url, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(api_request, timeout=60) as response:
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
    body = bytearray()
    for name, value in (("published", "false"), ("access_token", access_token)):
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(value.encode("utf-8"))
        body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="source"; filename="{image_path.name}"\r\n'.encode()
    )
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
    body.extend(image_path.read_bytes())
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    return bytes(body), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def upload_photo(page_id, access_token, image_path):
    data, headers = multipart_photo_data(image_path, access_token)
    response = send_request(
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/photos", data, headers
    )
    photo_id = response.get("id")
    if not photo_id:
        raise RuntimeError(f"Facebook did not return a photo ID for {image_path.name}.")
    return photo_id


def publish_post(page_id, access_token, caption, photo_id):
    form_data = {
        "message": caption,
        "access_token": access_token,
        "attached_media[0]": json.dumps({"media_fbid": photo_id}),
    }
    response = send_request(
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/feed",
        parse.urlencode(form_data).encode("utf-8"),
        {"Content-Type": "application/x-www-form-urlencoded"},
    )
    post_id = response.get("id")
    if not post_id:
        raise RuntimeError("Facebook did not return a post ID after publishing.")
    return post_id


def write_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary_path.replace(path)


def validate_posts(posts):
    ranks = [post.get("rank") for post in posts]
    if len(posts) != 5 or sorted(ranks) != [1, 2, 3, 4, 5]:
        raise RuntimeError("Publish state must contain exactly one valid post for every slot 1-5.")
    for post in posts:
        if not post.get("repo_name") or not post.get("caption") or not post.get("photo_id"):
            raise RuntimeError(f"Publish state for slot {post.get('rank')} is incomplete.")


def image_for_rank(rank):
    if not SCREENSHOTS_DIR.is_dir():
        raise RuntimeError(f"Missing {SCREENSHOTS_DIR}. Run the screenshot phase first.")
    matches = sorted(
        path for path in SCREENSHOTS_DIR.iterdir()
        if path.is_file()
        and path.suffix.lower() in IMAGE_SUFFIXES
        and path.name.startswith(f"{rank}_")
    )
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one final image beginning with '{rank}_' in {SCREENSHOTS_DIR}; "
            f"found {len(matches)}."
        )
    return matches[0]


def prepare_state(page_id, access_token, path):
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        validate_posts(existing.get("posts", []))
        print(f"Using existing daily publish state: {path}")
        return existing
    if not CAPTIONS_FILE.is_file():
        raise RuntimeError(f"Missing {CAPTIONS_FILE}. Run the caption-generation phase first.")

    captions = json.loads(CAPTIONS_FILE.read_text(encoding="utf-8")).get("posts", [])
    caption_by_rank = {post.get("rank"): post for post in captions}
    if len(captions) != 5 or sorted(caption_by_rank) != [1, 2, 3, 4, 5]:
        raise RuntimeError("captions.json must contain exactly one caption for every slot 1-5.")

    posts = []
    print("Uploading five unpublished Facebook Page photos...")
    for rank in range(1, 6):
        caption_post = caption_by_rank[rank]
        image_path = image_for_rank(rank)
        print(f"  Uploading slot {rank}: {image_path.name}")
        posts.append(
            {
                "rank": rank,
                "repo_name": caption_post.get("repo_name"),
                "caption": caption_post.get("caption"),
                "image_file": image_path.name,
                "photo_id": upload_photo(page_id, access_token, image_path),
                "published_post_id": None,
                "published_at": None,
            }
        )
    validate_posts(posts)
    state = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "posts": posts,
    }
    write_state(path, state)
    print(f"Saved daily publish state: {path}")
    return state


def load_state(path):
    if not path.is_file():
        raise RuntimeError(
            f"Missing {path}. Slot 1 must successfully prepare today's post packages before later slots run."
        )
    state = json.loads(path.read_text(encoding="utf-8"))
    validate_posts(state.get("posts", []))
    return state


def main():
    parser = argparse.ArgumentParser(description="Publish one scheduled Facebook Page post.")
    parser.add_argument("--slot", type=int, choices=range(1, 6), required=True)
    parser.add_argument(
        "--prepare-media",
        action="store_true",
        help="Upload all five unpublished photos and create today's publish state before posting.",
    )
    args = parser.parse_args()
    if args.prepare_media and args.slot != 1:
        raise RuntimeError("--prepare-media is only valid for slot 1.")

    access_token = require_environment("META_PAGE_ACCESS_TOKEN")
    page_id = require_environment("META_PAGE_ID")
    path = state_path()
    state = prepare_state(page_id, access_token, path) if args.prepare_media else load_state(path)
    post = next(item for item in state["posts"] if item["rank"] == args.slot)

    if post.get("published_post_id"):
        print(f"Slot {args.slot} was already published: {post['published_post_id']}")
        return

    print(f"Publishing Facebook Page post for slot {args.slot}: {post['repo_name']}")
    post_id = publish_post(page_id, access_token, post["caption"], post["photo_id"])
    post["published_post_id"] = post_id
    post["published_at"] = datetime.now(timezone.utc).isoformat()
    write_state(path, state)
    print(f"Published Facebook Post ID: {post_id}")


if __name__ == "__main__":
    main()
