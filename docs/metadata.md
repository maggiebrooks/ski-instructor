# Metadata System

A lightweight metadata system stores static skier attributes, ski equipment
specifications, and per-session context in YAML files. The `TurnInsights`
normalization layer consumes ski metadata (e.g. `length_cm`) for
physics-based comparisons. All metadata is optional -- the pipeline and
analytics gracefully degrade when it is absent.

## Skier Profiles (`ski/profiles/skiers/<skier_id>.yaml`)

Store static attributes about the skier that rarely change between sessions:

```yaml
skier_id: maggie
height_cm: 157
weight_kg: 63
ability_level: advanced
equipment:
  boots: Lange RX 95
preferences:
  dominant_side: right
```

## Ski Profiles (`ski/profiles/skis/<ski_id>.yaml`)

Store equipment specifications for each pair of skis:

```yaml
ski_id: sheeva10_104_158
brand: Blizzard
model: Sheeva 10
length_cm: 158
waist_mm: 104
type: all_mountain
```

## Session Metadata (`data/<session_dir>/metadata.yaml`)

Store per-day context alongside the raw sensor data. References a skier
and ski profile by ID:

```yaml
session_id: Aspen_Highlands-2026-02-26_16-52-11
skier: maggie
ski: sheeva10_104_158
location: aspen_highlands
terrain: groomer
snow: packed_powder
phone_mount: jacket_chest
notes: carving practice
```

## Adding Metadata

Use the interactive CLI to add metadata to existing sessions:

```bash
python3 scripts/add_metadata.py
```

This scans `data/` for session folders, auto-fills what it can from folder
names (session_id, location, date), and prompts for the remaining fields
(skier, ski, terrain, snow, phone_mount, notes). It can also fill missing
fields on existing metadata files without overwriting.

## MetadataLoader (`ski/metadata/metadata_loader.py`)

Read-only loader with three methods:

- `load_skier_profile(skier_id)` -- returns the profile dict, or `None`
- `load_ski_profile(ski_id)` -- returns the profile dict, or `None`
- `load_session_metadata(session_path)` -- returns the metadata dict, or `None`

All methods return `None` when the requested file does not exist, so
metadata is always optional and never blocks the pipeline.

## How Metadata Feeds Analytics

When metadata is passed to `TurnInsights.session_report()` or
`compute_movement_scores()`, the normalization layer uses it:

| Metadata field | Used by | Purpose |
|----------------|---------|---------|
| `ski.length_cm` | `normalized_turn_radius` | Dimensionless turn size comparison |
| `skier.weight_kg` | (future) | Weight-normalized g-force |
| `ski.waist_mm` | (future) | Edge angle estimation |
