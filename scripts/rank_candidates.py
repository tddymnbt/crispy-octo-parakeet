import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

CANDIDATES_FILE = "output/candidates.json"
HISTORY_DIR = "data/history"

API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/interactions"
)

API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not available")

MODEL = "gemini-3.5-flash-lite"


def load_candidates():
    with open(CANDIDATES_FILE, encoding="utf-8") as file:
        return json.load(file)


def load_previous_snapshot():
    today = datetime.now(timezone.utc).date()

    history_files = []

    if os.path.exists(HISTORY_DIR):
        for filename in os.listdir(HISTORY_DIR):
            if filename.endswith(".json"):
                history_files.append(filename)

    history_files.sort(reverse=True)

    for filename in history_files:
        try:
            date = datetime.strptime(
                filename.removesuffix(".json"),
                "%Y-%m-%d",
            ).date()
        except ValueError:
            continue

        if date < today:
            with open(
                os.path.join(HISTORY_DIR, filename),
                encoding="utf-8",
            ) as file:
                return json.load(file)

    return None


def calculate_momentum(candidates, previous_snapshot):
    if not previous_snapshot:
        return candidates

    previous_by_name = {
        repo["name"]: repo
        for repo in previous_snapshot.get("repositories", [])
    }

    for repo in candidates:
        previous = previous_by_name.get(repo["name"])

        if previous:
            repo["star_growth"] = max(
                0,
                repo["stars"] - previous.get("stars", repo["stars"]),
            )

            repo["fork_growth"] = max(
                0,
                repo["forks"] - previous.get("forks", repo["forks"]),
            )
        else:
            repo["star_growth"] = 0
            repo["fork_growth"] = 0

    return candidates


def build_prompt(candidates):
    candidate_data = []

    for repo in candidates:
        candidate_data.append(
            {
                "name": repo["name"],
                "url": repo["url"],
                "description": repo["description"],
                "stars": repo["stars"],
                "forks": repo["forks"],
                "star_growth": repo.get("star_growth", 0),
                "fork_growth": repo.get("fork_growth", 0),
                "language": repo["language"],
                "topics": repo["topics"],
                "created_at": repo["created_at"],
                "updated_at": repo["updated_at"],
                "pushed_at": repo["pushed_at"],
            }
        )

    candidates_json = json.dumps(
        candidate_data,
        indent=2,
        ensure_ascii=False,
    )

    return f"""
You are the ranking engine for a daily GitHub repository
research and social-media content system.

Your job is to select the TOP 3 repositories from the supplied
candidate pool.

Do NOT simply select the repositories with the most stars.

Evaluate each repository using:

1. Current popularity
2. Star momentum
3. Fork momentum
4. Recent development activity
5. Novelty
6. Practical developer usefulness
7. Technical significance
8. AI/technology relevance
9. Emerging-project potential
10. Potential interest to a developer audience

A repository with fewer total stars can outrank a famous repository
if it has substantially stronger momentum, usefulness, novelty, or
developer interest.

Avoid:
- obvious spam
- empty repositories
- forks when the original project is available
- inactive repositories
- repositories with little meaningful value
- selecting multiple repositories that are essentially the same type
  unless there is a strong reason

Aim for a diverse and interesting daily Top 3.

For each selected repository provide:

- rank
- repository name
- score from 0 to 100
- concise reason for selection
- why it is interesting today
- why developers should care
- momentum assessment
- novelty assessment

Return ONLY valid JSON.

Use exactly this structure:

{{
  "top_repositories": [
    {{
      "rank": 1,
      "name": "owner/repository",
      "score": 95,
      "reason": "...",
      "why_interesting_today": "...",
      "why_developers_should_care": "...",
      "momentum": "...",
      "novelty": "..."
    }}
  ]
}}

Candidate repositories:

{candidates_json}
"""


def call_gemini(prompt):
    payload = {
        "model": MODEL,
        "input": prompt,
    }

    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": API_KEY,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request) as response:
            return json.load(response)

    except urllib.error.HTTPError as error:
        body = error.read().decode(
            "utf-8",
            errors="replace",
        )

        print("======================================")
        print(" GEMINI API ERROR")
        print("======================================")
        print(body)
        print("======================================")

        raise


def extract_text(response):
    text = ""

    for step in response.get("steps", []):
        if step.get("type") != "model_output":
            continue

        for content in step.get("content", []):
            if content.get("type") == "text":
                text += content.get("text", "")

    return text.strip()


def parse_json(text):
    cleaned = text.strip()

    if cleaned.startswith("```"):
        lines = cleaned.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        cleaned = "\n".join(lines)

    return json.loads(cleaned)


def main():
    data = load_candidates()

    candidates = data.get("repositories", [])

    if not candidates:
        raise RuntimeError(
            "No candidate repositories found."
        )

    previous_snapshot = load_previous_snapshot()

    candidates = calculate_momentum(
        candidates,
        previous_snapshot,
    )

    prompt = build_prompt(candidates)

    print("======================================")
    print(" AI REPOSITORY RANKING")
    print("======================================")
    print(f"Candidates: {len(candidates)}")
    print(f"Model:      {MODEL}")
    print(
        "Previous snapshot:",
        "available" if previous_snapshot else "not available",
    )
    print()

    response = call_gemini(prompt)

    text = extract_text(response)

    if not text:
        raise RuntimeError(
            "Gemini returned no text."
        )

    ranking = parse_json(text)

    top_repositories = ranking.get(
        "top_repositories",
        [],
    )

    if len(top_repositories) != 3:
        raise RuntimeError(
            "AI did not return exactly 3 repositories."
        )

    os.makedirs("output", exist_ok=True)

    with open(
        "output/top3.json",
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            ranking,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print("======================================")
    print(" TOP 3")
    print("======================================")

    for repo in top_repositories:
        print(
            f"{repo['rank']}. "
            f"{repo['name']} "
            f"({repo['score']}/100)"
        )
        print(
            f"   {repo['reason']}"
        )
        print()

    print("Saved: output/top3.json")
    print("======================================")


if __name__ == "__main__":
    main()