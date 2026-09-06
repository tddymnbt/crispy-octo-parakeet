"""Capture GitHub READMEs and turn their strongest section into Facebook images.

The browser renders and saves a complete README. The final 4:5 framing is
chosen from that RAW image, never from fragile viewport clip coordinates.
"""

import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageStat
from playwright.sync_api import Locator, Page, sync_playwright

TOP3_FILE = Path("output/top3.json")
RAW_DIR = Path("output/screenshots/raw")
FINAL_DIR = Path("output/screenshots/final")
VIEWPORT = {"width": 1400, "height": 900}
FINAL_SIZE = (1080, 1350)
TARGET_RATIO = FINAL_SIZE[0] / FINAL_SIZE[1]


def safe_repo_name(repository: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", repository).strip("._") or "repository"


def first_meaningful_locator(page: Page) -> Locator | None:
    """Explicitly try selectors; Locator objects cannot be fallbacks via `or`."""
    for selector in ("#readme", "article.markdown-body", ".repository-content article", ".repository-content"):
        candidates = page.locator(selector)
        for index in range(candidates.count()):
            candidate = candidates.nth(index)
            try:
                text, box = candidate.inner_text(timeout=2_000).strip(), candidate.bounding_box()
                if box and box["width"] > 250 and box["height"] > 80 and len(text) > 30:
                    return candidate
            except Exception:
                continue
    return None


def prepare_page(page: Page, readme: Locator) -> list[dict]:
    """Remove only overlays/sticky UI and return README-relative landmarks."""
    page.evaluate("""() => {
        document.querySelectorAll('.js-cookie-consent-banner, [data-testid="cookie-banner"], [role="dialog"][aria-modal="true"]').forEach(el => el.remove());
        document.querySelectorAll('header, .AppHeader, .js-header-wrapper').forEach(el => {
          if (getComputedStyle(el).position === 'fixed' || getComputedStyle(el).position === 'sticky') el.remove();
        });
        document.documentElement.style.overflowX = 'hidden'; document.body.style.overflowX = 'hidden';
    }""")
    # Request lazy README images before taking its full element screenshot.
    return readme.evaluate("""async element => {
        const images = [...element.querySelectorAll('img')];
        images.forEach(image => { image.loading = 'eager'; });
        await Promise.all(images.map(async image => {
          if (!image.complete) await new Promise(resolve => {
            image.addEventListener('load', resolve, {once: true}); image.addEventListener('error', resolve, {once: true}); setTimeout(resolve, 5000);
          });
          try { await image.decode(); } catch (_) {}
        }));
        const root = element.getBoundingClientRect();
        return [...element.querySelectorAll('h1,h2,h3,p,img,pre,table,blockquote')].map(node => {
          const rect = node.getBoundingClientRect();
          return {tag: node.tagName, y: rect.top - root.top, height: rect.height, width: rect.width,
                  text: (node.innerText || node.alt || '').slice(0, 160)};
        }).filter(item => item.height > 0 && item.width > 0);
    }""")


def visual_density(image: Image.Image) -> float:
    """Flat backgrounds/whitespace score low; ink and varied images score high."""
    rgb = image.convert("RGB")
    difference = ImageChops.difference(rgb, Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))).convert("L")
    stat = ImageStat.Stat(difference)
    return stat.mean[0] + stat.var[0] ** 0.5 * 0.35


def semantic_score(landmarks: list[dict], start: int, end: int, image_width: int) -> float:
    """Favor headings/images/intro, avoid code and awkwardly split large images."""
    score = 0.0
    for item in landmarks:
        overlap = max(0, min(end, item["y"] + item["height"]) - max(start, item["y"]))
        if not overlap:
            continue
        coverage, tag, text = overlap / item["height"], item["tag"], item.get("text", "").lower()
        if tag in {"H1", "H2", "H3"}:
            score += 20 * coverage
        elif tag == "IMG":
            score += (18 + min(item["height"] / 30, 30)) * coverage
        elif tag == "P":
            score += 5 * coverage
        elif tag == "PRE":
            score -= min(28, item["height"] / 12) * coverage
        if any(word in text for word in ("installation", "install", "configuration", "license")):
            score -= 10 * coverage
        if item["height"] > 140 and overlap < item["height"] * 0.65:
            score -= 15
    # Intro gets a small tie-break preference, rather than a fixed top crop.
    return score + max(0, 8 - start / max(image_width, 1) * 0.25)


