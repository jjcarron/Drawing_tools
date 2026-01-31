"""Generate the GBS-8200 back panel drawing as a DXF file."""

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
from ezdxf.enums import TextEntityAlignment

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
    "hole3_diameter": "diamètre du trou circulaire 3",
    "hole4_diameter": "diamètre du trou circulaire 4",
    "rect_width": "largeur de l'ouverture rectangulaire",
    "rect_height": "hauteur de l'ouverture rectangulaire",
    "holes13_pos": "position horizontale des trous circulaires 1 et 3",
    "hole2_pos": "position horizontale du trou circulaire 2",
    "hole4_pos_left": "position horizontale du trou circulaire 4 par rapport au bord gauche de la pièce",
}

AxisLimits = dict[float | str, dict[str, float | None]]


@dataclass(frozen=True)
class PanelSpec:
    """Geometric specification for the back panel."""

    length_mm: float
    width_mm: float
    thickness_mm: float
    circle_diameter_mm: float
    circle1_offset_x_mm: float
    circle2_offset_x_mm: float
    circle3_offset_x_mm: float
    small_circle_diameter_mm: float
    small_circle_center_x_mm: float
    notch_height_mm: float
    rect_width_mm: float
    rect_height_mm: float
    rect_offset_x_mm: float


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
    """Return the panel specification extracted from the project file."""

    return PanelSpec(
        length_mm=147.0,
        width_mm=37.0,
        thickness_mm=3.0,
        circle_diameter_mm=10.0,
        circle1_offset_x_mm=-5.0,
        circle2_offset_x_mm=9.0,
        circle3_offset_x_mm=23.0,
        small_circle_diameter_mm=5.0,
        small_circle_center_x_mm=10.0,
        notch_height_mm=3.0,
        rect_width_mm=31.0,
        rect_height_mm=11.0,
        rect_offset_x_mm=-30.0,
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
        title="GBS-8200_Back_Panel",
        document_type="Case Part",
        drawing_number="20260131-01",
        issue_date=today,
        material="Plastic ABS",
    )


def build_output_path(output_dir: Path) -> Path:
    """Return the output .dxf file path."""

    return output_dir / "GBS-8200_Back_Panel.dxf"

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


def parse_dimension_requests(spec_path: Path) -> set[str]:
    """Return which dimension labels are requested in the spec file."""

    requested: set[str] = set()
    if not spec_path.exists():
        return requested

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

        label = line.split(";")[0].lstrip("-").strip().lower()
        for key, token in DIMENSION_KEYS.items():
            if token in label:
                requested.add(key)
                break

    return requested


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


def setup_text_style(doc: ezdxf.EzDXF) -> str:
    """Create a text style for the labels."""

    style_name = "LABEL"
    if style_name not in doc.styles:
        doc.styles.add(style_name, font="Segoe UI Semibold.ttf")
    return style_name


def add_panel_outline(msp: ezdxf.layouts.Modelspace, layers: dict[str, str], spec: PanelSpec) -> None:
    """Add the panel outline."""

    x0, y0 = 0.0, 0.0
    x1, y1 = spec.length_mm, spec.width_mm
    msp.add_lwpolyline(
        [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)],
        dxfattribs={"layer": layers["outline"]},
        close=False,
    )


