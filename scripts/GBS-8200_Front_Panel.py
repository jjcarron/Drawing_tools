"""Generate the RGBS2VGA front panel drawing as a DXF file."""

from __future__ import annotations

import argparse
import os
from datetime import date
from dataclasses import dataclass
from pathlib import Path

CACHE_ROOT = Path(".tmp")
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("XDG_CACHE_HOME", str(CACHE_ROOT))

import ezdxf
from ezdxf.enums import TextEntityAlignment
from ezdxf.math import Vec2
from ezdxf import bbox


@dataclass(frozen=True)
class PanelSpec:
    """Geometric specification for the front panel."""

    length_mm: float
    width_mm: float
    thickness_mm: float
    circular_hole_diameter_mm: float
    circular_hole_offset_x_mm: float
    rectangular_hole_width_mm: float
    rectangular_hole_height_mm: float
    rectangular_hole_offset_x_mm: float


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


@dataclass(frozen=True)
class TitleBlockFields:
    """Text fields to place in the title block template."""

    title: str
    document_type: str
    drawing_number: str
    issue_date: str
    material: str


def build_spec() -> PanelSpec:
    """Return the panel specification extracted from TODO.md."""

    return PanelSpec(
        length_mm=147.0,
        width_mm=37.0,
        thickness_mm=3.0,
        circular_hole_diameter_mm=8.0,
        circular_hole_offset_x_mm=-41.5,
        rectangular_hole_width_mm=31.0,
        rectangular_hole_height_mm=11.0,
        rectangular_hole_offset_x_mm=33.0,
    )


def build_config() -> DrawingConfig:
    """Return drawing configuration values."""

    # 9 pt -> 9/72 inch -> 3.175 mm
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
        title="GBS-8200_Front_Panel",
        document_type="Case Part",
        drawing_number="20260131-01",
        issue_date=today,
        material="Plastic ABS",
    )


def build_output_path(output_dir: Path) -> Path:
    """Return the output .dxf file path."""

    return output_dir / "GBS-8200_Front_Panel.dxf"


def to_lineweight_hundredths(lineweight_mm: float) -> int:
    """Convert lineweight in mm to DXF lineweight units (1/100 mm)."""

    return max(0, int(round(lineweight_mm * 100.0)))


def ensure_linetype(doc: ezdxf.EzDXF, name: str) -> None:
    """Ensure the custom symmetry axis linetype exists."""

    if name in doc.linetypes:
        linetype = doc.linetypes.get(name)
        linetype.pattern = [15.0, 6.0, -1.5, 0.0, -1.5, 6.0]
        return

    # Fallback dash-dot pattern if template does not define it.
    doc.linetypes.add(
        name,
        pattern=[15.0, 6.0, -1.5, 0.0, -1.5, 6.0],
        description="Symmetry axis dash-dot 6-1.5-0-1.5-6",
    )


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
    """Create a text style for the title."""

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


def add_holes(msp: ezdxf.layouts.Modelspace, layers: dict[str, str], spec: PanelSpec) -> None:
    """Add the circular and rectangular holes."""

    center_x = spec.length_mm / 2.0
    center_y = spec.width_mm / 2.0

    circle_center = (center_x + spec.circular_hole_offset_x_mm, center_y)
    msp.add_circle(
        circle_center,
        radius=spec.circular_hole_diameter_mm / 2.0,
        dxfattribs={"layer": layers["cutouts"]},
    )

    rect_center_x = center_x + spec.rectangular_hole_offset_x_mm
    rect_half_w = spec.rectangular_hole_width_mm / 2.0
    rect_half_h = spec.rectangular_hole_height_mm / 2.0
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
    top_dim_y: float,
) -> None:
    """Add symmetry axes with overhang."""

    center_x = spec.length_mm / 2.0
    center_y = spec.width_mm / 2.0
    overhang = config.axis_overhang_mm
    top_y = max(spec.width_mm + overhang, top_dim_y + 2.0)

    circle_center_x = center_x + spec.circular_hole_offset_x_mm
    rect_center_x = center_x + spec.rectangular_hole_offset_x_mm
    circle_bottom_y = center_y - spec.circular_hole_diameter_mm / 2.0
    rect_bottom_y = center_y - spec.rectangular_hole_height_mm / 2.0

    msp.add_line(
        (center_x, -overhang),
        (center_x, top_y),
        dxfattribs={
            "layer": layers["axes"],
            "linetype": config.axis_linetype_name,
            "lineweight": -1,
        },
    )
    msp.add_line(
        (-overhang, center_y),
        (spec.length_mm + overhang, center_y),
        dxfattribs={
            "layer": layers["axes"],
            "linetype": config.axis_linetype_name,
            "lineweight": -1,
        },
    )

    msp.add_line(
        (circle_center_x, circle_bottom_y - 2.0),
        (circle_center_x, top_y),
        dxfattribs={
            "layer": layers["axes"],
            "linetype": config.axis_linetype_name,
            "lineweight": -1,
        },
    )

    msp.add_line(
        (rect_center_x, rect_bottom_y - 2.0),
        (rect_center_x, top_y),
        dxfattribs={
            "layer": layers["axes"],
            "linetype": config.axis_linetype_name,
            "lineweight": -1,
        },
    )


