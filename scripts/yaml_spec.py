"""Load and normalize drawing specifications from YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_spec(path: Path) -> dict[str, Any]:
    """Load a YAML spec file into a normalized dictionary."""

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Spec file must contain a mapping: {path}")
    return data
