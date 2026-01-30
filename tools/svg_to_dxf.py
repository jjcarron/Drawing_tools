"""Convert an SVG template to DXF and emit a layer mapping report.

The converter focuses on simple SVG primitives (rect, circle, path, text) and
maps SVG groups to DXF layers using a default layer set compatible with QCAD.
"""

from __future__ import annotations

import argparse
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

CACHE_ROOT = Path(".tmp")
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("XDG_CACHE_HOME", str(CACHE_ROOT))

import ezdxf
from ezdxf.enums import TextEntityAlignment

DEFAULT_LAYERS = [
    "1.Outline",
    "Border.Thick",
    "Border.Thin",
    "TitleBlock.Outer",
    "TitleBlock.Inner",
    "Revision",
    "8.Dimension line",
    "Title",
    "9.Text",
    "7.Hatch",
    "6.Construction line",
    "3.Center",
    "AXES",
    "2.Hidden",
    "5.Thin line",
    "4.Note",
]

DEFAULT_GROUP_LAYER_MAP = {
    "drawing_space_frame": "Border.Thick",
    "centring_marks": "3.Center",
    "grid_reference_borders": "Border.Thin",
    "grid_reference_markers": "9.Text",
    "trimming_marks": "Border.Thin",
    "title_block_borders": "TitleBlock.Inner",
    "title_block_labels": "Title",
    "title_block_data_fields": "Title",
    "extras_outlines": "1.Outline",
    "extras_centre_lines": "3.Center",
}

LAYER_LINEWEIGHT_MM = {
    "Border.Thick": 0.7,
    "Border.Thin": 0.35,
    "TitleBlock.Outer": 0.7,
    "TitleBlock.Inner": 0.35,
    "1.Outline": 0.5,
    "2.Hidden": 0.35,
    "3.Center": 0.35,
    "AXES": 0.35,
    "4.Note": 0.25,
    "5.Thin line": 0.35,
    "6.Construction line": 0.25,
    "7.Hatch": 0.25,
    "8.Dimension line": 0.25,
    "9.Text": 0.25,
    "Title": 0.25,
    "Revision": 0.25,
}

SVG_NS = "{http://www.w3.org/2000/svg}"


@dataclass
class SvgElementInfo:
    """Container for parsed SVG element info."""

    group_id: str
    element_id: str
    tag: str


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Convert an SVG file into a DXF and a layer mapping report."
    )
    parser.add_argument("svg_path", type=Path, help="Path to the SVG template.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directory for the output DXF and MD files.",
    )
    parser.add_argument(
        "--layer-template",
        type=Path,
        default=Path("templates/iso_en_a4_metric_landscape_aec.dxf"),
        help="DXF file used to seed layer names.",
    )
    return parser.parse_args()


def strip_namespace(tag: str) -> str:
    """Remove XML namespace from a tag."""

    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def parse_float(value: str | None, default: float = 0.0) -> float:
    """Parse a float, ignoring unit suffixes like 'mm'."""

    if value is None:
        return default
    return float(re.sub(r"[^0-9.+-]", "", value) or default)


def parse_style(style: str | None) -> dict[str, str]:
    """Parse a CSS style attribute into a dictionary."""

    if not style:
        return {}
    items = {}
    for part in style.split(";"):
        if ":" in part:
            key, val = part.split(":", 1)
            items[key.strip()] = val.strip()
    return items


def merge_style(base: dict[str, str], override: dict[str, str]) -> dict[str, str]:
    """Return merged style with override values applied."""

    merged = dict(base)
    merged.update(override)
    return merged


def parse_font_size(value: str | None, default_mm: float) -> float:
    """Parse font size and return millimeters."""

    if not value:
        return default_mm
    value = value.strip()
    try:
        if value.endswith("pt"):
            pt = float(value[:-2])
            return pt * 25.4 / 72.0
        if value.endswith("px"):
            px = float(value[:-2])
            return px * 25.4 / 96.0
        if value.endswith("mm"):
            return float(value[:-2])
        if value.endswith("cm"):
            return float(value[:-2]) * 10.0
        return float(value) * 25.4 / 96.0
    except ValueError:
        return default_mm


def parse_length(value: str | None, default_mm: float) -> float:
    """Parse a CSS length into millimeters."""

    if not value:
        return default_mm
    value = value.strip()
    try:
        if value.endswith("pt"):
            pt = float(value[:-2])
            return pt * 25.4 / 72.0
        if value.endswith("px"):
            px = float(value[:-2])
            return px * 25.4 / 96.0
        if value.endswith("mm"):
            return float(value[:-2])
        if value.endswith("cm"):
            return float(value[:-2]) * 10.0
        return float(value) * 25.4 / 96.0
    except ValueError:
        return default_mm


