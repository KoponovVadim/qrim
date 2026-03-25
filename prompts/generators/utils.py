"""Utility helpers for prompt JSON generation."""

from __future__ import annotations

import json
import random
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

import yaml


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"
CONFIG_DIR = BASE_DIR / "config"

TEMPLATE_BY_TYPE = {
    "loop": "loop_template.json",
    "oneshot": "oneshot_template.json",
    "midi": "midi_template.json",
}


def load_json(path: Path) -> Any:
    """Read JSON file with explicit errors for invalid payloads."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def load_yaml(path: Path) -> Any:
    """Read YAML file with explicit errors for invalid payloads."""
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"YAML file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {path}: {exc}") from exc
    if parsed is None:
        raise ValueError(f"YAML file is empty: {path}")
    return parsed


def load_template(file_type: str) -> Dict[str, Any]:
    """Load a JSON template by file type."""
    template_name = TEMPLATE_BY_TYPE.get(file_type)
    if not template_name:
        raise ValueError(
            f"Unsupported file type '{file_type}'. Allowed: {sorted(TEMPLATE_BY_TYPE)}"
        )
    return load_json(TEMPLATES_DIR / template_name)


def load_all_data() -> Dict[str, Any]:
    """Load genres, instruments and moods from prompts/data."""
    return {
        "genres": load_json(DATA_DIR / "genres.json"),
        "instruments": load_json(DATA_DIR / "instruments.json"),
        "moods": load_json(DATA_DIR / "moods.json"),
    }


def load_pack_config() -> Dict[str, Any]:
    """Load main pack configuration from prompts/config."""
    return load_yaml(CONFIG_DIR / "pack_config.yaml")


def find_pack(pack_config: Dict[str, Any], pack_id: str) -> Dict[str, Any]:
    """Find pack by ID in pack config."""
    packs = pack_config.get("packs", [])
    for pack in packs:
        if pack.get("pack_id") == pack_id:
            return pack
    known_ids = ", ".join(sorted(p.get("pack_id", "<unknown>") for p in packs))
    raise ValueError(f"Pack '{pack_id}' not found. Available: {known_ids}")


def find_genre(genres: List[Dict[str, Any]], style: str) -> Dict[str, Any]:
    """Find a genre by style name, case-insensitive."""
    normalized = style.strip().casefold()
    for genre in genres:
        if str(genre.get("name", "")).strip().casefold() == normalized:
            return genre
    known = ", ".join(sorted(g.get("name", "<unknown>") for g in genres))
    raise ValueError(f"Style '{style}' not found in genres.json. Available: {known}")


def random_bpm(genre: Dict[str, Any], rng: random.Random) -> int:
    """Generate a BPM from genre range."""
    bpm_min = int(genre["bpm_min"])
    bpm_max = int(genre["bpm_max"])
    if bpm_min > bpm_max:
        raise ValueError(f"Invalid BPM range in genre '{genre.get('name')}'")
    return rng.randint(bpm_min, bpm_max)


def random_key(genre: Dict[str, Any], rng: random.Random) -> str:
    """Select a random key from genre keys."""
    keys = genre.get("keys")
    if not keys:
        raise ValueError(f"No keys configured for genre '{genre.get('name')}'")
    return str(rng.choice(keys))


def random_duration(file_type: str, rng: random.Random) -> int | None:
    """Return duration in bars for loop/oneshot/midi."""
    if file_type == "loop":
        return rng.choice([4, 8, 16])
    if file_type == "oneshot":
        return 1
    if file_type == "midi":
        return None
    raise ValueError(f"Unsupported file type for duration: {file_type}")


def random_variant(
    instruments_data: Dict[str, Dict[str, List[str]]],
    file_type_plural: str,
    instrument: str,
    rng: random.Random,
) -> str:
    """Pick one phrase variant for selected type/instrument."""
    categories = instruments_data.get(file_type_plural, {})
    variants = categories.get(instrument)
    if not variants:
        known = ", ".join(sorted(categories.keys()))
        raise ValueError(
            f"Instrument '{instrument}' is not available for {file_type_plural}. "
            f"Available: {known}"
        )
    return str(rng.choice(variants))


def generate_filename(
    pack_id: str,
    instrument: str,
    file_type: str,
    number: int,
) -> str:
    """Build deterministic output filename used by orchestrator."""
    safe_instrument = instrument.replace(" ", "_").replace("-", "_")
    ext = ".mid" if file_type == "midi" else ".wav"
    return f"{pack_id}_{safe_instrument}_{file_type}_{number:03d}{ext}"


def generate_prompt_text(
    style: str,
    mood: str,
    instrument: str,
    variant: str,
    file_type: str,
    key: str | None,
    bpm: int | None,
    duration: int | None,
    number: int,
) -> str:
    """Build a human-readable prompt string with unique variation marker."""
    parts = [
        f"Create a {mood} {style} {file_type}",
        f"focused on {instrument}",
        f"with {variant}",
    ]
    if bpm is not None:
        parts.append(f"at {bpm} BPM")
    if key:
        parts.append(f"in {key}")
    if duration:
        parts.append(f"{duration} bars")
    parts.append(f"variation {number:03d}")
    return ", ".join(parts)


def compose_item(
    template: Dict[str, Any],
    pack_id: str,
    file_type: str,
    instrument: str,
    bpm: int | None,
    key: str | None,
    prompt_text: str,
    duration: int | None,
    filename: str,
) -> Dict[str, Any]:
    """Fill template fields for one generated prompt item."""
    item = deepcopy(template)
    item["pack_id"] = pack_id
    item["type"] = file_type
    item["instrument"] = instrument
    item["bpm"] = bpm
    item["key"] = key
    item["prompt"] = prompt_text
    item["duration"] = duration
    item["filename"] = filename
    return item


def plural_to_singular(file_type_plural: str) -> str:
    """Convert loops/oneshots/midi section names to file types."""
    mapping = {"loops": "loop", "oneshots": "oneshot", "midi": "midi"}
    singular = mapping.get(file_type_plural)
    if not singular:
        raise ValueError("Type must be one of: loops, oneshots, midi")
    return singular


def singular_to_plural(file_type: str) -> str:
    """Convert loop/oneshot/midi to config section names."""
    mapping = {"loop": "loops", "oneshot": "oneshots", "midi": "midi"}
    plural = mapping.get(file_type)
    if not plural:
        raise ValueError("Type must be one of: loop, oneshot, midi")
    return plural


def write_json(path: Path, payload: Any) -> None:
    """Write JSON payload with stable formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
