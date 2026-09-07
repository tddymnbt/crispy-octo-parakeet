"""Allow scheduled publishing slots to safely skip when Slot 1 did not prepare today."""

import argparse
import json
import os
from pathlib import Path

from publish_facebook import state_path, validate_posts


def write_output(name, value):
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with Path(output_file).open("a", encoding="utf-8") as file:
            file.write(f"{name}={value}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", type=int, choices=range(2, 6), required=True)
    args = parser.parse_args()
    path = state_path()
    if not path.is_file():
        print(f"Skipping slot {args.slot}: Slot 1 has not prepared today's publish state ({path}).")
        write_output("ready", "false")
        return
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        validate_posts(state.get("posts", []))
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"Skipping slot {args.slot}: today's publish state is not usable: {exc}")
        write_output("ready", "false")
        return
    print(f"Slot {args.slot} can publish from {path}.")
    write_output("ready", "true")


if __name__ == "__main__":
    main()
