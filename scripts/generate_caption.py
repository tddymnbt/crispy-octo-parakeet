import json
import os
import urllib.error
import urllib.request

RESEARCH_FILE = "output/research_details.json"
OUTPUT_FILE = "output/facebook_caption.txt"
API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"

API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not available")

MODEL = "gemini-3.5-flash-lite"


def build_caption_prompt(research_data):
    repo_summaries = []

    for item in research_data.get("repositories", []):
        analysis = item.get("deep_analysis", {})
        repo_summaries.append(
            f"""
Repository: {item['name']}
Score: {item.get('score', 'N/A')}/100
URL: https://github.com/{item['name']}
Hook: {analysis.get('headline_hook', '')}
Core Functionality: {analysis.get('core_functionality', '')}
Target Audience: {analysis.get('target_audience', '')}
Developer Value: {analysis.get('practical_developer_value', '')}
Key Features: {', '.join(analysis.get('key_features', []))}
Suggested Use Cases: {', '.join(analysis.get('suggested_use_cases', []))}
"""
        )

    all_repos_text = "\n---\n".join(repo_summaries)

    return f"""
You are an expert tech social media marketer writing a Facebook post for software developers, AI engineers, and tech enthusiasts.

Write an engaging, clear, and informative Facebook post featuring today's Top 3 GitHub Repositories based on the research provided below.

Requirements for the post:
1. Attention-grabbing Headline/Hook with emojis.
2. Concise breakdown for each of the 3 repositories:
   - Name & Star Rank/Score
   - What it does & why it matters
   - Key developer benefit
   - Direct Link (https://github.com/owner/repo)
3. A brief summary/conclusion asking an engaging question to prompt comments.
4. Relevant hashtags (e.g., #GitHub #OpenSource #SoftwareEngineering #DevTools #Coding).

Formatting guidelines:
- Use clean line breaks and emojis to make it scannable.
- Do NOT use Markdown formatting like bold `**` or headers `##` because Facebook text posts render raw Markdown as plain asterisks.
- Use plain text formatting with CAPITAL LETTERS or emoji bullet points for emphasis.

Here is the research data:

{all_repos_text}

Return ONLY the raw post caption text ready to copy-paste or post via API.
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


def main():
    if not os.path.exists(RESEARCH_FILE):
        raise RuntimeError(f"Missing {RESEARCH_FILE}. Run Phase 2C first.")

    with open(RESEARCH_FILE, encoding="utf-8") as f:
        research_data = json.load(f)

    print("======================================")
    print(" PHASE 2D: GENERATING FACEBOOK CAPTION")
    print("======================================")

    prompt = build_caption_prompt(research_data)
    response = call_gemini(prompt)
    caption = extract_text(response)

    if not caption:
        raise RuntimeError("Gemini generated an empty caption.")

    os.makedirs("output", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(caption)

    print("\n--------------------------------------")
    print(" GENERATED CAPTION PREVIEW:")
    print("--------------------------------------")
    print(caption[:500] + ("\n..." if len(caption) > 500 else ""))
    print("--------------------------------------")
    print(f"\nSaved to {OUTPUT_FILE}")
    print("======================================")


if __name__ == "__main__":
    main()