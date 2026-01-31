# Repository Guidelines

## Project Structure & Module Organization
This repository describes a workflow to generate technical drawing sketches in `.xdf` from the specification in `TODO.md`.
- `README.md`: project instructions and drawing conventions.
- `TODO.md`: the current drawing specification (dimensions, text, placement).
- `scripts/`: generated Python scripts that create `.xdf` files.
- `output/`: generated `.xdf` files.

## Build, Test, and Development Commands
There is no build system configured; use Python directly.
- `python -m venv .venv` and `.\.venv\Scripts\Activate.ps1`: create/activate a virtual environment.
- `python scripts/<name>.py --help`: show script parameters once a generator script exists.
- `python scripts/<name>.py`: generate the `.xdf` file into `output/`.
- `python -m pytest`: run tests if a `tests/` folder is added.
- `pylint scripts`: lint Python code if `pylint` is installed.

## Coding Style & Naming Conventions
- Follow PEP 8 and include docstrings on modules, classes, and functions.
- Keep all text in code (strings, comments) in English.
- Use clear, descriptive names: `snake_case` for Python, `UPPER_SNAKE_CASE` for constants.
- Keep scripts named after the output file name from `TODO.md` (e.g., `RGBS2VGA_Front_Panel.py`).

## Testing Guidelines
No test framework is currently configured. If tests are added, prefer `pytest` with files named `test_*.py` under a `tests/` directory, and cover geometry rules and `.xdf` output correctness.

## Commit & Pull Request Guidelines
This folder is not a Git repository, so there is no commit history to infer conventions. If you initialize Git, prefer frequent, clear commit messages and do not track generated files under `output/` or any future `data/` directory. Pull requests should describe the drawing change, include the updated script name, and link any updated requirements.

## Agent-Specific Instructions
- Read `TODO.md` before generating or updating scripts.
- Generate `.xdf` output in `output/` and the matching Python script in `scripts/`.
- Maintain symmetry axes and dimensions per the documented drawing conventions in `README.md`.
- Record new instructions in `Instructions_History.md` with numbered, human-readable entries.
- Center drawings vertically within the free sheet area by excluding the 60 mm cartouche height; compute from the template border extents and round the center Y to the nearest millimeter.
- Always draw vertical and horizontal symmetry axes through each circular hole (for drilling), and ensure dimension lines attach to axes instead of floating in space.
