import json
import os
import sys
from playwright.sync_api import sync_playwright

TOP3_FILE = "output/top3.json"
SCREENSHOT_DIR = "output/screenshots"

# Facebook Standard Portrait Dimensions (4:5 ratio)
VIEWPORT_WIDTH = 1080
VIEWPORT_HEIGHT = 1350


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
    print(" PHASE 3: PLAYWRIGHT SCREENSHOTS (READABLE README PORTRAIT)")
    print("======================================")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
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

                # Remove sticky top navigation bars and cookie popups
                page.evaluate(
                    """() => {
                    const selectors = ['.js-cookie-consent-banner', 'header', 'nav', '.AppHeader', '.js-header-wrapper'];
                    selectors.forEach(s => {
                        const el = document.querySelector(s);
                        if (el) el.remove();
                    });
                }"""
                )

                # Locate README or main content section
                readme_locator = (
                    page.locator("#readme")
                    or page.locator("article.markdown-body")
                    or page.locator(".repository-content")
                )

                if readme_locator.count() > 0:
                    readme = readme_locator.first
                    readme.scroll_into_view_if_needed()
                    page.wait_for_timeout(1000)

                    # Add padding around markdown body for clean margins on Facebook
                    page.evaluate(
                        """() => {
                        const target = document.querySelector('#readme') || document.querySelector('article.markdown-body');
                        if (target) {
                            target.style.padding = '24px';
                            target.style.borderRadius = '8px';
                            target.style.backgroundColor = '#0d1117';
                        }
                    }"""
                    )

                    # Get bounding box of README element
                    box = readme.bounding_box()
                    if box:
                        # Capture up to 1350px height so the text is fully readable and naturally framed
                        capture_height = min(box["height"], VIEWPORT_HEIGHT)
                        page.screenshot(
                            path=output_path,
                            clip={
                                "x": box["x"],
                                "y": box["y"],
                                "width": VIEWPORT_WIDTH,
                                "height": capture_height,
                            },
                        )
                        print(f"  Captured clean README section: {output_path}")
                    else:
                        page.screenshot(path=output_path, full_page=False)
                else:
                    # Fallback: Scroll past the main file navigation bar
                    page.evaluate("window.scrollBy(0, 300)")
                    page.wait_for_timeout(1000)
                    page.screenshot(path=output_path, full_page=False)
                    print(f"  Fallback scrolled screenshot captured: {output_path}")

            except Exception as e:
                print(f"  Failed to capture {repo_name}: {e}")

        browser.close()

    print("======================================")
    print(f" Screenshots complete. Output directory: {SCREENSHOT_DIR}")
    print("======================================")


if __name__ == "__main__":
    main()