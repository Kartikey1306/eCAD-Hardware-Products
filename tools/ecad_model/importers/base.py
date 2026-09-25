"""The common interface every CAD format importer implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional

# First bytes by which a format identifies itself. Detection trusts content,
# not the file extension, because CAD files are untrusted input.
SIGNATURES = {
    "step": (b"ISO-10303-21;",),
    "stl": (b"solid",),  # ASCII STL only; recognised solely to reject it clearly.
    "gltf": (b"glTF",),  # binary glTF (.glb) magic; likewise rejected.
}

MAX_CAD_BYTES = 256 * 1024 * 1024


class UnsupportedFormat(ValueError):
    """The file is a format no importer here can read. Never guessed around."""


class ExtractionError(ValueError):
    """Extraction did not produce a result, with the reason classified.

    kind is one of:
        "rejected"     the file was read and refused on its content (decisive)
        "crashed"      the parser died or produced no usable result
        "timed_out"    the parser exceeded its time limit
        "unavailable"  the kernel is not installed here
    Callers map these to different verdicts; they are not all "unavailable".
    """

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def regular_file(path: Path, limit: Optional[int] = None) -> int:
    """Refuse anything but a regular file within the size limit, before opening it.

    A FIFO would block a read forever, and an oversized file would be read
    whole before any other guard ran.

    Args:
        path: The file about to be read.
        limit: Largest acceptable size in bytes; MAX_CAD_BYTES when None, read at
            call time so the module constant stays the single setting.

    Returns:
        The file's size in bytes.

    Raises:
        UnsupportedFormat: Not a regular file (or a symlink), or too large.

    Example:
        >>> import tempfile, os
        >>> with tempfile.TemporaryDirectory() as d:
        ...     fifo = Path(d) / "part.step"; os.mkfifo(fifo)
        ...     regular_file(fifo)
        Traceback (most recent call last):
        ...
        ecad_model.importers.base.UnsupportedFormat: part.step: not a regular file
    """
    import stat

    limit = MAX_CAD_BYTES if limit is None else limit
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise UnsupportedFormat(f"{path.name}: not a regular file")
    if info.st_size > limit:
        raise UnsupportedFormat(f"{path.name}: {info.st_size} bytes exceeds the {limit}-byte input limit")
    return info.st_size


class CADImporter(ABC):
    """Reads one CAD format into a raw extraction document.

    An importer reports what the file contains and nothing else: geometry in
    the file's own length unit, the assembly structure, and mass properties at
    unit density. It never assigns materials, joints or component kinds --
    that is design intent, supplied by annotations.
    """

    format_name: str

    @abstractmethod
    def available(self) -> bool:
        """True when the kernel this importer needs can be imported here."""

    @abstractmethod
    def kernel_version(self) -> str:
        """Exact version of the CAD kernel, recorded in every extraction."""

    @abstractmethod
    def extract(self, path: Path, repository_root: Path) -> Dict[str, Any]:
        """Return a document conforming to cad-dataset/v1/cad-extraction."""


def detect_format(path: Path) -> str:
    """Identify a CAD file by its content, rejecting anything unrecognised.

    Args:
        path: The file to inspect. Only its first 64 bytes are read.

    Returns:
        The format name, e.g. "step".

    Raises:
        UnsupportedFormat: The file is too large, is a Git LFS pointer, or its
            content matches no known format.

    Example:
        >>> from pathlib import Path
        >>> root = Path(__file__).resolve().parents[3]
        >>> detect_format(root / "datasets/cad/robotic_joint_001/source/robotic_joint_001.step")
        'step'
    """
    regular_file(path)
    with path.open("rb") as handle:
        head = handle.read(64)
    if head.startswith(b"version https://git-lfs.github.com/spec/"):
        raise UnsupportedFormat(
            f"{path.name}: is a Git LFS pointer, not CAD content -- fetch it with git lfs pull"
        )
    for name, signatures in SIGNATURES.items():
        if any(head.lstrip().startswith(signature) for signature in signatures):
            return name
    raise UnsupportedFormat(f"{path.name}: content matches no supported CAD format")
