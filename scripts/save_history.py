import json
import os
from datetime import datetime, timezone


INPUT_FILE = "output/candidates.json"
HISTORY_DIR = "data/history"


if not os.path.exists(INPUT_FILE):
    raise RuntimeError(
        f"Input file not found: {INPUT_FILE}"
    )


with open(INPUT_FILE, encoding="utf-8") as file:
    data = json.load(file)


now = datetime.now(timezone.utc)

date_string = now.strftime("%Y-%m-%d")

os.makedirs(HISTORY_DIR, exist_ok=True)

history_file = os.path.join(
    HISTORY_DIR,
    f"{date_string}.json",
)


snapshot = {
    "snapshot_date": date_string,
    "generated_at": now.isoformat(),

    "candidate_count": data["candidate_count"],

    "repositories": [
        {
            "name": repo["name"],
            "url": repo["url"],
            "stars": repo["stars"],
            "forks": repo["forks"],
            "language": repo["language"],
            "created_at": repo["created_at"],
            "updated_at": repo["updated_at"],
            "pushed_at": repo["pushed_at"],
        }
        for repo in data["repositories"]
    ],
}


with open(
    history_file,
    "w",
    encoding="utf-8",
) as file:
    json.dump(
        snapshot,
        file,
        indent=2,
        ensure_ascii=False,
    )


print("======================================")
print(" Historical Snapshot")
print("======================================")
print(f"Date:        {date_string}")
print(f"Repositories: {len(snapshot['repositories'])}")
print(f"File:        {history_file}")
print("======================================")