#!/usr/bin/env python3
"""Interactive CLI for adding metadata.yaml to ski sessions.

Scans data/ for session folders missing metadata, auto-fills what it can
from the folder name, and prompts for the rest.

Usage:
    python scripts/add_metadata.py              # scan default data/ dir
    python scripts/add_metadata.py /path/to/data  # scan custom dir
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROFILES_DIR = PROJECT_ROOT / "ski" / "profiles"

TERRAIN_OPTIONS = [
    "groomer", "moguls", "trees", "steeps", "park", "backcountry", "mixed",
]
SNOW_OPTIONS = [
    "packed_powder", "powder", "hardpack", "ice", "slush", "spring", "variable",
]
MOUNT_OPTIONS = [
    "jacket_chest", "pants_pocket", "armband", "backpack_strap", "helmet", "waist_pocket",
]
ABILITY_OPTIONS = [
    "beginner", "intermediate", "advanced", "expert",
]
DOMINANT_SIDE_OPTIONS = [
    "right", "left",
]
SKI_TYPE_OPTIONS = [
    "all_mountain", "carving", "powder", "park", "race", "touring",
]


def discover_sessions(data_dir: Path) -> list[Path]:
    """Return session dirs that contain sensor CSVs."""
    sessions = []
    for d in sorted(data_dir.iterdir()):
        if not d.is_dir():
            continue
        has_sensor_csv = any(
            f.suffix == ".csv" and f.stem in (
                "Accelerometer", "Gyroscope", "Orientation", "Location",
                "Barometer", "Gravity", "Magnetometer", "Compass",
            )
            for f in d.iterdir()
        )
        if has_sensor_csv:
            sessions.append(d)
    return sessions


def parse_folder_name(folder_name: str) -> dict:
    """Extract session_id, location, and date from folder name.

    Expected format: Location_Name-YYYY-MM-DD_HH-MM-SS
    """
    info: dict = {"session_id": folder_name}

    match = re.match(r"^(.+?)-(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})$", folder_name)
    if match:
        raw_location = match.group(1)
        info["location"] = raw_location.lower().replace("_", " ")
        info["date"] = match.group(2)
    else:
        info["location"] = folder_name.lower().replace("_", " ")
        info["date"] = None

    return info


def list_profiles(kind: str) -> list[str]:
    """List available profile IDs (skiers or skis)."""
    profile_dir = PROFILES_DIR / kind
    if not profile_dir.is_dir():
        return []
    return sorted(p.stem for p in profile_dir.glob("*.yaml"))


def prompt_choice(prompt_text: str, options: list[str],
                  allow_new: bool = False, allow_skip: bool = False) -> str | None:
    """Show numbered options and return the chosen value."""
    print(f"\n  {prompt_text}")
    for i, opt in enumerate(options, 1):
        print(f"    [{i}] {opt}")
    extras = []
    if allow_new:
        extras.append("'new' to create one")
    if allow_skip:
        extras.append("Enter to skip")
    if extras:
        print(f"    ({', '.join(extras)})")

    while True:
        raw = input("  > ").strip()
        if not raw and allow_skip:
            return None
        if raw.lower() == "new" and allow_new:
            return "__new__"
        try:
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        except ValueError:
            if raw in options:
                return raw
        print("    Invalid choice, try again.")


def prompt_free(prompt_text: str, default: str | None = None) -> str:
    """Prompt for free-text input with optional default."""
    suffix = f" [{default}]" if default else ""
    raw = input(f"  {prompt_text}{suffix}: ").strip()
    return raw if raw else (default or "")


def create_skier_profile() -> str:
    """Interactively create a new skier profile and return its ID."""
    print("\n  --- New skier profile ---")
    skier_id = prompt_free("Skier ID (short, no spaces)")
    data: dict = {"skier_id": skier_id}

    height = prompt_free("Height (inches)", default="")
    if height:
        data["height_in"] = float(height)
    weight = prompt_free("Weight (lbs)", default="")
    if weight:
        data["weight_lbs"] = float(weight)

    ability = prompt_choice("Ability level:", ABILITY_OPTIONS)
    data["ability_level"] = ability

    boots = prompt_free("Boots (brand/model)", default="")
    if boots:
        data["equipment"] = {"boots": boots}

    dominant = prompt_choice("Dominant side:", DOMINANT_SIDE_OPTIONS)
    data["preferences"] = {"dominant_side": dominant}

    out_path = PROFILES_DIR / "skiers" / f"{skier_id}.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    print(f"  Saved: {out_path.relative_to(PROJECT_ROOT)}")
    return skier_id


def create_ski_profile() -> str:
    """Interactively create a new ski profile and return its ID."""
    print("\n  --- New ski profile ---")
    brand = prompt_free("Brand")
    model = prompt_free("Model")
    length = prompt_free("Length (cm)")
    waist = prompt_free("Waist width (mm)", default="")
    ski_type = prompt_choice("Type:", SKI_TYPE_OPTIONS)

    ski_id = f"{model.lower().replace(' ', '_')}_{length}"
    ski_id = prompt_free("Ski ID", default=ski_id)

    data: dict = {
        "ski_id": ski_id,
        "brand": brand,
        "model": model,
        "length_cm": int(length),
    }
    if waist:
        data["waist_mm"] = int(waist)
    data["type"] = ski_type

    out_path = PROFILES_DIR / "skis" / f"{ski_id}.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    print(f"  Saved: {out_path.relative_to(PROJECT_ROOT)}")
    return ski_id


def add_metadata_for_session(session_dir: Path) -> None:
    """Walk the user through creating metadata.yaml for one session."""
    folder_name = session_dir.name
    parsed = parse_folder_name(folder_name)

    print(f"\n{'=' * 60}")
    print(f"  Session: {folder_name}")
    if parsed.get("date"):
        print(f"  Date:    {parsed['date']}")
    print(f"  Auto-detected location: {parsed['location']}")
    print(f"{'=' * 60}")

    # -- Skier --
    skiers = list_profiles("skiers")
    if skiers:
        choice = prompt_choice("Select skier profile:", skiers, allow_new=True)
    else:
        print("\n  No skier profiles found.")
        choice = "__new__"
    if choice == "__new__":
        skier_id = create_skier_profile()
    else:
        skier_id = choice

    # -- Ski --
    skis = list_profiles("skis")
    if skis:
        choice = prompt_choice("Select ski profile:", skis, allow_new=True)
    else:
        print("\n  No ski profiles found.")
        choice = "__new__"
    if choice == "__new__":
        ski_id = create_ski_profile()
    else:
        ski_id = choice

    # -- Location --
    location = prompt_free("Location", default=parsed["location"])

    # -- Terrain --
    terrain = prompt_choice("Terrain:", TERRAIN_OPTIONS, allow_skip=True)

    # -- Snow --
    snow = prompt_choice("Snow conditions:", SNOW_OPTIONS, allow_skip=True)

    # -- Phone mount --
    mount = prompt_choice("Phone mount position:", MOUNT_OPTIONS, allow_skip=True)

    # -- Notes --
    notes = prompt_free("Notes (optional)", default="")

    # -- Build and save --
    meta: dict = {"session_id": parsed["session_id"]}
    if parsed.get("date"):
        meta["date"] = parsed["date"]
    meta["skier"] = skier_id
    meta["ski"] = ski_id
    meta["location"] = location.replace(" ", "_")
    if terrain:
        meta["terrain"] = terrain
    if snow:
        meta["snow"] = snow
    if mount:
        meta["phone_mount"] = mount
    if notes:
        meta["notes"] = notes

    out_path = session_dir / "metadata.yaml"
    with open(out_path, "w") as f:
        yaml.dump(meta, f, default_flow_style=False, sort_keys=False)

    print(f"\n  Saved: {out_path.relative_to(PROJECT_ROOT)}")


def fill_missing_metadata(session_dir: Path) -> None:
    """Prompt only for fields that are missing in an existing metadata.yaml."""
    meta_path = session_dir / "metadata.yaml"
    with open(meta_path, "r") as f:
        meta = yaml.safe_load(f) or {}

    folder_name = session_dir.name
    parsed = parse_folder_name(folder_name)

    print(f"\n{'=' * 60}")
    print(f"  Session: {folder_name}")
    print(f"  Filling in missing fields (existing values kept)")
    print(f"{'=' * 60}")

    existing = {k: v for k, v in meta.items() if v is not None and v != ""}
    missing_keys = []

    if "session_id" not in existing:
        meta["session_id"] = parsed["session_id"]
    if "date" not in existing and parsed.get("date"):
        meta["date"] = parsed["date"]

    field_order = ["skier", "ski", "location", "terrain", "snow", "phone_mount", "notes"]
    for key in field_order:
        if key not in existing:
            missing_keys.append(key)

    if not missing_keys:
        print("\n  All fields are already filled. Nothing to add.")
        return

    print(f"\n  Already set: {', '.join(existing.keys())}")
    print(f"  Missing:     {', '.join(missing_keys)}\n")

    if "skier" in missing_keys:
        skiers = list_profiles("skiers")
        if skiers:
            choice = prompt_choice("Select skier profile:", skiers, allow_new=True, allow_skip=True)
        else:
            choice = "__new__"
        if choice == "__new__":
            meta["skier"] = create_skier_profile()
        elif choice is not None:
            meta["skier"] = choice

    if "ski" in missing_keys:
        skis = list_profiles("skis")
        if skis:
            choice = prompt_choice("Select ski profile:", skis, allow_new=True, allow_skip=True)
        else:
            choice = "__new__"
        if choice == "__new__":
            meta["ski"] = create_ski_profile()
        elif choice is not None:
            meta["ski"] = choice

    if "location" in missing_keys:
        location = prompt_free("Location", default=parsed["location"])
        if location:
            meta["location"] = location.replace(" ", "_")

    if "terrain" in missing_keys:
        terrain = prompt_choice("Terrain:", TERRAIN_OPTIONS, allow_skip=True)
        if terrain:
            meta["terrain"] = terrain

    if "snow" in missing_keys:
        snow = prompt_choice("Snow conditions:", SNOW_OPTIONS, allow_skip=True)
        if snow:
            meta["snow"] = snow

    if "phone_mount" in missing_keys:
        mount = prompt_choice("Phone mount position:", MOUNT_OPTIONS, allow_skip=True)
        if mount:
            meta["phone_mount"] = mount

    if "notes" in missing_keys:
        notes = prompt_free("Notes (optional)", default="")
        if notes:
            meta["notes"] = notes

    with open(meta_path, "w") as f:
        yaml.dump(meta, f, default_flow_style=False, sort_keys=False)

    print(f"\n  Updated: {meta_path.relative_to(PROJECT_ROOT)}")


def main():
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT_ROOT / "data"

    if not data_dir.is_dir():
        print(f"Error: {data_dir} is not a directory.")
        sys.exit(1)

    sessions = discover_sessions(data_dir)
    if not sessions:
        print("No session folders found.")
        sys.exit(0)

    missing = [s for s in sessions if not (s / "metadata.yaml").is_file()]
    has_meta = [s for s in sessions if (s / "metadata.yaml").is_file()]

    print(f"\nFound {len(sessions)} session(s), {len(missing)} missing metadata.\n")

    labels = []
    if missing:
        labels.append(f"Add metadata to all {len(missing)} missing session(s)")
    labels.append("Pick a specific session")
    labels.append("Quit")

    action = prompt_choice("What would you like to do?", labels)

    if action and action.startswith("Quit"):
        return

    if action and action.startswith("Add metadata to all"):
        for session_dir in missing:
            add_metadata_for_session(session_dir)
            print()
        print(f"\nDone! Added metadata to {len(missing)} session(s).")
        return

    session_names = []
    for s in sessions:
        tag = "" if s in missing else " (has metadata)"
        session_names.append(f"{s.name}{tag}")

    choice = prompt_choice("Select a session:", session_names)
    if choice is None:
        return
    clean_name = choice.replace(" (has metadata)", "")
    session_dir = next(s for s in sessions if s.name == clean_name)

    if session_dir in has_meta:
        action2 = prompt_choice(
            f"{clean_name} already has metadata.",
            ["Fill in missing fields", "Overwrite completely", "Cancel"],
        )
        if action2 == "Fill in missing fields":
            fill_missing_metadata(session_dir)
            return
        if action2 != "Overwrite completely":
            print("  Skipped.")
            return

    add_metadata_for_session(session_dir)


if __name__ == "__main__":
    main()
