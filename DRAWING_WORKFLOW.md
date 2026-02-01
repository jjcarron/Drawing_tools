# Automated Drawing Workflow (YAML → DXF)

## Purpose
This project converts human-readable drawing specifications into DXF files usable in QCAD/LibreCAD. The goal is to keep AI usage focused on translating natural-language requirements into a **stable, editable YAML format**, while the Python renderer handles **repeatable, deterministic** DXF generation.

## High-Level Workflow
1. **Describe the drawing in YAML** (editable by hand).
2. **Run a renderer** to produce the DXF output.
3. **Review in CAD** and adjust YAML if needed.
4. **Extend the renderer** only when a new feature is required (new opening type, new dimension type, new projection, etc.).

## Files and Roles
- `projets/<project>/*.yml`: **Source of truth** for geometry, dimensions, text, and title block.
- `scripts/drawing_engine.py`: Generic renderer (YAML → DXF).
- `scripts/yaml_spec.py`: YAML loader.
- `scripts/render_from_yaml.py`: CLI renderer for any YAML file.
- `scripts/<name>.py`: Per‑drawing wrappers that load a specific YAML.
- `templates/`: DXF templates (sheet, cartouche).

## Running the Generator
Generic:
```
python scripts/render_from_yaml.py --spec projets/GBS-8200/GBS-8200_Front_Panel.yml
```
Per‑drawing wrapper:
```
python scripts/GBS-8200_Front_Panel.py
```

Outputs are written **next to the YAML spec** (same folder, same base name).

## YAML Structure (v0.1)
Each drawing YAML is organized by sections:

- `meta`: filename, version, units
- `sheet`: template and centering rules
- `styles`: layer, dimension, text settings
- `panel`: overall plate size
- `axes`: center axes and opening axes rules
- `openings`: circles, rectangles, notches
- `dimensions`: list of dimension items
- `text`: annotations
- `title_block`: cartouche field values

### Example Skeleton
```
meta:
  filename: Example_Panel
  version: 0.1
  units: mm

sheet:
  template: templates/A4_Landscape_ISO5457_minimal.dxf
  free_area: { top: 200, bottom: 60, left: 0, right: 297 }
  center: { mode: free_area, round_to_mm: true }

styles:
  layers:
    outline: { name: OUTLINE, lineweight: 0.7 }
    cutouts: { name: CUTOUTS, lineweight: 0.7 }
    axes: { name: AXES, lineweight: 0.35, linetype: DASHDOT }
    dimensions: { name: DIMENSIONS, lineweight: 0.35 }
    text: { name: TEXT, lineweight: 0.35 }
  text: { font: "Segoe UI Semibold", height_pt: 9 }
  dimensions:
    style: ISO-25
    offset: 7
    spacing: 5
    small_hole_outside_threshold: 6

panel:
  size: { length: 147, width: 37, thickness: 3 }

axes:
  center: { horizontal: true, vertical: true }
  openings: { circles: true, rects: true }
  overhang: 2
  extend_to_dimensions: true

openings:
  - id: hole1
    type: circle
    diameter: 8
    center: { x_from_center: -41.5, y_from_center: 0 }

# ... dimensions, text, title_block ...
```

## Supported Opening Types
- `circle`: diameter + center
- `rect`: width + height + center
- `notch_u`: height + `from_left` + `to_x` or `to_x_ref` (open‑left U)

## Background Layer (Optional)
You can add a solid background fill that follows the outline using a dedicated
`BACKGROUND` layer. This is useful for printing colored panels.

YAML example:
```
styles:
  layers:
    background: { name: BACKGROUND, lineweight: 0.0, color: "#dadada" }
```

Notes:
- The background is rendered as a solid HATCH on the `BACKGROUND` layer.
- The color is a true color; you can use `#RRGGBB` or `r,g,b`.
- The hatch is BYLAYER, so changing the layer color in CAD updates the fill.

## Supported Dimension Types
- `overall_length`
- `overall_width`
- `diameter`
- `rect_width`
- `rect_height`
- `offset_from_center_x`
- `offset_from_center_y`
- `offset_from_left`

Dimensions accept optional placement controls:
- `where`: `left | right | up | down`
- `distance`: mm from the **object edge** (not the plate)

Small hole diameters automatically place text outside if
`styles.dimensions.small_hole_outside_threshold` is set.

## Reference Syntax
Some fields can reference other geometry:
- `x_ref: hole4.center.x`
- `y_ref: rect1.center.y`
- `to_x_ref: hole4.center.x`

## Title Block
`title_block.fields` replaces placeholders in the template. If `Issue date` is set to `DD.MM.YYYY`, it is replaced with the current date when generating.

## Extension Points (Safe and Backward-Compatible)
1. **Add a new opening type**
   - Extend `_add_openings` in `scripts/drawing_engine.py`
   - Add minimal geometry info to the `openings` map (center, size)

2. **Add a new dimension type**
   - Extend `_add_dimensions` to interpret new items
   - Use existing axis extension logic (`axis_limits`)

3. **Add new projections (front/top/side)**
   - Add a `views:` section in YAML (future)
   - Each view can define its origin, scale, and which openings/dims to render
   - The renderer can iterate views and apply transforms before drawing

4. **Add annotations or symbols**
   - Extend `_add_text` or add a new `annotations:` section

### Backward Compatibility Rules
- New YAML keys **must be optional** with safe defaults.
- Never change meaning of existing keys.
- Older YAML files should still render the same output.

## Why This Architecture
- **Stable core**: the renderer is generic and only grows by adding new features.
- **Editable specs**: you can tweak dimensions and placements directly in YAML.
- **AI‑assisted translation**: AI is used to convert human text into YAML, not to rewrite the renderer each time.
