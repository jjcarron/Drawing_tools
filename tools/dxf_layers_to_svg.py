"""Export selected DXF layers to SVG for laser cutting/engraving."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import ezdxf
from ezdxf import bbox
from ezdxf.addons import text2path
from xml.sax.saxutils import escape


@dataclass(frozen=True)
class SvgConfig:
    """SVG export configuration."""

    stroke_color: str = "#000000"
    stroke_width_mm: float = 0.1
    fill: str = "none"
    padding_mm: float = 2.0


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Export selected DXF layers to SVG."
    )
    parser.add_argument(
        "dxf_path",
        type=Path,
        help="Input DXF file path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output SVG path (defaults to output/<name>_<preset>.svg).",
    )
    parser.add_argument(
        "--layers",
        nargs="+",
        default=None,
        help="Layer names to export (overrides preset).",
    )
    parser.add_argument(
        "--preset",
        choices=["cut", "engrave"],
        default="cut",
        help="Layer presets: cut=OUTLINE+CUTOUTS, engrave=OUTLINE+TEXT.",
    )
    parser.add_argument(
        "--text-as-text",
        action="store_true",
        help="Export TEXT/MTEXT as <text> elements instead of paths.",
    )
    return parser.parse_args()


def collect_entities(msp: ezdxf.layouts.Modelspace, layers: set[str]) -> list[ezdxf.entities.DXFGraphic]:
    """Collect entities from modelspace by layer."""

    return [
        e
        for e in msp
        if isinstance(e, ezdxf.entities.DXFGraphic) and e.dxf.layer in layers
    ]


def compute_bounds(entities: Iterable[ezdxf.entities.DXFGraphic]) -> bbox.BoundingBox:
    """Compute bounding box for given entities."""

    return bbox.extents(entities, fast=True)


def svg_coords(x: float, y: float, min_x: float, max_y: float) -> tuple[float, float]:
    """Map DXF coordinates to SVG coordinates (invert Y)."""

    return x - min_x, max_y - y


def export_svg(
    entities: list[ezdxf.entities.DXFGraphic],
    output_path: Path,
    config: SvgConfig,
    text_as_paths: bool,
) -> None:
    """Write SVG file with given entities."""

    bounds = compute_bounds(entities)
    if not bounds.has_data:
        raise ValueError("No geometry found for selected layers.")

    min_x, min_y, _ = bounds.extmin
    max_x, max_y, _ = bounds.extmax

    min_x -= config.padding_mm
    min_y -= config.padding_mm
    max_x += config.padding_mm
    max_y += config.padding_mm

    width = max_x - min_x
    height = max_y - min_y

    lines: list[str] = []
    lines.append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>")
    lines.append(
        f"<svg xmlns=\"http://www.w3.org/2000/svg\" "
        f"width=\"{width}mm\" height=\"{height}mm\" "
        f"viewBox=\"0 0 {width} {height}\">"
    )
    lines.append(
        f"<g fill=\"{config.fill}\" stroke=\"{config.stroke_color}\" "
        f"stroke-width=\"{config.stroke_width_mm}\">"
    )

    for entity in entities:
        if entity.dxftype() == "LWPOLYLINE":
            points = [
                svg_coords(x, y, min_x, max_y)
                for x, y, *_ in entity.get_points("xy")
            ]
            if not points:
                continue
            d = [f"M {points[0][0]} {points[0][1]}"]
            for x, y in points[1:]:
                d.append(f"L {x} {y}")
            if entity.closed:
                d.append("Z")
            lines.append(f"<path d=\"{' '.join(d)}\" />")
        elif entity.dxftype() == "LINE":
            x1, y1, _ = entity.dxf.start
            x2, y2, _ = entity.dxf.end
            sx1, sy1 = svg_coords(x1, y1, min_x, max_y)
            sx2, sy2 = svg_coords(x2, y2, min_x, max_y)
            lines.append(
                f"<line x1=\"{sx1}\" y1=\"{sy1}\" x2=\"{sx2}\" y2=\"{sy2}\" />"
            )
        elif entity.dxftype() == "CIRCLE":
            cx, cy, _ = entity.dxf.center
            r = entity.dxf.radius
            scx, scy = svg_coords(cx, cy, min_x, max_y)
            lines.append(f"<circle cx=\"{scx}\" cy=\"{scy}\" r=\"{r}\" />")
        elif entity.dxftype() in {"TEXT", "MTEXT"}:
            if text_as_paths and entity.dxftype() == "TEXT":
                paths = text2path.make_paths_from_entity(entity)
                for path in paths:
                    points = list(path.flattening(0.1))
                    if not points:
                        continue
                    sx, sy = svg_coords(points[0].x, points[0].y, min_x, max_y)
                    d = [f"M {sx} {sy}"]
                    for pt in points[1:]:
                        px, py = svg_coords(pt.x, pt.y, min_x, max_y)
                        d.append(f"L {px} {py}")
                    if points[0].isclose(points[-1]):
                        d.append("Z")
                    lines.append(f"<path d=\"{' '.join(d)}\" />")
            else:
                # Close the geometry group before writing text.
                lines.append("</g>")
                lines.append(f"<g fill=\"{config.stroke_color}\" stroke=\"none\">")
                if entity.dxftype() == "TEXT":
                    text = entity.dxf.text
                    x, y, _ = entity.dxf.insert
                    height_mm = entity.dxf.height
                else:
                    text = entity.text
                    x, y, _ = entity.dxf.insert
                    height_mm = entity.dxf.char_height
                sx, sy = svg_coords(x, y, min_x, max_y)
                safe_text = escape(text)
                lines.append(
                    f"<text x=\"{sx}\" y=\"{sy}\" font-size=\"{height_mm}\">{safe_text}</text>"
                )
                lines.append("</g>")
                lines.append(
                    f"<g fill=\"{config.fill}\" stroke=\"{config.stroke_color}\" "
                    f"stroke-width=\"{config.stroke_width_mm}\">"
                )

    lines.append("</g>")
    lines.append("</svg>")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """CLI entry point."""

    args = parse_args()
    dxf_path: Path = args.dxf_path

    if args.layers:
        layers = set(args.layers)
        preset = "custom"
    else:
        if args.preset == "cut":
            layers = {"OUTLINE", "CUTOUTS"}
        else:
            layers = {"OUTLINE", "TEXT"}
        preset = args.preset

    output_path = args.output
    if output_path is None:
        output_path = Path("output") / f"{dxf_path.stem}_{preset}.svg"

    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    entities = collect_entities(msp, layers)
    text_as_paths = not args.text_as_text
    export_svg(entities, output_path, SvgConfig(), text_as_paths)

    print(f"SVG written to: {output_path}")


if __name__ == "__main__":
    main()
