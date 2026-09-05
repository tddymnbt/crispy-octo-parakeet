import json
import os
import urllib.error
import urllib.request

API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not available")

MODEL = "gemini-2.5-flash"

URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{MODEL}:generateContent?key={API_KEY}"
)

payload = {
    "contents": [
        {
            "parts": [
                {
                    "text": (
                        "You are the AI research engine for a GitHub "
                        "daily trending repository system. "
                        "Reply with exactly: AI CONNECTION SUCCESS"
                    )
                }
            ]
        }
    ]
}

request = urllib.request.Request(
    URL,
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(request) as response:
        data = json.load(response)

except urllib.error.HTTPError as error:
    body = error.read().decode("utf-8", errors="replace")
    print(body)
    raise

text = (
    data["candidates"][0]["content"]["parts"][0]["text"]
)

print("======================================")
print(" AI CONNECTION TEST")
print("======================================")
print(f"Model: {MODEL}")
print(f"Response: {text}")
print("======================================")