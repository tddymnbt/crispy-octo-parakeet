import json
import os
import sys
from playwright.sync_api import sync_playwright

TOP3_FILE = "output/top3.json"
SCREENSHOT_DIR = "output/screenshots"


def main():
    if not os.path.exists(TOP3_FILE):
        print(f"Error: {TOP3_FILE} not found. Run Phase 2B first.")
        sys.exit(1)

    with open(TOP3_FILE, encoding="utf-8") as f:
        data = json.load(f)

    top_repositories = data.get("top_repositories", [])
    if not top_repositories:
        print("No top repositories found in top3.json.")
        sys.exit(1)

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    print("======================================")
    print(" PHASE 3: PLAYWRIGHT SCREENSHOTS")
    print("======================================")

    with sync_playwright() as p:
        # Launch headless Chromium with desktop viewport dimensions
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            color_scheme="dark",  # GitHub dark mode looks clean in social posts
        )
        page = context.new_page()

        for repo in top_repositories:
            rank = repo.get("rank")
            repo_name = repo.get("name")
            url = f"https://github.com/{repo_name}"

            # Sanitize filename (e.g., owner_repo.png)
            safe_name = repo_name.replace("/", "_")
            output_path = os.path.join(SCREENSHOT_DIR, f"{rank}_{safe_name}.png")

            print(f"Capturing [{rank}] {repo_name} -> {output_path}...")

            try:
                page.goto(url, wait_until="networkidle", timeout=30000)

                # Dismiss cookie banners or popups if present
                page.evaluate(
                    """() => {
                    const selectors = ['.js-cookie-consent-banner', 'header'];
                    selectors.forEach(s => {
                        const el = document.querySelector(s);
                        if (el) el.remove();
                    });
                }"""
                )

                # Capture viewport-sized screenshot
                page.screenshot(path=output_path, full_page=False)
                print(f"  Saved screenshot: {output_path}")

            except Exception as e:
                print(f"  Failed to capture {repo_name}: {e}")

        browser.close()

    print("======================================")
    print(f" Screenshots complete. Output directory: {SCREENSHOT_DIR}")
    print("======================================")


if __name__ == "__main__":
    main()