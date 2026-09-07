import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from posting_history import (  # noqa: E402
    load_history,
    recently_posted_repositories,
    record_successful_post,
)


PHT = ZoneInfo("Asia/Manila")


class PostingHistoryTests(unittest.TestCase):
    def test_records_a_success_only_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "posting_history.json"
            timestamp = datetime(2026, 9, 7, 8, 0, tzinfo=PHT)
            self.assertTrue(record_successful_post("owner/repo", "post-1", 1, timestamp, path))
            self.assertFalse(record_successful_post("owner/repo", "post-1", 1, timestamp, path))
            self.assertEqual(len(load_history(path)["posts"]), 1)

    def test_14_day_cooldown_expires_at_day_14(self):
        history = {
            "version": 1,
            "posts": [
                {
                    "repository": "Owner/Repo",
                    "facebook_post_id": "post-1",
                    "slot": 1,
                    "posted_at": "2026-08-24T08:00:00+08:00",
                }
            ],
        }
        self.assertIn(
            "owner/repo",
            recently_posted_repositories(history, datetime(2026, 9, 7, 7, 59, tzinfo=PHT)),
        )
        self.assertNotIn(
            "owner/repo",
            recently_posted_repositories(history, datetime(2026, 9, 7, 8, 0, tzinfo=PHT)),
        )


if __name__ == "__main__":
    unittest.main()
