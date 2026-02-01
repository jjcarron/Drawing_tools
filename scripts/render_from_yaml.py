"""Render a DXF drawing from a YAML specification."""

from __future__ import annotations

import argparse
from pathlib import Path

from drawing_engine import render_from_spec
from yaml_spec import load_spec


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="Render a DXF drawing from a YAML spec.")
    parser.add_argument("--spec", type=Path, required=True, help="YAML specification file.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output DXF path (defaults to <spec-dir>/<filename>.dxf).",
    )
    parser.add_argument("--template", type=Path, default=None, help="Template DXF override.")
    return parser.parse_args()


def main() -> None:
    """Run the renderer."""

    args = parse_args()
    spec = load_spec(args.spec)
    output_path = args.output
    if output_path is None:
        filename = spec.get("meta", {}).get("filename", args.spec.stem)
        output_path = args.spec.parent / f"{filename}.dxf"
    render_from_spec(spec, output_path, template_override=args.template)
    print(f"DXF written to: {output_path}")


if __name__ == "__main__":
    main()
