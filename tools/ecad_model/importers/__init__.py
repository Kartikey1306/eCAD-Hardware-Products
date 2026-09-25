"""CAD importers, selected by the format a file's content declares."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from .base import CADImporter, UnsupportedFormat, detect_format
from .step_ocp import StepImporter

IMPORTERS: Dict[str, CADImporter] = {"step": StepImporter()}


def importer_for(path: Path) -> CADImporter:
    """Return the importer for a file, or raise UnsupportedFormat.

    A format that is recognised but has no importer here (STL, glTF) is
    reported as unsupported rather than read partially: STL carries no
    assembly, and pretending otherwise would fabricate structure.

    Args:
        path: The CAD file.

    Returns:
        The importer registered for the file's detected format.

    Raises:
        UnsupportedFormat: See detect_format(), or no importer is implemented.

    Example:
        >>> from pathlib import Path
        >>> root = Path(__file__).resolve().parents[3]
        >>> type(importer_for(root / "datasets/cad/robotic_joint_001/source/robotic_joint_001.step")).__name__
        'StepImporter'
    """
    name = detect_format(path)
    importer = IMPORTERS.get(name)
    if importer is None:
        raise UnsupportedFormat(f"{path.name}: recognised as {name}, but no {name} importer is implemented")
    return importer


__all__ = ["CADImporter", "IMPORTERS", "UnsupportedFormat", "detect_format", "importer_for"]
