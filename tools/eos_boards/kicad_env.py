"""Where KiCad is: its command-line tool, its bundled Python and its libraries.

Set KICAD_APP to the KiCad.app (or install directory) to use another installation.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

_CANDIDATES = [
    Path(os.environ.get("KICAD_APP", "")),
    Path.home() / "Applications/KiCad/KiCad.app",
    Path("/Applications/KiCad/KiCad.app"),
]


def app() -> Path:
    for c in _CANDIDATES:
        if str(c) not in ("", ".") and (c / "Contents/MacOS/kicad-cli").is_file():
            return c
    raise FileNotFoundError("KiCad not found; set KICAD_APP to KiCad.app")


def cli() -> str:
    found = shutil.which("kicad-cli")
    return found or str(app() / "Contents/MacOS/kicad-cli")


def python() -> str:
    return str(sorted((app() / "Contents/Frameworks/Python.framework/Versions").glob("3*/bin/python3"))[-1])


def symbols() -> Path:
    return app() / "Contents/SharedSupport/symbols"


def footprints() -> Path:
    return app() / "Contents/SharedSupport/footprints"
