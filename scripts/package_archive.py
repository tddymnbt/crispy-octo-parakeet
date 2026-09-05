import os
import shutil
from datetime import datetime, timezone

OUTPUT_DIR = "output"
CONTENT_DIR = "content"

def main():
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_archive_dir = os.path.join(CONTENT_DIR, today_str)

    print("======================================")
    print(" PHASE 4: PACKAGING DAILY TEXT ARCHIVE")
    print("======================================")
    print(f"Target Directory: {daily_archive_dir}")

    if not os.path.exists(OUTPUT_DIR):
        raise RuntimeError("Output directory does not exist. Run previous phases first.")

    os.makedirs(daily_archive_dir, exist_ok=True)

    # Archive text JSON/TXT assets permanently in Git
    text_files = [
        "candidates.json",
        "top3.json",
        "research_details.json",
        "facebook_caption.txt"
    ]

    for filename in text_files:
        src_path = os.path.join(OUTPUT_DIR, filename)
        dest_path = os.path.join(daily_archive_dir, filename)

        if os.path.exists(src_path):
            shutil.copy2(src_path, dest_path)
            print(f"  Archived text asset: {filename}")

    print("======================================")
    print(" Daily Text Archive Successfully Packaged!")
    print("======================================")

if __name__ == "__main__":
    main()