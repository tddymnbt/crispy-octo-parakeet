import json
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = "https://api.github.com/search/repositories"

TOKEN = os.environ.get("GITHUB_TOKEN")

if not TOKEN:
    raise RuntimeError("GITHUB_TOKEN is not available")


# Look at repositories that have been pushed recently.
since = datetime.now(timezone.utc) - timedelta(hours=24)
since_date = since.strftime("%Y-%m-%d")


params = {
    "q": f"pushed:>={since_date}",
    "sort": "stars",
    "order": "desc",
    "per_page": 20,
}


url = f"{API_URL}?{urlencode(params)}"

request = Request(
    url,
    headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "github-daily-agent",
    },
)


with urlopen(request) as response:
    data = json.load(response)


repositories = []

for index, repo in enumerate(data.get("items", []), start=1):
    repositories.append(
        {
            "rank": index,
            "name": repo["full_name"],
            "url": repo["html_url"],
            "description": repo["description"],
            "stars": repo["stargazers_count"],
            "forks": repo["forks_count"],
            "language": repo["language"],
            "topics": repo.get("topics", []),
            "created_at": repo["created_at"],
            "updated_at": repo["updated_at"],
            "pushed_at": repo["pushed_at"],
            "open_issues": repo["open_issues_count"],
            "license": (
                repo["license"]["spdx_id"]
                if repo.get("license")
                else None
            ),
        }
    )


output = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "search_window": {
        "pushed_since": since.isoformat(),
        "description": "Repositories pushed within the last 24 hours",
    },
    "candidate_count": len(repositories),
    "repositories": repositories,
}


os.makedirs("output", exist_ok=True)

with open("output/candidates.json", "w", encoding="utf-8") as file:
    json.dump(output, file, indent=2, ensure_ascii=False)


print(f"Collected {len(repositories)} GitHub repositories.")