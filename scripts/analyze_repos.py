import base64
import json
import os
import urllib.error
import urllib.request

TOP5_FILE = "output/top5.json"
OUTPUT_FILE = "output/research_details.json"
API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"

# Keys are read lazily inside main() so the module can be imported for tests
# without environment variables being present.
API_KEY = os.environ.get("GEMINI_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

MODEL = "gemini-3.5-flash-lite"

_JSON_CONTROL_ESCAPES = {
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}

# Extra instruction sent on a bounded retry when the first response could not
# be parsed. Reinforces strict JSON output without changing the schema.
_STRICT_JSON_RETRY_HINT = """
IMPORTANT: Your previous response could not be parsed as JSON.
Return ONLY valid JSON with the exact structure requested above.
Do not use Markdown fences like ``` or ```json.
Do not include any commentary, headings, or surrounding text.
All strings must use valid JSON escaping.
Never emit unescaped backslashes inside JSON strings; escape a literal
backslash as \\\\.
"""


class GeminiJsonParseError(Exception):
    """Raised when a Gemini response cannot be parsed as JSON."""

    def __init__(self, message, snippet=""):
        super().__init__(message)
        self.snippet = snippet


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
    prompt = f"""
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

STRICT JSON REQUIREMENTS:
- Return ONLY valid JSON. No Markdown.
- Do not use code fences like ``` or ```json.
- Do not include any commentary, headings, or prose before or after the JSON.
- All strings must use valid JSON escaping.
- Never emit unescaped backslashes inside JSON strings. If you need a literal
  backslash (for example in a regex or a Windows path), write it as \\\\.
- For emphasis, spell out words or use plain text; do not use Markdown such as
  **bold** or `code`.
"""
    return prompt


def strip_code_fences(text):
    """Remove a leading/trailing Markdown code fence around a JSON payload.

    Handles ```, ```json, ```text and ~~~ style fences, with or without a
    language tag, plus a leading byte-order mark.
    """
    cleaned = text.lstrip("\ufeff").strip()
    lines = cleaned.splitlines()
    if not lines:
        return cleaned
    first = lines[0].strip()
    if first.startswith("```") or first.startswith("~~~"):
        opener = first[:3]
        lines = lines[1:]
        if lines and lines[-1].strip().startswith(opener):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def extract_json_candidate(text):
    """Extract the first balanced JSON object/array from surrounding prose.

    Returns the substring spanning the first '{' or '[' through its matching
    close, respecting nested structures and the contents of quoted strings
    (including escaped quotes). Returns None when no structural start exists.
    """
    stripped = text.lstrip()
    if not stripped:
        return None

    open_idx = None
    brace_idx = stripped.find("{")
    bracket_idx = stripped.find("[")
    if brace_idx != -1 and (bracket_idx == -1 or brace_idx < bracket_idx):
        open_idx = brace_idx
    elif bracket_idx != -1:
        open_idx = bracket_idx
    if open_idx is None:
        return None

    opener = stripped[open_idx]
    closer = "}" if opener == "{" else "]"

    in_string = False
    escaped = False
    depth = 0
    for i in range(open_idx, len(stripped)):
        ch = stripped[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return stripped[open_idx : i + 1]
    return None


def _escape_control(ch):
    """Return a JSON-valid escape for an illegal raw control character."""
    mapped = _JSON_CONTROL_ESCAPES.get(ch)
    if mapped is not None:
        return mapped
    return "\\u{:04x}".format(ord(ch))


def repair_invalid_json_escapes(text):
    """Repair invalid JSON string escapes while preserving valid ones.

    Operates ONLY inside JSON string literals (tracked by the scan). Valid
    escapes (\\", \\\\, \\/, \\b, \\f, \\n, \\r, \\t, \\uXXXX) are kept
    verbatim. An invalid escape such as \\_, \\(, \\d, or a Windows-style
    path separator is made safe by escaping the backslash (\\X -> \\\\X), which
    preserves the originally intended characters without removing content.
    Raw control characters inside strings are likewise escaped.
    """
    result = []
    in_string = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if not in_string:
            if ch == '"':
                result.append(ch)
                in_string = True
            else:
                result.append(ch)
            i += 1
            continue

        if ch == '"':
            result.append(ch)
            in_string = False
            i += 1
            continue

        if ch == "\\":
            if i + 1 >= n:
                # Trailing lone backslash inside a string: escape it.
                result.append("\\\\")
                i += 1
                continue
            nxt = text[i + 1]
            if nxt == "u":
                hex_part = text[i + 2 : i + 6]
                if len(hex_part) == 4 and all(c in "0123456789abcdefABCDEF" for c in hex_part):
                    result.append("\\u" + hex_part)
                    i += 6
                    continue
                # Invalid \uXXXX: preserve the characters literally.
                result.append("\\\\")
                result.append("u")
                i += 2
                continue
            if nxt in '"\\/bfnrt':
                # Valid JSON escape: keep it exactly as-is.
                result.append("\\" + nxt)
                i += 2
                continue
            # Invalid escape: escape the backslash so the intended characters
            # survive (e.g. \_ -> \\_ parses as the literal text \_).
            result.append("\\\\")
            result.append(nxt)
            i += 2
            continue

        if ord(ch) < 0x20:
            result.append(_escape_control(ch))
        else:
            result.append(ch)
        i += 1

    return "".join(result)


def _response_region(text, error, span=60):
    """Return a short single-line window around the reported error position."""
    pos = getattr(error, "pos", None)
    if pos is None or not isinstance(text, str):
        return ""
    start = max(0, pos - span)
    end = min(len(text), pos + span)
    return text[start:end].replace("\n", "\\n")


def log_parse_failure(repo_name, attempt, raw_text, error):
    """Log a parse failure with a bounded, secret-free diagnostic excerpt."""
    print(
        "[WARN] JSON parsing failed for {} (attempt {}): {}: {}".format(
            repo_name,
            attempt,
            type(error).__name__,
            error,
        )
    )
    excerpt = raw_text[:320].replace("\n", "\\n")
    print("[WARN]   response excerpt: {}".format(excerpt))
    region = _response_region(raw_text, error)
    if region:
        print("[WARN]   around error position: {}".format(region))


def parse_json(text):
    """Parse a Gemini JSON response through a layered repair pipeline.

    Strategy order: plain loads -> strip Markdown fences -> extract balanced
    JSON candidate -> repair invalid escapes -> loads. Valid JSON is returned
    exactly as-is (no transformation). Raises GeminiJsonParseError on failure.
    """
    cleaned = strip_code_fences(text)

    candidates = [cleaned]
    extracted = extract_json_candidate(cleaned)
    if extracted is not None and extracted != cleaned:
        candidates.append(extracted)

    for candidate in list(candidates):
        repaired = repair_invalid_json_escapes(candidate)
        if repaired not in candidates:
            candidates.append(repaired)

    last_error = None
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError) as error:
            last_error = error

    snippet = _response_region(candidates[-1], last_error)
    raise GeminiJsonParseError(
        "Could not parse Gemini response as JSON: {}: {}".format(
            type(last_error).__name__, last_error
        ),
        snippet=snippet,
    ) from last_error


def build_fallback_analysis(repo_info):
    """Return a schema-compatible neutral analysis for an unparseable response.

    No meaningful repository analysis is invented; all fields are empty. The
    ``analysis_status`` key marks the result as degraded so downstream code and
    logs can tell a real analysis apart from a fallback.
    """
    return {
        "name": repo_info["name"],
        "headline_hook": "",
        "core_functionality": "",
        "key_features": [],
        "target_audience": "",
        "practical_developer_value": "",
        "suggested_use_cases": [],
        "analysis_status": "degraded",
    }


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


def _extract_analysis(repo_name, prompt):
    """Run the parse pipeline with a single bounded retry for bad JSON."""
    try:
        raw_text = extract_text(call_gemini(prompt))
    except Exception as error:
        print(
            "[WARN] Gemini request failed for {} (attempt 1): {}: {}".format(
                repo_name, type(error).__name__, error
            )
        )
    else:
        try:
            return parse_json(raw_text)
        except GeminiJsonParseError as error:
            log_parse_failure(repo_name, attempt=1, raw_text=raw_text, error=error)

    try:
        raw_text = extract_text(call_gemini(prompt + _STRICT_JSON_RETRY_HINT))
    except Exception as error:
        print(
            "[WARN] Gemini retry failed for {}: {}: {}".format(
                repo_name, type(error).__name__, error
            )
        )
        return None

    try:
        return parse_json(raw_text)
    except GeminiJsonParseError as error:
        log_parse_failure(repo_name, attempt=2, raw_text=raw_text, error=error)
        return None


def analyze_repository(repo):
    """Analyze one repository in isolation so callers can continue on failure."""
    repo_name = repo["name"]
    readme_text = fetch_readme(repo_name)
    prompt = build_analysis_prompt(repo, readme_text)
    analysis = _extract_analysis(repo_name, prompt)
    if analysis is None:
        print("[WARN] Using degraded fallback analysis for {}.".format(repo_name))
        analysis = build_fallback_analysis(repo)
    return {**repo, "deep_analysis": analysis}


def main():
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not available")

    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN is not available")

    if not os.path.exists(TOP5_FILE):
        raise RuntimeError(f"Missing {TOP5_FILE}. Run the ranking phase first.")

    with open(TOP5_FILE, encoding="utf-8") as f:
        top5_data = json.load(f)

    top_repositories = top5_data.get("top_repositories", [])
    if len(top_repositories) != 5:
        raise RuntimeError("Expected exactly 5 repositories in output/top5.json.")
    analyzed_repositories = []

    print("======================================")
    print(" PHASE 2C: DEEP REPOSITORY ANALYSIS")
    print("======================================")

    for repo in top_repositories:
        repo_name = repo["name"]
        print(f"\nAnalyzing README for: {repo_name}...")
        try:
            analyzed_repositories.append(analyze_repository(repo))
        except Exception as error:
            print(
                "[ERROR] Failed to analyze {}: {}: {}".format(
                    repo_name, type(error).__name__, error
                )
            )
            analyzed_repositories.append(
                {**repo, "deep_analysis": build_fallback_analysis(repo)}
            )

    output = {
        "generated_at": top5_data.get("generated_at"),
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