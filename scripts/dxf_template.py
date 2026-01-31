"""Reusable DXF template utilities for drawings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple

import ezdxf
from ezdxf import bbox
from ezdxf.math import Vec2
from ezdxf.enums import TextEntityAlignment


@dataclass(frozen=True)
class TitleBlockFields:
    """Text fields to place in the title block template."""

    title: str
    document_type: str
    drawing_number: str
    issue_date: str
    material: str


def load_template(template_path: Path | None) -> tuple[ezdxf.EzDXF, set[str]]:
    """Load a DXF template and return the doc and existing handles."""

    existing_handles: set[str] = set()
    if template_path and template_path.exists():
        doc = ezdxf.readfile(template_path)
        existing_handles = {e.dxf.handle for e in doc.modelspace()}
    else:
        doc = ezdxf.new(dxfversion="R2010")
    return doc, existing_handles


def ensure_linetype(doc: ezdxf.EzDXF, name: str) -> None:
    """Ensure the custom symmetry axis linetype exists and has correct pattern."""

    pattern = [15.0, 6.0, -1.5, 0.0, -1.5, 6.0]
    if name in doc.linetypes:
        linetype = doc.linetypes.get(name)
        linetype.pattern = pattern
        return

    doc.linetypes.add(
        name,
        pattern=pattern,
        description="Symmetry axis dash-dot 6-1.5-0-1.5-6",
    )


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
    msp: ezdxf.layouts.Modelspace,
    drawing_entities: Iterable[ezdxf.entities.DXFGraphic],
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
