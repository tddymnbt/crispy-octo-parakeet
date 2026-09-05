import base64
import json
import os
import urllib.error
import urllib.request

TOP3_FILE = "output/top3.json"
OUTPUT_FILE = "output/research_details.json"
API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"

API_KEY = os.environ.get("GEMINI_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not available")

if not GITHUB_TOKEN:
    raise RuntimeError("GITHUB_TOKEN is not available")

MODEL = "gemini-3.6-flash"


def fetch_readme(repo_name):
    """Fetch and decode the raw README markdown from GitHub API."""
    url = f"https://api.github.com/repos/{repo_name}/readme"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "github-daily-agent",
        },
    )

    try:
        with urllib.request.urlopen(request) as response:
            data = json.load(response)
            content = data.get("content", "")
            encoding = data.get("encoding", "")

            if encoding == "base64":
                decoded_bytes = base64.b64decode(content)
                # Truncate README to avoid excessive token sizes
                return decoded_bytes.decode("utf-8", errors="replace")[:10000]
            return content[:10000]
    except urllib.error.HTTPError as error:
        print(f"Warning: Could not fetch README for {repo_name} (HTTP {error.code})")
        return "No README available."


def build_analysis_prompt(repo_info, readme_text):
    return f"""
You are an expert technical content researcher analyzing GitHub repositories for a software developer audience.

Analyze the following repository and its README documentation:

Repository Name: {repo_info['name']}
Selection Reason: {repo_info.get('reason', '')}
Why Interesting Today: {repo_info.get('why_interesting_today', '')}

--- README PREVIEW ---
{readme_text}
--- END README PREVIEW ---

Provide a structured, deep analysis explaining:
1. Core Functionality: What problem does this project solve?
2. Key Features: Top 3-4 notable technical capabilities.
3. Target Audience: Who benefits most from using this (e.g., DevOps, AI engineers, frontend developers)?
4. Practical Developer Value: Why should a developer care, and how could they use it in a real-world project?
5. Content Hook: A compelling 1-sentence hook for a social media post.

Return ONLY valid JSON with this exact structure:

{{
  "name": "{repo_info['name']}",
  "headline_hook": "...",
  "core_functionality": "...",
  "key_features": [
    "...",
    "..."
  ],
  "target_audience": "...",
  "practical_developer_value": "...",
  "suggested_use_cases": [
    "...",
    "..."
  ]
}}
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
        body = error.read().decode("utf-8", errors="replace")
        print("GEMINI API ERROR:", body)
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
    if not os.path.exists(TOP3_FILE):
        raise RuntimeError(f"Missing {TOP3_FILE}. Run Phase 2B first.")

    with open(TOP3_FILE, encoding="utf-8") as f:
        top3_data = json.load(f)

    top_repositories = top3_data.get("top_repositories", [])
    analyzed_repositories = []

    print("======================================")
    print(" PHASE 2C: DEEP REPOSITORY ANALYSIS")
    print("======================================")

    for repo in top_repositories:
        repo_name = repo["name"]
        print(f"\nAnalyzing README for: {repo_name}...")

        readme_text = fetch_readme(repo_name)
        prompt = build_analysis_prompt(repo, readme_text)

        response = call_gemini(prompt)
        raw_text = extract_text(response)
        analysis = parse_json(raw_text)

        # Merge Phase 2B scoring with Phase 2C analysis
        merged_item = {**repo, "deep_analysis": analysis}
        analyzed_repositories.append(merged_item)

    output = {
        "generated_at": top3_data.get("generated_at"),
        "repositories": analyzed_repositories,
    }

    os.makedirs("output", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print("\n======================================")
    print(f" Analysis complete. Saved to {OUTPUT_FILE}")
    print("======================================")


if __name__ == "__main__":
    main()