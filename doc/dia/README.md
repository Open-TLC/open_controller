# Diagram Style and Export Notes

This folder contains the source diagrams used in `README.md`.

## Naming

- Keep draw.io tab names aligned with README image filenames (lowercase snake_case).
- Current tab/file naming:
  - `open_controller_overview` -> `doc/images/open_controller_overview.png`
  - `sim_integrated` -> `doc/images/sim_integrated.png`
  - `hwil_sim` -> `doc/images/hwil_sim.png`
  - `live_control` -> `doc/images/live_control.png`
  - `nats_messages` (not currently exported to README from this file)

## Style (Brand Consistency)

- Font family: `poppins`
- Brand black: `#231f20` (use for text, box outlines, arrow strokes, black fills)
- Brand red: `#dd5433`
- Brand yellow: `#eebc46`
- Brand green: `#6fa489`
- Visible stroke widths (boxes + arrows): `2.3 pt`

### draw.io cleanup rules

- Avoid hidden secondary colors:
  - If `fillOpacity=0`, use `fillColor=none` (not a hidden color value).
- Avoid mixed black fill + non-black outline unless intentionally white-on-black styling is required.
- draw.io can visually show stale/cached style colors in UI; trust the XML style values and exported PNGs.

## Export (README PNGs)

Use high-resolution PNG export with border/margin:

- Format: `png`
- Scale: `3`
- Border: `20`

### Important

Do not rely on draw.io `--page-index` for this file. It has produced wrong page mappings in practice.

Instead:

1. Split the multi-page `.drawio` into one-page temporary `.drawio` files in tab order.
2. Export each split file directly to the matching `doc/images/*.png`.

This makes the mapping deterministic even if tabs are renamed.

