"""Generate the GBS-8200 ground plane drawing as a DXF file."""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

CACHE_ROOT = Path(".tmp")
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("XDG_CACHE_HOME", str(CACHE_ROOT))

import ezdxf

from dxf_template import (
    TitleBlockFields,
    apply_title_block_fields,
    center_entities_on_sheet,
    ensure_linetype,
    fit_layout_to_free_area,
    find_border_bbox,
    load_template,
)

DIMENSION_KEYS = {
    "length": "longueur totale",
    "width": "largeur totale",
    "offset_x": "positions horizontale du trou en haut à droite",
    "offset_y": "positions verticale du trou en haut à droite",
}


@dataclass(frozen=True)
class PanelSpec:
    """Geometric specification for the ground plane."""

    length_mm: float
    width_mm: float
    thickness_mm: float
    hole_diameter_mm: float
    hole_offset_x_mm: float
    hole_offset_y_mm: float


@dataclass(frozen=True)
class DrawingConfig:
    """Drawing configuration and styling."""

    axis_overhang_mm: float
    axis_linetype_name: str
    outline_lineweight_mm: float
    dimension_lineweight_mm: float
    axis_lineweight_mm: float
    text_height_mm: float
    dim_offset_mm: float


def build_spec() -> PanelSpec:
    """Return the ground plane specification."""

    return PanelSpec(
        length_mm=150.0,
        width_mm=120.0,
        thickness_mm=3.0,
        hole_diameter_mm=3.5,
        hole_offset_x_mm=55.0,
        hole_offset_y_mm=47.0,
    )


def build_config() -> DrawingConfig:
    """Return drawing configuration values."""

    text_height_mm = 9.0 / 72.0 * 25.4
    return DrawingConfig(
        axis_overhang_mm=3.0,
        axis_linetype_name="DASHDOT",
        outline_lineweight_mm=0.7,
        dimension_lineweight_mm=0.35,
        axis_lineweight_mm=0.35,
        text_height_mm=text_height_mm,
        dim_offset_mm=8.0,
    )


def build_title_block_fields() -> TitleBlockFields:
    """Return title block values from the project spec."""

    today = date.today().strftime("%d.%m.%Y")
    return TitleBlockFields(
        title="GBS-8200_Ground_Plane",
        document_type="Case Part",
        drawing_number="20260131-03",
        issue_date=today,
        material="Plastic ABS",
    )


def build_output_path(output_dir: Path) -> Path:
    """Return the output .dxf file path."""

    return output_dir / "GBS-8200_Ground_Plane.dxf"

def parse_dimension_overrides(spec_path: Path) -> dict[str, tuple[str, float]]:
    """Parse optional where/distance overrides from the spec file."""

    overrides: dict[str, tuple[str, float]] = {}
    if not spec_path.exists():
        return overrides

    in_cotes = False
    for raw_line in spec_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("#### Cotes"):
            in_cotes = True
            continue
        if in_cotes and line.startswith("###"):
            break
        if not in_cotes or not line.startswith("-"):
            continue
        if "where:" not in line or "distance:" not in line:
            continue

        label = line.split(";")[0].lstrip("-").strip().lower()
        where_match = re.search(r"where:\s*(left|right|up|down)", line, re.IGNORECASE)
        dist_match = re.search(r"distance:\s*([0-9.]+)", line, re.IGNORECASE)
        if not where_match or not dist_match:
            continue
        where = where_match.group(1).lower()
        distance = float(dist_match.group(1))

        for key, token in DIMENSION_KEYS.items():
            if token in label:
                overrides[key] = (where, distance)
                break

    return overrides


def to_lineweight_hundredths(lineweight_mm: float) -> int:
    """Convert lineweight in mm to DXF lineweight units (1/100 mm)."""

    return max(0, int(round(lineweight_mm * 100.0)))


def setup_layers(doc: ezdxf.EzDXF, config: DrawingConfig) -> dict[str, str]:
    """Create layers and return layer names."""

    outline_weight = to_lineweight_hundredths(config.outline_lineweight_mm)
    dim_weight = to_lineweight_hundredths(config.dimension_lineweight_mm)
    axis_weight = to_lineweight_hundredths(config.axis_lineweight_mm)
    ensure_linetype(doc, config.axis_linetype_name)

    def ensure_layer(name: str, **attribs: float | str) -> None:
        if name in doc.layers:
            layer = doc.layers.get(name)
            for key, value in attribs.items():
                setattr(layer.dxf, key, value)
        else:
            doc.layers.add(name, **attribs)

    ensure_layer("OUTLINE", lineweight=outline_weight)
    ensure_layer("CUTOUTS", lineweight=outline_weight)
    ensure_layer("AXES", lineweight=axis_weight, linetype=config.axis_linetype_name)
    ensure_layer("DIMENSIONS", lineweight=dim_weight)
    ensure_layer("TEXT", lineweight=dim_weight)

    return {
        "outline": "OUTLINE",
        "cutouts": "CUTOUTS",
        "axes": "AXES",
        "dimensions": "DIMENSIONS",
        "text": "TEXT",
    }