def normalize_style(element: ET.Element, inherited: dict[str, str]) -> dict[str, str]:
    """Combine inherited and element styles."""

    element_style = parse_style(element.get("style"))
    combined = merge_style(inherited, element_style)
    # Allow direct attributes to override style map
    if element.get("font-size"):
        combined["font-size"] = element.get("font-size", "")
    if element.get("font-family"):
        combined["font-family"] = element.get("font-family", "")
    if element.get("stroke-width"):
        combined["stroke-width"] = element.get("stroke-width", "")
    return combined


def ensure_layers(doc: ezdxf.EzDXF, layer_names: list[str]) -> None:
    """Ensure the given layers exist in the DXF document."""

    if "DASHDOT" not in doc.linetypes:
        doc.linetypes.add(
            "DASHDOT",
            pattern=[15.0, 6.0, -1.5, 0.0, -1.5, 6.0],
            description="Symmetry axis dash-dot 6-1.5-0-1.5-6",
        )

    for name in layer_names:
        if name not in doc.layers:
            doc.layers.add(name)
        if name in LAYER_LINEWEIGHT_MM:
            lineweight = int(round(LAYER_LINEWEIGHT_MM[name] * 100))
            doc.layers.get(name).dxf.lineweight = lineweight
        if name == "AXES":
            doc.layers.get(name).dxf.linetype = "DASHDOT"


def load_template_layers(template_path: Path) -> list[str]:
    """Load layer names from a DXF template if it exists."""

    if not template_path.exists():
        return []
    doc = ezdxf.readfile(template_path)
    return [layer.dxf.name for layer in doc.layers]


def add_rect(
    msp: ezdxf.layouts.Modelspace,
    rect: ET.Element,
    layer: str,
    svg_height: float,
    style: dict[str, str],
    element_id: str,
    group_id: str,
) -> None:
    """Add a rectangle as a lightweight polyline."""

    x = parse_float(rect.get("x"))
    y = parse_float(rect.get("y"))
    width = parse_float(rect.get("width"))
    height = parse_float(rect.get("height"))
    y = svg_height - y - height
    points = [
        (x, y),
        (x + width, y),
        (x + width, y + height),
        (x, y + height),
        (x, y),
    ]
    msp.add_lwpolyline(points, dxfattribs={"layer": layer, "lineweight": -1})


def add_circle(
    msp: ezdxf.layouts.Modelspace,
    circle: ET.Element,
    layer: str,
    svg_height: float,
    style: dict[str, str],
    element_id: str,
    group_id: str,
) -> None:
    """Add a circle entity."""

    cx = parse_float(circle.get("cx"))
    cy = parse_float(circle.get("cy"))
    r = parse_float(circle.get("r"))
    msp.add_circle((cx, svg_height - cy), r, dxfattribs={"layer": layer, "lineweight": -1})


def parse_path_commands(d: str) -> list[tuple[str, list[float]]]:
    """Parse path commands (M/L/H/V/Z only)."""

    tokens = re.findall(r"[MmLlHhVvZz]|-?\d*\.?\d+(?:e[+-]?\d+)?", d)
    commands: list[tuple[str, list[float]]] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if re.match(r"[MmLlHhVvZz]", token):
            cmd = token
            i += 1
            nums: list[float] = []
            while i < len(tokens) and not re.match(r"[MmLlHhVvZz]", tokens[i]):
                nums.append(float(tokens[i]))
                i += 1
            commands.append((cmd, nums))
        else:
            i += 1
    return commands


def add_path(
    msp: ezdxf.layouts.Modelspace,
    path: ET.Element,
    layer: str,
    unsupported: set[str],
    svg_height: float,
    style: dict[str, str],
    element_id: str,
    group_id: str,
) -> None:
    """Add a polyline from a simple path."""

    d = path.get("d")
    if not d:
        return

    commands = parse_path_commands(d)
    points: list[tuple[float, float]] = []
    current = (0.0, svg_height)
    start = (0.0, svg_height)

    for cmd, nums in commands:
        if cmd in "Mm":
            if len(nums) < 2:
                continue
            dx, dy = nums[0], nums[1]
            if cmd == "m":
                current = (current[0] + dx, current[1] - dy)
            else:
                current = (dx, svg_height - dy)
            start = current
            points.append(current)
            for i in range(2, len(nums), 2):
                if cmd == "m":
                    current = (current[0] + nums[i], current[1] - nums[i + 1])
                else:
                    current = (nums[i], svg_height - nums[i + 1])
                points.append(current)
        elif cmd in "Ll":
            for i in range(0, len(nums), 2):
                if cmd == "l":
                    current = (current[0] + nums[i], current[1] - nums[i + 1])
                else:
                    current = (nums[i], svg_height - nums[i + 1])
                points.append(current)
        elif cmd in "Hh":
            for value in nums:
                x = current[0] + value if cmd == "h" else value
                current = (x, current[1])
                points.append(current)
        elif cmd in "Vv":
            for value in nums:
                if cmd == "v":
                    current = (current[0], current[1] - value)
                else:
                    current = (current[0], svg_height - value)
                points.append(current)
        elif cmd in "Zz":
            points.append(start)
        else:
            unsupported.add(cmd)

    if points:
        poly = msp.add_lwpolyline(points, dxfattribs={"layer": layer, "lineweight": -1})
        if style.get("fill") == "#000000":
            poly.closed = True


