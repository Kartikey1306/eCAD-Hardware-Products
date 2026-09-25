"""STEP (ISO 10303-21) importer backed by the OpenCASCADE kernel via cadquery-ocp.

CAD files are untrusted input and the STEP parser is native code, so parsing
never happens in the calling process. extract() runs this module as a child
through the repository's hardened run_process: the child sees a copy of the
one STEP file inside a throwaway workspace, under a scrubbed environment and a
timeout, so a crash or hang in the kernel costs one extraction rather than the
caller. The child reports the SHA-256 of the bytes it parsed, and the parent
refuses the result unless that matches the file it was asked to read.

The workspace alone does not confine the parser: OCCT resolves a STEP file's
external document references (DOCUMENT_FILE and friends) at transfer time,
including absolute and ``../`` paths, and a hash of the top-level file would
not cover what they load. Such files are therefore refused before parsing, and
the reader's own list of external files is checked again after transfer.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

from .base import CADImporter, ExtractionError

EXTRACTION_SCHEMA = "https://embeddedos.org/schemas/cad-dataset/v1/cad-extraction.schema.json"
IMPORTER_VERSION = "1.0.0"
EXTRACTION_TIMEOUT_SECONDS = 120
MEMORY_LIMIT_BYTES = 2 * 1024 * 1024 * 1024
REJECTED_EXIT = 3  # the child's exit status when it refuses a file on its content
# OCCT prints transfer statistics to stdout from C++, interleaved with ours,
# so the document is found by this prefix rather than by being the last line.
RESULT_MARKER = "ECAD_EXTRACTION_JSON:"
# Entities through which a STEP file makes the reader load other files.
EXTERNAL_REFERENCE_ENTITIES = (
    "DOCUMENT_FILE",
    "EXTERNAL_SOURCE",
    "APPLIED_EXTERNAL_IDENTIFICATION_ASSIGNMENT",
    "PRODUCT_DEFINITION_WITH_ASSOCIATED_DOCUMENTS",
)
_STRING_LITERAL = re.compile(rb"'(?:[^']|'')*'")
_EXTERNAL = re.compile(rb"\b(" + b"|".join(name.encode() for name in EXTERNAL_REFERENCE_ENTITIES) + rb")\s*\(", re.IGNORECASE)


def external_references(data: bytes) -> list:
    """Names of the external-reference entities a STEP file instantiates.

    String literals are removed first, so a part *named* DOCUMENT_FILE is not
    mistaken for one; anything left over is refused rather than guessed about.

    Args:
        data: The STEP file's bytes.

    Returns:
        Sorted distinct entity names found; empty for a self-contained file.

    Example:
        >>> external_references(b"#1 = DOCUMENT_FILE('../../secret.stp','',$,#2,'',$);")
        ['DOCUMENT_FILE']
        >>> external_references(b"#1 = PRODUCT('DOCUMENT_FILE(','',$,(#2));")
        []
    """
    stripped = _STRING_LITERAL.sub(b"''", data)
    return sorted({match.group(1).decode().upper() for match in _EXTERNAL.finditer(stripped)})


def _kernel_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return f"cadquery-ocp {version('cadquery-ocp')}"
    except PackageNotFoundError:
        return "unknown"


class StepImporter(CADImporter):
    """Read a STEP assembly: names, placements, volumes, inertia, axes.

    Example (run against the committed dataset item):
        >>> from pathlib import Path
        >>> root = Path(__file__).resolve().parents[3]
        >>> step = root / "datasets/cad/robotic_joint_001/source/robotic_joint_001.step"
        >>> extraction = StepImporter().extract(step, root)
        >>> sorted(part["name"] for part in extraction["parts"])
        ['base_plate', 'link', 'payload', 'pillar', 'shaft']
    """

    format_name = "step"

    def available(self) -> bool:
        """True when cadquery-ocp can be imported here.

        Returns:
            Whether the OpenCASCADE kernel is installed.

        Example:
            >>> StepImporter().available()
            True
        """
        try:
            import OCP  # noqa: F401
        except ImportError:
            return False
        return True

    def kernel_version(self) -> str:
        """Exact version of the kernel bindings, recorded in every extraction.

        Returns:
            e.g. "cadquery-ocp 8.0.1.0.0", or "unknown" when not installed.

        Example:
            >>> StepImporter().kernel_version().startswith("cadquery-ocp ")
            True
        """
        return _kernel_version()

    def extract(self, path: Path, repository_root: Path) -> Dict[str, Any]:
        """Extract a STEP file in an isolated child process.

        Args:
            path: The STEP file. Must lie inside repository_root.
            repository_root: Root that the recorded source path is relative to.

        Returns:
            A document conforming to cad-dataset/v1/cad-extraction.

        Raises:
            ValueError: The kernel is unavailable, the child failed, timed out
                or produced unparseable output, or it parsed different bytes.
        """
        from ecad_validation.adapters.process import ProcessRequest, run_process
        from ecad_validation.models import ExecutionStatus

        if not self.available():
            raise ExtractionError("unavailable", "the STEP importer needs cadquery-ocp, which is not installed")
        resolved = path.resolve()
        root = repository_root.resolve()
        relative = resolved.relative_to(root).as_posix()
        expected = hashlib.sha256(resolved.read_bytes()).hexdigest()
        tools = Path(__file__).resolve().parents[2]
        result = run_process(
            ProcessRequest(
                argv=[sys.executable, "-m", "ecad_model.importers.step_ocp", relative],
                input_root=root,
                input_files=[resolved],
                timeout_seconds=EXTRACTION_TIMEOUT_SECONDS,
                environment={"PYTHONPATH": str(tools), "PYTHONDONTWRITEBYTECODE": "1"},
            )
        )
        detail = ((result.stderr or "").strip().splitlines()[-1:] or [result.reason_code])[0]
        if result.execution_status is ExecutionStatus.TIMED_OUT:
            raise ExtractionError("timed_out", f"STEP extraction of {relative} timed out after {EXTRACTION_TIMEOUT_SECONDS} s")
        if result.execution_status is ExecutionStatus.UNAVAILABLE:
            raise ExtractionError("unavailable", f"STEP extraction of {relative} could not start: {result.reason_code}")
        if result.returncode == REJECTED_EXIT:
            # The child read the file and refused it on its content.
            raise ExtractionError("rejected", f"STEP extraction of {relative} refused the file: {detail}")
        if result.execution_status is not ExecutionStatus.COMPLETED or result.returncode != 0:
            raise ExtractionError(
                "crashed", f"STEP extraction of {relative} failed ({result.reason_code}, exit {result.returncode}): {detail}")
        marked = [line[len(RESULT_MARKER):] for line in result.stdout.splitlines() if line.startswith(RESULT_MARKER)]
        if len(marked) != 1:
            raise ExtractionError("crashed", f"STEP extraction of {relative} produced {len(marked)} result documents, expected 1")
        try:
            document = json.loads(marked[0])
        except json.JSONDecodeError as exc:
            raise ExtractionError("crashed", f"STEP extraction of {relative} produced malformed JSON") from exc
        if document["source"]["sha256"] != expected:
            raise ExtractionError("rejected", f"STEP extraction parsed different bytes than {relative}")
        return document


def _name(label) -> str:
    from OCP.TDataStd import TDataStd_Name

    attribute = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attribute):
        return attribute.Get().ToExtString()
    return ""


def _matrix(mat) -> List[List[float]]:
    return [[mat.Value(row, column) for column in (1, 2, 3)] for row in (1, 2, 3)]


def _part(shape) -> Dict[str, Any]:
    """Geometry and unit-density mass properties of one part, in its local frame."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepGProp import BRepGProp
    from OCP.Bnd import Bnd_Box
    from OCP.GeomAbs import GeomAbs_Cylinder
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    volume = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, volume)
    surface = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, surface)
    bounds = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, bounds, False, False)
    # Bnd_Box.Get() is unusable in cadquery-ocp 8.0 (its Limits return type
    # is not registered with the bindings); the corner points are.
    low, high = bounds.CornerMin(), bounds.CornerMax()
    centre = volume.CentreOfMass()

    solids = 0
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    while explorer.More():
        solids += 1
        explorer.Next()

    faces = 0
    cylinders = []
    seen = set()
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        faces += 1
        adaptor = BRepAdaptor_Surface(TopoDS.Face(explorer.Current()))
        if adaptor.GetType() == GeomAbs_Cylinder:
            cylinder = adaptor.Cylinder()
            axis = cylinder.Axis()
            origin, direction = axis.Location(), axis.Direction()
            entry = {
                "axis_origin_local": [origin.X(), origin.Y(), origin.Z()],
                "axis_direction_local": [direction.X(), direction.Y(), direction.Z()],
                "radius": cylinder.Radius(),
            }
            key = json.dumps(entry, sort_keys=True)
            if key not in seen:
                seen.add(key)
                cylinders.append(entry)
        explorer.Next()

    return {
        "solid_count": solids,
        "face_count": faces,
        "volume": volume.Mass(),
        "surface_area": surface.Mass(),
        # GProp_GProps.MatrixOfInertia is about the centre of mass, in tensor
        # convention (products of inertia negative). Verified against a
        # 2x4x6 box ([208, 160, 80]) and an offset pair of cubes (Ixy = -0.5).
        "center_of_mass_local": [centre.X(), centre.Y(), centre.Z()],
        "inertia_about_com_unit_density_local": _matrix(volume.MatrixOfInertia()),
        "bounding_box_local": {"min": [low.X(), low.Y(), low.Z()], "max": [high.X(), high.Y(), high.Z()]},
        "cylindrical_faces": sorted(cylinders, key=lambda item: json.dumps(item, sort_keys=True)),
    }