def add_panel_outline(msp: ezdxf.layouts.Modelspace, layers: dict[str, str], spec: PanelSpec) -> None:
    """Add the panel outline."""

    x0, y0 = 0.0, 0.0
    x1, y1 = spec.length_mm, spec.width_mm
    msp.add_lwpolyline(
        [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)],
        dxfattribs={"layer": layers["outline"]},
        close=False,
    )


def add_holes(msp: ezdxf.layouts.Modelspace, layers: dict[str, str], spec: PanelSpec) -> None:
    """Add the four corner holes."""

    center_x = spec.length_mm / 2.0
    center_y = spec.width_mm / 2.0
    offsets = [
        (-spec.hole_offset_x_mm, spec.hole_offset_y_mm),
        (-spec.hole_offset_x_mm, -spec.hole_offset_y_mm),
        (spec.hole_offset_x_mm, -spec.hole_offset_y_mm),
        (spec.hole_offset_x_mm, spec.hole_offset_y_mm),
    ]
    for dx, dy in offsets:
        msp.add_circle(
            (center_x + dx, center_y + dy),
            radius=spec.hole_diameter_mm / 2.0,
            dxfattribs={"layer": layers["cutouts"]},
        )


def add_axes(
    msp: ezdxf.layouts.Modelspace,
    layers: dict[str, str],
    spec: PanelSpec,
    config: DrawingConfig,
    extend_top_y: float | None,
    extend_right_x: float | None,
    dim_hole_center: tuple[float, float] | None,
) -> None:
    """Add symmetry axes with overhang."""

    center_x = spec.length_mm / 2.0
    center_y = spec.width_mm / 2.0
    overhang = config.axis_overhang_mm

    msp.add_line(
        (center_x, -overhang),
        (center_x, spec.width_mm + overhang),
        dxfattribs={"layer": layers["axes"], "linetype": config.axis_linetype_name, "lineweight": -1},
    )
    msp.add_line(
        (-overhang, center_y),
        (spec.length_mm + overhang, center_y),
        dxfattribs={"layer": layers["axes"], "linetype": config.axis_linetype_name, "lineweight": -1},
    )

    hole_radius = spec.hole_diameter_mm / 2.0
    short_extra = 2.0
    top_y = extend_top_y + 2.0 if extend_top_y is not None else None
    right_x = extend_right_x + 2.0 if extend_right_x is not None else None

    hole_centers = [
        (center_x - spec.hole_offset_x_mm, center_y + spec.hole_offset_y_mm),
        (center_x - spec.hole_offset_x_mm, center_y - spec.hole_offset_y_mm),
        (center_x + spec.hole_offset_x_mm, center_y - spec.hole_offset_y_mm),
        (center_x + spec.hole_offset_x_mm, center_y + spec.hole_offset_y_mm),
    ]

    for hx, hy in hole_centers:
        y1 = hy - hole_radius - short_extra
        y2 = hy + hole_radius + short_extra
        x1 = hx - hole_radius - short_extra
        x2 = hx + hole_radius + short_extra

        if dim_hole_center and (hx, hy) == dim_hole_center and top_y is not None:
            y2 = max(y2, top_y)
        if dim_hole_center and (hx, hy) == dim_hole_center and right_x is not None:
            x2 = max(x2, right_x)

        msp.add_line(
            (hx, y1),
            (hx, y2),
            dxfattribs={"layer": layers["axes"], "linetype": config.axis_linetype_name, "lineweight": -1},
        )
        msp.add_line(
            (x1, hy),
            (x2, hy),
            dxfattribs={"layer": layers["axes"], "linetype": config.axis_linetype_name, "lineweight": -1},
        )


