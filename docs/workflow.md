# Workflow Guide

## Schedule and manual runs

The `GitHub Daily Research` workflow runs every day at 04:00 UTC, which is
12:00 PM in `Asia/Manila` (PHT, UTC+8). GitHub Actions schedules are best
effort, so a run can begin a few minutes after the scheduled time.

To run it on demand, open **Actions**, select **GitHub Daily Research**, then
choose **Run workflow**. Manual runs use the same pipeline and secrets as
scheduled runs.

## Pipeline

The workflow runs these stages in order:

1. Fetch and retain a daily snapshot of GitHub repository candidates.
2. Test the AI connection, rank the candidates, and analyse the top three.
3. Generate `output/facebook_caption.txt`.
4. Capture repository README screenshots.
5. Copy text outputs into `content/YYYY-MM-DD/`.
6. Publish the caption and final screenshots as one Facebook Page post.
7. Commit the text archive and upload the complete `output/` directory as a
   seven-day Actions artifact.

## Output layout

| Location | Contents |
| --- | --- |
| `output/facebook_caption.txt` | Generated post caption |
| `output/top3.json` | Ranked repositories |
| `output/research_details.json` | Deep-analysis data |
| `output/screenshots/raw/` | Full README captures; not published |
| `output/screenshots/final/` | Verified 1080x1350 PNGs published to Facebook |
| `content/YYYY-MM-DD/` | Versioned daily text archive |

## Facebook publishing

`scripts/publish_facebook.py` uses the Meta Graph API directly through Python's
standard library. It first uploads every image in `output/screenshots/final/`
as an unpublished Page photo, then creates a single feed post that attaches the
returned photo IDs and uses `output/facebook_caption.txt` as its message.

Required Actions secrets:

| Secret | Description |
| --- | --- |
| `META_PAGE_ACCESS_TOKEN` | Page access token with `pages_manage_posts`, `pages_read_engagement`, and `pages_show_list` |
| `META_PAGE_ID` | Target Page ID |
| `GEMINI_API_KEY` | Key used by the AI stages |

Never add these values to repository files, workflow logs, or commits.

## Troubleshooting

If Facebook publishing reports that no final images are available, inspect the
**Capture Repository Screenshots** log first. A successful capture reports the
number of successful and failed repositories and writes its publish-ready
assets to `output/screenshots/final/`.

If the Graph API rejects a request, verify the Page ID, confirm that the token
has not expired, and ensure the token carries the required Page permissions.
The publishing script prints the API's error message but never prints the
access token.
