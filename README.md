# Drawings - DXF Technical Sketch Generator

This project generates technical drawing sketches in DXF based on the
specification in `TODO.md`. The main output is a DXF file in `output/`
and a matching Python generator in `scripts/`.

## Project Goals
- Generate ISO-style technical sketches from `TODO.md`
- Use a stable DXF template for QCAD/LibreCAD/FreeCAD compatibility
- Export DXF layers to SVG for laser cutting or engraving

## Tools

### 1) DXF Generator
Script: `scripts/GBS-8200_Front_Panel.py`
- Reads the geometry spec in `TODO.md`
- Outputs `projets/GBS-8200/output/GBS-8200_Front_Panel.dxf`
- Uses default template: `templates/A4_Landscape_ISO5457_minimal.dxf`

Run:
```
python scripts/GBS-8200_Front_Panel.py --help
python scripts/GBS-8200_Front_Panel.py
```

### 2) SVG to DXF Template Converter
Script: `tools/svg_to_dxf.py`
- Converts a template SVG to DXF
- Creates a layer mapping report alongside the DXF

Run:
```
python tools/svg_to_dxf.py templates/svg/A4_Landscape_ISO5457_minimal.svg
```

### 3) DXF Layer Export to SVG (Laser)
Script: `tools/dxf_layers_to_svg.py`
- Export selected layers to SVG
- Presets:
  - `cut`: `OUTLINE` + `CUTOUTS`
  - `engrave`: `OUTLINE` + `TEXT` (text exported as paths by default)

Run:
```
python tools/dxf_layers_to_svg.py projets/GBS-8200/output/GBS-8200_Front_Panel.dxf --preset cut
python tools/dxf_layers_to_svg.py projets/GBS-8200/output/GBS-8200_Front_Panel.dxf --preset engrave
```

## Workflow to Create a New Drawing
1. Update `TODO.md` with the new geometry spec.
2. Create a generator script in `scripts/` named after the output DXF.
3. Run the script to generate the DXF in `output/`.
4. Open in QCAD/LibreCAD/FreeCAD and validate geometry, layers, and dimensions.
5. Export SVG for laser use if needed.

## Conventions
- Text, comments, and docstrings in English.
- Follow PEP 8 for Python code.
- Use DXF lineweights and ISO linetypes for axes and dimensions.
- Keep symmetry axes as dash-dot and extend 3 mm beyond part edges unless specified.

## Files
- `TODO.md`: current geometry spec
- `scripts/`: DXF generators
- `output/`: generated DXF/SVG (not tracked)
- `templates/`: DXF templates used as sheets
- `tools/`: conversion utilities
