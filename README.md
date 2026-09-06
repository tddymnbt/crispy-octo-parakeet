# GitHub Daily Agent

An automated GitHub Actions workflow that finds notable repositories, ranks and
analyses the top five with AI, produces five Facebook-ready captions and
portrait screenshots, then publishes one post at each scheduled slot.

The workflow runs automatically every day at **8:00 AM, 12:00 PM, 3:00 PM,
7:00 PM, and 11:00 PM Philippines Time (PHT)**, subject to normal GitHub
Actions scheduling delays. It can also be started manually from the
repository's **Actions** tab.

## What the workflow does

1. Collects GitHub repository candidates and saves the daily history.
2. Ranks candidates and generates detailed research for the top five.
3. Generates five repository-specific Facebook captions and 1080x1350
   repository screenshots.
4. At 8:00 AM, uploads all five photos as unpublished Page media, publishes
   slot 1, and archives the daily publishing state.
5. Publishes slots 2-5 from the saved media IDs and captions throughout the
   day, then records each Facebook post ID in the archive.
6. Retains complete outputs as a seven-day workflow artifact. Screenshots are
   not committed to Git.

## Required repository secrets

Configure these under **Settings > Secrets and variables > Actions**:

| Secret | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | AI ranking, research, and caption generation |
| `META_PAGE_ACCESS_TOKEN` | Facebook Page token with publishing permissions |
| `META_PAGE_ID` | ID of the Facebook Page to publish to |

The Facebook Page token needs `pages_manage_posts`, `pages_read_engagement`,
and `pages_show_list` permissions.

## Documentation

See [the workflow guide](docs/workflow.md) for the schedule, output layout,
Facebook publishing flow, and troubleshooting notes.
