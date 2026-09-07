"""Durable, Git-tracked record of repositories successfully posted to Facebook."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


HISTORY_FILE = Path("data/posting_history.json")
PHT = ZoneInfo("Asia/Manila")
REPEAT_COOLDOWN_DAYS = 14


def now_pht():
    return datetime.now(PHT)


def normalize_repository(name):
    return name.strip().lower()


def load_history(path=HISTORY_FILE):
    """Return a valid history document, treating a missing file as no history."""
    if not path.is_file():
        return {"version": 1, "posts": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    posts = data.get("posts")
    if not isinstance(posts, list):
        raise RuntimeError(f"Posting history in {path} has an invalid posts list.")
    return {"version": 1, "posts": posts}


def parse_posted_at(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise RuntimeError(f"Posting history has an invalid posted_at value: {value!r}") from exc
    if parsed.tzinfo is None:
        raise RuntimeError("Posting history timestamps must include a timezone.")
    return parsed.astimezone(PHT)


def latest_posts_by_repository(history):
    latest = {}
    for post in history["posts"]:
        name = post.get("repository")
        posted_at = post.get("posted_at")
        if not isinstance(name, str) or not isinstance(posted_at, str):
            raise RuntimeError("Each posting-history record requires repository and posted_at.")
        normalized = normalize_repository(name)
        timestamp = parse_posted_at(posted_at)
        if normalized not in latest or timestamp > latest[normalized]:
            latest[normalized] = timestamp
    return latest


def recently_posted_repositories(history, reference_time=None, cooldown_days=REPEAT_COOLDOWN_DAYS):
    """Map repo name to its latest post time if it is still within the cooldown."""
    reference_time = (reference_time or now_pht()).astimezone(PHT)
    cutoff = reference_time - timedelta(days=cooldown_days)
    return {
        name: posted_at
        for name, posted_at in latest_posts_by_repository(history).items()
        if posted_at > cutoff
    }


def record_successful_post(repository, facebook_post_id, slot, posted_at=None, path=HISTORY_FILE):
    """Append a successful publication exactly once and persist it atomically."""
    if not repository or not facebook_post_id:
        raise RuntimeError("A repository and Facebook post ID are required for posting history.")
    history = load_history(path)
    if any(post.get("facebook_post_id") == facebook_post_id for post in history["posts"]):
        return False
    timestamp = (posted_at or now_pht()).astimezone(PHT)
    history["posts"].append(
        {
            "repository": repository,
            "facebook_post_id": facebook_post_id,
            "slot": slot,
            "posted_at": timestamp.isoformat(),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary_path.replace(path)
    return True
