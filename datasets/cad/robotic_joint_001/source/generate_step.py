#!/usr/bin/env python3
"""Author the robotic_joint_001 STEP assembly (self-authored, MIT licensed).

This script is authoring provenance, not part of the pipeline: the STEP file it
writes is the source of truth, and everything downstream is derived from that
file alone. Re-running it reproduces the committed STEP byte for byte only
with the same cadquery-ocp version, which the dataset item records.

Every part is modelled in its own local frame and then placed, so extraction
exercises real assembly transforms rather than parts drawn in place. The shaft
is modelled along its local Z and rotated onto the assembly Y axis for the
same reason: the joint axis must be recovered from geometry.

Assembly frame, millimetres, +Z up. Joint axis: +Y through (0, *, 200).

    base_plate  aluminium plate under the link's swing plane
    pillar      aluminium pillar on the plate, with the shaft bore
    shaft       steel shaft running in the pillar bore, fixed to the link
    link        aluminium arm on the shaft
    payload     steel block on the link tip

The link swings in the plane y = 33..53 mm. The pillar ends at y = 25, an
8 mm gap, and the base plate lies under the swing plane so that rotating the
link too far down makes real contact. A range-of-motion check therefore has
something to find.

Usage:
    python generate_step.py [output.step]
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

ASSEMBLY_NAME = "robotic_joint_001"
# STEP headers carry a wall-clock timestamp. Pinning it makes the file a pure
# function of this script and the kernel version.
FIXED_TIMESTAMP = "2026-09-24T00:00:00"


def box(x0: float, y0: float, z0: float, dx: float, dy: float, dz: float):
    return BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), dx, dy, dz).Shape()


def bore_along_y(shape, x: float, z: float, radius: float, y0: float, length: float):
    cylinder = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x, y0, z), gp_Dir(0, 1, 0)), radius, length).Shape()
    return BRepAlgoAPI_Cut(shape, cylinder).Shape()


def placement(translation=(0.0, 0.0, 0.0), rotate_x_deg: float = 0.0) -> TopLoc_Location:
    transform = gp_Trsf()
    if rotate_x_deg:
        transform.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)), math.radians(rotate_x_deg))
    translate = gp_Trsf()
    translate.SetTranslation(gp_Vec(*translation))
    return TopLoc_Location(translate.Multiplied(transform))


def parts():
    """(name, local shape, placement) for every part, in the order written."""
    base_plate = box(-60, -25, 0, 420, 100, 20)
    pillar = bore_along_y(box(-30, -25, 0, 60, 50, 210), x=0, z=180, radius=6.5, y0=-30, length=60)
    shaft = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 6.0, 100.0).Shape()
    link = bore_along_y(box(-20, 0, -15, 340, 20, 30), x=0, z=0, radius=6.0, y0=-5, length=30)
    payload = box(0, 0, 0, 40, 24, 40)
    return [
        ("base_plate", base_plate, placement()),
        ("pillar", pillar, placement((0, 0, 20))),
        # Local +Z onto assembly +Y: rotate -90 degrees about X.
        ("shaft", shaft, placement((0, -35, 200), rotate_x_deg=-90.0)),
        ("link", link, placement((0, 33, 200))),
        ("payload", payload, placement((275, 31, 215))),
    ]


def write_step(path: Path) -> None:
    document = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    assembly = shape_tool.NewShape()
    TDataStd_Name.Set_s(assembly, TCollection_ExtendedString(ASSEMBLY_NAME))
    for name, shape, location in parts():
        part = shape_tool.AddShape(shape, False)
        TDataStd_Name.Set_s(part, TCollection_ExtendedString(name))
        component = shape_tool.AddComponent(assembly, part, location)
        TDataStd_Name.Set_s(component, TCollection_ExtendedString(f"{name}:1"))
    shape_tool.UpdateAssemblies()

    Interface_Static.SetCVal_s("write.step.unit", "MM")
    Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    if not writer.Transfer(document, STEPControl_AsIs):
        raise RuntimeError("STEP transfer failed")
    path.parent.mkdir(parents=True, exist_ok=True)
    if writer.Write(str(path)) != IFSelect_RetDone:
        raise RuntimeError(f"STEP write failed: {path}")

    text = path.read_text(encoding="utf-8")
    text, count = re.subn(
        r"(FILE_NAME\('[^']*',')[^']*(')", lambda m: m.group(1) + FIXED_TIMESTAMP + m.group(2), text, count=1
    )
    if count != 1:
        raise RuntimeError("could not pin the STEP header timestamp")
    path.write_bytes(text.encode("utf-8"))


def main(argv) -> int:
    target = Path(argv[1]) if len(argv) > 1 else Path(__file__).with_name(f"{ASSEMBLY_NAME}.step")
    write_step(target)
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