def add_openings(msp: ezdxf.layouts.Modelspace, layers: dict[str, str], spec: PanelSpec) -> None:
    """Add circular holes, rectangular opening, and U-notch."""

    center_x = spec.length_mm / 2.0
    center_y = spec.width_mm / 2.0

    # Circular holes 1-3 (10 mm)
    offsets = [spec.circle1_offset_x_mm, spec.circle2_offset_x_mm, spec.circle3_offset_x_mm]
    for offset in offsets:
        cx = center_x + offset
        msp.add_circle(
            (cx, center_y),
            radius=spec.circle_diameter_mm / 2.0,
            dxfattribs={"layer": layers["cutouts"]},
        )

    # Circular hole 4 (5 mm)
    msp.add_circle(
        (spec.small_circle_center_x_mm, center_y),
        radius=spec.small_circle_diameter_mm / 2.0,
        dxfattribs={"layer": layers["cutouts"]},
    )

    # U-notch open to the left, height 3 mm, ends at the 5 mm hole center.
    notch_half_h = spec.notch_height_mm / 2.0
    notch_points = [
        (0.0, center_y - notch_half_h),
        (spec.small_circle_center_x_mm, center_y - notch_half_h),
        (spec.small_circle_center_x_mm, center_y + notch_half_h),
        (0.0, center_y + notch_half_h),
        (0.0, center_y - notch_half_h),
    ]
    msp.add_lwpolyline(notch_points, dxfattribs={"layer": layers["cutouts"]})

    # Rectangular opening
    rect_center_x = center_x + spec.rect_offset_x_mm
    rect_half_w = spec.rect_width_mm / 2.0
    rect_half_h = spec.rect_height_mm / 2.0
    rect_points = [
        (rect_center_x - rect_half_w, center_y - rect_half_h),
        (rect_center_x + rect_half_w, center_y - rect_half_h),
        (rect_center_x + rect_half_w, center_y + rect_half_h),
        (rect_center_x - rect_half_w, center_y + rect_half_h),
        (rect_center_x - rect_half_w, center_y - rect_half_h),
    ]
    msp.add_lwpolyline(rect_points, dxfattribs={"layer": layers["cutouts"]})


def add_axes(
    msp: ezdxf.layouts.Modelspace,
    layers: dict[str, str],
    spec: PanelSpec,
    config: DrawingConfig,
    axis_limits: AxisLimits | None,
) -> None:
    """Add symmetry axes with overhang."""

    center_x = spec.length_mm / 2.0
    center_y = spec.width_mm / 2.0
    overhang = config.axis_overhang_mm

    rect_center_x = center_x + spec.rect_offset_x_mm
    circle1_center_x = center_x + spec.circle1_offset_x_mm
    circle2_center_x = center_x + spec.circle2_offset_x_mm
    circle3_center_x = center_x + spec.circle3_offset_x_mm
    small_circle_center_x = spec.small_circle_center_x_mm

    # Main center axes (extend if dimension levels are above/below the plate)
    center_top = spec.width_mm + overhang
    center_bottom = -overhang
    if axis_limits and axis_limits.get("center"):
        center_limits = axis_limits["center"]
        if center_limits.get("max") is not None:
            center_top = max(center_top, center_limits["max"])
        if center_limits.get("min") is not None:
            center_bottom = min(center_bottom, center_limits["min"])
    msp.add_line(
        (center_x, center_bottom),
        (center_x, center_top),
        dxfattribs={"layer": layers["axes"], "linetype": config.axis_linetype_name, "lineweight": -1},
    )
    msp.add_line(
        (-overhang, center_y),
        (spec.length_mm + overhang, center_y),
        dxfattribs={"layer": layers["axes"], "linetype": config.axis_linetype_name, "lineweight": -1},
    )

    hole_radius = spec.circle_diameter_mm / 2.0
    small_radius = spec.small_circle_diameter_mm / 2.0
    short_extra = 2.0
    default_top = center_y + hole_radius + short_extra
    default_bottom = center_y - hole_radius - short_extra
    default_small_top = center_y + small_radius + short_extra
    default_small_bottom = center_y - small_radius - short_extra
    # Axes through circular holes (short axes, extended when dimensions require)
    for x_pos in {circle1_center_x, circle2_center_x, circle3_center_x}:
        y1 = default_bottom
        y2 = default_top
        if axis_limits and x_pos in axis_limits:
            limits = axis_limits[x_pos]
            if limits.get("min") is not None:
                y1 = min(y1, limits["min"])
            if limits.get("max") is not None:
                y2 = max(y2, limits["max"])
        msp.add_line(
            (x_pos, y1),
            (x_pos, y2),
            dxfattribs={"layer": layers["axes"], "linetype": config.axis_linetype_name, "lineweight": -1},
        )
        msp.add_line(
            (x_pos - hole_radius - short_extra, center_y),
            (x_pos + hole_radius + short_extra, center_y),
            dxfattribs={"layer": layers["axes"], "linetype": config.axis_linetype_name, "lineweight": -1},
        )

    # Axis through small circular hole
    y1 = default_small_bottom
    y2 = default_small_top
    if axis_limits and small_circle_center_x in axis_limits:
        limits = axis_limits[small_circle_center_x]
        if limits.get("min") is not None:
            y1 = min(y1, limits["min"])
        if limits.get("max") is not None:
            y2 = max(y2, limits["max"])
    msp.add_line(
        (small_circle_center_x, y1),
        (small_circle_center_x, y2),
        dxfattribs={"layer": layers["axes"], "linetype": config.axis_linetype_name, "lineweight": -1},
    )
    msp.add_line(
        (small_circle_center_x - small_radius - short_extra, center_y),
        (small_circle_center_x + small_radius + short_extra, center_y),
        dxfattribs={"layer": layers["axes"], "linetype": config.axis_linetype_name, "lineweight": -1},
    )

    # Axis through rectangular opening (full height)
    msp.add_line(
        (rect_center_x, -overhang),
        (rect_center_x, spec.width_mm + overhang),
        dxfattribs={"layer": layers["axes"], "linetype": config.axis_linetype_name, "lineweight": -1},
    )