def choose_crop(raw_path: Path, landmarks: list[dict]) -> tuple[Image.Image, int, int, tuple[int, int]]:
    """Score vertical windows in the complete RAW image, crop, then resize."""
    with Image.open(raw_path) as source:
        image = source.convert("RGB")
    width, height = image.size
    crop_height = round(width / TARGET_RATIO)
    # Preserve a short README's full natural width by padding, never horizontal clipping.
    if height < crop_height:
        canvas = Image.new("RGB", (width, crop_height), image.getpixel((0, 0)))
        canvas.paste(image, (0, (crop_height - height) // 2))
        image, height = canvas, crop_height
    maximum_start = height - crop_height
    starts = sorted({round(maximum_start * index / 48) for index in range(49)} | {0, maximum_start})
    best_start, best_score = 0, float("-inf")
    for start in starts:
        end = start + crop_height
        score = visual_density(image.crop((0, start, width, end))) + semantic_score(landmarks, start, end, width)
        if score > best_score:
            best_start, best_score = start, score
    crop = image.crop((0, best_start, width, best_start + crop_height))
    return crop.resize(FINAL_SIZE, Image.Resampling.LANCZOS), best_start, best_start + crop_height, (width, height)


def main() -> None:
    if not TOP3_FILE.exists():
        sys.exit(f"Error: {TOP3_FILE} not found. Run Phase 2B first.")
    repositories = json.loads(TOP3_FILE.read_text(encoding="utf-8")).get("top_repositories", [])
    if not repositories:
        sys.exit("No top repositories found in top3.json.")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    successful = failed = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport=VIEWPORT, color_scheme="dark", device_scale_factor=1)
        page = context.new_page()
        for repo in repositories:
            rank, name = repo.get("rank"), repo.get("name")
            if not rank or not name:
                print(f"FAILED: {name or '<missing repository>'}\nReason: invalid top3.json record")
                failed += 1
                continue
            stem = f"{rank}_{safe_repo_name(name)}.png"
            raw_path, final_path = RAW_DIR / stem, FINAL_DIR / stem
            print(f"Repository: {name}")
            try:
                page.goto(f"https://github.com/{name}", wait_until="domcontentloaded", timeout=45_000)
                page.wait_for_timeout(1_500)
                readme = first_meaningful_locator(page)
                if readme is None:
                    print("  README not found; using main-content fallback capture.")
                    readme = page.locator("main").first
                    if readme.count() == 0:
                        raise RuntimeError("README and main-content fallback were unavailable")
                landmarks = prepare_page(page, readme)
                readme.screenshot(path=str(raw_path), animations="disabled", timeout=45_000)
                final, start, end, raw_size = choose_crop(raw_path, landmarks)
                final.save(final_path, "PNG", optimize=True)
                with Image.open(final_path) as verified:
                    if verified.size != FINAL_SIZE:
                        raise RuntimeError(f"final dimensions are {verified.size}, expected {FINAL_SIZE}")
                print(f"  README size: {raw_size[0]}x{raw_size[1]}")
                print(f"  Selected crop: y={start} to y={end}")
                print(f"  Final size: {FINAL_SIZE[0]}x{FINAL_SIZE[1]}")
                successful += 1
            except Exception as error:
                print(f"FAILED: {name}\nReason: {error}")
                failed += 1
        browser.close()
    print("======================================\n SCREENSHOT SUMMARY\n======================================")
    print(f"Successful: {successful}\nFailed:     {failed}\n\nRAW:\n{RAW_DIR}/\n\nFINAL:\n{FINAL_DIR}/")
    print("======================================")


if __name__ == "__main__":
    main()
