import json
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = "https://api.github.com/search/repositories"

TOKEN = os.environ.get("GITHUB_TOKEN")

if not TOKEN:
    raise RuntimeError("GITHUB_TOKEN is not available")


now = datetime.now(timezone.utc)

# GitHub repository search accepts date-based filters.
recent_date = (now - timedelta(days=2)).strftime("%Y-%m-%d")
created_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")


headers = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "github-daily-agent",
}


def search_repositories(query, sort="stars", per_page=20):
    params = {
        "q": query,
        "sort": sort,
        "order": "desc",
        "per_page": per_page,
    }

    url = f"{API_URL}?{urlencode(params)}"

    request = Request(url, headers=headers)

    with urlopen(request) as response:
        data = json.load(response)

    return data.get("items", [])


# ---------------------------------------------------------
# POOL A
# Recently active repositories
# ---------------------------------------------------------

pool_recent_activity = search_repositories(
    f"pushed:>={recent_date} "
    "archived:false "
    "fork:false",
    sort="stars",
    per_page=20,
)


# ---------------------------------------------------------
# POOL B
# Recently created repositories
# ---------------------------------------------------------

pool_recently_created = search_repositories(
    f"created:>={created_date} "
    "archived:false "
    "fork:false",
    sort="stars",
    per_page=20,
)


# ---------------------------------------------------------
# POOL C
# Popular + recently active
# ---------------------------------------------------------

pool_popular_active = search_repositories(
    f"pushed:>={recent_date} "
    "stars:>=100 "
    "archived:false "
    "fork:false",
    sort="stars",
    per_page=20,
)


# ---------------------------------------------------------
# POOL D
# Emerging repositories
# ---------------------------------------------------------

pool_emerging = search_repositories(
    f"created:>={created_date} "
    "stars:>=10 "
    "archived:false "
    "fork:false",
    sort="stars",
    per_page=20,
)


# ---------------------------------------------------------
# Combine and deduplicate
# ---------------------------------------------------------

all_repositories = (
    pool_recent_activity
    + pool_recently_created
    + pool_popular_active
    + pool_emerging
)


unique_repositories = {}

for repo in all_repositories:
    unique_repositories[repo["full_name"]] = repo


# ---------------------------------------------------------
# Convert to our normalized format
# ---------------------------------------------------------

repositories = []

for repo in unique_repositories.values():

    repositories.append(
        {
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


# Sort initially by stars.
# AI will perform the actual qualitative ranking later.
repositories.sort(
    key=lambda repo: repo["stars"],
    reverse=True,
)


# ---------------------------------------------------------
# Output
# ---------------------------------------------------------

output = {
    "generated_at": now.isoformat(),

    "collection_window": {
        "recent_activity_since": recent_date,
        "recently_created_since": created_date,
    },

    "pool_counts": {
        "recent_activity": len(pool_recent_activity),
        "recently_created": len(pool_recently_created),
        "popular_active": len(pool_popular_active),
        "emerging": len(pool_emerging),
    },

    "candidate_count": len(repositories),

    "repositories": repositories,
}


os.makedirs("output", exist_ok=True)

with open(
    "output/candidates.json",
    "w",
    encoding="utf-8",
) as file:
    json.dump(
        output,
        file,
        indent=2,
        ensure_ascii=False,
    )


print("======================================")
print(" GitHub Daily Candidate Collection")
print("======================================")

print(
    f"Recent activity:   {len(pool_recent_activity)}"
)

print(
    f"Recently created:  {len(pool_recently_created)}"
)

print(
    f"Popular + active:  {len(pool_popular_active)}"
)

print(
    f"Emerging:          {len(pool_emerging)}"
)

print("--------------------------------------")

print(
    f"Unique candidates: {len(repositories)}"
)

print("======================================")