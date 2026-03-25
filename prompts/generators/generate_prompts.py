"""CLI generator for sample prompt JSON files used by ComfyUI orchestrator."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any, Dict, List

from utils import (
    BASE_DIR,
    compose_item,
    find_genre,
    find_pack,
    generate_filename,
    generate_prompt_text,
    load_all_data,
    load_pack_config,
    load_template,
    plural_to_singular,
    random_bpm,
    random_duration,
    random_key,
    random_variant,
    singular_to_plural,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate JSON prompts for loops, one-shots and MIDI assets."
    )
    parser.add_argument("--mode", choices=["full_pack", "set", "single"], help="Run mode")
    parser.add_argument("--pack_id", help="Pack ID from prompts/config/pack_config.yaml")
    parser.add_argument(
        "--type",
        dest="asset_type",
        help="Type: set mode uses loops|oneshots|midi, single mode uses loop|oneshot|midi",
    )
    parser.add_argument("--instrument", help="Instrument category for single mode")
    parser.add_argument("--count", type=int, help="Override generated items count")
    parser.add_argument(
        "--output-dir",
        default=str(BASE_DIR / "packs"),
        help="Output directory for generated JSON files",
    )
    parser.add_argument("--list-packs", action="store_true", help="Show available pack IDs")
    parser.add_argument("--dry-run", action="store_true", help="Preview output without writing files")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible output")
    return parser.parse_args()


def list_packs(pack_config: Dict[str, Any]) -> None:
    packs = pack_config.get("packs", [])
    if not packs:
        print("No packs defined in pack_config.yaml")
        return
    print("Available packs:")
    for pack in packs:
        counts = pack.get("target_counts", {})
        print(
            f"- {pack.get('pack_id')} | {pack.get('name')} | "
            f"style={pack.get('style')} | loops={counts.get('loops', 0)} "
            f"oneshots={counts.get('oneshots', 0)} midi={counts.get('midi', 0)}"
        )


def generate_items(
    *,
    pack: Dict[str, Any],
    file_type: str,
    instrument: str,
    count: int,
    all_data: Dict[str, Any],
    rng: random.Random,
) -> List[Dict[str, Any]]:
    template = load_template(file_type)
    genres = all_data["genres"]
    instruments_data = all_data["instruments"]
    moods = all_data["moods"]

    genre = find_genre(genres, str(pack["style"]))
    file_type_plural = singular_to_plural(file_type)

    items: List[Dict[str, Any]] = []
    seen_prompts = set()

    for index in range(1, count + 1):
        bpm = random_bpm(genre, rng) if file_type in {"loop", "oneshot"} else random_bpm(genre, rng)
        key = random_key(genre, rng)
        duration = random_duration(file_type, rng)
        mood = str(rng.choice(moods))
        variant = random_variant(instruments_data, file_type_plural, instrument, rng)

        prompt = generate_prompt_text(
            style=str(pack["style"]),
            mood=mood,
            instrument=instrument,
            variant=variant,
            file_type=file_type,
            key=key,
            bpm=bpm,
            duration=duration,
            number=index,
        )
        if prompt in seen_prompts:
            prompt = f"{prompt}, alt take {index:03d}"
        seen_prompts.add(prompt)

        filename = generate_filename(
            pack_id=str(pack["pack_id"]),
            instrument=instrument,
            file_type=file_type,
            number=index,
        )
        item = compose_item(
            template=template,
            pack_id=str(pack["pack_id"]),
            file_type=file_type,
            instrument=instrument,
            bpm=bpm,
            key=key,
            prompt_text=prompt,
            duration=duration,
            filename=filename,
        )
        items.append(item)

    return items


def choose_instrument_for_type(
    all_data: Dict[str, Any], file_type: str, rng: random.Random
) -> str:
    section = singular_to_plural(file_type)
    instruments = all_data["instruments"].get(section, {})
    if not instruments:
        raise ValueError(f"No instruments configured for type '{file_type}'")
    return str(rng.choice(list(instruments.keys())))


def build_pack_payload(
    pack: Dict[str, Any],
    all_data: Dict[str, Any],
    rng: random.Random,
    only_type: str | None = None,
    override_count: int | None = None,
) -> Dict[str, List[Dict[str, Any]]]:
    target_counts = pack.get("target_counts", {})
    payload: Dict[str, List[Dict[str, Any]]] = {}

    sections = ["loops", "oneshots", "midi"]
    for section in sections:
        if only_type and section != only_type:
            continue
        singular_type = plural_to_singular(section)
        count = int(override_count if override_count is not None else target_counts.get(section, 0))
        if count <= 0:
            payload[section] = []
            continue

        items: List[Dict[str, Any]] = []
        for index in range(1, count + 1):
            instrument = choose_instrument_for_type(all_data, singular_type, rng)
            one = generate_items(
                pack=pack,
                file_type=singular_type,
                instrument=instrument,
                count=1,
                all_data=all_data,
                rng=rng,
            )[0]
            one["filename"] = generate_filename(
                pack_id=str(pack["pack_id"]),
                instrument=instrument,
                file_type=singular_type,
                number=index,
            )
            one["prompt"] = f"{one['prompt']} [{section}:{index:03d}]"
            items.append(one)
        payload[section] = items

    return payload


def write_pack_files(
    pack_id: str,
    payload: Dict[str, List[Dict[str, Any]]],
    output_dir: Path,
    dry_run: bool,
) -> None:
    pack_dir = output_dir / pack_id
    for section, items in payload.items():
        file_path = pack_dir / f"{section}.json"
        if dry_run:
            print(f"[dry-run] {file_path} <- {len(items)} items")
            continue
        write_json(file_path, items)
        print(f"Saved {file_path} ({len(items)} items)")


def write_readme(pack_config: Dict[str, Any], dry_run: bool) -> None:
    genres = load_all_data()["genres"]
    genre_map = {g["name"]: g for g in genres}

    lines = [
        "# Prompt Packs",
        "",
        "This directory contains template-driven prompt packs for the audio orchestrator.",
        "",
        "## Catalog",
        "",
        "| Pack | ID | Style | BPM | Keys | Loops | One-shots | MIDI | Starter | Producer | Collector |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]

    for pack in pack_config.get("packs", []):
        genre = genre_map.get(pack["style"])
        bpm_text = "n/a"
        keys_text = "n/a"
        if genre:
            bpm_text = f"{genre['bpm_min']}-{genre['bpm_max']}"
            keys_text = ", ".join(genre.get("keys", []))
        counts = pack.get("target_counts", {})
        lines.append(
            "| "
            f"{pack.get('name')} | {pack.get('pack_id')} | {pack.get('style')} | "
            f"{bpm_text} | {keys_text} | {counts.get('loops', 0)} | "
            f"{counts.get('oneshots', 0)} | {counts.get('midi', 0)} | "
            f"{pack.get('price_starter', 0)} | {pack.get('price_producer', 0)} | "
            f"{pack.get('price_collector', 0)} |"
        )

    lines.extend(
        [
            "",
            "## License Notes",
            "",
            "- Generated prompts are intended for royalty-free sample creation workflows.",
            "- Verify final audio outputs for third-party trademarked names or melodic similarity.",
            "",
            "## Usage",
            "",
            "```bash",
            "python prompts/generators/generate_prompts.py --list-packs",
            "python prompts/generators/generate_prompts.py --mode full_pack --pack_id afro_house_vol1",
            "python prompts/generators/generate_prompts.py --mode set --pack_id afro_house_vol1 --type loops",
            "python prompts/generators/generate_prompts.py --mode single --pack_id afro_house_vol1 --type loop --instrument drums",
            "```",
        ]
    )

    target = BASE_DIR / "README.md"
    if dry_run:
        print(f"[dry-run] {target} would be updated")
    else:
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Updated {target}")


def run() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    pack_config = load_pack_config()

    if args.list_packs:
        list_packs(pack_config)
        return 0

    if not args.mode:
        raise ValueError("--mode is required unless --list-packs is used")
    if not args.pack_id:
        raise ValueError("--pack_id is required for modes full_pack, set, single")

    pack = find_pack(pack_config, args.pack_id)
    all_data = load_all_data()
    output_dir = Path(args.output_dir)

    if args.mode == "full_pack":
        payload = build_pack_payload(pack, all_data, rng)
        write_pack_files(str(pack["pack_id"]), payload, output_dir, args.dry_run)
        write_readme(pack_config, args.dry_run)
        return 0

    if args.mode == "set":
        if not args.asset_type:
            raise ValueError("--type is required in set mode (loops|oneshots|midi)")
        set_type = args.asset_type.strip().lower()
        if set_type not in {"loops", "oneshots", "midi"}:
            raise ValueError("set mode --type must be loops, oneshots, or midi")
        payload = build_pack_payload(pack, all_data, rng, only_type=set_type, override_count=args.count)
        write_pack_files(str(pack["pack_id"]), payload, output_dir, args.dry_run)
        return 0

    if args.mode == "single":
        if not args.asset_type:
            raise ValueError("--type is required in single mode (loop|oneshot|midi)")
        file_type = args.asset_type.strip().lower()
        if file_type not in {"loop", "oneshot", "midi"}:
            raise ValueError("single mode --type must be loop, oneshot, or midi")
        if not args.instrument:
            raise ValueError("--instrument is required in single mode")

        items = generate_items(
            pack=pack,
            file_type=file_type,
            instrument=args.instrument.strip().lower(),
            count=max(1, int(args.count or 1)),
            all_data=all_data,
            rng=rng,
        )
        print(json.dumps(items if len(items) > 1 else items[0], indent=2, ensure_ascii=False))

        if not args.dry_run:
            pack_dir = output_dir / str(pack["pack_id"])
            target = pack_dir / f"single_{file_type}.json"
            write_json(target, items)
            print(f"Saved {target}")
        return 0

    raise ValueError(f"Unsupported mode: {args.mode}")


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception as exc:  # noqa: BLE001 - clear CLI error for operators.
        print(f"Error: {exc}")
        raise SystemExit(1)
