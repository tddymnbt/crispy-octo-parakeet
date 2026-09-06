# Workflow Guide

## Schedule and manual runs

The `GitHub Daily Research` workflow has five daily PHT slots. GitHub Actions
cron uses UTC; schedules are best effort, so a run can begin a few minutes
after its scheduled time.

| PHT slot | UTC cron | Work performed |
| --- | --- | --- |
| 8:00 AM (slot 1) | `0 0 * * *` | Full research pipeline, media preparation, and post 1 |
| 12:00 PM (slot 2) | `0 4 * * *` | Publish post 2 |
| 3:00 PM (slot 3) | `0 7 * * *` | Publish post 3 |
| 7:00 PM (slot 4) | `0 11 * * *` | Publish post 4 |
| 11:00 PM (slot 5) | `0 15 * * *` | Publish post 5 |

To run it on demand, open **Actions**, select **GitHub Daily Research**, then
choose **Run workflow**, and select a slot. Slot 1 creates today's five post
packages; manual slots 2-5 require slot 1 to have completed for that day.

## Pipeline

The workflow runs these stages in order:

1. Fetch and retain a daily snapshot of GitHub repository candidates.
2. Test the AI connection, rank the candidates, and analyse the top five.
3. Generate `output/captions.json`, with one caption for each rank.
4. Capture five repository README screenshots.
5. Copy text outputs into `content/YYYY-MM-DD/`.
6. Upload five final images as unpublished Facebook Page photos and save their
   IDs in the daily publish state.
7. Publish slot 1 immediately, then publish one saved media ID and caption at
   each later slot.
8. Commit the text archive/publish state and upload the complete `output/`
   directory as a seven-day Actions artifact.

## Output layout

| Location | Contents |
| --- | --- |
| `output/captions.json` | Five generated captions, one per repository |
| `output/top5.json` | Five ranked repositories |
| `output/research_details.json` | Deep-analysis data |
| `output/screenshots/raw/` | Full README captures; not published |
| `output/screenshots/final/` | Verified 1080x1350 PNGs published to Facebook |
| `content/YYYY-MM-DD/facebook_publish_state.json` | Unpublished photo IDs, captions, and publication status |
| `content/YYYY-MM-DD/` | Versioned daily text archive |

## Facebook publishing

`scripts/publish_facebook.py` uses the Meta Graph API directly through Python's
standard library. At slot 1, it uploads every image in
`output/screenshots/final/` as an unpublished Page photo and saves the returned
IDs with their corresponding captions in the dated publishing-state file. Each
slot creates one separate feed post using its assigned saved photo ID and
caption. The state records the returned Facebook post ID, preventing a retry
from duplicating a successfully published slot.

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