def add_dimensions(
    msp: ezdxf.layouts.Modelspace,
    layers: dict[str, str],
    spec: PanelSpec,
    config: DrawingConfig,
) -> None:
    """Add ISO-style dimensions for length, width, and hole diameter."""

    lineweight = to_lineweight_hundredths(config.dimension_lineweight_mm)
    dimstyle = "ISO-25"
    if dimstyle not in msp.doc.dimstyles:
        msp.doc.dimstyles.new(dimstyle)
    style = msp.doc.dimstyles.get(dimstyle)
    style.dxf.dimlwd = lineweight
    style.dxf.dimlwe = lineweight

    # Overall length dimension (below the panel).
    msp.add_linear_dim(
        base=(0.0, -config.dim_offset_mm),
        p1=(0.0, 0.0),
        p2=(spec.length_mm, 0.0),
        dimstyle=dimstyle,
        dxfattribs={"layer": layers["dimensions"], "lineweight": lineweight},
    ).render()

    # Overall width dimension (left of the panel).
    msp.add_linear_dim(
        base=(-config.dim_offset_mm, 0.0),
        p1=(0.0, 0.0),
        p2=(0.0, spec.width_mm),
        angle=90.0,
        dimstyle=dimstyle,
        dxfattribs={"layer": layers["dimensions"], "lineweight": lineweight},
    ).render()

    # Diameter dimension for the circular hole.
    center_x = spec.length_mm / 2.0 + spec.circular_hole_offset_x_mm
    center_y = spec.width_mm / 2.0
    radius = spec.circular_hole_diameter_mm / 2.0

    msp.add_diameter_dim(
        center=(center_x, center_y),
        radius=radius,
        angle=45.0,
        dimstyle=dimstyle,
        dxfattribs={"layer": layers["dimensions"], "lineweight": lineweight},
    ).render()

    # Horizontal offsets from plate centerline to opening centers (top level).
    top_dim_y = spec.width_mm + config.dim_offset_mm
    plate_center_x = spec.length_mm / 2.0
    msp.add_linear_dim(
        base=(plate_center_x, top_dim_y),
        p1=(plate_center_x, top_dim_y),
        p2=(center_x, top_dim_y),
        dimstyle=dimstyle,
        dxfattribs={"layer": layers["dimensions"], "lineweight": lineweight},
    ).render()

    rect_center_x = spec.length_mm / 2.0 + spec.rectangular_hole_offset_x_mm
    msp.add_linear_dim(
        base=(plate_center_x, top_dim_y),
        p1=(plate_center_x, top_dim_y),
        p2=(rect_center_x, top_dim_y),
        dimstyle=dimstyle,
        dxfattribs={"layer": layers["dimensions"], "lineweight": lineweight},
    ).render()

    # Rectangular hole width and height dimensions.
    plate_center_y = spec.width_mm / 2.0
    rect_half_w = spec.rectangular_hole_width_mm / 2.0
    rect_half_h = spec.rectangular_hole_height_mm / 2.0
    rect_left = rect_center_x - rect_half_w
    rect_right = rect_center_x + rect_half_w
    rect_bottom = center_y - rect_half_h
    rect_top = center_y + rect_half_h

    msp.add_linear_dim(
        base=(rect_left, plate_center_y + config.dim_offset_mm),
        p1=(rect_left, plate_center_y),
        p2=(rect_right, plate_center_y),
        dimstyle=dimstyle,
        dxfattribs={"layer": layers["dimensions"], "lineweight": lineweight},
    ).render()

    msp.add_linear_dim(
        base=(rect_right + config.dim_offset_mm, rect_bottom),
        p1=(rect_right, rect_bottom),
        p2=(rect_right, rect_top),
        angle=90.0,
        dimstyle=dimstyle,
        dxfattribs={"layer": layers["dimensions"], "lineweight": lineweight},
    ).render()

    return top_dim_y


