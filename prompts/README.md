# Prompt Packs

Toolkit for generating JSON prompt files for loop, one-shot and MIDI sample packs.
Catalog includes 15 packs (5 styles x 3 volumes) with three Stars support tiers:

- Starter: 100⭐
- Producer: 300⭐
- Collector: 600⭐

## Structure

```
prompts/
├── templates/
│   ├── loop_template.json
│   ├── oneshot_template.json
│   └── midi_template.json
├── data/
│   ├── genres.json
│   ├── instruments.json
│   └── moods.json
├── config/
│   ├── pack_config.yaml
│   └── single_config.yaml
├── generators/
│   ├── generate_prompts.py
│   └── utils.py
├── packs/
└── README.md
```

## Dependencies

- Python 3.10+
- PyYAML

Install:

```bash
pip install pyyaml
```

## Examples

List packs:

```bash
python prompts/generators/generate_prompts.py --list-packs
```

Generate full pack:

```bash
python prompts/generators/generate_prompts.py --mode full_pack --pack_id afro_house_vol1
```

Generate only loops for a pack:

```bash
python prompts/generators/generate_prompts.py --mode set --pack_id afro_house_vol1 --type loops
```

Generate one file prompt:

```bash
python prompts/generators/generate_prompts.py --mode single --pack_id afro_house_vol1 --type loop --instrument drums
```

Dry run without writing files:

```bash
python prompts/generators/generate_prompts.py --mode full_pack --pack_id afro_house_vol1 --dry-run
```

## Output

- Full and set modes write arrays to:
  - `prompts/packs/<pack_id>/loops.json`
  - `prompts/packs/<pack_id>/oneshots.json`
  - `prompts/packs/<pack_id>/midi.json`
- Single mode prints JSON to stdout and optionally saves `single_<type>.json`.

## Notes

- Prompt generation is random but reproducible via `--seed`.
- One-shots always have `duration: 1`.
- Loops use `duration` in bars: 4, 8, or 16.
- MIDI uses `duration: null`.
- Prices in `pack_config.yaml` are metadata for storefront/README export and not used in prompt text generation.