def add_dimensions(
    msp: ezdxf.layouts.Modelspace,
    layers: dict[str, str],
    spec: PanelSpec,
    config: DrawingConfig,
) -> AxisLimits:
    """Add ISO-style dimensions for length, width, hole diameters, and offsets."""

    dimstyle = "ISO-25"
    if dimstyle not in msp.doc.dimstyles:
        msp.doc.dimstyles.new(dimstyle)

    lineweight = to_lineweight_hundredths(config.dimension_lineweight_mm)
    style = msp.doc.dimstyles.get(dimstyle)
    style.dxf.dimlwd = lineweight
    style.dxf.dimlwe = lineweight

    spec_path = Path("projets/GBS-8200/GBS-8200_Back_Panel.md")
    overrides = parse_dimension_overrides(spec_path)
    requested = parse_dimension_requests(spec_path)
    length_where, length_dist = overrides.get("length", ("down", config.dim_offset_mm))
    width_where, width_dist = overrides.get("width", ("left", config.dim_offset_mm))

    length_base_y = -length_dist if length_where == "down" else spec.width_mm + length_dist
    width_base_x = -width_dist if width_where == "left" else spec.length_mm + width_dist

    # Overall length and width
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

    # Diameter for 10 mm hole 3
    circle1_center_x = center_x + spec.circle1_offset_x_mm
    circle2_center_x = center_x + spec.circle2_offset_x_mm
    circle3_center_x = center_x + spec.circle3_offset_x_mm
    hole_radius = spec.circle_diameter_mm / 2.0
    small_radius = spec.small_circle_diameter_mm / 2.0
    if "hole3_diameter" in requested:
        hole3_location = None
        hole3_angle = 45.0
        if "hole3_diameter" in overrides:
            hole3_where, hole3_dist = overrides["hole3_diameter"]
            if hole3_where == "right":
                hole3_location = (circle3_center_x + hole_radius + hole3_dist, center_y)
            elif hole3_where == "left":
                hole3_location = (circle3_center_x - hole_radius - hole3_dist, center_y)
            elif hole3_where == "up":
                hole3_location = (circle3_center_x, center_y + hole_radius + hole3_dist)
            elif hole3_where == "down":
                hole3_location = (circle3_center_x, center_y - hole_radius - hole3_dist)
            if hole3_location is not None:
                hole3_angle = None

        msp.add_diameter_dim(
            center=(circle3_center_x, center_y),
            radius=hole_radius,
            angle=hole3_angle,
            location=hole3_location,
            dimstyle=dimstyle,
            dxfattribs={"layer": layers["dimensions"]},
        ).render()

    if "hole4_diameter" in requested:
        hole4_location = None
        hole4_angle = 45.0
        if "hole4_diameter" in overrides:
            hole4_where, hole4_dist = overrides["hole4_diameter"]
            if hole4_where == "right":
                hole4_location = (
                    spec.small_circle_center_x_mm + small_radius + hole4_dist,
                    center_y,
                )
            elif hole4_where == "left":
                hole4_location = (
                    spec.small_circle_center_x_mm - small_radius - hole4_dist,
                    center_y,
                )
            elif hole4_where == "up":
                hole4_location = (
                    spec.small_circle_center_x_mm,
                    center_y + small_radius + hole4_dist,
                )
            elif hole4_where == "down":
                hole4_location = (
                    spec.small_circle_center_x_mm,
                    center_y - small_radius - hole4_dist,
                )
            if hole4_location is not None:
                hole4_angle = None
        else:
            diag_offset = (small_radius + config.dim_offset_mm) / (2.0**0.5)
            hole4_location = (
                spec.small_circle_center_x_mm + diag_offset,
                center_y + diag_offset,
            )
            hole4_angle = None

        msp.add_diameter_dim(
            center=(spec.small_circle_center_x_mm, center_y),
            radius=small_radius,
            angle=hole4_angle,
            location=hole4_location,
            dimstyle=dimstyle,
            dxfattribs={"layer": layers["dimensions"]},
        ).render()

    # Rectangular hole width and height
    rect_center_x = center_x + spec.rect_offset_x_mm
    rect_half_w = spec.rect_width_mm / 2.0
    rect_half_h = spec.rect_height_mm / 2.0
    rect_left = rect_center_x - rect_half_w
    rect_right = rect_center_x + rect_half_w
    rect_bottom = center_y - rect_half_h
    rect_top = center_y + rect_half_h

    rect_width_where, rect_width_dist = overrides.get("rect_width", ("down", config.dim_offset_mm))
    rect_height_where, rect_height_dist = overrides.get("rect_height", ("left", config.dim_offset_mm))

    if rect_width_where == "down":
        rect_width_base_y = rect_bottom - rect_width_dist
        rect_width_p1 = (rect_left, rect_bottom)
        rect_width_p2 = (rect_right, rect_bottom)
    else:
        rect_width_base_y = rect_top + rect_width_dist
        rect_width_p1 = (rect_left, rect_top)
        rect_width_p2 = (rect_right, rect_top)

    msp.add_linear_dim(
        base=(rect_left, rect_width_base_y),
        p1=rect_width_p1,
        p2=rect_width_p2,
        dimstyle=dimstyle,
        dxfattribs={"layer": layers["dimensions"]},
    ).render()

    if rect_height_where == "left":
        rect_height_base_x = rect_left - rect_height_dist
        rect_height_p1 = (rect_left, rect_bottom)
        rect_height_p2 = (rect_left, rect_top)
    else:
        rect_height_base_x = rect_right + rect_height_dist
        rect_height_p1 = (rect_right, rect_bottom)
        rect_height_p2 = (rect_right, rect_top)

    msp.add_linear_dim(
        base=(rect_height_base_x, rect_bottom),
        p1=rect_height_p1,
        p2=rect_height_p2,
        angle=90.0,
        dimstyle=dimstyle,
        dxfattribs={"layer": layers["dimensions"]},
    ).render()

    def update_limit(limit: dict[str, float | None], base_y: float) -> None:
        if base_y >= center_y:
            value = base_y + 2.0
            limit["max"] = value if limit.get("max") is None else max(limit["max"], value)
        else:
            value = base_y - 2.0
            limit["min"] = value if limit.get("min") is None else min(limit["min"], value)

    axis_limits: dict[str, dict[str, float | None]] = {
        "center": {"min": None, "max": None},
        circle1_center_x: {"min": None, "max": None},
        circle2_center_x: {"min": None, "max": None},
        circle3_center_x: {"min": None, "max": None},
        spec.small_circle_center_x_mm: {"min": None, "max": None},
    }

    def base_y_for_hole(where: str, distance: float, radius: float) -> float:
        if where == "down":
            return center_y - (radius + distance)
        return center_y + (radius + distance)

    holes13_where, holes13_dist = overrides.get("holes13_pos", ("up", config.dim_offset_mm))
    holes13_base_y = base_y_for_hole(holes13_where, holes13_dist, hole_radius)
    for x_pos in (circle1_center_x, circle3_center_x):
        msp.add_linear_dim(
            base=(center_x, holes13_base_y),
            p1=(center_x, center_y),
            p2=(x_pos, center_y),
            dimstyle=dimstyle,
            dxfattribs={"layer": layers["dimensions"]},
        ).render()
        update_limit(axis_limits["center"], holes13_base_y)
        update_limit(axis_limits[x_pos], holes13_base_y)

    hole2_where, hole2_dist = overrides.get("hole2_pos", ("down", config.dim_offset_mm))
    hole2_base_y = base_y_for_hole(hole2_where, hole2_dist, hole_radius)
    msp.add_linear_dim(
        base=(center_x, hole2_base_y),
        p1=(center_x, center_y),
        p2=(circle2_center_x, center_y),
        dimstyle=dimstyle,
        dxfattribs={"layer": layers["dimensions"]},
    ).render()
    update_limit(axis_limits["center"], hole2_base_y)
    update_limit(axis_limits[circle2_center_x], hole2_base_y)

    hole4_where, hole4_dist = overrides.get("hole4_pos_left", ("up", config.dim_offset_mm))
    hole4_base_y = base_y_for_hole(hole4_where, hole4_dist, small_radius)
    msp.add_linear_dim(
        base=(0.0, hole4_base_y),
        p1=(0.0, center_y),
        p2=(spec.small_circle_center_x_mm, center_y),
        dimstyle=dimstyle,
        dxfattribs={"layer": layers["dimensions"]},
    ).render()
    update_limit(axis_limits[spec.small_circle_center_x_mm], hole4_base_y)

    return axis_limits


