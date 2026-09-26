#!/usr/bin/env python3
"""Mutation suite for the CAD dataset pipeline: every mutant must be killed.

Each mutant is one targeted edit that makes a behaviour the tests claim to
protect wrong. For every mutant this copies the repository, applies the edit,
runs the fast engineering-model tests and, only if they stay green, the slower
CAD-kernel tests. A mutant the suite does not kill is a test gap, and the
script exits 1. The unmutated copy runs first and must be green: against a
failing baseline every mutant would look killed.

Needs the CAD kernel and MuJoCo (tools/requirements-cad.txt), with `python3`
on PATH able to import mujoco. Not collected by pytest.

Usage:
    python3 tests/mutation/run_mutations.py [--workers N] [--only NAME ...]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]
B = "tools/ecad_model/builder.py"
D = "tools/ecad_model/dataset.py"
R = "tools/ecad_model/requirements.py"
M = "tools/ecad_model/mjcf.py"
S = "tools/ecad_model/importers/step_ocp.py"
F = "tools/ecad_model/importers/base.py"
Q = "tools/ecad_model/quantity.py"
J = "datasets/cad/robotic_joint_001/simulation/joint_dynamics.py"
FAST = "tests/unit/test_engineering_model.py"
SLOW = "tests/unit/test_cad_dataset.py"

# (name, file, text to replace, replacement). The replaced text must occur
# exactly once, or the harness itself fails: a stale anchor is not a kill.
MUTANTS: List[Tuple[str, str, str, str]] = [
    # builder: units, frames, provenance
    ("mass-ignores-density", B, "rounded(rho * volume)", "rounded(volume)"),
    ("no-mm-to-m", B, "scale = LENGTH_TO_METRES[unit]\n", "scale = 1.0\n"),
    ("area-scaled-cubed", B, 'part["surface_area"] * scale**2', 'part["surface_area"] * scale**3'),
    ("com-ignores-rotation", B, 'zip(_apply(rotation, [c * scale for c in part["center_of_mass_local"]]), translation)',
     'zip([c * scale for c in part["center_of_mass_local"]], translation)'),
    ("inertia-rt-i-r", B, "_matmul(rotation, [[item * scale**5", "_matmul(_transpose(rotation), [[item * scale**5"),
    ("unknown-mass-defaulted", B, 'mass = unknown("kg", computation, "mass = density x volume, and density is UNKNOWN")',
     'mass = quantity(0.0, "kg", Status.ESTIMATED, computation)'),
    ("unknowns-unsorted", B, 'return sorted(found, key=lambda entry: entry["path"])', "return found"),
    ("axis-sense-ignored", B, "oriented = line if agreement > 0 else [0.0 - item for item in line]", "oriented = line"),
    ("axis-sense-threshold-off", B, "if abs(agreement) < AXIS_SENSE_MIN_COSINE:", "if False:"),
    ("coaxial-ignores-axial-offset", B, "perpendicular = [o - along * d for o, d in zip(offset, direction)]", "perpendicular = offset"),
    ("origin-is-anchor", B, "origin = [a + along * d for a, d in zip(anchor, direction)]", "origin = anchor"),
    ("negative-zero-returns", B, "return [0.0 - item for item in unit] if unit[largest] < 0 else unit",
     "return [-item for item in unit] if unit[largest] < 0 else unit"),
    # mjcf: collision exclusions, inertia layout
    ("bearing-vs-fixed-root", M, "bearing = (realizer, parent)\n", "bearing = (realizer, fixed_root)\n"),
    ("fixed-pin-not-excluded", M, "        bearing = (realizer, child)", "        bearing = (realizer, parent)"),
    ("fullinertia-misordered", M, "inertia[0][1], inertia[0][2], inertia[1][2]", "inertia[0][1], inertia[1][2], inertia[0][2]"),
    ("filterparent-left-on", M, '    <flag filterparent="disable"/>', '    <flag filterparent="enable"/>'),
    # requirements: closed forms and compilation
    ("lever-ignores-origin", R, "arms = [[c - o for c, o in zip(com, origin)] for _, com, _ in bodies]",
     "arms = [list(com) for _, com, _ in bodies]"),
    ("parallel-axis-dropped", R, "+ mass * _dot(perpendicular, perpendicular)", ""),
    ("g-perp-is-gravity", R, "g_perp = [g - _dot(gravity, axis) * a for g, a in zip(gravity, axis)]", "g_perp = list(gravity)"),
    ("payload-override-ignored", R, 'if mass is not None and scenario.get("payload_component") == cid:', "if False:"),
    ("move-torque-ignores-gravity", R, "abs(inertia_axis * accel - gravity_torque(angle))", "abs(inertia_axis * accel)"),
    ("unknown-limit-compiled", R, '            if item["status"] == Status.UNKNOWN.value:\n                blocked.append(',
     '            if False:\n                blocked.append('),
    ("inequality-operator-flipped", R, '"maximum" if requirement["operator"] == "<=" else "minimum"',
     '"minimum" if requirement["operator"] == "<=" else "maximum"'),
    # simulation script
    ("proxies-push-on-statics", J,
     "def static_sweep(model: mujoco.MjModel, scenario: Dict[str, Any]) -> Dict[str, float]:\n    model.opt.disableflags |= mujoco.mjtDisableBit.mjDSBL_CONTACT\n",
     "def static_sweep(model: mujoco.MjModel, scenario: Dict[str, Any]) -> Dict[str, float]:\n"),
    ("payload-override-not-applied", J, "        model.body_mass[body] *= ratio\n", ""),
    ("min-jerk-velocity-wrong", J, "delta * (30 * s**2 - 60 * s**3 + 30 * s**4) / duration", "delta * (30 * s**2 - 60 * s**3) / duration"),
    ("min-jerk-accel-wrong", J, "delta * (60 * s - 180 * s**2 + 120 * s**3) / duration**2", "delta * (60 * s - 180 * s**2) / duration**2"),
    ("crossing-not-interpolated", J, "crossings.append(t0 + (data.time - t0) * (-previous) / (current - previous))", "crossings.append(data.time)"),
    ("clearance-by-contact-only", J, "        minimum = min(minimum, pose_minimum)", "        minimum = min(minimum, 0.01 if pose_minimum >= 0 else pose_minimum)"),
    ("joint-pair-unchecked-hidden", J, "    if joint_pair in excluded:", "    if False:"),
    # dataset: gates, integrity, provenance, comparison
    ("reltol-too-loose", D, "RELATIVE_TOLERANCE = 1e-9", "RELATIVE_TOLERANCE = 5e-5"),
    ("per-element-tolerance", D, "    scale = max([abs(item) for item in a + b] or [0.0])", "    scale = 0.0"),
    ("xml-identifiers-numeric", D, "            if x != y:\n                problems.append(f\"{where}: value {value}: {x!r} != {y!r}\")",
     "            pass"),
    ("integrity-no-byte-compare", D, 'if _sha256(data) != artifact["sha256"] or len(data) != artifact["size_bytes"]:', "if False:"),
    ("unrecorded-files-allowed", D, "    if unrecorded:\n", "    if False:\n"),
    ("manifest-check-off", D, "    return same_content(_without_derived_hashes(committed), _without_derived_hashes(fresh), \"dataset-item.json\")",
     "    return []"),
    ("cited-sources-unchecked", D, "                        if _sha256(path.read_bytes()) != origin[\"sha256\"]:",
     "                        if False:"),
    ("citation-outside-repository-read", D, "                if not path.is_relative_to(REPOSITORY_ROOT):", "                if False:"),
    ("kernel-missing-from-receipt", D, '    if extraction:\n        tools["opencascade"] = {', '    if False:\n        tools["opencascade"] = {'),
    ("validator-invocation-wrong", D, '"invocation": ["python3", "tools/cad_dataset.py", "validate",',
     '"invocation": ["python3", "tools/ecad_model/cli.py", "validate",'),
    ("v1-sanity-skipped", D, "v1_problems = _sanity_problems(model)", "v1_problems = []"),
    ("v2-reproducibility-skipped", D, "v2_problems = reproducibility(item, fresh) + manifest_problems(item, fresh) + _invariant_problems(",
     "v2_problems = [] and reproducibility(item, fresh) + _invariant_problems("),
    ("triangle-inequality-unchecked", D, "if moments[2] > moments[0] + moments[1] + 1e-9 * scale:", "if False:"),
    ("blocked-checks-not-emitted", D, '            if entry["gate"] != level.value:\n                continue', "            continue"),
    ("rejection-reported-unavailable", D,
     '"rejected": (ExecutionStatus.COMPLETED, Verdict.FAIL, "CAD_REJECTED",',
     '"rejected": (ExecutionStatus.UNAVAILABLE, Verdict.BLOCKED, "CAD_REJECTED",'),
    ("provenance-not-required", D, '        raise ValueError(f"{item.item_id}: {PROVENANCE} is missing; licence and origin are never assumed")',
     '        return {"origin": {"kind": "self_authored", "author": "x"}, "license": {}}'),
    ("symlinks-allowed", D, "            if path.is_symlink():\n                raise ValueError(f\"{item.item_id}: {item.root.name}", "            if False:\n                raise ValueError(f\"{item.item_id}: {item.root.name}"),
    ("ignored-item-allowed", D, "        if ignored.returncode == 0:", "        if False:"),
    ("clearance-trace-one-side", D, 'sorted(moving + fixed) if metric.startswith("rom_") else moving', "moving"),
    # importer and input guards
    ("external-references-allowed", S, "    if external:\n        raise ValueError(", "    if False:\n        raise ValueError("),
    ("string-literals-not-stripped", S, "    stripped = _STRING_LITERAL.sub(b\"''\", data)", "    stripped = data"),
    ("mirrored-placement-allowed", S, "if abs(transform.ScaleFactor() - 1.0) > 1e-12 or transform.IsNegative():", "if False:"),
    ("duplicate-names-allowed", S, "if not name or name in names:", "if not name:"),
    ("nested-assembly-allowed", S, "        if XCAFDoc_ShapeTool.IsAssembly_s(referred):\n            raise", "        if False:\n            raise"),
    ("item-read-unguarded", D, "        regular_file(path)\n        return path.read_bytes()", "        return path.read_bytes()"),
    ("check-follows-symlinks", D, "    _refuse_symlinks(item)\n    item.files()\n    derived = _derive(item)",
     "    item.files()\n    derived = _derive(item)"),
    ("check-skips-enumeration", D, "    _refuse_symlinks(item)\n    item.files()\n    derived = _derive(item)",
     "    _refuse_symlinks(item)\n    derived = _derive(item)"),
    ("reader-extern-files-unchecked", S, "    if reader.ExternFiles().Size():", "    if False:"),
    ("requirement-binding-dropped", D,
     "                check_result.requirement_ids = [*check_result.requirement_ids, case_id]", "                pass"),
    ("illustrative-limit-passes", D, "            if case_id in illustrative_ids and check_result.verdict is Verdict.PASS:",
     "            if False:"),
    ("missing-input-reported-fail", D,
     'failure = (ExecutionStatus.SKIPPED, Verdict.BLOCKED, "MISSING_REQUIRED_INPUT",',
     'failure = (ExecutionStatus.COMPLETED, Verdict.FAIL, "MISSING_REQUIRED_INPUT",'),
    ("unverified-licence-permits-use", "schemas/cad-dataset/v1/source-provenance.schema.json",
     '"redistribution_permitted": {"const": false},\n        "training_use_permitted": {"const": false}',
     '"redistribution_permitted": {"type": "boolean"},\n        "training_use_permitted": {"type": "boolean"}'),
    ("fifo-allowed", F, "    if not stat.S_ISREG(info.st_mode):", "    if False:"),
    ("lfs-pointer-not-named", F, 'if head.startswith(b"version https://git-lfs.github.com/spec/"):', "if False:"),
    # quantity rules
    ("unknown-may-carry-value", Q, "    if (value is None) != (status is Status.UNKNOWN):", "    if value is None and status is not Status.UNKNOWN:"),
    ("derived-without-inputs", Q, "    if status is Status.DERIVED and not inputs:", "    if False:"),
]


def _first_failure(output: str) -> str:
    """The first failing test pytest's short summary names, or "" if none.

    A failing subtest is summarised as "SUBFAILED(<params>) <test> - ..."; its
    parameters are kept, since they say which case the mutant broke.
    """
    for line in output.splitlines():
        if line.startswith(("FAILED ", "ERROR ")):
            return line.split()[1]
        if line.startswith("SUBFAILED"):
            node = next((token for token in line.split() if "::" in token), "")
            params = line[len("SUBFAILED"):line.index(node)].strip() if node else ""
            return f"{node} {params}".strip() or line
    return ""


def run(name: str, relative: Optional[str], old: str, new: str) -> Tuple[str, str, str]:
    with tempfile.TemporaryDirectory(prefix="ecad-mutant-") as scratch:
        copy = Path(scratch) / "repo"
        shutil.copytree(REPO, copy, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".pytest_cache", "tmp-cad-dataset-test-*"))
        # A private repository per copy: sharing the source checkout's index
        # between parallel copies would race on its lock.
        for command in (["git", "init", "-q"], ["git", "add", "-A"],
                        ["git", "-c", "user.name=mutation", "-c", "user.email=mutation@localhost",
                         "commit", "-q", "-m", "base"]):
            subprocess.run(command, cwd=copy, check=True, capture_output=True, timeout=300)
        if relative is not None:
            target = copy / relative
            text = target.read_bytes().decode("utf-8")
            if text.count(old) != 1:
                return name, "ANCHOR", f"expected the anchor once in {relative}, found {text.count(old)}"
            target.write_bytes(text.replace(old, new).encode("utf-8"))
        environment = dict(os.environ, ECAD_REQUIRE_CAD_TOOLS="1", PYTHONDONTWRITEBYTECODE="1")
        for suite in (FAST, SLOW):
            result = subprocess.run(
                [sys.executable, "-m", "pytest", suite, "-q", "-x", "-p", "no:cacheprovider"],
                cwd=copy, env=environment, capture_output=True, text=True, timeout=1800,
            )
            if result.returncode != 0:
                return name, "KILLED", f"by {_first_failure(result.stdout) or Path(suite).name}"
        return name, "SURVIVED", "both suites green"


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--only", nargs="*", help="run only the named mutants")
    args = parser.parse_args(argv)
    selected = [m for m in MUTANTS if not args.only or m[0] in args.only]
    baseline = run("baseline", None, "", "")
    if baseline[1] != "SURVIVED":
        print(f"baseline is not green ({baseline[2]}); every mutant would look killed, so none were run")
        return 2
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        outcomes = list(pool.map(lambda mutant: run(*mutant), selected))
    for name, outcome, detail in outcomes:
        print(f"{outcome:9s} {name:36s} {detail}")
    killed = sum(outcome == "KILLED" for _, outcome, _ in outcomes)
    print(f"\n{killed} of {len(outcomes)} mutants killed")
    return 0 if killed == len(outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
