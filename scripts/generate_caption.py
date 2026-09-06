"""Generate one Facebook-ready caption for each of the five selected repositories."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request


RESEARCH_FILE = Path("output/research_details.json")
OUTPUT_FILE = Path("output/captions.json")
API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
MODEL = "gemini-3.5-flash-lite"


def require_api_key():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not available")
    return api_key


def build_caption_prompt(item):
    analysis = item.get("deep_analysis", {})
    return f"""
You are an expert tech social-media marketer writing one Facebook post for
software developers, AI engineers, and tech enthusiasts.

Write one high-converting, repository-specific caption using this research:

Repository: {item['name']}
Repository URL: https://github.com/{item['name']}
Rank: {item['rank']}
Hook: {analysis.get('headline_hook', '')}
Problem solved: {analysis.get('core_functionality', '')}
Key features: {', '.join(analysis.get('key_features', []))}
Target audience: {analysis.get('target_audience', '')}
Developer value: {analysis.get('practical_developer_value', '')}
Use cases: {', '.join(analysis.get('suggested_use_cases', []))}

Requirements:
- Include a catchy hook, the problem it solves, notable features, the direct
  GitHub link, a call to action, and relevant hashtags.
- Tailor it specifically to this repository; do not mention other repositories.
- Use clean line breaks, emojis, and plain-text emphasis where useful.
- Do not use Markdown syntax such as **bold** or ## headings.

Return ONLY the raw caption text ready for Facebook.
"""


def call_gemini(prompt, api_key):
    payload = {"model": MODEL, "input": prompt}
    api_request = request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with request.urlopen(api_request, timeout=90) as response:
            return json.load(response)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini API request failed ({exc.code}): {body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach Gemini API: {exc.reason}") from exc


def extract_text(response):
    return "".join(
        content.get("text", "")
        for step in response.get("steps", [])
        if step.get("type") == "model_output"
        for content in step.get("content", [])
        if content.get("type") == "text"
    ).strip()


def main():
    if not RESEARCH_FILE.is_file():
        raise RuntimeError(f"Missing {RESEARCH_FILE}. Run the analysis phase first.")

    research_data = json.loads(RESEARCH_FILE.read_text(encoding="utf-8"))
    repositories = research_data.get("repositories", [])
    ranks = [item.get("rank") for item in repositories]
    if len(repositories) != 5 or sorted(ranks) != [1, 2, 3, 4, 5]:
        raise RuntimeError("Research data must contain exactly one repository for each rank 1-5.")

    api_key = require_api_key()
    posts = []
    print("Generating five repository-specific Facebook captions...")
    for item in sorted(repositories, key=lambda repository: repository["rank"]):
        print(f"  Generating caption for #{item['rank']}: {item['name']}")
        caption = extract_text(call_gemini(build_caption_prompt(item), api_key))
        if not caption:
            raise RuntimeError(f"Gemini generated an empty caption for {item['name']}.")
        posts.append({"rank": item["rank"], "repo_name": item["name"], "caption": caption})

    output = {"generated_at": datetime.now(timezone.utc).isoformat(), "posts": posts}
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved {len(posts)} captions to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