def add_text(
    msp: ezdxf.layouts.Modelspace,
    text: ET.Element,
    layer: str,
    svg_height: float,
    style: dict[str, str],
    doc: ezdxf.EzDXF,
) -> None:
    """Add a text entity."""

    x = parse_float(text.get("x"))
    y = parse_float(text.get("y"))
    content = "".join(text.itertext()).strip()

    height = parse_font_size(style.get("font-size"), 3.5 * 25.4 / 96.0) * 2.82
    font_family = style.get("font-family", "").strip()
    style_name = None
    if font_family:
        style_name = re.sub(r"[^A-Za-z0-9_-]", "_", font_family)
        if style_name not in doc.styles:
            doc.styles.add(style_name, font=f"{font_family}.ttf")

    dxfattribs = {"layer": layer, "height": height}
    if style_name:
        dxfattribs["style"] = style_name

    text = msp.add_text(content, dxfattribs=dxfattribs)
    text_anchor = style.get("text-anchor", "").strip()
    if text_anchor == "middle":
        alignment = TextEntityAlignment.CENTER
    elif text_anchor == "end":
        alignment = TextEntityAlignment.RIGHT
    else:
        alignment = TextEntityAlignment.LEFT
    text.set_placement((x, svg_height - y), align=alignment)


def map_layer(group_id: str, element_id: str) -> str:
    """Map SVG group/element ids to DXF layer names."""

    if element_id == "grid_reference_border":
        return "Border.Thin"
    if element_id == "title_block_frame":
        return "TitleBlock.Outer"
    if element_id in DEFAULT_GROUP_LAYER_MAP:
        return DEFAULT_GROUP_LAYER_MAP[element_id]
    if group_id in DEFAULT_GROUP_LAYER_MAP:
        return DEFAULT_GROUP_LAYER_MAP[group_id]
    return "5.Thin line"


def walk_svg(
    element: ET.Element,
    group_stack: list[str],
    elements: list[SvgElementInfo],
) -> None:
    """Walk SVG and collect element metadata."""

    tag = strip_namespace(element.tag)
    group_id = group_stack[-1] if group_stack else ""
    element_id = element.get("id", "")

    if tag == "g":
        new_group_id = element_id or group_id
        group_stack.append(new_group_id)
        for child in element:
            walk_svg(child, group_stack, elements)
        group_stack.pop()
        return

    if tag in {"rect", "circle", "path", "text"}:
        elements.append(SvgElementInfo(group_id, element_id, tag))

    for child in element:
        walk_svg(child, group_stack, elements)


def convert_elements(
    element: ET.Element,
    msp: ezdxf.layouts.Modelspace,
    group_stack: list[str],
    layer_map: dict[str, str],
    unsupported_cmds: set[str],
    svg_height: float,
    inherited_style: dict[str, str],
    doc: ezdxf.EzDXF,
) -> None:
    """Convert SVG elements to DXF entities with group-aware layer mapping."""

    tag = strip_namespace(element.tag)
    group_id = group_stack[-1] if group_stack else ""
    element_id = element.get("id", "")
    current_style = normalize_style(element, inherited_style)

    if tag == "g":
        new_group_id = element_id or group_id
        group_stack.append(new_group_id)
        for child in element:
            convert_elements(
                child,
                msp,
                group_stack,
                layer_map,
                unsupported_cmds,
                svg_height,
                current_style,
                doc,
            )
        group_stack.pop()
        return

    if tag in {"rect", "circle", "path", "text"}:
        layer = map_layer(group_id, element_id)
        if group_id:
            layer_map[group_id] = layer
        elif element_id:
            layer_map[element_id] = layer

        if tag == "rect":
            add_rect(msp, element, layer, svg_height, current_style, element_id, group_id)
        elif tag == "circle":
            add_circle(msp, element, layer, svg_height, current_style, element_id, group_id)
        elif tag == "path":
            add_path(
                msp,
                element,
                layer,
                unsupported_cmds,
                svg_height,
                current_style,
                element_id,
                group_id,
            )
        elif tag == "text":
            add_text(msp, element, layer, svg_height, current_style, doc)

    for child in element:
        convert_elements(
            child,
            msp,
            group_stack,
            layer_map,
            unsupported_cmds,
            svg_height,
            current_style,
            doc,
        )