def add_dimensions(
    msp: ezdxf.layouts.Modelspace,
    layers: dict[str, str],
    spec: PanelSpec,
    config: DrawingConfig,
) -> tuple[float, float, tuple[float, float]]:
    """Add ISO-style dimensions for length, width, hole diameters, and offsets."""

    dimstyle = "ISO-25"
    if dimstyle not in msp.doc.dimstyles:
        msp.doc.dimstyles.new(dimstyle)

    lineweight = to_lineweight_hundredths(config.dimension_lineweight_mm)
    style = msp.doc.dimstyles.get(dimstyle)
    style.dxf.dimlwd = lineweight
    style.dxf.dimlwe = lineweight

    # Overall length and width
    overrides = parse_dimension_overrides(Path("projets/GBS-8200/GBS-8200_Ground_Plane.md"))
    length_where, length_dist = overrides.get("length", ("down", config.dim_offset_mm))
    width_where, width_dist = overrides.get("width", ("left", config.dim_offset_mm))

    length_base_y = -length_dist if length_where == "down" else spec.width_mm + length_dist
    width_base_x = -width_dist if width_where == "left" else spec.length_mm + width_dist

    msp.add_linear_dim(
        base=(0.0, length_base_y),
        p1=(0.0, 0.0),
        p2=(spec.length_mm, 0.0),
        dimstyle=dimstyle,
        dxfattribs={"layer": layers["dimensions"]},
    ).render()

    msp.add_linear_dim(
        base=(width_base_x, 0.0),
        p1=(0.0, 0.0),
        p2=(0.0, spec.width_mm),
        angle=90.0,
        dimstyle=dimstyle,
        dxfattribs={"layer": layers["dimensions"]},
    ).render()

    center_x = spec.length_mm / 2.0
    center_y = spec.width_mm / 2.0

    # Diameter dimension for holes
    msp.add_diameter_dim(
        center=(center_x - spec.hole_offset_x_mm, center_y + spec.hole_offset_y_mm),
        radius=spec.hole_diameter_mm / 2.0,
        angle=45.0,
        dimstyle=dimstyle,
        dxfattribs={"layer": layers["dimensions"]},
    ).render()

    # Offset dimensions from axes
    offset_x_where, offset_x_dist = overrides.get("offset_x", ("down", config.dim_offset_mm))
    offset_y_where, offset_y_dist = overrides.get("offset_y", ("left", config.dim_offset_mm))

    # Use top-right hole as reference
    hole_x = center_x + spec.hole_offset_x_mm
    hole_y = center_y + spec.hole_offset_y_mm
    radius = spec.hole_diameter_mm / 2.0

    if offset_x_where == "down":
        top_dim_y = hole_y - (radius + offset_x_dist)
    elif offset_x_where == "up":
        top_dim_y = hole_y + (radius + offset_x_dist)
    else:
        top_dim_y = hole_y + (radius + offset_x_dist)

    msp.add_linear_dim(
        base=(center_x, top_dim_y),
        p1=(center_x, hole_y),
        p2=(hole_x, hole_y),
        dimstyle=dimstyle,
        dxfattribs={"layer": layers["dimensions"]},
    ).render()

    if offset_y_where == "left":
        right_dim_x = hole_x - (radius + offset_y_dist)
    elif offset_y_where == "right":
        right_dim_x = hole_x + (radius + offset_y_dist)
    else:
        right_dim_x = hole_x + (radius + offset_y_dist)

    msp.add_linear_dim(
        base=(right_dim_x, hole_y),
        p1=(hole_x, center_y),
        p2=(hole_x, hole_y),
        angle=90.0,
        dimstyle=dimstyle,
        dxfattribs={"layer": layers["dimensions"]},
    ).render()

    return top_dim_y, right_dim_x, (hole_x, hole_y)


def create_drawing(
    output_path: Path,
    spec: PanelSpec,
    config: DrawingConfig,
    template_path: Path | None,
) -> None:
    """Create and save the DXF drawing."""

    doc, existing_handles = load_template(template_path)
    if template_path and not template_path.exists():
        print(f"Template not found, using blank DXF: {template_path}")

    doc.units = ezdxf.units.MM
    doc.header["$LTSCALE"] = 1.0

    layers = setup_layers(doc, config)
    apply_title_block_fields(doc, build_title_block_fields())

    msp = doc.modelspace()
    add_panel_outline(msp, layers, spec)
    add_holes(msp, layers, spec)
    top_dim_y, right_dim_x, dim_hole_center = add_dimensions(msp, layers, spec, config)
    add_axes(msp, layers, spec, config, top_dim_y, right_dim_x, dim_hole_center)

    border_box = None
    if template_path and template_path.exists():
        drawing_entities = [
            entity
            for entity in msp
            if isinstance(entity, ezdxf.entities.DXFGraphic)
            and entity.dxf.handle not in existing_handles
        ]
        border_box = center_entities_on_sheet(msp, drawing_entities)

    if template_path and template_path.exists():
        try:
            layout = doc.layouts.get("Layout1")
        except KeyError:
            layout = None
        if layout is not None:
            if border_box is None or not border_box.has_data:
                border_box = find_border_bbox(msp)
            fit_layout_to_free_area(layout, border_box)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(output_path)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Generate the GBS-8200 ground plane drawing as a DXF file."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("projets/GBS-8200"),
        help="Directory where the DXF file will be written.",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=Path("templates/A4_Landscape_ISO5457_minimal.dxf"),
        help="DXF template to use for the drawing sheet.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the DXF generator."""

    args = parse_args()
    spec = build_spec()
    config = build_config()

    output_path = build_output_path(args.output_dir)
    create_drawing(output_path, spec, config, args.template)

    print(f"DXF written to: {output_path}")


if __name__ == "__main__":
    main()