def add_text_annotations(
    msp: ezdxf.layouts.Modelspace,
    layers: dict[str, str],
    spec: PanelSpec,
    config: DrawingConfig,
    style_name: str,
) -> None:
    """Add text annotations for the panel."""

    center_x = spec.length_mm / 2.0
    bottom_y = 6.0

    rect_center_x = center_x + spec.rect_offset_x_mm
    circle1_center_x = center_x + spec.circle1_offset_x_mm
    circle2_center_x = center_x + spec.circle2_offset_x_mm
    circle3_center_x = center_x + spec.circle3_offset_x_mm

    labels = [
        ("RGBHV", rect_center_x),
        ("Y", circle1_center_x),
        ("Pb", circle2_center_x),
        ("Pr", circle3_center_x),
    ]

    for text_value, x_pos in labels:
        text = msp.add_text(
            text_value,
            dxfattribs={
                "layer": layers["text"],
                "style": style_name,
                "height": config.text_height_mm,
            },
        )
        text.set_placement((x_pos, bottom_y), align=TextEntityAlignment.MIDDLE_CENTER)


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
    style_name = setup_text_style(doc)
    apply_title_block_fields(doc, build_title_block_fields())

    msp = doc.modelspace()
    add_panel_outline(msp, layers, spec)
    add_openings(msp, layers, spec)
    axis_limits = add_dimensions(msp, layers, spec, config)
    add_axes(msp, layers, spec, config, axis_limits)
    add_text_annotations(msp, layers, spec, config, style_name)

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
        description="Generate the GBS-8200 back panel drawing as a DXF file."
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
