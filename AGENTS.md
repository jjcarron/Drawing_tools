# Repository Guidelines

## Project Structure & Module Organization
This repository describes a workflow to generate technical drawing sketches in `.dxf` from YAML specifications.
- `README.md`: project instructions and drawing conventions.
- `projets/<project>/`: YAML specs (`*.yml`) and generated DXF outputs.
- `scripts/`: Python modules and entry points that render DXF from YAML.

## Build, Test, and Development Commands
There is no build system configured; use Python directly.
- `python -m venv .venv` and `.\.venv\Scripts\Activate.ps1`: create/activate a virtual environment.
- `python scripts/<name>.py --help`: show script parameters (project entry points).
- `python scripts/<name>.py`: generate the `.dxf` file alongside the YAML spec.
- `python scripts/render_from_yaml.py --spec <path.yml>`: generic renderer.
- `python -m pytest`: run tests if a `tests/` folder is added.
- `pylint scripts`: lint Python code if `pylint` is installed.

## Coding Style & Naming Conventions
- Follow PEP 8 and include docstrings on modules, classes, and functions.
- Keep all text in code (strings, comments) in English.
- Use clear, descriptive names: `snake_case` for Python, `UPPER_SNAKE_CASE` for constants.
- Keep scripts named after the output file name (e.g., `GBS-8200_Front_Panel.py`).

## Testing Guidelines
No test framework is currently configured. If tests are added, prefer `pytest` with files named `test_*.py` under a `tests/` directory, and cover geometry rules and `.xdf` output correctness.

## Commit & Pull Request Guidelines
This folder is not a Git repository, so there is no commit history to infer conventions. If you initialize Git, prefer frequent, clear commit messages and do not track generated files under `output/` or any future `data/` directory. Pull requests should describe the drawing change, include the updated script name, and link any updated requirements.

## Agent-Specific Instructions
- Use YAML specs as the source of truth; update the YAML instead of hard-coding geometry in scripts.
- Generate `.dxf` outputs next to their YAML specs under `projets/<project>/`.
- Maintain symmetry axes and dimensions per the documented drawing conventions in `README.md`.
- Record new instructions in `Instructions_History.md` with numbered, human-readable entries.
- Center drawings vertically within the free sheet area by excluding the 60 mm cartouche height; compute from the template border extents and round the center Y to the nearest millimeter.
- Always draw vertical and horizontal symmetry axes through each circular hole (for drilling), and ensure dimension lines attach to axes instead of floating in space.