def _extract_in_process(path: Path, relative: str) -> Dict[str, Any]:
    """Parse a STEP file with OCCT in the current process. Only the child calls this."""
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDF import TDF_Label
    from OCP.TDocStd import TDocStd_Document
    from OCP.collections import Sequence_TDF_Label
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool

    data = path.read_bytes()
    external = external_references(data)
    if external:
        raise ValueError(
            f"{relative}: external document references are not supported ({', '.join(external)}); "
            "every part must be inside the one file that is hashed")
    document = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    # Pin the document to millimetres: OCCT then converts whatever unit the
    # file declares. Verified with one 10 mm cube written as mm, m and inch
    # (raw coordinates 10., 1.E-02 and 0.3937): all three read back as
    # 1000 mm^3. The unit is set, not queried, because in cadquery-ocp 8.0
    # GetLengthUnit_s returns only a bool -- the value is lost in the binding,
    # and reading that bool as metres-per-unit would scale every mass by 1e9.
    XCAFDoc_DocumentTool.SetLengthUnit_s(document, 0.001)
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise ValueError(f"{relative}: OCCT could not read the file as STEP")
    if not reader.Transfer(document):
        raise ValueError(f"{relative}: OCCT could not transfer the STEP data")
    if reader.ExternFiles().Size():
        raise ValueError(f"{relative}: the reader loaded external files; refusing the result")

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    roots = Sequence_TDF_Label()
    shape_tool.GetFreeShapes(roots)
    if roots.Length() != 1:
        raise ValueError(f"{relative}: expected exactly one top-level assembly, found {roots.Length()}")
    root = roots.Value(1)
    if not XCAFDoc_ShapeTool.IsAssembly_s(root):
        raise ValueError(f"{relative}: the top-level shape is not an assembly")

    components = Sequence_TDF_Label()
    XCAFDoc_ShapeTool.GetComponents_s(root, components, False)
    parts = []
    names = set()
    for index in range(1, components.Length() + 1):
        component = components.Value(index)
        referred = TDF_Label()
        if not XCAFDoc_ShapeTool.GetReferredShape_s(component, referred):
            raise ValueError(f"{relative}: assembly component {index} refers to no shape")
        if XCAFDoc_ShapeTool.IsAssembly_s(referred):
            raise ValueError(f"{relative}: nested sub-assemblies are not supported by this importer")
        name = _name(referred)
        if not name or name in names:
            raise ValueError(f"{relative}: parts must have unique non-empty names, got {name!r}")
        names.add(name)
        transform = XCAFDoc_ShapeTool.GetLocation_s(component).Transformation()
        if abs(transform.ScaleFactor() - 1.0) > 1e-12 or transform.IsNegative():
            raise ValueError(f"{relative}: part {name!r} has a scaled or mirrored placement")
        translation = transform.TranslationPart()
        part = {
            "name": name,
            "occurrence": _name(component) or f"{name}:{index}",
            "translation": [translation.X(), translation.Y(), translation.Z()],
            "rotation": _matrix(transform.VectorialPart()),
        }
        part.update(_part(XCAFDoc_ShapeTool.GetShape_s(referred)))
        parts.append(part)

    return {
        "$schema": EXTRACTION_SCHEMA,
        "extraction_version": "1.0.0",
        "source": {"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "format": "step"},
        "importer": {
            "name": "ecad_model.importers.step_ocp",
            "version": IMPORTER_VERSION,
            "kernel": "OpenCASCADE",
            "kernel_version": _kernel_version(),
        },
        "length_unit": "mm",
        "parts": sorted(parts, key=lambda item: item["name"]),
    }


def _limit_memory() -> None:
    """Cap the child's address space where the platform enforces it."""
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
    except (ImportError, ValueError, OSError) as exc:
        print(f"note: address-space limit not enforced on this platform: {exc}", file=sys.stderr)


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m ecad_model.importers.step_ocp <file.step>", file=sys.stderr)
        return 2
    _limit_memory()
    relative = argv[1]
    try:
        document = _extract_in_process(Path(relative), relative)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return REJECTED_EXIT
    print(RESULT_MARKER + json.dumps(document, sort_keys=True, allow_nan=False, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
