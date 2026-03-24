import argparse
import os
import random
import string
import zipfile
from pathlib import Path

import httpx


def _rand_name(prefix: str = "pack") -> str:
    suffix = "".join(random.choice(string.ascii_lowercase) for _ in range(6))
    return f"{prefix}_{suffix}"


def generate_local_pack(output_dir: Path) -> tuple[Path, Path, list[Path], dict]:
    output_dir.mkdir(parents=True, exist_ok=True)

    pack_name = _rand_name("samplepack")
    pack_dir = output_dir / pack_name
    pack_dir.mkdir(parents=True, exist_ok=True)

    # Placeholder for ComfyUI output integration.
    wav_file = pack_dir / "demo_1.txt"
    wav_file.write_text("Replace with generated audio from ComfyUI pipeline.", encoding="utf-8")

    zip_path = output_dir / f"{pack_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(wav_file, arcname=wav_file.name)

    cover_path = output_dir / f"{pack_name}.jpg"
    cover_path.write_bytes(b"\xff\xd8\xff\xd9")

    demo_path = output_dir / f"{pack_name}_demo.mp3"
    demo_path.write_bytes(b"ID3")

    meta = {
        "name": pack_name,
        "genre": "Generated",
        "price_usdt": 19,
        "price_ton": 7,
        "description": "Auto-generated pack via local orchestrator",
    }
    return zip_path, cover_path, [demo_path], meta


def upload_to_panel(panel_base_url: str, password: str, zip_path: Path, cover_path: Path, demo_paths: list[Path], meta: dict):
    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        login_resp = client.post(
            f"{panel_base_url}/login",
            data={"password": password, "telegram_id": ""},
        )
        login_resp.raise_for_status()

        files = [
            ("zip_file", (zip_path.name, zip_path.read_bytes(), "application/zip")),
            ("cover_file", (cover_path.name, cover_path.read_bytes(), "image/jpeg")),
        ]
        for demo in demo_paths:
            files.append(("demo_files", (demo.name, demo.read_bytes(), "audio/mpeg")))

        resp = client.post(
            f"{panel_base_url}/packs/add",
            data={
                "name": meta["name"],
                "genre": meta["genre"],
                "price_usdt": str(meta["price_usdt"]),
                "price_ton": str(meta["price_ton"]),
                "description": meta["description"],
            },
            files=files,
        )
        resp.raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate pack locally and upload to admin panel")
    parser.add_argument("--panel", default=os.getenv("PANEL_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--password", default=os.getenv("WEB_PASSWORD", ""))
    parser.add_argument("--out", default="./tmp_generated")
    args = parser.parse_args()

    if not args.password:
        raise SystemExit("Set WEB_PASSWORD or pass --password")

    out_dir = Path(args.out)
    zip_path, cover_path, demo_paths, meta = generate_local_pack(out_dir)
    upload_to_panel(args.panel, args.password, zip_path, cover_path, demo_paths, meta)
    print("Uploaded generated pack:", meta["name"])


if __name__ == "__main__":
    main()
