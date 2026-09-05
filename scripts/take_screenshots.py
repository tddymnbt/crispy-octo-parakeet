import json
import os
import sys
from playwright.sync_api import sync_playwright

TOP3_FILE = "output/top3.json"
SCREENSHOT_DIR = "output/screenshots"

# Standard Facebook Square Post Dimension
FB_WIDTH = 1080
FB_HEIGHT = 1080


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
    print(" PHASE 3: PLAYWRIGHT SCREENSHOTS (1080x1080 FB CROPPED)")
    print("======================================")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": FB_WIDTH, "height": 1200},
            color_scheme="dark",
            device_scale_factor=1,
        )
        page = context.new_page()

        for repo in top_repositories:
            rank = repo.get("rank")
            repo_name = repo.get("name")
            url = f"https://github.com/{repo_name}"

            safe_name = repo_name.replace("/", "_")
            output_path = os.path.join(SCREENSHOT_DIR, f"{rank}_{safe_name}.png")

            print(f"Capturing [{rank}] {repo_name} -> {output_path}...")

            try:
                page.goto(url, wait_until="networkidle", timeout=30000)

                # Remove sticky top bars to keep the image clean
                page.evaluate(
                    """() => {
                    const selectors = ['.js-cookie-consent-banner', 'header', 'nav', '.AppHeader'];
                    selectors.forEach(s => {
                        const el = document.querySelector(s);
                        if (el) el.remove();
                    });
                }"""
                )

                # Look for README container
                readme_element = (
                    page.query_selector("#readme")
                    or page.query_selector("article.markdown-body")
                    or page.query_selector(".markdown-body")
                )

                if readme_element:
                    box = readme_element.bounding_box()
                    if box:
                        # Capture top 1080x1080 section of the README
                        page.screenshot(
                            path=output_path,
                            clip={
                                "x": box["x"],
                                "y": box["y"],
                                "width": FB_WIDTH,
                                "height": FB_HEIGHT,
                            },
                        )
                        print(f"  Captured cropped 1080x1080 README: {output_path}")
                    else:
                        page.screenshot(
                            path=output_path,
                            clip={"x": 0, "y": 0, "width": FB_WIDTH, "height": FB_HEIGHT},
                        )
                else:
                    # Fallback: Scroll 350px past file tree and crop 1080x1080
                    page.evaluate("window.scrollBy(0, 350)")
                    page.wait_for_timeout(1000)
                    page.screenshot(
                        path=output_path,
                        clip={"x": 0, "y": 0, "width": FB_WIDTH, "height": FB_HEIGHT},
                    )
                    print(f"  Fallback 1080x1080 screenshot captured: {output_path}")

            except Exception as e:
                print(f"  Failed to capture {repo_name}: {e}")

        browser.close()

    print("======================================")
    print(f" Screenshots complete. Output directory: {SCREENSHOT_DIR}")
    print("======================================")


if __name__ == "__main__":
    main()