def add_text_annotations(
    msp: ezdxf.layouts.Modelspace,
    layers: dict[str, str],
    spec: PanelSpec,
    config: DrawingConfig,
    style_name: str,
) -> None:
    """Add text annotations for the panel."""

    right_x = spec.length_mm - 6.0
    top_y = spec.width_mm - 6.0
    center_y = spec.width_mm / 2.0
    bottom_y = 6.0

    circle_center_x = spec.length_mm / 2.0 + spec.circular_hole_offset_x_mm
    rect_center_x = spec.length_mm / 2.0 + spec.rectangular_hole_offset_x_mm

    text = msp.add_text(
        "GBS-8200",
        dxfattribs={
            "layer": layers["text"],
            "style": style_name,
            "height": config.text_height_mm,
        },
    )
    text.set_placement((right_x, top_y), align=TextEntityAlignment.TOP_RIGHT)

    text = msp.add_text(
        "VGA-Out",
        dxfattribs={
            "layer": layers["text"],
            "style": style_name,
            "height": config.text_height_mm,
        },
    )
    text.set_placement((rect_center_x, bottom_y), align=TextEntityAlignment.MIDDLE_CENTER)

    text = msp.add_text(
        "5-12V -(o+",
        dxfattribs={
            "layer": layers["text"],
            "style": style_name,
            "height": config.text_height_mm,
        },
    )
    text.set_placement((circle_center_x, bottom_y), align=TextEntityAlignment.MIDDLE_CENTER)


def fit_layout_to_free_area(layout: ezdxf.layouts.Layout, free_box: bbox.BoundingBox) -> None:
    """Fit the layout viewport to the free sheet area bounding box."""

    if not free_box.has_data:
        return

    viewport = layout.main_viewport()
    if viewport is None:
        layout.reset_main_viewport(Vec2(free_box.center), Vec2(free_box.size) * 1.02)
        return

    width = float(viewport.dxf.width)
    height = float(viewport.dxf.height)
    if width <= 0 or height <= 0:
        layout.reset_main_viewport(Vec2(free_box.center), Vec2(free_box.size) * 1.02)
        return

    aspect = width / height
    view_height = max(free_box.size.y, free_box.size.x / aspect) * 1.02
    viewport.dxf.view_center_point = (float(free_box.center.x), float(free_box.center.y))
    viewport.dxf.view_height = view_height


def find_border_bbox(msp: ezdxf.layouts.Modelspace) -> bbox.BoundingBox:
    """Find the drawing border bounding box from the template."""

    border_entities = [e for e in msp if e.dxf.layer == "Border"]
    border_box = bbox.extents(border_entities, fast=True)
    if not border_box.has_data:
        border_box = bbox.extents(msp, fast=True)
    return border_box


def center_entities_on_sheet(
    msp: ezdxf.layouts.Modelspace, drawing_entities: list[ezdxf.entities.DXFGraphic]
) -> bbox.BoundingBox:
    """Translate drawing entities to center them on the sheet."""

    drawing_box = bbox.extents(drawing_entities, fast=True)
    if not drawing_box.has_data:
        return bbox.BoundingBox()

    border_box = find_border_bbox(msp)
    if not border_box.has_data:
        return bbox.BoundingBox()

    target_center = border_box.center
    delta = target_center - drawing_box.center
    if delta.is_null:
        return border_box

    for entity in drawing_entities:
        entity.translate(delta.x, delta.y, 0.0)
    return border_box


def create_drawing(
    output_path: Path,
    spec: PanelSpec,
    config: DrawingConfig,
    template_path: Path | None,
) -> None:
    """Create and save the DXF drawing."""

    existing_handles: set[str] = set()
    if template_path and template_path.exists():
        doc = ezdxf.readfile(template_path)
        existing_handles = {e.dxf.handle for e in doc.modelspace()}
    else:
        if template_path:
            print(f"Template not found, using blank DXF: {template_path}")
        doc = ezdxf.new(dxfversion="R2010")

    doc.units = ezdxf.units.MM
    doc.header["$LTSCALE"] = 1.0

    layers = setup_layers(doc, config)
    style_name = setup_text_style(doc)
    apply_title_block_fields(doc, build_title_block_fields())

    msp = doc.modelspace()
    add_panel_outline(msp, layers, spec)
    add_holes(msp, layers, spec)
    top_dim_y = add_dimensions(msp, layers, spec, config)
    add_axes(msp, layers, spec, config, top_dim_y)
    add_text_annotations(msp, layers, spec, config, style_name)

    border_box = None
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


def apply_title_block_fields(doc: ezdxf.EzDXF, fields: TitleBlockFields) -> None:
    """Replace placeholder title block values in the template."""

    replacements: dict[str, str] = {}
    if fields.title:
        replacements["ISO 5457 template"] = fields.title
    if fields.document_type:
        replacements["Component Drawing"] = fields.document_type
    if fields.drawing_number:
        replacements["DN"] = fields.drawing_number
    if fields.issue_date:
        replacements["DD-MM-YYYY"] = fields.issue_date
        replacements["YYYY-MM-DD"] = fields.issue_date
    if fields.material:
        replacements["<Material>"] = fields.material

    for entity in doc.modelspace():
        if entity.dxftype() != "TEXT":
            continue
        text_value = entity.dxf.text
        if text_value in replacements:
            entity.dxf.text = replacements[text_value]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Generate the RGBS2VGA front panel drawing as a DXF file."
        )
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