def build_markdown(
    svg_path: Path,
    output_path: Path,
    elements: list[SvgElementInfo],
    layer_map: dict[str, str],
    unsupported_cmds: set[str],
    group_styles: dict[str, dict[str, str]],
) -> None:
    """Write a markdown report about SVG layers and mapping."""

    lines = []
    lines.append(f"# {svg_path.name} — Layer/Structure Notes")
    lines.append("")
    lines.append(f"Source: `{svg_path}`  ")
    lines.append("")
    lines.append("## SVG Groups and Elements")

    by_group: dict[str, list[SvgElementInfo]] = {}
    for info in elements:
        key = info.group_id or "(root)"
        by_group.setdefault(key, []).append(info)

    for group, items in sorted(by_group.items()):
        lines.append(f"### {group}")
        type_counts: dict[str, int] = {}
        for item in items:
            type_counts[item.tag] = type_counts.get(item.tag, 0) + 1
        counts = ", ".join(f"{k}:{v}" for k, v in sorted(type_counts.items()))
        lines.append(f"- Elements: {counts}")
        mapped = layer_map.get(group, "5.Thin line")
        lines.append(f"- Suggested DXF layer: {mapped}")
        if group in group_styles:
            style = group_styles[group]
            font_size = style.get("font-size", "")
            font_family = style.get("font-family", "")
            if font_size or font_family:
                lines.append(
                    f"- Text style: font-size={font_size or 'inherit'}, "
                    f"font-family={font_family or 'inherit'}"
                )
        lines.append("")

    lines.append("## Default DXF Layers")
    for name in DEFAULT_LAYERS:
        lines.append(f"- {name}")
    lines.append("")

    if unsupported_cmds:
        lines.append("## Unsupported SVG Path Commands")
        lines.append(", ".join(sorted(unsupported_cmds)))
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def convert_svg(svg_path: Path, output_dir: Path, layer_template: Path) -> None:
    """Convert the SVG file to DXF and generate a markdown report."""

    tree = ET.parse(svg_path)
    root = tree.getroot()
    view_box = root.get("viewBox", "")
    view_parts = view_box.split()
    if len(view_parts) == 4:
        svg_width = float(view_parts[2])
        svg_height = float(view_parts[3])
    else:
        svg_width = parse_float(root.get("width"), 0.0)
        svg_height = parse_float(root.get("height"), 0.0)
    if svg_height <= 0:
        svg_height = 0.0
    if svg_width <= 0:
        svg_width = 0.0

    doc = ezdxf.new(dxfversion="R2010")
    doc.units = ezdxf.units.MM

    layer_names = list(dict.fromkeys(load_template_layers(layer_template) + DEFAULT_LAYERS))
    ensure_layers(doc, layer_names)

    msp = doc.modelspace()
    elements: list[SvgElementInfo] = []
    walk_svg(root, [], elements)

    unsupported_cmds: set[str] = set()
    layer_map: dict[str, str] = {}
    group_styles: dict[str, dict[str, str]] = {}

    def collect_group_styles(element: ET.Element, inherited: dict[str, str]) -> None:
        tag = strip_namespace(element.tag)
        current = normalize_style(element, inherited)
        if tag == "g":
            group_id = element.get("id", "")
            if group_id:
                group_styles[group_id] = current
        for child in element:
            collect_group_styles(child, current)

    collect_group_styles(root, {})
    convert_elements(root, msp, [], layer_map, unsupported_cmds, svg_height, {}, doc)

    # Add a temporary 100 mm axis line at sheet center for QCAD linetype setup.
    if svg_width > 0 and svg_height > 0:
        center_x = svg_width / 2.0
        center_y = svg_height / 2.0
        half_len = 50.0
        msp.add_line(
            (center_x - half_len, center_y),
            (center_x + half_len, center_y),
            dxfattribs={"layer": "AXES", "linetype": "DASHDOT", "lineweight": -1},
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    dxf_path = output_dir / f"{svg_path.stem}.dxf"
    md_path = output_dir / f"{svg_path.stem}.md"

    doc.saveas(dxf_path)
    build_markdown(svg_path, md_path, elements, layer_map, unsupported_cmds, group_styles)

    print(f"DXF written to: {dxf_path}")
    print(f"Report written to: {md_path}")


def main() -> None:
    """Entry point."""

    args = parse_args()
    convert_svg(args.svg_path, args.output_dir, args.layer_template)


if __name__ == "__main__":
    main()
