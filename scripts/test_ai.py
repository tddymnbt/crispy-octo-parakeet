import json
import os
import urllib.error
import urllib.request

API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not available")

MODEL = "gemini-3.5-flash-lite"

URL = (
    "https://generativelanguage.googleapis.com/v1beta/interactions"
)

payload = {
    "model": MODEL,
    "input": (
        "You are the AI research engine for a GitHub "
        "daily trending repository system. "
        "Reply with exactly: AI CONNECTION SUCCESS"
    ),
}

request = urllib.request.Request(
    URL,
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "x-goog-api-key": API_KEY,
    },
    method="POST",
)

try:
    with urllib.request.urlopen(request) as response:
        data = json.load(response)

except urllib.error.HTTPError as error:
    body = error.read().decode("utf-8", errors="replace")

    print("======================================")
    print(" GEMINI API ERROR")
    print("======================================")
    print(body)
    print("======================================")

    raise

output_text = ""

for step in data.get("steps", []):
    if step.get("type") != "model_output":
        continue

    for content in step.get("content", []):
        if content.get("type") == "text":
            output_text += content.get("text", "")

print("======================================")
print(" AI CONNECTION TEST")
print("======================================")
print(f"Model: {MODEL}")
print(f"Response: {output_text.strip()}")
print("======================================")

if "AI CONNECTION SUCCESS" not in output_text:
    raise RuntimeError(
        "Gemini responded, but the expected test response was not found."
    )