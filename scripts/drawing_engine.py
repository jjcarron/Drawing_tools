"""Generic DXF renderer for YAML drawing specifications."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import ezdxf
from ezdxf import colors
from ezdxf import bbox
from ezdxf.enums import TextEntityAlignment
from ezdxf.math import Vec2

from dxf_template import (
    TitleBlockFields,
    apply_title_block_fields,
    ensure_linetype,
    fit_layout_to_free_area,
    load_template,
)


@dataclass(frozen=True)
class LayerConfig:
    """Layer configuration."""

    name: str
    lineweight_mm: float
    linetype: str | None = None
    color: str | None = None


def to_lineweight_hundredths(lineweight_mm: float) -> int:
    """Convert lineweight in mm to DXF lineweight units (1/100 mm)."""

    return max(0, int(round(lineweight_mm * 100.0)))


def _get_nested(spec: dict[str, Any], path: list[str], default: Any | None = None) -> Any:
    """Return nested dictionary value."""

    cursor: Any = spec
    for key in path:
        if not isinstance(cursor, dict) or key not in cursor:
            return default
        cursor = cursor[key]
    return cursor


def _resolve_ref(ref: str, openings: dict[str, dict[str, float]]) -> float:
    """Resolve reference strings like 'hole1.center.x'."""

    parts = ref.split(".")
    if len(parts) < 3:
        raise ValueError(f"Invalid reference: {ref}")
    opening_id = parts[0]
    field = ".".join(parts[1:])
    opening = openings.get(opening_id)
    if opening is None:
        raise ValueError(f"Unknown opening reference: {ref}")

    if field == "center.x":
        return opening["center_x"]
    if field == "center.y":
        return opening["center_y"]
    if field == "left":
        return opening["left"]
    if field == "right":
        return opening["right"]
    if field == "top":
        return opening["top"]
    if field == "bottom":
        return opening["bottom"]
    raise ValueError(f"Unsupported reference field: {ref}")


def _resolve_center(
    center_spec: dict[str, float], panel_length: float, panel_width: float
) -> tuple[float, float]:
    """Resolve opening center from relative coordinates."""

    center_x = panel_length / 2.0
    center_y = panel_width / 2.0

    if "x_from_center" in center_spec:
        x = center_x + float(center_spec["x_from_center"])
    elif "x_from_left" in center_spec:
        x = float(center_spec["x_from_left"])
    elif "x_from_right" in center_spec:
        x = panel_length - float(center_spec["x_from_right"])
    elif "x" in center_spec:
        x = float(center_spec["x"])
    else:
        x = center_x

    if "y_from_center" in center_spec:
        y = center_y + float(center_spec["y_from_center"])
    elif "y_from_bottom" in center_spec:
        y = float(center_spec["y_from_bottom"])
    elif "y_from_top" in center_spec:
        y = panel_width - float(center_spec["y_from_top"])
    elif "y" in center_spec:
        y = float(center_spec["y"])
    else:
        y = center_y

    return x, y


def _add_panel_outline(
    msp: ezdxf.layouts.Modelspace, layer_name: str, length: float, width: float
) -> None:
    """Add the panel outline."""

    msp.add_lwpolyline(
        [(0.0, 0.0), (length, 0.0), (length, width), (0.0, width), (0.0, 0.0)],
        dxfattribs={"layer": layer_name},
        close=False,
    )


def _parse_true_color(color: str | tuple[int, int, int] | list[int]) -> int:
    """Convert a color value to DXF true color integer."""

    if isinstance(color, (tuple, list)):
        if len(color) != 3:
            raise ValueError(f"Invalid color tuple: {color}")
        return colors.rgb2int((int(color[0]), int(color[1]), int(color[2])))

    value = str(color).strip()
    if value.startswith("#"):
        value = value[1:]
        if len(value) != 6:
            raise ValueError(f"Invalid color: #{value}")
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
        return colors.rgb2int((r, g, b))

    if "," in value:
        parts = [p.strip() for p in value.split(",")]
        if len(parts) != 3:
            raise ValueError(f"Invalid color: {color}")
        return colors.rgb2int((int(parts[0]), int(parts[1]), int(parts[2])))

    raise ValueError(f"Invalid color: {color}")


def _add_background(
    msp: ezdxf.layouts.Modelspace,
    length: float,
    width: float,
    layer: LayerConfig,
) -> None:
    """Add a solid hatch background following the outline."""

    hatch = msp.add_hatch(color=256)
    hatch.dxf.layer = layer.name
    hatch.set_solid_fill(True)
    # Keep hatch BYLAYER so changing the layer color updates the fill.
    hatch.dxf.color = 256
    hatch.paths.add_polyline_path(
        [(0.0, 0.0), (length, 0.0), (length, width), (0.0, width), (0.0, 0.0)],
        is_closed=True,
    )


def _add_openings(
    msp: ezdxf.layouts.Modelspace,
    spec: dict[str, Any],
    panel_length: float,
    panel_width: float,
    cutout_layer: str,
) -> dict[str, dict[str, float]]:
    """Add openings and return their resolved geometry."""

    openings: dict[str, dict[str, float]] = {}
    for opening in spec.get("openings", []):
        opening_id = opening["id"]
        opening_type = opening["type"]

        if opening_type == "circle":
            diameter = float(opening["diameter"])
            center = _resolve_center(opening["center"], panel_length, panel_width)
            radius = diameter / 2.0
            msp.add_circle(center, radius=radius, dxfattribs={"layer": cutout_layer})

            openings[opening_id] = {
                "type": "circle",
                "center_x": center[0],
                "center_y": center[1],
                "radius": radius,
                "left": center[0] - radius,
                "right": center[0] + radius,
                "top": center[1] + radius,
                "bottom": center[1] - radius,
                "width": diameter,
                "height": diameter,
            }
            continue

        if opening_type == "rect":
            width = float(opening["width"])
            height = float(opening["height"])
            center = _resolve_center(opening["center"], panel_length, panel_width)
            half_w = width / 2.0
            half_h = height / 2.0
            points = [
                (center[0] - half_w, center[1] - half_h),
                (center[0] + half_w, center[1] - half_h),
                (center[0] + half_w, center[1] + half_h),
                (center[0] - half_w, center[1] + half_h),
                (center[0] - half_w, center[1] - half_h),
            ]
            msp.add_lwpolyline(points, dxfattribs={"layer": cutout_layer})

            openings[opening_id] = {
                "type": "rect",
                "center_x": center[0],
                "center_y": center[1],
                "radius": 0.0,
                "left": center[0] - half_w,
                "right": center[0] + half_w,
                "top": center[1] + half_h,
                "bottom": center[1] - half_h,
                "width": width,
                "height": height,
            }
            continue

        if opening_type == "notch_u":
            height = float(opening["height"])
            y_center = panel_width / 2.0
            if not opening.get("centered_on_y", True):
                y_center = float(opening.get("center_y", y_center))
            y1 = y_center - height / 2.0
            y2 = y_center + height / 2.0
            x0 = float(opening.get("from_left", 0.0))
            if "to_x_ref" in opening:
                x1 = _resolve_ref(opening["to_x_ref"], openings)
            else:
                x1 = float(opening["to_x"])
            points = [(x0, y1), (x1, y1), (x1, y2), (x0, y2), (x0, y1)]
            msp.add_lwpolyline(points, dxfattribs={"layer": cutout_layer})
            openings[opening_id] = {
                "type": "notch_u",
                "center_x": (x0 + x1) / 2.0,
                "center_y": y_center,
                "radius": 0.0,
                "left": x0,
                "right": x1,
                "top": y2,
                "bottom": y1,
                "width": abs(x1 - x0),
                "height": height,
            }
            continue

        raise ValueError(f"Unsupported opening type: {opening_type}")

    return openings


def _init_axis_limits(openings: dict[str, dict[str, float]]) -> dict[str, dict[str, float | None]]:
    """Initialize axis extension limits for openings and center axes."""

    limits: dict[str, dict[str, float | None]] = {"__center__": {"v_min": None, "v_max": None, "h_min": None, "h_max": None}}
    for opening_id in openings:
        limits[opening_id] = {"v_min": None, "v_max": None, "h_min": None, "h_max": None}
    return limits


def _update_vertical_limit(
    limits: dict[str, float | None], base_y: float, center_y: float, offset: float = 2.0
) -> None:
    if base_y >= center_y:
        value = base_y + offset
        limits["v_max"] = value if limits["v_max"] is None else max(limits["v_max"], value)
    else:
        value = base_y - offset
        limits["v_min"] = value if limits["v_min"] is None else min(limits["v_min"], value)


def _update_horizontal_limit(
    limits: dict[str, float | None], base_x: float, center_x: float, offset: float = 2.0
) -> None:
    if base_x >= center_x:
        value = base_x + offset
        limits["h_max"] = value if limits["h_max"] is None else max(limits["h_max"], value)
    else:
        value = base_x - offset
        limits["h_min"] = value if limits["h_min"] is None else min(limits["h_min"], value)


def _dimension_offset(item: dict[str, Any], default_offset: float) -> float:
    return float(item.get("distance", default_offset))


def _dimension_where(item: dict[str, Any], default_where: str) -> str:
    return str(item.get("where", default_where))


def _target_size_for_offset(opening: dict[str, float], axis: str) -> float:
    if opening["type"] == "circle":
        return opening["radius"]
    if axis == "x":
        return opening["width"] / 2.0
    return opening["height"] / 2.0


def _add_dimensions(
    msp: ezdxf.layouts.Modelspace,
    spec: dict[str, Any],
    panel_length: float,
    panel_width: float,
    openings: dict[str, dict[str, float]],
    dim_layer: str,
    axis_limits: dict[str, dict[str, float | None]],
) -> None:
    """Add dimensions from the spec."""

    dim_style_name = _get_nested(spec, ["styles", "dimensions", "style"], "ISO-25")
    if dim_style_name not in msp.doc.dimstyles:
        msp.doc.dimstyles.new(dim_style_name)
    dim_style = msp.doc.dimstyles.get(dim_style_name)
    dim_weight = _get_nested(spec, ["styles", "layers", "dimensions", "lineweight"], 0.35)
    dim_weight_hundredths = to_lineweight_hundredths(float(dim_weight))
    dim_style.dxf.dimlwd = dim_weight_hundredths
    dim_style.dxf.dimlwe = dim_weight_hundredths

    default_offset = float(_get_nested(spec, ["styles", "dimensions", "offset"], 7))
    center_x = panel_length / 2.0
    center_y = panel_width / 2.0

    small_hole_threshold = _get_nested(spec, ["styles", "dimensions", "small_hole_outside_threshold"])
    small_hole_threshold = float(small_hole_threshold) if small_hole_threshold is not None else None

    for item in spec.get("dimensions", {}).get("items", []):
        dim_type = item["type"]

        if dim_type == "overall_length":
            where = _dimension_where(item, "down")
            distance = _dimension_offset(item, default_offset)
            base_y = -distance if where == "down" else panel_width + distance
            msp.add_linear_dim(
                base=(0.0, base_y),
                p1=(0.0, 0.0),
                p2=(panel_length, 0.0),
                dimstyle=dim_style_name,
                dxfattribs={"layer": dim_layer},
            ).render()
            continue

        if dim_type == "overall_width":
            where = _dimension_where(item, "left")
            distance = _dimension_offset(item, default_offset)
            base_x = -distance if where == "left" else panel_length + distance
            msp.add_linear_dim(
                base=(base_x, 0.0),
                p1=(0.0, 0.0),
                p2=(0.0, panel_width),
                angle=90.0,
                dimstyle=dim_style_name,
                dxfattribs={"layer": dim_layer},
            ).render()
            continue

        if dim_type == "diameter":
            opening = openings[item["target"]]
            radius = opening["radius"]
            diameter = radius * 2.0
            placement = item.get("placement")
            location = None
            angle = 45.0

            if "where" in item:
                where = _dimension_where(item, "right")
                distance = _dimension_offset(item, default_offset)
                if where == "right":
                    location = (opening["center_x"] + radius + distance, opening["center_y"])
                elif where == "left":
                    location = (opening["center_x"] - radius - distance, opening["center_y"])
                elif where == "up":
                    location = (opening["center_x"], opening["center_y"] + radius + distance)
                elif where == "down":
                    location = (opening["center_x"], opening["center_y"] - radius - distance)
            elif placement == "outside" or (small_hole_threshold is not None and diameter <= small_hole_threshold):
                distance = float(item.get("outside_offset", default_offset))
                diag = (radius + distance) / math.sqrt(2.0)
                location = (opening["center_x"] + diag, opening["center_y"] + diag)

            if location is not None:
                angle = None

            msp.add_diameter_dim(
                center=(opening["center_x"], opening["center_y"]),
                radius=radius,
                angle=angle,
                location=location,
                dimstyle=dim_style_name,
                dxfattribs={"layer": dim_layer},
            ).render()
            continue

        if dim_type in {"rect_width", "rect_height"}:
            opening = openings[item["target"]]
            distance = _dimension_offset(item, default_offset)
            if dim_type == "rect_width":
                where = _dimension_where(item, "down")
                if where == "down":
                    base_y = opening["bottom"] - distance
                    p1 = (opening["left"], opening["bottom"])
                    p2 = (opening["right"], opening["bottom"])
                else:
                    base_y = opening["top"] + distance
                    p1 = (opening["left"], opening["top"])
                    p2 = (opening["right"], opening["top"])
                msp.add_linear_dim(
                    base=(opening["left"], base_y),
                    p1=p1,
                    p2=p2,
                    dimstyle=dim_style_name,
                    dxfattribs={"layer": dim_layer},
                ).render()
            else:
                where = _dimension_where(item, "left")
                if where == "left":
                    base_x = opening["left"] - distance
                    p1 = (opening["left"], opening["bottom"])
                    p2 = (opening["left"], opening["top"])
                else:
                    base_x = opening["right"] + distance
                    p1 = (opening["right"], opening["bottom"])
                    p2 = (opening["right"], opening["top"])
                msp.add_linear_dim(
                    base=(base_x, opening["bottom"]),
                    p1=p1,
                    p2=p2,
                    angle=90.0,
                    dimstyle=dim_style_name,
                    dxfattribs={"layer": dim_layer},
                ).render()
            continue

        if dim_type == "offset_from_center_x":
            where = _dimension_where(item, "up")
            distance = _dimension_offset(item, default_offset)
            targets = item.get("targets", [])
            for target_id in targets:
                opening = openings[target_id]
                size_y = _target_size_for_offset(opening, "y")
                base_y = opening["center_y"] + (size_y + distance) * (1 if where == "up" else -1)
                msp.add_linear_dim(
                    base=(center_x, base_y),
                    p1=(center_x, opening["center_y"]),
                    p2=(opening["center_x"], opening["center_y"]),
                    dimstyle=dim_style_name,
                    dxfattribs={"layer": dim_layer},
                ).render()
                _update_vertical_limit(axis_limits["__center__"], base_y, center_y)
                _update_vertical_limit(axis_limits[target_id], base_y, opening["center_y"])
            continue

        if dim_type == "offset_from_center_y":
            where = _dimension_where(item, "right")
            distance = _dimension_offset(item, default_offset)
            targets = item.get("targets", [])
            for target_id in targets:
                opening = openings[target_id]
                size_x = _target_size_for_offset(opening, "x")
                base_x = opening["center_x"] + (size_x + distance) * (1 if where == "right" else -1)
                msp.add_linear_dim(
                    base=(base_x, center_y),
                    p1=(opening["center_x"], center_y),
                    p2=(opening["center_x"], opening["center_y"]),
                    angle=90.0,
                    dimstyle=dim_style_name,
                    dxfattribs={"layer": dim_layer},
                ).render()
                _update_horizontal_limit(axis_limits["__center__"], base_x, center_x)
                _update_horizontal_limit(axis_limits[target_id], base_x, opening["center_x"])
            continue

        if dim_type == "offset_from_left":
            where = _dimension_where(item, "up")
            distance = _dimension_offset(item, default_offset)
            opening = openings[item["target"]]
            size_y = _target_size_for_offset(opening, "y")
            base_y = opening["center_y"] + (size_y + distance) * (1 if where == "up" else -1)
            msp.add_linear_dim(
                base=(0.0, base_y),
                p1=(0.0, opening["center_y"]),
                p2=(opening["center_x"], opening["center_y"]),
                dimstyle=dim_style_name,
                dxfattribs={"layer": dim_layer},
            ).render()
            _update_vertical_limit(axis_limits[item["target"]], base_y, opening["center_y"])
            continue

        raise ValueError(f"Unsupported dimension type: {dim_type}")


def _add_axes(
    msp: ezdxf.layouts.Modelspace,
    panel_length: float,
    panel_width: float,
    openings: dict[str, dict[str, float]],
    axes_spec: dict[str, Any],
    axis_layer: str,
    axis_linetype: str | None,
    axis_limits: dict[str, dict[str, float | None]],
) -> None:
    """Add axes based on the spec."""

    center_x = panel_length / 2.0
    center_y = panel_width / 2.0
    overhang = float(axes_spec.get("overhang", 2.0))
    extend_to_dims = bool(axes_spec.get("extend_to_dimensions", True))

    def axis_attribs() -> dict[str, Any]:
        attribs: dict[str, Any] = {"layer": axis_layer, "lineweight": -1}
        if axis_linetype:
            attribs["linetype"] = axis_linetype
        return attribs

    if axes_spec.get("center", {}).get("vertical", False):
        y1 = -overhang
        y2 = panel_width + overhang
        if extend_to_dims:
            limits = axis_limits["__center__"]
            if limits["v_min"] is not None:
                y1 = min(y1, limits["v_min"])
            if limits["v_max"] is not None:
                y2 = max(y2, limits["v_max"])
        msp.add_line((center_x, y1), (center_x, y2), dxfattribs=axis_attribs())

    if axes_spec.get("center", {}).get("horizontal", False):
        x1 = -overhang
        x2 = panel_length + overhang
        if extend_to_dims:
            limits = axis_limits["__center__"]
            if limits["h_min"] is not None:
                x1 = min(x1, limits["h_min"])
            if limits["h_max"] is not None:
                x2 = max(x2, limits["h_max"])
        msp.add_line((x1, center_y), (x2, center_y), dxfattribs=axis_attribs())

    draw_circle_axes = axes_spec.get("openings", {}).get("circles", False)
    draw_rect_axes = axes_spec.get("openings", {}).get("rects", False)

    for opening_id, opening in openings.items():
        if opening["type"] == "circle" and draw_circle_axes:
            radius = opening["radius"]
            y1 = opening["center_y"] - (radius + overhang)
            y2 = opening["center_y"] + (radius + overhang)
            x1 = opening["center_x"] - (radius + overhang)
            x2 = opening["center_x"] + (radius + overhang)
            if extend_to_dims:
                limits = axis_limits[opening_id]
                if limits["v_min"] is not None:
                    y1 = min(y1, limits["v_min"])
                if limits["v_max"] is not None:
                    y2 = max(y2, limits["v_max"])
                if limits["h_min"] is not None:
                    x1 = min(x1, limits["h_min"])
                if limits["h_max"] is not None:
                    x2 = max(x2, limits["h_max"])
            msp.add_line((opening["center_x"], y1), (opening["center_x"], y2), dxfattribs=axis_attribs())
            msp.add_line((x1, opening["center_y"]), (x2, opening["center_y"]), dxfattribs=axis_attribs())

        if opening["type"] == "rect" and draw_rect_axes:
            half_h = opening["height"] / 2.0
            y1 = opening["center_y"] - (half_h + overhang)
            y2 = opening["center_y"] + (half_h + overhang)
            if extend_to_dims:
                limits = axis_limits[opening_id]
                if limits["v_min"] is not None:
                    y1 = min(y1, limits["v_min"])
                if limits["v_max"] is not None:
                    y2 = max(y2, limits["v_max"])
            msp.add_line((opening["center_x"], y1), (opening["center_x"], y2), dxfattribs=axis_attribs())


def _add_text(
    msp: ezdxf.layouts.Modelspace,
    spec: dict[str, Any],
    panel_length: float,
    panel_width: float,
    openings: dict[str, dict[str, float]],
    text_layer: str,
    text_style: str,
    text_height_mm: float,
) -> None:
    """Add text annotations."""

    for item in spec.get("text", {}).get("items", []):
        value = item["value"]
        align = item.get("align", "center")
        at = item.get("at", {})

        if "x_ref" in at:
            x = _resolve_ref(at["x_ref"], openings)
        elif "x_from_right" in at:
            x = panel_length - float(at["x_from_right"])
        elif "x_from_left" in at:
            x = float(at["x_from_left"])
        else:
            x = panel_length / 2.0

        if "y_ref" in at:
            y = _resolve_ref(at["y_ref"], openings)
        elif "y_from_top" in at:
            y = panel_width - float(at["y_from_top"])
        elif "y_from_bottom" in at:
            y = float(at["y_from_bottom"])
        else:
            y = panel_width / 2.0

        text = msp.add_text(
            value,
            dxfattribs={"layer": text_layer, "style": text_style, "height": text_height_mm},
        )

        if align == "top_right":
            text.set_placement((x, y), align=TextEntityAlignment.TOP_RIGHT)
        elif align == "center":
            text.set_placement((x, y), align=TextEntityAlignment.MIDDLE_CENTER)
        else:
            text.set_placement((x, y), align=TextEntityAlignment.LEFT)


def _center_entities(
    msp: ezdxf.layouts.Modelspace,
    entities: Iterable[ezdxf.entities.DXFGraphic],
    free_area: dict[str, float],
    round_to_mm: bool,
) -> bbox.BoundingBox:
    """Center drawing entities inside the free area box."""

    drawing_box = bbox.extents(entities, fast=True)
    if not drawing_box.has_data:
        return bbox.BoundingBox()

    free_box = bbox.BoundingBox(
        [(free_area["left"], free_area["bottom"]), (free_area["right"], free_area["top"])]
    )
    target_center = free_box.center
    if round_to_mm:
        target_center = Vec2(target_center.x, round(target_center.y))

    delta = Vec2(target_center.x, target_center.y) - drawing_box.center
    if delta.is_null:
        return free_box
    for entity in entities:
        entity.translate(delta.x, delta.y, 0.0)
    return free_box


def render_from_spec(spec: dict[str, Any], output_path: Path, template_override: Path | None = None) -> None:
    """Render a drawing from the spec."""

    template_value = _get_nested(spec, ["sheet", "template"], "")
    template_path = template_override or (Path(template_value) if template_value else None)
    doc, existing_handles = load_template(template_path if template_path else None)
    # Ensure DXF version supports true color (AC1018+); use R2010 for compatibility.
    doc.dxfversion = "R2010"
    if template_override and template_path and not template_path.exists():
        print(f"Template not found, using blank DXF: {template_path}")

    doc.units = ezdxf.units.MM
    doc.header["$LTSCALE"] = 1.0

    layers_spec = _get_nested(spec, ["styles", "layers"], {})
    background_layer = None
    if "background" in layers_spec:
        background_layer = LayerConfig(
            name=layers_spec.get("background", {}).get("name", "BACKGROUND"),
            lineweight_mm=float(layers_spec.get("background", {}).get("lineweight", 0.0)),
            color=layers_spec.get("background", {}).get("color"),
        )

    outline_layer = LayerConfig(
        name=layers_spec.get("outline", {}).get("name", "OUTLINE"),
        lineweight_mm=float(layers_spec.get("outline", {}).get("lineweight", 0.7)),
    )
    cutout_layer = LayerConfig(
        name=layers_spec.get("cutouts", {}).get("name", "CUTOUTS"),
        lineweight_mm=float(layers_spec.get("cutouts", {}).get("lineweight", 0.7)),
    )
    axis_layer = LayerConfig(
        name=layers_spec.get("axes", {}).get("name", "AXES"),
        lineweight_mm=float(layers_spec.get("axes", {}).get("lineweight", 0.35)),
        linetype=layers_spec.get("axes", {}).get("linetype", "DASHDOT"),
    )
    dim_layer = LayerConfig(
        name=layers_spec.get("dimensions", {}).get("name", "DIMENSIONS"),
        lineweight_mm=float(layers_spec.get("dimensions", {}).get("lineweight", 0.35)),
    )
    text_layer = LayerConfig(
        name=layers_spec.get("text", {}).get("name", "TEXT"),
        lineweight_mm=float(layers_spec.get("text", {}).get("lineweight", 0.35)),
    )

    if axis_layer.linetype:
        ensure_linetype(doc, axis_layer.linetype)

    def ensure_layer(layer: LayerConfig) -> None:
        lineweight = to_lineweight_hundredths(layer.lineweight_mm)
        if layer.name in doc.layers:
            l = doc.layers.get(layer.name)
            l.dxf.lineweight = lineweight
            if layer.linetype:
                l.dxf.linetype = layer.linetype
            if layer.color:
                l.dxf.true_color = _parse_true_color(layer.color)
        else:
            attribs: dict[str, Any] = {"lineweight": lineweight}
            if layer.linetype:
                attribs["linetype"] = layer.linetype
            if layer.color:
                attribs["true_color"] = _parse_true_color(layer.color)
            doc.layers.add(layer.name, **attribs)

    for layer in (background_layer, outline_layer, cutout_layer, axis_layer, dim_layer, text_layer):
        if layer is not None:
            ensure_layer(layer)

    text_style_name = "LABEL"
    text_font = _get_nested(spec, ["styles", "text", "font"], "Segoe UI Semibold")
    if text_style_name not in doc.styles:
        doc.styles.add(text_style_name, font=f"{text_font}.ttf")

    text_height_pt = float(_get_nested(spec, ["styles", "text", "height_pt"], 9))
    text_height_mm = text_height_pt / 72.0 * 25.4

    panel_length = float(_get_nested(spec, ["panel", "size", "length"]))
    panel_width = float(_get_nested(spec, ["panel", "size", "width"]))

    msp = doc.modelspace()
    if background_layer is not None:
        _add_background(msp, panel_length, panel_width, background_layer)
    _add_panel_outline(msp, outline_layer.name, panel_length, panel_width)
    openings = _add_openings(msp, spec, panel_length, panel_width, cutout_layer.name)

    axis_limits = _init_axis_limits(openings)
    _add_dimensions(msp, spec, panel_length, panel_width, openings, dim_layer.name, axis_limits)

    axes_spec = spec.get("axes", {})
    _add_axes(
        msp,
        panel_length,
        panel_width,
        openings,
        axes_spec,
        axis_layer.name,
        axis_layer.linetype,
        axis_limits,
    )

    _add_text(
        msp,
        spec,
        panel_length,
        panel_width,
        openings,
        text_layer.name,
        text_style_name,
        text_height_mm,
    )

    title_block_spec = spec.get("title_block", {})
    if title_block_spec.get("apply", True):
        fields = title_block_spec.get("fields", {})
        issue_date = fields.get("Issue date", "")
        if issue_date == "DD.MM.YYYY":
            issue_date = date.today().strftime("%d.%m.%Y")
        title_fields = TitleBlockFields(
            title=str(fields.get("Title", "")),
            document_type=str(fields.get("Document Type", "")),
            drawing_number=str(fields.get("Drawing number", "")),
            issue_date=str(issue_date),
            material=str(fields.get("Material", "")),
        )
        apply_title_block_fields(doc, title_fields)

    drawing_entities = [
        entity
        for entity in msp
        if isinstance(entity, ezdxf.entities.DXFGraphic)
        and entity.dxf.handle not in existing_handles
    ]
    free_area = _get_nested(spec, ["sheet", "free_area"], None)
    free_box = None
    if free_area:
        round_to_mm = bool(_get_nested(spec, ["sheet", "center", "round_to_mm"], True))
        free_box = _center_entities(msp, drawing_entities, free_area, round_to_mm)

    if template_path and template_path.exists():
        try:
            layout = doc.layouts.get("Layout1")
        except KeyError:
            layout = None
        if layout is not None:
            if free_box is None and free_area:
                free_box = bbox.BoundingBox(
                    [
                        (free_area["left"], free_area["bottom"]),
                        (free_area["right"], free_area["top"]),
                    ]
                )
            if free_box is not None and free_box.has_data:
                fit_layout_to_free_area(layout, free_box)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(output_path)
