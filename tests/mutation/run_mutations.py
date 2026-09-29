#!/usr/bin/env python3
"""Mutation suite for the CAD dataset pipeline: every mutant must be killed.

Each mutant is one targeted edit that makes a behaviour the tests claim to
protect wrong. For every mutant this copies the repository, applies the edit,
runs the fast engineering-model, domain-adapter, netlist, ngspice-adapter,
electrical, Verilog-grammar, hdl-adapter and digital tests, then the
electrical tests that run ngspice and the digital tests that run Icarus
Verilog and, if they all stay green, the slower CAD-kernel tests. A mutant of
a dataset item's own file (a simulation script, a netlist or HDL source, its
annotations, requirements or provenance) is followed by a rebuild of that
item, so the manifest's hashes cannot kill it: a behavioural test must. A mutant the
suite does not kill is a test gap, and the script exits 1. The
unmutated copy runs first and must be green: against a failing baseline every
mutant would look killed.

Needs the CAD kernel and MuJoCo (tools/requirements-cad.txt), with `python3`
on PATH able to import mujoco, ngspice whose `--version` names its version
(brew install ngspice; apt install ngspice), and Icarus Verilog whose
`iverilog -V` names it, with vvp (brew install icarus-verilog; apt install
iverilog). Not collected by pytest.

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
MA = "tools/ecad_model/domains/mechanical.py"
RS = "tools/ecad_model/results.py"
DR = "tools/ecad_model/domains/__init__.py"
J = "datasets/cad/robotic_joint_001/simulation/joint_dynamics.py"
NG = "tools/ecad_validation/adapters/ngspice.py"
CP = "tools/ecad_validation/adapters/capabilities.py"
HD = "tools/ecad_validation/adapters/hdl.py"
PR = "tools/ecad_validation/adapters/process.py"
SP = "tools/ecad_model/spice.py"
EL = "tools/ecad_model/domains/electrical.py"
VG = "tools/ecad_model/verilog.py"
DG = "tools/ecad_model/domains/digital.py"
EN = "datasets/cad/servo_supply_001/source/servo_supply_001.cir"
EA = "datasets/cad/servo_supply_001/design/annotations.json"
ER = "datasets/cad/servo_supply_001/requirements/requirements.json"
EP = "datasets/cad/servo_supply_001/source/provenance.json"
DT = "datasets/cad/uart_loopback_001/source/tb_uart_loopback.v"
DA = "datasets/cad/uart_loopback_001/design/annotations.json"
DQ = "datasets/cad/uart_loopback_001/requirements/requirements.json"
DP = "datasets/cad/uart_loopback_001/source/provenance.json"
MS = "schemas/engineering-model/v1/engineering-model.schema.json"
AS = "schemas/engineering-model/v1/design-annotations.schema.json"
PS = "schemas/cad-dataset/v1/source-provenance.schema.json"
GA = ".gitattributes"
FAST = "tests/unit/test_engineering_model.py"
ADAPTER = "tests/unit/test_domain_adapter.py"
NETLIST = "tests/unit/test_spice_netlist.py"
NGSPICE = "tests/unit/test_ngspice_adapter.py"
ELECTRICAL = "tests/unit/test_electrical_domain.py"
VERILOG = "tests/unit/test_verilog_source.py"
HDLAD = "tests/unit/test_hdl_adapter.py"
DIGITAL = "tests/unit/test_digital_domain.py"
SPICE = "tests/unit/test_electrical_spice.py"
ICARUS = "tests/unit/test_digital_icarus.py"
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
    ("unknown-mass-defaulted", B, 'mass = quantity(None, "kg", Status.UNKNOWN, computation, derived_from=[volume_path, density_path],\n'
     '                            note=f"mass = density x volume, and density is {density[\'status\']}")',
     'mass = quantity(0.0, "kg", Status.SPECIFIED, computation)'),
    ("null-mass-loses-its-inputs", B, 'mass = quantity(None, "kg", Status.UNKNOWN, computation, derived_from=[volume_path, density_path],',
     'mass = quantity(None, "kg", Status.UNKNOWN, computation, derived_from=[],'),
    ("index-drops-null-status", B, 'entry = {"path": path, "status": node["status"], "needed_by": _needed_by(path)}',
     'entry = {"path": path, "needed_by": _needed_by(path)}'),
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
    ("lever-ignores-origin", MA, "arms = [[c - o for c, o in zip(com, origin)] for _, com, _ in bodies]",
     "arms = [list(com) for _, com, _ in bodies]"),
    ("parallel-axis-dropped", MA, "+ mass * _dot(perpendicular, perpendicular)", ""),
    ("g-perp-is-gravity", MA, "g_perp = [g - _dot(gravity, axis) * a for g, a in zip(gravity, axis)]", "g_perp = list(gravity)"),
    ("payload-override-ignored", MA, 'if mass is not None and scenario.get("payload_component") == cid:', "if False:"),
    ("move-torque-ignores-gravity", MA, "abs(inertia_axis * accel - gravity_torque(angle))", "abs(inertia_axis * accel)"),
    ("unknown-limit-compiled", R, '            if is_null(item["status"]):\n                blocked.append(',
     '            if False:\n                blocked.append('),
    ("inequality-operator-flipped", R, 'if requirement["operator"] == "<="\n', 'if requirement["operator"] == ">="\n'),
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
    ("manifest-check-off", D, "    return same_content(committed, _without_derived_hashes(fresh), MANIFEST)",
     "    return []"),
    ("cited-sources-unchecked", D, "    if _sha256(path.read_bytes()) != sha256:", "    if False:"),
    ("licence-text-unchecked", D, "    if licence:\n", "    if False:\n"),
    ("citation-outside-repository-read", D, "    if not path.is_relative_to(REPOSITORY_ROOT):\n        return f\"{what}",
     "    if False:\n        return f\"{what}"),
    ("kernel-missing-from-receipt", D, '            tools[tool["tool_id"]] = tool', "            pass"),
    ("validator-invocation-wrong", D, '"invocation": ["python3", "tools/cad_dataset.py", "validate",',
     '"invocation": ["python3", "tools/ecad_model/cli.py", "validate",'),
    ("v1-sanity-skipped", D, "            v1_problems = adapter.sanity_problems(fresh.model)", "            v1_problems = []"),
    ("v2-reproducibility-skipped", D, "                   reproducibility(item, fresh) + manifest_problems(item, fresh, registry)",
     "                   [] and reproducibility(item, fresh) + manifest_problems(item, fresh, registry)"),
    ("triangle-inequality-unchecked", MA, "if moments[2] > moments[0] + moments[1] + 1e-9 * scale:", "if False:"),
    ("blocked-checks-not-emitted", D, '    blocked = {entry["id"]: entry for entry in fresh.blocked if entry["gate"] == level.value}',
     '    blocked = {}'),
    ("rejection-reported-unavailable", D,
     '"rejected": (ExecutionStatus.COMPLETED, Verdict.FAIL, "SOURCE_REJECTED",',
     '"rejected": (ExecutionStatus.UNAVAILABLE, Verdict.BLOCKED, "SOURCE_REJECTED",'),
    ("provenance-not-required", D, '        raise ValueError(f"{item.item_id}: {PROVENANCE} is missing; licence and origin are never assumed")',
     '        return {"origin": {"kind": "self_authored", "author": "x"}, "license": {}}'),
    ("symlinks-allowed", D, "            if path.is_symlink():\n                raise ValueError(f\"{item.item_id}: {item.root.name}", "            if False:\n                raise ValueError(f\"{item.item_id}: {item.root.name}"),
    ("ignored-item-allowed", D, "        if ignored.returncode == 0:", "        if False:"),
    ("clearance-trace-one-side", MA, 'return sorted(moving + fixed) if metric.startswith("rom_") else sorted(moving)',
     "return sorted(moving)"),
    # importer and input guards
    ("external-references-allowed", S, "    if external:\n        raise ValueError(", "    if False:\n        raise ValueError("),
    ("string-literals-not-stripped", S, "    stripped = _STRING_LITERAL.sub(b\"''\", data)", "    stripped = data"),
    ("mirrored-placement-allowed", S, "if abs(transform.ScaleFactor() - 1.0) > 1e-12 or transform.IsNegative():", "if False:"),
    ("duplicate-names-allowed", S, "if not name or name in names:", "if not name:"),
    ("nested-assembly-allowed", S, "        if XCAFDoc_ShapeTool.IsAssembly_s(referred):\n            raise", "        if False:\n            raise"),
    ("item-read-unguarded", D, "        regular_file(path)\n        return path.read_bytes()", "        return path.read_bytes()"),
    ("check-follows-symlinks", D, "        _refuse_symlinks(self)\n        self.provenance = _provenance(self)",
     "        self.provenance = _provenance(self)"),
    ("tolerance-ignored", R, '({"maximum": bound + tolerance} if', '({"maximum": bound} if'),
    ("tolerance-widens-the-wrong-way", R, 'else {"minimum": bound - tolerance})', 'else {"minimum": bound + tolerance})'),
    ("unit-unchecked", R, "    if metrics[metric].unit != unit:", "    if False:"),
    ("vocabulary-unchecked", MA, '        validate_schema({\n            "scenarios"', '        return None\n        validate_schema({\n            "scenarios"'),
    ("foreign-requirement-compiled", D, "    if foreign:\n", "    if False:\n"),
    ("ai-rule-dropped", RS, '    if assumed and verdict in ("PASS", "FAIL") and reason_code in COMPARATOR_CODES:', "    if False:"),
    ("ai-rule-spares-a-pass", RS, '    if assumed and verdict in ("PASS", "FAIL") and reason_code in COMPARATOR_CODES:',
     '    if assumed and verdict == "FAIL" and reason_code in COMPARATOR_CODES:'),
    ("inputs-not-transitive", RS,
     '        stack.extend(parents)\n        if not parents or quantity["status"] != "DERIVED":\n            found[path] = quantity["status"]',
     '        found[path] = quantity["status"]'),
    ("limit-not-an-input", D, '[requirement["limit"]["quantity"]] if "quantity" in requirement["limit"] else [])', '[])'),
    ("result-status-recomputed", RS, '"status": check["verdict"],', '"status": "PASS",'),
    ("fidelity-per-domain", RS, '"model_fidelity": metrics[metric].fidelity if metric in metrics else None,', '"model_fidelity": "EXACT_GEOMETRY",'),
    ("measured-side-dropped", RS, "if (other_id != check_id and value is not None and other_case", "if (False and other_case"),
    ("simulator-version-inferred", RS, '"simulator_version": execution.get("tool_version") or None,', '"simulator_version": "3.14.0",'),
    ("check-skips-enumeration", D, "    item.files()\n    derived = _derive(item, registry)", "    derived = _derive(item, registry)"),
    ("status-from-registry-alone", DR, "        if adapter is not None and domain == primary and adapter.formats & formats:",
     "        if adapter is not None:"),
    ("empty-case-document-written", D, '        if not document["cases"]:\n            continue', "        pass"),
    ("tool-record-last-writer-wins", D, "        tools[tool_id] = _tool_record(tool_id, tool_checks)",
     "        tools[tool_id] = {**_tool_record(tool_id, tool_checks), \"invocation\": list(tool_checks[-1].tool_invocation)}"),
    ("reader-extern-files-unchecked", S, "    if reader.ExternFiles().Size():", "    if False:"),
    ("requirement-binding-dropped", D,
     "            check_result.requirement_ids = [*check_result.requirement_ids, case_id]", "            pass"),
    ("illustrative-limit-passes", D, "        if case_id in illustrative_ids and check_result.verdict is Verdict.PASS:",
     "        if False:"),
    ("missing-input-reported-fail", D,
     'failure = (ExecutionStatus.SKIPPED, Verdict.BLOCKED, "MISSING_REQUIRED_INPUT",',
     'failure = (ExecutionStatus.COMPLETED, Verdict.FAIL, "MISSING_REQUIRED_INPUT",'),
    ("unverified-licence-permits-use", "schemas/cad-dataset/v1/source-provenance.schema.json",
     '"redistribution_permitted": {"const": false},\n        "training_use_permitted": {"const": false}',
     '"redistribution_permitted": {"type": "boolean"},\n        "training_use_permitted": {"type": "boolean"}'),
    ("fifo-allowed", F, "    if not stat.S_ISREG(info.st_mode):", "    if False:"),
    ("lfs-pointer-not-named", F, 'if head.startswith(b"version https://git-lfs.github.com/spec/"):', "if False:"),
    # quantity rules
    ("unknown-may-carry-value", Q, "    if (value is None) != (status in NULL_STATUSES):", "    if value is None and status not in NULL_STATUSES:"),
    ("null-means-only-unknown", Q, "    return Status(status) in NULL_STATUSES", "    return Status(status) is Status.UNKNOWN"),
    ("null-status-note-optional", Q, "    if status in _NOTE_REQUIRED and not note:", "    if False:"),
    ("unspecified-cites-nothing", Q, '    if status is Status.UNSPECIFIED and "sha256" not in origin:', "    if False:"),
    ("status-source-kind-unchecked", Q, "    if status in _SOURCE_KIND and origin.get(\"kind\") != _SOURCE_KIND[status]:", "    if False:"),
    ("schema-null-means-only-unknown", "schemas/engineering-model/v1/common.schema.json",
     '"then": {"properties": {"status": {"enum": ["UNKNOWN", "UNSPECIFIED", "NOT_AVAILABLE"]}}}',
     '"then": {"properties": {"status": {"const": "UNKNOWN"}}}'),
    ("missing-input-reason-renamed", D, 'reason_code="MISSING_REQUIRED_INPUT" if entry["missing_inputs"] else "REFERENCE_NOT_APPLICABLE",',
     'reason_code="REQUIREMENT_INPUT_UNKNOWN",'),
    ("derived-without-inputs", Q, "    if status is Status.DERIVED and not inputs:", "    if False:"),
    # Foundation review: input statuses and their propagation
    ("null-input-not-blocking", RS, '    if missing:\n        return "BLOCKED", "MISSING_REQUIRED_INPUT", missing',
     '    if False:\n        return "BLOCKED", "MISSING_REQUIRED_INPUT", missing'),
    ("null-input-only-unknown", RS, 'for leaf in inputs if is_null(leaf["status"])]', 'for leaf in inputs if leaf["status"] == "UNKNOWN"]'),
    ("ai-rule-on-any-verdict", RS, ' and reason_code in COMPARATOR_CODES:', ':'),
    ("unresolved-ignored", RS, '    if unresolved and verdict != "BLOCKED":', '    if False:'),
    ("unresolved-overrides-blocked", RS, '    if unresolved and verdict != "BLOCKED":', '    if unresolved:'),
    ("assumption-with-parents-walked-past", RS, '        if not parents or quantity["status"] != "DERIVED":', '        if not parents:'),
    ("unresolvable-input-raises", RS, '        except KeyError:\n            unresolved.add(path)', '        except ZeroDivisionError:\n            unresolved.add(path)'),
    ("lineage-dangling-allowed", RS, '            if parent not in graph:', '            if False:'),
    ("lineage-cycle-allowed", RS, '                if colour.get(parent) == 1:', '                if False:'),
    ("lineage-unchecked-at-build", D, '    if lineage:\n', '    if False:\n'),
    ("missing-input-paths-dropped", D,
     '            v1_findings = [f"{entry[\'status\']}: {entry[\'path\']}" for entry in exc.inputs] or [str(exc)]',
     '            v1_findings = [str(exc)]'),
    ("missing-input-not-traced-to-its-root", D, '        raise MissingInput(str(exc), roots or exc.inputs) from exc',
     '        raise MissingInput(str(exc), exc.inputs) from exc'),
    ("mjcf-single-missing-unnamed", M, '    if missing:\n        raise MissingInput("the mechanical model needs values',
     '    if missing[1:]:\n        raise MissingInput("the mechanical model needs values'),
    # Foundation review: what the mechanical adapter says a metric rests on
    ("range-not-an-input", MA,
     '        paths = [f"joints/{jid}/axis", f"joints/{jid}/origin", f"joints/{jid}/limits/lower", f"joints/{jid}/limits/upper"]',
     '        paths = [f"joints/{jid}/axis", f"joints/{jid}/origin"]'),
    ("gravity-not-an-input", MA, '        if not clearance:\n            paths.append("design/gravity")',
     '        if False:\n            paths.append("design/gravity")'),
    ("clearance-reads-mass", MA, '            if clearance:\n                paths += [f"components/{cid}/geometry/bounding_box_local/min",',
     '            if False:\n                paths += [f"components/{cid}/geometry/bounding_box_local/min",'),
    ("reference-inputs-empty", MA, '            return reference_value(model, derivation, scenario)[1]', '            return []'),
    ("reference-gravity-unlisted", MA, '    used.append("design/gravity")', '    pass'),
    ("gravity-read-unchecked", MA, '    gravity = _known(model, "design/gravity", missing)', '    gravity = model["design"]["gravity"]["value"]'),
    ("weightless-design-crashes", MA, '    if "gravity" not in model["design"]:\n        raise ReferenceBlocked',
     '    if False:\n        raise ReferenceBlocked'),
    ("reference-scenarios-unchecked", MA,
     '"scenarios": [entry["scenario"] for entry in (*requirements["reference_values"], *requirements["requirements"])],',
     '"scenarios": [entry["scenario"] for entry in requirements["requirements"]],'),
    ("move-derivation-any-scenario", MA, '            if needed and reference["scenario"]["name"] != needed:', '            if False:'),
    ("extraction-schema-not-checked", MA, '        return {EXTRACTION: "cad-dataset/v1/cad-extraction"}', '        return {}'),
    ("rated-move-parameters-optional", "schemas/engineering-model/v1/mechanical-vocabulary.schema.json", '"then": {"required": ["start_rad", "end_rad", "duration_s"]}', '"then": {}'),
    ("free-swing-amplitude-optional", "schemas/engineering-model/v1/mechanical-vocabulary.schema.json", '"then": {"required": ["amplitude_rad"]}', '"then": {}'),
    # Foundation review: what the compiler refuses
    ("reference-unit-unchecked", R, '        _check_unit(reference["reference_id"], reference["metric"], reference["unit"], metrics)', '        pass'),
    ("duplicate-ids-allowed", R, '    if duplicated:\n', '    if False:\n'),
    ("vector-limit-accepted", R, '            if not isinstance(bound, (int, float)) or isinstance(bound, bool):', '            if False:'),
    ("foreign-reference-compiled", D,
     'foreign = sorted({entry["domain"] for entry in (*requirements["reference_values"], *requirements["requirements"])}',
     'foreign = sorted({entry["domain"] for entry in requirements["requirements"]}'),
    # Foundation review: a receipt is always written, and says what ran
    ("item-error-crashes-validate", D, '        except (OSError, ValueError, KeyError, IndexError, TypeError, ArithmeticError) as exc:',
     '        except (OSError, ValueError) as exc:'),
    ("requirements-unreadable-crash", D, '    except (OSError, ValueError) as exc:\n        requirements_problem = f"{REQUIREMENTS}: {exc}"',
     '    except ZeroDivisionError as exc:\n        requirements_problem = f"{REQUIREMENTS}: {exc}"'),
    ("cases-run-without-derivation", D, '    if fresh is None or requirements_problem is not None:', '    if requirements_problem is not None:'),
    ("stale-case-document-run", D, '    if relative in fresh.files:\n        try:\n            ran = execute_cases(item.root, level, name)',
     '    if True:\n        try:\n            ran = execute_cases(item.root, level, name)'),
    ("stale-case-document-kept", D, '            item.path(relative).unlink()', '            pass'),
    ("stale-case-document-unreported", D,
     '            problems.append(f"{relative}: committed, but a fresh derivation compiles no such document")', '            pass'),
    ("exact-comparator-ignored", D, '        return [] if committed == fresh.data else [f"{relative}: bytes differ from a fresh derivation"]',
     '        return []'),
    # Foundation review: results are the run's, from its receipt and evidence
    ("results-decided-by-nothing", RS,
     '            check_id = own if own in checks else next((c for c in stand_ins if c in checks), None)', '            check_id = own'),
    ("sibling-arguments-ignored", RS, '                            and other_case.get("arguments") == arguments):', '                            ):'),
    ("borrowed-for-any-verdict", RS, 'if measured is None and gate == "V4" and check.get("verdict") == "BLOCKED" and null_limit:',
     'if measured is None:'),
    ("non-number-measured", RS, '            measured = _number((check.get("metrics") or {}).get(metric))',
     '            measured = (check.get("metrics") or {}).get(metric)'),
    ("scenario-inputs-include-identifiers", RS,
     'if key != "name" and isinstance(scenario[key], (int, float)) and not isinstance(scenario[key], bool)]', 'if key != "name"]'),
    ("scenario-inputs-dropped", RS, '"inputs": inputs + _scenario_inputs(label, entry["scenario"]),', '"inputs": inputs,'),
    ("illustrative-label-dropped", RS, '                kind = "illustrative requirement" if entry["illustrative"] else "requirement"',
     '                kind = "illustrative requirement"'),
    ("result-illustrative-flag-dropped", RS, '                illustrative, component = entry["illustrative"], entry["component"]',
     '                illustrative, component = False, entry["component"]'),
    ("v3-bound-as-min-max", RS,
     'bound = {"value": expected["value"], "absolute_tolerance": expected["absolute_tolerance"]} if expected else None',
     'bound = {"minimum": expected["value"], "maximum": expected["value"]} if expected else None'),
    ("expected-value-dropped", RS, '                    expected_value = limit["value"]', '                    expected_value = None'),
    ("applied-bound-dropped", RS, '                bound = (case.get("metric_limits") or {}).get(metric) if case else None', '                bound = None'),
    ("seed-dropped", RS, '"seed": case.get("seed") if case else None}', '"seed": None}'),
    ("environment-tools-empty", RS, '            "tools": {tool["tool_id"]: tool["version"] for tool in tools}}', '            "tools": {}}'),
    ("constraints-digest-dropped", RS,
     '"constraints_sha256": hashlib.sha256(constraints).hexdigest() if constraints is not None else None,', '"constraints_sha256": None,'),
    ("environment-from-this-process", D, 'executions=executions, environment_record=environment(recorded, receipt["tools"]),',
     'executions=executions, environment_record={**run_environment(None), "tools": {}},'),
    ("regenerate-ignores-item-changes", D, '    if hash_tree(item.root, files) != receipt["source"]["input_sha256"]:', '    if False:'),
    ("evidence-digest-unchecked", D, '    if _sha256(data) != reference["sha256"]:\n        raise ValueError(f"evidence {expected}',
     '    if False:\n        raise ValueError(f"evidence {expected}'),
    ("evidence-path-trusted", D, '    if reference["path"] != expected:', '    if False:'),
    ("receipt-not-schema-checked", D,
     '    try:\n        validate_document(REPOSITORY_ROOT, "validation-receipt.schema.json", receipt)\n    except RecursionError:',
     '    try:\n        pass\n    except RecursionError:'),
    ("receipt-for-another-item", D, '    if receipt["product"]["id"] != f"datasets:{item.item_id}":', '    if False:'),
    ("execution-record-of-another-check", D,
     'elif record.get("case_id") == check["check_id"].split(".", 1)[1] and "tool_version" in record:',
     'elif "case_id" in record and "tool_version" in record:'),
    ("results-pass-without-version", "schemas/engineering-model/v1/validation-results.schema.json", '"then": {"properties": {"simulator_version": {"$ref": "common.schema.json#/definitions/nonEmptyString"}}}',
     '"then": {}'),
    ("results-reference-any-operator", "schemas/engineering-model/v1/validation-results.schema.json", '"then": {"properties": {"operator": {"const": "within"}}}', '"then": {}'),
    ("results-kind-disagrees", "schemas/engineering-model/v1/validation-results.schema.json", ',\n          "else": {"properties": {"illustrative": {"const": false}}}', ''),
    ("results-illustrative-pass", "schemas/engineering-model/v1/validation-results.schema.json", '"then": {"properties": {"status": {"not": {"const": "PASS"}}}}', '"then": {}'),
    ("results-pass-unmeasured", "schemas/engineering-model/v1/validation-results.schema.json", '"then": {"properties": {"measured_value": {"type": "number"}}}', '"then": {}'),
    ("results-null-input-not-blocked", "schemas/engineering-model/v1/validation-results.schema.json", '"then": {"properties": {"status": {"const": "BLOCKED"}}}', '"then": {}'),
    ("results-assumption-passes", "schemas/engineering-model/v1/validation-results.schema.json", '"status": {"not": {"enum": ["PASS", "WARNING"]}},', '"status": {},'),
    ("results-comparator-reason-on-assumption", "schemas/engineering-model/v1/validation-results.schema.json",
     '"reason_code": {"not": {"enum": ["CORNER_LIMITS_PASSED", "CORNER_LIMITS_FAILED", "WITHIN_ILLUSTRATIVE_LIMIT"]}}', '"reason_code": {}'),
    # Foundation review: domain status, provenance, metadata, untrusted items
    ("secondary-domain-available", DR, '        if adapter is not None and domain == primary and adapter.formats & formats:',
     '        if adapter is not None and adapter.formats & formats:'),
    ("manifest-domain-hard-coded", D, '        "domain": item.domain,\n', '        "domain": "mechanical",\n'),
    ("source-url-dropped", D, '        "source_url": provenance["origin"].get("url"),', '        "source_url": None,'),
    ("model-lineage-omits-artefacts", D,
     '        derived_from=(*([derived.path for derived in extraction.files]\n'
     '                        or [source.path for source in item.sources if source.format in adapter.formats]),',
     '        derived_from=(*[derived.path for derived in extraction.files],'),
    ("undeclared-source-format-allowed", D, '        elif (item.item_relative(path), source["format"]) not in declared:', '        elif False:'),
    ("declared-source-missing-unnamed", D, '            if not os.path.lexists(self.root / relative):', '            if False:'),
    ("unlisted-sources-skipped", D, '        if unlisted:\n', '        if False:\n'),
    ("item-root-symlink-followed", D, '        if Path(directory).is_symlink():', '        if False:'),
    ("item-outside-repository-read", D, '        if not self.root.is_relative_to(REPOSITORY_ROOT):', '        if False:'),
    ("manifest-path-outside-item-read", D,
     '        if relative.is_absolute() or ".." in relative.parts or not path.resolve().is_relative_to(item.root):', '        if False:'),
    ("source-url-null-for-third-party", "schemas/cad-dataset/v1/dataset-item.schema.json", '"const": "self_authored"', '"enum": ["self_authored", "third_party"]'),
    ("manifest-unverified-permits-use", "schemas/cad-dataset/v1/dataset-item.schema.json",
     '"then": {"properties": {"license": {"properties": {"redistribution_permitted": {"const": false}, "training_use_permitted": {"const": false}}}}}',
     '"then": {}'),
    ("manifest-verified-uncited", "schemas/cad-dataset/v1/dataset-item.schema.json",
     '"description": "A verified licence cites the text that was read.",\n          "if": {"properties": {"license": {"properties": {"license_verified": {"const": true}}}}},\n          "then": {"properties": {"license": {"required": ["license_text"]}}}',
     '"description": "A verified licence cites the text that was read.",\n          "if": {"properties": {"license": {"properties": {"license_verified": {"const": true}}}}},\n          "then": {}'),
    ("manifest-third-party-verifier-optional", "schemas/cad-dataset/v1/dataset-item.schema.json",
     '"then": {"properties": {"license": {"required": ["license_text", "verified_by", "verified_at"]}}}', '"then": {}'),
    ("manifest-modifications-optional", "schemas/cad-dataset/v1/dataset-item.schema.json", '                  "url",\n                  "modifications"\n', '                  "url"\n'),
    ("provenance-verified-at-optional", "schemas/cad-dataset/v1/source-provenance.schema.json",
     '"then": {"properties": {"license": {"required": ["license_text", "verified_by", "verified_at"]}}}',
     '"then": {"properties": {"license": {"required": ["license_text", "verified_by"]}}}'),
    ("provenance-third-party-uncited", "schemas/cad-dataset/v1/source-provenance.schema.json",
     '"if": {"properties": {"origin": {"properties": {"kind": {"const": "third_party"}}}}},\n      "then": {"properties": {"license": {"required": ["license_text"]}}}',
     '"if": {"properties": {"origin": {"properties": {"kind": {"const": "third_party"}}}}},\n      "then": {}'),
    # Foundation review: each per-status rule of the schema, on its own
    ("schema-unknown-may-carry-value", "schemas/engineering-model/v1/common.schema.json",
     '"if": {"properties": {"status": {"enum": ["UNKNOWN", "UNSPECIFIED", "NOT_AVAILABLE"]}}},\n          "then": {"properties": {"value": {"type": "null"}}}',
     '"if": {"properties": {"status": {"enum": ["UNSPECIFIED", "NOT_AVAILABLE"]}}},\n          "then": {"properties": {"value": {"type": "null"}}}'),
    ("schema-note-optional", "schemas/engineering-model/v1/common.schema.json", '"then": {"required": ["note"]}', '"then": {}'),
    ("schema-unspecified-cites-nothing", "schemas/engineering-model/v1/common.schema.json", '"then": {"properties": {"source": {"required": ["sha256"]}}}', '"then": {}'),
    ("schema-measured-any-source", "schemas/engineering-model/v1/common.schema.json", '"then": {"properties": {"source": {"properties": {"kind": {"const": "measurement"}}}}}', '"then": {}'),
    ("schema-simulated-any-source", "schemas/engineering-model/v1/common.schema.json", '"then": {"properties": {"source": {"properties": {"kind": {"const": "simulation"}}}}}', '"then": {}'),
    ("schema-assumption-any-source", "schemas/engineering-model/v1/common.schema.json", '"then": {"properties": {"source": {"properties": {"kind": {"const": "ai"}}}}}', '"then": {}'),
    ("schema-derived-without-inputs", "schemas/engineering-model/v1/common.schema.json", '"required": ["derived_from"],\n            "properties": {"derived_from": {"minItems": 1}}',
     '"properties": {}'),
    ("unknown-comparator-accepted", "tools/ecad_model/domains/base.py", '        if self.comparator not in COMPARATORS:', '        if False:'),
    ("unknown-fidelity-accepted", "tools/ecad_model/domains/base.py", '        if self.fidelity not in FIDELITIES:', '        if False:'),
    # Second review of the foundation: a receipt whatever the committed files say
    ("stale-committed-case-counted", D, '                  if check.check_id.split(".", 1)[1] in compiled - set(differs)\n',
     '                  if True\n'),
    ("stale-case-unnoted", D, '    stale = set(committed_cases) & set(blocked)', '    stale = set()'),
    ("committed-case-missing-unreported", D, '    for entry_id in sorted(compiled - counted):', '    for entry_id in []:'),
    ("uncited-engine-failure-kept", D, '            if not check.evidence and check.verdict is not Verdict.BLOCKED:', '            if False:'),
    ("v3-inputs-ignored", D, '                elif level is GateLevel.V3 and case_id in by_reference:', '                elif False:'),
    ("committed-model-schema-unchecked", D,
     '        model = _json(item.read(MODEL))\n        validate_schema(model, "engineering-model/v1/engineering-model")',
     '        model = _json(item.read(MODEL))'),
    ("reproducibility-parse-crash", D, '    except (ValueError, RecursionError) as exc:  # JSONDecodeError and UnicodeDecodeError are ValueErrors',
     '    except ZeroDivisionError as exc:'),
    ("manifest-shape-crash", D, '    except (KeyError, TypeError, AttributeError, RecursionError) as exc:\n        return [f"{MANIFEST}: does not have the shape',
     '    except ZeroDivisionError as exc:\n        return [f"{MANIFEST}: does not have the shape'),
    ("results-before-receipt", D,
     '    (output / "receipt.json").write_bytes(receipt_bytes)\n    (output / "evidence-index.json").write_bytes(canonical(evidence_index))\n    document: Optional[Dict[str, Any]] = None',
     '    document: Optional[Dict[str, Any]] = None'),
    ("regenerate-no-results-unchecked", D, '    if why is not None:\n        raise ValueError(f"the run wrote no results to regenerate',
     '    if False:\n        raise ValueError(f"the run wrote no results to regenerate'),
    ("environment-shape-unchecked", D,
     '        raise ValueError("the run\'s environment record is malformed")', '        pass'),
    ("lineage-fallback-all-sources", D, '                        or [source.path for source in item.sources if source.format in adapter.formats]),',
     '                        or [source.path for source in item.sources]),'),
    ("results-inputs-unguarded", RS, '            except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:\n                inputs, unresolved, cad_components = [], [], []',
     '            except ZeroDivisionError as exc:\n                inputs, unresolved, cad_components = [], [], []'),
    ("unknown-metric-fidelity-crashes", RS, '"model_fidelity": metrics[metric].fidelity if metric in metrics else None,',
     '"model_fidelity": metrics[metric].fidelity,'),
    ("result-operator-fixed", RS, '                operator, tolerance = entry["operator"], entry.get("tolerance", 0.0)',
     '                operator, tolerance = "<=", entry.get("tolerance", 0.0)'),
    ("result-tolerance-dropped", RS, '                operator, tolerance = entry["operator"], entry.get("tolerance", 0.0)',
     '                operator, tolerance = entry["operator"], 0.0'),
    ("manifest-third-party-uncited", "schemas/cad-dataset/v1/dataset-item.schema.json",
     '"description": "The licence rules of source-provenance, restated so the manifest is checkable on its own: a third-party artefact cites its licence text.",\n          "if": {"properties": {"origin": {"properties": {"kind": {"const": "third_party"}}}}},\n          "then": {"properties": {"license": {"required": ["license_text"]}}}',
     '"description": "The licence rules of source-provenance, restated so the manifest is checkable on its own: a third-party artefact cites its licence text.",\n          "if": {"properties": {"origin": {"properties": {"kind": {"const": "third_party"}}}}},\n          "then": {}'),
    # Third review of the foundation: a committed case counts only as compiled
    ("content-stale-case-counted", D, '    differs = {entry_id: problems for entry_id, problems in differs.items() if problems}', '    differs = {}'),
    ("engine-error-crashes", D, '        except (OSError, ValueError, RecursionError) as exc:\n            # The case engine is merged code',
     '        except ZeroDivisionError as exc:\n            # The case engine is merged code'),
    ("engine-recursion-crashes", D, '        except (OSError, ValueError, RecursionError) as exc:\n            # The case engine is merged code',
     '        except (OSError, ValueError) as exc:\n            # The case engine is merged code'),
    ("fresh-statuses-ignored", D, '            for model in (committed_model, fresh.model):', '            for model in (committed_model,):'),
    ("results-cases-schema-unchecked", D, '                        validate_schema(record, "hardware-validation/v1/validation-cases")',
     '                        pass'),
    ("case-without-execution-used", RS,
     '                    if check_id == own and (own in executions or check.get("reason_code") not in NOT_RUN_REASONS)',
     '                    if True'),
    ("crashed-case-bound-dropped", RS,
     '                    if check_id == own and (own in executions or check.get("reason_code") not in NOT_RUN_REASONS)',
     '                    if check_id == own and own in executions'),
    ("null-limit-from-findings-ignored", RS, '                or any(finding.split(": ", 1) == [status, limit["quantity"]]',
     '                or False and any(finding.split(": ", 1) == [status, limit["quantity"]]'),
    ("reserved-ids-allowed", R, '    if reserved:\n', '    if False:\n'),
    ("results-failure-exit-code", "tools/ecad_model/cli.py", '        print(f"error: {exc}; see {output / \'report.md\'}", file=sys.stderr)\n        return 3',
     '        print(f"error: {exc}; see {output / \'report.md\'}", file=sys.stderr)\n        return 1'),
    ("regenerate-unlisted-model", D, '    if unlisted:\n        # Only the files git lists', '    if False:\n        # Only the files git lists'),
    ("deep-json-crashes", "tools/ecad_model/schemas.py", '    except RecursionError:\n        # A document nested deeper',
     '    except ZeroDivisionError:\n        # A document nested deeper'),
    # Fourth review: a case's derived inputs, the engine's failures, non-finite numbers
    ("input-staleness-ignored", D, '                if input_divergence[input_path]:', '                if False:'),
    ("engine-error-marked-blocked", D, '            status, verdict = ExecutionStatus.CRASHED, Verdict.INCONCLUSIVE',
     '            status, verdict = ExecutionStatus.UNAVAILABLE, Verdict.BLOCKED'),
    ("gate-level-id-counted", D, '                  or (check.check_id.split(".", 1)[1] in gate_level_ids and _engine_gate_level(check.reason_code))]',
     '                  or check.check_id.split(".", 1)[1] in gate_level_ids]'),
    ("refusal-unlabelled", D, '        elif refusal is not None and entry_id in committed_cases:', '        elif False:'),
    ("inputs-not-recorded", D, '            if found or unresolved:\n                # What the verdict rests on',
     '            if False:\n                # What the verdict rests on'),
    ("recorded-inputs-ignored", RS, '                if recorded is not None:\n                    inputs, unresolved = recorded',
     '                if False:\n                    inputs, unresolved = recorded'),
    ("infinite-constants-accepted", D, '        return json.loads(data, parse_constant=_refuse_constant)', '        return json.loads(data)'),
    ("infinity-equals-anything", D, '    if not (math.isfinite(a) and math.isfinite(b) and math.isfinite(scale)):\n        return a == b',
     '    if False:\n        return a == b'),
    ("manifest-deep-crash", D, '    except RecursionError:\n        return [f"{MANIFEST}: nested too deeply to compare',
     '    except ZeroDivisionError:\n        return [f"{MANIFEST}: nested too deeply to compare'),
    ("regenerate-deep-receipt", D, '    except RecursionError:\n        raise ValueError("receipt.json is nested too deeply',
     '    except ZeroDivisionError:\n        raise ValueError("receipt.json is nested too deeply'),
    ("manifest-verified-at-optional", "schemas/cad-dataset/v1/dataset-item.schema.json",
     '"then": {"properties": {"license": {"required": ["license_text", "verified_by", "verified_at"]}}}',
     '"then": {"properties": {"license": {"required": ["license_text", "verified_by"]}}}'),
    # spice: the netlist grammar refuses what ngspice would reinterpret
    ("spice-control-accepted", SP, '            if keyword != ".model":\n',
     '            if keyword in (".control", ".endc"):\n                continue\n            if keyword != ".model":\n'),
    ("spice-include-accepted", SP, '            if keyword != ".model":\n',
     '            if keyword in (".include", ".lib"):\n                continue\n            if keyword != ".model":\n'),
    ("spice-milli-read-as-micro", SP, '"m": -3,', '"m": -6,'),
    ("spice-number-case-folded", SP, "    match = _NUMBER.fullmatch(token)\n", "    match = _NUMBER.fullmatch(token.lower())\n"),
    ("spice-unit-letters-ignored", SP, '+ "))?")', '+ "))?[A-Za-z]*")'),
    ("spice-femto-accepted", SP, '"n": -9, "p": -12}', '"n": -9, "p": -12, "f": -15}'),
    ("spice-gnd-accepted", SP, '    if node == "gnd":\n', "    if False:\n"),
    ("spice-par-node-accepted", SP, "    if _PAR_NODE.fullmatch(node):\n", "    if False:\n"),
    ("spice-after-end-ignored", SP, '            if text:\n                raise NetlistRefused(f"{where}: text after .end',
     '            if False:\n                raise NetlistRefused(f"{where}: text after .end'),
    ("spice-end-optional", SP, '    if not ended:\n        raise NetlistRefused(f"{path}: no .end line',
     '    if False:\n        raise NetlistRefused(f"{path}: no .end line'),
    ("spice-title-card-accepted", SP, "    problem = _title_problem(lines[0])\n", "    problem = None\n"),
    ("spice-continuation-accepted", SP,
     '        if text.startswith("+"):\n            raise NetlistRefused(f"{where}: a \'+\' continuation, which joins this line to the one before it")\n',
     '        if text.startswith("+"):\n            continue\n'),
    ("spice-dangling-node-allowed", SP, '        if node != "0" and len(terminals) < 2:\n', "        if False:\n"),
    ("spice-dc-path-unchecked", SP, "    unreached = [node for node in first_line if node not in reached]\n",
     "    unreached = []\n"),
    ("spice-duplicate-designator-accepted", SP, "        if designator in designators:\n", "        if False:\n"),
    ("spice-switch-defaults-allowed", SP, "    missing = [key for key in _SWITCH_KEYS if key not in params]\n",
     '    missing = [key for key in ("RON", "ROFF") if key not in params]\n'),
    ("spice-pwl-order-unchecked", SP, "    if any(later <= earlier for earlier, later in zip(times, times[1:])):\n",
     "    if False:\n"),
    ("spice-writer-rounds-values", SP, "    return repr(float(value))\n", '    return f"{value:.6g}"\n'),
    # electrical: the network class, the closed forms, the deck, V1 and V2
    ("el-extra-element-accepted", EL, '    if extra:\n        raise refuse("C8"', '    if False:\n        raise refuse("C8"'),
    ("el-capacitor-anywhere", EL, 'capacitors = [c for c in of("capacitor") if rail in _main(c)]', 'capacitors = of("capacitor")'),
    ("el-esr-left-out-of-references", EL, "tau1 = (alpha * r_s + r_e) * c", "tau1 = alpha * r_s * c"),
    ("el-ramp-read-as-step", EL, "peak = g * supply_voltage + b", "peak = supply_voltage / (r_s + r_e)"),
    ("el-charge-level-changed", EL, "CHARGED_FRACTION = 0.9  #", "CHARGED_FRACTION = 1 - 1 / math.e  #"),
    ("el-supply-current-sign-flipped", EL, "current = f\"par('-i({supply})')\"", "current = f\"par('i({supply})')\""),
    ("el-fault-measured-at-the-fault", EL, '"fault_input_current_a": f"FIND {current} AT={_n(t_end)}",',
     '"fault_input_current_a": f"FIND {current} AT={_n(t_flt)}",'),
    ("el-steady-sampled-after-the-fault", EL, '"steady_bus_voltage_v": f"FIND {rail} AT={_n(t_flt)}",',
     '"steady_bus_voltage_v": f"FIND {rail} AT={_n(t_end)}",'),
    ("el-settling-unchecked", EL, "    return span >= SETTLE_TIME_CONSTANTS * tau\n", "    return True\n"),
    ("el-scenario-pairing-unchecked", EL, 'if window is not None and entry["scenario"]["name"] != window:', "if False:"),
    ("el-derivation-pairing-unchecked", EL, 'if DERIVATION_METRIC[reference["derivation"]] != reference["metric"]:', "if False:"),
    ("el-metric-unit-wrong", EL, '"inrush_peak_current_a": Metric("A", ', '"inrush_peak_current_a": Metric("mA", '),
    ("el-facet-unit-unchecked", EL, '                elif facet["unit"] != unit:\n', "                elif False:\n"),
    ("el-supply-sheet-invariant-off", EL, '            if final != stated["value"]:\n', "            if False:\n"),
    ("el-netlist-hash-not-bound", EL, 'netlist_source = source("design_annotation", netlist_ref, netlist_sha256)',
     'netlist_source = source("design_annotation", netlist_ref)'),
    ("el-annotation-overrides-netlist", EL, "        if twice:\n            raise ValueError(", "        if False:\n            raise ValueError("),
    ("el-ratings-dropped", EL, 'domains["electrical"] = {**stated, **added}', 'domains["electrical"] = dict(stated)'),
    # electrical: the branches a line-coverage run found no test going through
    ("el-capacitor-to-ground-refused", EL, '    if far != "0":\n', "    if True:\n"),
    ("el-no-esr-read-as-50-milliohm", EL, 'r_e = values.get(("esr", "resistance"), 0.0)',
     'r_e = values.get(("esr", "resistance"), 0.05)'),
    ("el-absent-esr-dereferenced", EL, "        if component is None:\n            continue\n", ""),
    ("el-spice-source-count-unchecked", EL, "        if len(netlists) != 1:\n", "        if False:\n"),
    ("el-null-supply-voltage-compared", EL, 'if (stated is None or is_null(stated["status"]) or supply is None',
     "if (stated is None or supply is None"),
    ("spice-source-fields-unchecked", SP, "        if len(parts) != 4:\n", "        if False:\n"),
    ("spice-model-card-name-unchecked", SP, "    if not _MODEL_NAME.fullmatch(name):\n", "    if False:\n"),
    # electrical: the sample's own files (each rebuilt, so a behavioural test must kill it)
    ("el-precharge-resistor-changed", EN, "R_PRE n_f n_bus 10\n", "R_PRE n_f n_bus 1\n"),
    ("el-capacitance-plus-one-percent", EN, "C_BULK n_bus n_esr 470u", "C_BULK n_bus n_esr 474.7u"),
    # REQ-EL-001's limit; REQ-EL-008 states 10 A too
    ("el-inrush-limit-changed", ER, '"metric": "inrush_peak_current_a",\n      "scenario": {\n        "name": "startup"\n      },\n      "operator": "<=",\n'
     '      "limit": {\n        "value": 10.0',
     '"metric": "inrush_peak_current_a",\n      "scenario": {\n        "name": "startup"\n      },\n      "operator": "<=",\n'
     '      "limit": {\n        "value": 4.0'),
    ("el-illustrative-flag-cleared", ER,
     '"metric": "inrush_peak_current_a",\n      "scenario": {\n        "name": "startup"\n      },\n      "operator": "<=",\n'
     '      "limit": {\n        "value": 10.0\n      },\n      "unit": "A",\n      "source": {\n        "kind": "requirement",\n        "ref": "example requirement '
     'for the servo_supply_001 MVP, chosen to exercise the pipeline; not a customer, safety or certification requirement"\n'
     '      },\n      "illustrative": true',
     '"metric": "inrush_peak_current_a",\n      "scenario": {\n        "name": "startup"\n      },\n      "operator": "<=",\n'
     '      "limit": {\n        "value": 10.0\n      },\n      "unit": "A",\n      "source": {\n        "kind": "requirement",\n        "ref": "example requirement '
     'for the servo_supply_001 MVP, chosen to exercise the pipeline; not a customer, safety or certification requirement"\n'
     '      },\n      "illustrative": false'),
    ("el-operator-flipped", ER, '"operator": ">=",\n      "limit": {\n        "value": 47.0',
     '"operator": "<=",\n      "limit": {\n        "value": 47.0'),
    ("el-rating-invented", EA, '"value": null,\n            "unit": "V",\n            "status": "UNKNOWN"',
     '"value": 63.0,\n            "unit": "V",\n            "status": "SPECIFIED"'),
    ("el-sheet-digest-changed", EA,
     '"value": 5.0,\n            "unit": "A",\n            "status": "SPECIFIED",\n            "source": {\n'
     '              "kind": "product_specification",\n              "ref": "eRobotics_CAD_Design/robot_components/product_datasheet.md",\n'
     '              "sha256": "f6e4502a3a93112aab7fcd91c9c9242c1227cde8d21c6614dabbab2291094f8c"',
     '"value": 5.0,\n            "unit": "A",\n            "status": "SPECIFIED",\n            "source": {\n'
     '              "kind": "product_specification",\n              "ref": "eRobotics_CAD_Design/robot_components/product_datasheet.md",\n'
     '              "sha256": "2779b5d4987171210e3c18f461e4ee832426c3c52ca3e53a7dce23af057c4c0a"'),
    ("el-artifact-type-changed", EP, '"artifact_type": "spice_netlist"', '"artifact_type": "other"'),
    # electrical: the format rule and the registry
    ("circuit-format-rule-dropped", MS, '"then": {"properties": {"model_version": {"const": "1.1.0"}}}', '"then": {}'),
    ("electrical-unregistered", DR, '"electrical": ElectricalAdapter(),', ""),
    # ngspice: batch invocation, .meas capture from stdout, version banner, receipt-safe probe reasons
    ("ngspice-rawfile-requested", NG, 'argv=[capability.executable or "ngspice", "-b", relative],',
     'argv=[capability.executable or "ngspice", "-b", "-r", "ngspice.raw", relative],'),
    ("ngspice-log-requested", NG, 'argv=[capability.executable or "ngspice", "-b", relative],',
     'argv=[capability.executable or "ngspice", "-b", "-o", "ngspice.log", relative],'),
    ("ngspice-arguments-passed", NG, 'argv=[capability.executable or "ngspice", "-b", relative],',
     'argv=[capability.executable or "ngspice", "-b", relative, *request.arguments],'),
    ("ngspice-suffix-refused", NG, r'(\S+)(?:[ \t]+(?:at|from|to)=[ \t]*\S+)*[ \t]*$")', r'(\S+)[ \t]*$")'),
    ("ngspice-duplicate-kept", NG, "reported.setdefault(found.group(1), []).append(found.group(2))",
     "reported[found.group(1)] = [found.group(2)]"),
    ("ngspice-non-finite-kept", NG, "        elif not math.isfinite(float(values[0])):\n", "        elif False:\n"),
    ("ngspice-python-number-spellings", NG, "        elif not NUMBER.match(values[0]):\n", "        elif False:\n"),
    ("ngspice-failed-read-as-zero", NG, '            problems[name] = f"failed: {failed[name]}"', "            metrics[name] = 0.0"),
    ("ngspice-undeclared-names-read", NG, "    for name in declared:\n", "    for name in [*declared, *reported]:\n"),
    ("ngspice-truncation-ignored", NG, "            if process.stdout.endswith(TRUNCATED):", "            if False:"),
    ("ngspice-parsed-on-failure", NG, "        if verdict is Verdict.PASS:\n",
     "        if process.execution_status is ExecutionStatus.COMPLETED:\n"),
    ("ngspice-oversize-deck-read", NG, "        if netlist.stat().st_size > MAX_DECK_BYTES:", "        if False:"),
    ("ngspice-reason-unsanitised", NG, "    if RECEIPT_CODE.match(reason):\n", "    if True:\n"),
    ("ngspice-version-first-line", CP, r'= {"ngspice": re.compile(r"\bngspice-([0-9][0-9A-Za-z.+~-]*)")}', "= {}"),
    ("ngspice-version-invented", CP, "    return match.group(1) if match else None\n",
     '    return match.group(1) if match else "unknown"\n'),
    ("ngspice-version-minor-dropped", CP, r'= {"ngspice": re.compile(r"\bngspice-([0-9][0-9A-Za-z.+~-]*)")}',
     r'= {"ngspice": re.compile(r"\bngspice-([0-9]+)")}'),
    ("probe-pattern-for-every-tool", CP, "    pattern = VERSION_PATTERNS.get(adapter)\n",
     '    pattern = VERSION_PATTERNS.get("ngspice")\n'),
    # the domain adapter names its model's producer
    ("model-producer-hard-coded", D, "producer=extraction.producer[0], version=extraction.producer[1],",
     'producer="ecad_model.builder", version="1.0.0",'),
    # the review of the electrical branch: names ngspice reads as its own (CS-1)
    ("spice-node-prefix-dropped", SP, '_NODE = re.compile(r"0|n_[a-z0-9_]{1,30}")',
     '_NODE = re.compile(r"0|[a-z][a-z0-9_]{0,31}")'),
    ("spice-model-prefix-dropped", SP, '_MODEL_NAME = re.compile(r"SW_[A-Z0-9_]{1,29}")',
     '_MODEL_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,31}")'),
    ("schema-node-prefix-dropped", MS, '"pattern": "^(0|n_[a-z0-9_]{1,30})$"',
     '"pattern": "^(0|(?!gnd$)(?!pa_[0-9]+$)[a-z][a-z0-9_]{0,31})$"'),
    ("schema-model-prefix-dropped", MS, '"pattern": "^SW_[A-Z0-9_]{1,29}$"', '"pattern": "^[A-Z][A-Z0-9_]{0,31}$"'),
    # the review of the electrical branch: a fault the window cannot measure (CS-2)
    ("el-fault-window-unchecked", EL, "    if not _settled(t_end - closes, tau_f):\n", "    if False:\n"),
    ("el-fault-that-never-closes-accepted", EL, "    if not levels[2] > threshold + hysteresis:\n        return",
     "    if False:\n        return"),
    ("el-fault-hysteresis-ignored-at-extraction", EL, "    closes = _closing_time(times, levels, threshold, hysteresis)\n",
     "    closes = _closing_time(times, levels, threshold, 0.0)\n"),
    # values the closed forms divide by, and errors that cost a receipt (CS-3)
    ("el-nonpositive-value-accepted", EL, "            if value is not None and not value > 0:\n", "            if False:\n"),
    ("el-ramp-after-bypass-accepted", EL, "    if not t_r < t_b:\n        return", "    if False:\n        return"),
    ("el-arithmetic-error-raised", EL, "    except ArithmeticError as exc:\n", "    except LookupError as exc:\n"),
    ("el-non-finite-reference-kept", EL, "    if not math.isfinite(value):\n        raise ReferenceBlocked",
     "    if False:\n        raise ReferenceBlocked"),
    ("runner-arithmetic-error-crashes", D,
     '        except (OSError, ValueError, KeyError, IndexError, TypeError, ArithmeticError) as exc:',
     '        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:'),
    # the open fault switch in the precharge forms (CS-4)
    ("el-precharge-fault-divider-ignored", EL, "alpha = r_off_f / (r_s + r_off_f)", "alpha = 1.0"),
    ("el-precharge-fault-current-ignored", EL, "g = 1 / (r_s + r_off_f)  #", "g = 0.0  #"),
    # the startup peak and its closed form (CS-5)
    ("el-startup-window-ends-at-bypass", EL, '"startup_peak_current_a": f"MAX {current} FROM=0.0 TO={_n(t_flt)}",',
     '"startup_peak_current_a": f"MAX {current} FROM=0.0 TO={_n(t_byp)}",'),
    ("el-startup-surge-ignored", EL, "            if surge >= max(peak, i_ss):\n", "            if False:\n"),
    ("el-startup-load-ignored", EL, "            return max(peak, i_ss)\n", "            return peak\n"),
    ("el-startup-surge-without-esr", EL, "            rail = (supply_voltage * r_e * r_off_f + v_c * r_c * r_off_f)",
     "            rail = v_c + 0 * (supply_voltage * r_e * r_off_f + v_c * r_c * r_off_f)"),
    ("el-startup-limit-changed", ER, '"metric": "startup_peak_current_a",\n      "scenario": {\n        "name": "startup"\n      },\n'
     '      "operator": "<=",\n      "limit": {\n        "value": 10.0',
     '"metric": "startup_peak_current_a",\n      "scenario": {\n        "name": "startup"\n      },\n'
     '      "operator": "<=",\n      "limit": {\n        "value": 100.0'),
    # conditions of rules C1, C3, C4 and C7 no test reached (HT-3)
    ("el-ramp-zero-level", EL, "and points[1][0] > 0 and points[1][1] > 0", "and points[1][0] > 0 and points[1][1] >= 0"),
    ("el-command-node-shared", EL, ' or len(at[control["cp"]]) != 2', ""),
    ("el-command-cn-ground", EL, 'if (control["cn"] != "0" or control["cp"] == "0"', 'if (control["cp"] == "0"'),
    ("el-bypass-other-end", EL, " or _other(bypasses[0], junction) != _other(limiters[0], junction)", ""),
    # branches no test reached (HT-5)
    ("ng-summary-cap", NG, "list(problems.items())[:MAX_SUMMARY_PROBLEMS])", "list(problems.items()))"),
    ("el-invariant-ref-unchecked", EL, ' or facet["source"]["ref"] != netlist["path"])', ")"),
    ("el-powered-by-any-element", EL, '\n                    or supply.get("circuit", {}).get("element") != "voltage_source"):', "):"),
    ("el-closes-hysteresis-bypass", EL,
     'values[("bypass_command", "waveform_voltage")],\n                               values[("bypass", "threshold_voltage")], '
     'values[("bypass", "hysteresis_voltage")])',
     'values[("bypass_command", "waveform_voltage")],\n                               values[("bypass", "threshold_voltage")], 0.0)'),
    ("el-closes-hysteresis-startup", EL,
     '\n                                   values[("bypass", "threshold_voltage")], values[("bypass", "hysteresis_voltage")])',
     '\n                                   values[("bypass", "threshold_voltage")], 0.0)'),
    ("el-closes-hysteresis-fault", EL, 'values[("fault", "threshold_voltage")], values[("fault", "hysteresis_voltage")])',
     'values[("fault", "threshold_voltage")], 0.0)'),
    ("el-closing-time-ignores-hysteresis", EL, "(times[2] - times[1]) * (threshold + hysteresis) / levels[2]",
     "(times[2] - times[1]) * threshold / levels[2]"),
    # run_process: declared outputs copied out before the workspace is deleted; an empty stdin on request
    ("process-collect-skipped", PR, "    for name in names:\n", "    for name in ():\n"),
    ("process-collect-follows-symlink", PR, "            status = candidate.lstat()\n",
     "            status = candidate.stat()\n"),
    ("process-collect-unbounded", PR, "        elif status.st_size > MAX_COLLECT_BYTES:\n", "        elif False:\n"),
    ("process-collect-after-timeout", PR, '                reason_code="TOOL_TIMED_OUT",\n                argv=argv,\n',
     '                reason_code="TOOL_TIMED_OUT",\n                argv=argv,\n'
     "                collected=_collect(workspace, request.collect, request.collect_into)[0] if request.collect_into else [],\n"),
    ("process-collect-name-unchecked", PR, "            if not _plain_file_name(name):\n", "            if False:\n"),
    ("process-collect-by-default", PR,
     "        if request.collect and request.collect_into is not None:\n"
     "            collected, collect_problems = _collect(workspace, request.collect, request.collect_into)\n",
     "        if True:\n"
     "            collected, collect_problems = _collect(workspace, request.collect or tuple(p.as_posix() for p in outputs),\n"
     '                                                   request.collect_into or workspace / ".home")\n'),
    ("process-stdin-inherited", PR, "                stdin=subprocess.DEVNULL if request.stdin_devnull else None,\n",
     "                stdin=None,\n"),
    # iverilog: both steps on run_process, the program carried between them, arguments refused, declared markers
    ("hdl-compile-inherits-environment", HD,
     "                timeout_seconds=request.timeout_seconds, stdin_devnull=True,\n                collect=(PROGRAM,)",
     "                timeout_seconds=request.timeout_seconds, stdin_devnull=True,\n"
     '                environment=dict(__import__("os").environ), collect=(PROGRAM,)'),
    ("hdl-run-inherits-environment", HD, "                timeout_seconds=request.timeout_seconds, stdin_devnull=True))\n",
     "                timeout_seconds=request.timeout_seconds, stdin_devnull=True,\n"
     '                environment=dict(__import__("os").environ)))\n'),
    ("hdl-compile-stdin-inherited", HD,
     "                timeout_seconds=request.timeout_seconds, stdin_devnull=True,\n                collect=(PROGRAM,)",
     "                timeout_seconds=request.timeout_seconds,\n                collect=(PROGRAM,)"),
    ("hdl-run-stdin-inherited", HD, "                timeout_seconds=request.timeout_seconds, stdin_devnull=True))\n",
     "                timeout_seconds=request.timeout_seconds))\n"),
    ("hdl-compile-bypasses-run-process", HD,
     "            compiled = run_process(ProcessRequest(\n"
     "                argv=compile_command, input_root=request.product_root, input_files=request.input_files,\n"
     "                timeout_seconds=request.timeout_seconds, stdin_devnull=True,\n"
     "                collect=(PROGRAM,), collect_into=Path(stage)))\n",
     "            for source, relative in zip(request.input_files, relatives):\n"
     "                (Path(stage) / relative).parent.mkdir(parents=True, exist_ok=True)\n"
     "                shutil.copyfile(source, Path(stage) / relative)\n"
     '            done = __import__("subprocess").run(\n'
     "                [shutil.which(compile_command[0]) or compile_command[0], *compile_command[1:]], cwd=stage,\n"
     "                capture_output=True, text=True, timeout=request.timeout_seconds, shell=False,\n"
     '                stdin=__import__("subprocess").DEVNULL)\n'
     "            compiled = ProcessResult(\n"
     "                execution_status=ExecutionStatus.COMPLETED, argv=list(done.args), returncode=done.returncode,\n"
     '                reason_code="TOOL_EXITED_ZERO" if done.returncode == 0 else "TOOL_EXITED_NONZERO",\n'
     "                stdout=done.stdout, stderr=done.stderr,\n"
     "                collected=[Path(stage) / PROGRAM] if (Path(stage) / PROGRAM).is_file() else [])\n"),
    ("hdl-run-bypasses-run-process", HD,
     "            executed = run_process(ProcessRequest(\n"
     '                argv=["vvp", PROGRAM], input_root=Path(stage), input_files=list(compiled.collected),\n'
     "                timeout_seconds=request.timeout_seconds, stdin_devnull=True))\n",
     '            done = __import__("subprocess").run(\n'
     '                [shutil.which("vvp") or "vvp", PROGRAM], cwd=stage, capture_output=True, text=True,\n'
     '                timeout=request.timeout_seconds, shell=False, stdin=__import__("subprocess").DEVNULL)\n'
     "            executed = ProcessResult(\n"
     "                execution_status=ExecutionStatus.COMPLETED, argv=list(done.args), returncode=done.returncode,\n"
     '                reason_code="TOOL_EXITED_ZERO" if done.returncode == 0 else "TOOL_EXITED_NONZERO",\n'
     "                stdout=done.stdout, stderr=done.stderr)\n"),
    ("hdl-program-not-carried", HD, "collect=(PROGRAM,), collect_into=Path(stage)))", "collect=(), collect_into=Path(stage)))"),
    ("hdl-program-missing-passes", HD, "            if not compiled.collected:\n", "            if False:\n"),
    ("hdl-arguments-passed", HD,
     "        if request.arguments:\n"
     "            return self._blocked(\n"
     '                "RTL_ARGUMENTS_REFUSED",\n'
     '                f"case arguments are not passed to Icarus Verilog and nothing was run: {list(request.arguments)!r}",\n'
     "            )\n"
     "        relatives = [relative_input_path(request.product_root, source).as_posix() for source in request.input_files]\n",
     "        relatives = [relative_input_path(request.product_root, source).as_posix() for source in request.input_files]\n"
     "        relatives += list(request.arguments)\n"),
    ("hdl-truncation-ignored", HD, "            if executed.stdout.endswith(TRUNCATED):\n", "            if False:\n"),
    ("hdl-metrics-parsed-on-failure", HD, "        if verdict is Verdict.PASS:\n",
     "        if executed.returncode is not None:\n"),
    ("hdl-undeclared-metrics-read", HD, "    for name in declared:\n", "    for name in [*declared, *reported]:\n"),
    ("hdl-duplicate-report-kept", HD, "reported.setdefault(found.group(1), []).append(found.group(2))",
     "reported.setdefault(found.group(1), [found.group(2)])"),
    ("hdl-non-finite-kept", HD, "        elif not math.isfinite(float(values[0])):\n", "        elif False:\n"),
    ("hdl-python-number-spellings", HD, "        elif not NUMBER.match(values[0]):\n", "        elif False:\n"),
    ("hdl-declared-twice-read", HD, "    return ([name for name, count in counts.items() if count == 1],\n",
     "    return ([name for name, count in counts.items() if count >= 1],\n"),
    ("hdl-oversize-input-read", HD, "            if source.stat().st_size > MAX_INPUT_BYTES:\n", "            if False:\n"),
    ("hdl-reason-unsanitised", HD, "    if RECEIPT_CODE.match(reason):\n", "    if True:\n"),
    ("hdl-timeout-names-compile-step", HD, '        unfinished = self._unfinished("RTL testbench execution", executed)\n',
     '        unfinished = self._unfinished("RTL compilation", __import__("dataclasses").replace(executed, argv=compile_command))\n'),
    # the digital review (CS-6): the version probe runs through run_process, with its scrubbed environment
    ("hdl-probe-bypasses-run-process", HD, "        compiler = probe_iverilog()\n",
     '        compiler = __import__("ecad_validation.adapters.capabilities", fromlist=["probe_executable"])'
     '.probe_executable("iverilog", ("iverilog", "-V"))\n'),
    ("hdl-probe-inherits-environment", HD, "timeout_seconds=PROBE_TIMEOUT_S, stdin_devnull=True))",
     'timeout_seconds=PROBE_TIMEOUT_S, stdin_devnull=True, environment=dict(__import__("os").environ)))'),
    # iverilog's version: the first line of `iverilog -V`, never an invented one
    ("iverilog-version-pattern-added", CP, r'= {"ngspice": re.compile(r"\bngspice-([0-9][0-9A-Za-z.+~-]*)")}',
     r'= {"ngspice": re.compile(r"\bngspice-([0-9][0-9A-Za-z.+~-]*)"), "iverilog": re.compile(r"version ([0-9.]+)")}'),
    ("silent-probe-version-invented", CP, "        return output.splitlines()[0].strip() if output else None\n",
     '        return output.splitlines()[0].strip() if output else "unknown"\n'),
    # the Verilog grammar (tools/ecad_model/verilog.py): refusals, bounds, elaboration
    ("vg-include-accepted", VG, '            if value == "`timescale" and not tokens and lines[line - 1] == TIMESCALE:\n', '            if value == "`include":\n                position = text.index("\\n", position)\n                continue\n            if value == "`timescale" and not tokens and lines[line - 1] == TIMESCALE:\n'),
    ("vg-timescale-any", VG, "lines[line - 1] == TIMESCALE:", 'lines[line - 1].startswith("`timescale"):'),
    ("vg-system-task-accepted", VG, '            if not (harness and value in HARNESS_TASKS):\n                suffix = "; the harness uses only $display, $finish and $realtime" if harness else ""\n                raise HdlRefused(f"{where}: {value}: {_system_reason(value)}{suffix}")\n            tokens.append(("system", value, line, None))\n', '            tokens.append(("name", value, line, None))\n'),
    ("vg-string-accepted", VG, '            if not harness:\n                raise HdlRefused(f"{where}: a string: outside the lexical subset (file names and import "\n', "            if not harness:\n                position = text.index('\"', position + 1) + 1\n                continue\n                raise HdlRefused(f\"{where}: a string: outside the lexical subset (file names and import \"\n"),
    ("vg-attribute-accepted", VG, '            if value == "(*":\n                raise HdlRefused(f"{where}: (*: an attribute: outside the lexical subset")\n', '            if value == "(*":\n                position = text.index("*)", position) + 2\n                continue\n'),
    ("vg-dpi-import-accepted", VG, '"calls C code": "import export chandle bind",', '"calls C code": "export chandle bind",'),
    ("vg-initial-in-rtl-accepted", VG, 'if else case endcase default"', 'if else case endcase default initial"'),
    ("vg-defparam-accepted", VG, '"defparam force release deassign', '"force release deassign'),
    ("vg-blocking-assign-accepted", VG, '    if operator[1] == "=":\n', "    if False:\n"),
    ("vg-hierarchical-reference-accepted", VG, '    if cursor.at("."):\n        raise cursor.refuse(token, f"{token[1]}.{cursor.peek(1)[1]}: a hierarchical reference, which reads or "\n', '    while cursor.at("."):\n        cursor.index += 2\n    if False:\n        raise cursor.refuse(token, f"{token[1]}.{cursor.peek(1)[1]}: a hierarchical reference, which reads or "\n'),
    ("vg-instance-in-leaf-accepted", VG, '        elif token[0] == "name" and (cursor.peek(1)[0] == "name" or cursor.at("#", 1)):\n            raise cursor.refuse(token, f"an instance of {token[1]}: a leaf instantiates no module; a top is written "\n', '        elif token[0] == "name" and (cursor.peek(1)[0] == "name" or cursor.at("#", 1)):\n            while cursor.take()[1] != ";":\n                pass\n        elif False:\n            raise cursor.refuse(token, f"an instance of {token[1]}: a leaf instantiates no module; a top is written "\n'),
    ("vg-non-ascii-code-accepted", VG, '            if ord(char) > 0x7F:\n                raise HdlRefused(f"{where}: non-ASCII outside a comment (U+{ord(char):04X})")\n', "            if ord(char) > 0x7F:\n                position += 1\n                continue\n"),
    ("vg-size-limit-off-by-one", VG, "    if len(data) > MAX_SOURCE_BYTES:\n", "    if len(data) >= MAX_SOURCE_BYTES:\n"),
    ("vg-depth-unbounded", VG, '            if len(stack) == MAX_DEPTH:\n                raise cursor.refuse(token, f"{word}: statements nested more than {MAX_DEPTH} deep")\n', '            if False:\n                raise cursor.refuse(token, f"{word}: statements nested more than {MAX_DEPTH} deep")\n'),
    ("vg-range-lsb-ignored", VG, "    if lsb[3] != 0:\n", "    if False:\n"),
    ("vg-literal-overflow-accepted", VG, "    if number >= 1 << width:\n", "    if False:\n"),
    ("vg-top-initialiser-accepted", VG, '                if not harness or word == "wire":\n', '                if word == "wire":\n'),
    ("vg-width-mismatch-accepted", VG, "        if width != port.width:\n", "        if False:\n"),
    ("vg-two-drivers-accepted", VG, "        if len(outputs) > 1:\n", "        if False:\n"),
    ("vg-second-top-accepted", VG, "    if len(tops) != 1:\n", "    if len(tops) < 1:\n"),
    ("vg-harness-names-allowed", VG, '    if value.startswith("ecad_") and not harness:\n', "    if False:\n"),
    ("vg-marker-text-allowed", VG, "    marker = text.find(_MARKER)\n    if marker >= 0:\n", "    marker = text.find(_MARKER)\n    if False:\n"),
    # beyond section 10: the expression depth, the decimal bound, bidirectional controls, the harness's tasks
    ("vg-expression-depth-unbounded", VG, '                if len(stack) == MAX_DEPTH:\n                    raise cursor.refuse(token, f"an expression nested more than {MAX_DEPTH} deep")\n                cursor.take()\n                stack.append("(")\n', '                if False:\n                    raise cursor.refuse(token, f"an expression nested more than {MAX_DEPTH} deep")\n                cursor.take()\n                stack.append("(")\n'),
    ("vg-decimal-unbounded", VG, "            if number > MAX_DECIMAL:\n", "            if False:\n"),
    ("vg-bidi-control-accepted", VG, '    for pattern, what in ((_CONTROL, "a control character"), (_BIDI, "a bidirectional control character")):\n', '    for pattern, what in ((_CONTROL, "a control character"),):\n'),
    ("vg-harness-any-system-task", VG, "            if not (harness and value in HARNESS_TASKS):\n", "            if not harness:\n"),
    # the digital review (CS-2): the words Icarus alone reserves, and a unary operator's operand
    ("vg-icarus-extended-types-accepted", VG, '    "an Icarus Verilog extended type (its -gxtypes, on by default)": "bool wreal",\n', ""),
    ("vg-wone-accepted", VG, 'wand wor uwire wone"', 'wand wor uwire"'),
    ("vg-unary-after-unary-accepted", VG, '                if following[0] == "op" and following[1] in _UNARY:\n',
     "                if False:\n"),
    # the digital domain: the class rules, V1, the closed forms, the harness writer and the model
    ("dg-rule-c2-unchecked", DG, "if shape[2] == TRANSMITTER_PORTS and shape[3] == parameters]",
     "if shape[3] == parameters]"),
    ("dg-rule-c5-line-unchecked", DG, '        "line": only(tx_ports["tx"], "wire", [f"{tx_name}.tx", f"{rx_name}.rx"],\n                     "the line, which the transmitter\'s tx and the receiver\'s rx share,"),\n',
     '        "line": tx_ports["tx"],\n'),
    ("dg-rule-c6-inert-localparam", DG, "    if inert:\n",
     "    if False:\n"),
    ("dg-resource-guard-off", DG, "        if end > MAX_CYCLES:\n",
     "        if end > 10**12:\n"),
    ("dg-clock-consistency-unchecked", DG,
     "            if half_ns is not None and not abs(2 * half_ns * clock - 10**9) < 2 * half_ns:\n",
     "            if False:\n"),
    ("dg-receiver-ticks-unchecked", DG, "and clock // (rate * oversample) < 1:\n",
     "and False:\n"),
    ("dg-facet-unit-unchecked", DG, '                elif facet["unit"] != unit:\n',
     "                elif False:\n"),
    ("dg-frame-bits-nine", DG, "FRAME_BITS = 10  # 8N1",
     "FRAME_BITS = 9  # 8N1"),
    ("dg-bit-period-rounded", DG, '    bit_cycles = values[("transmitter", "clk_freq")] // values[("transmitter", "baud_rate")]\n',
     '    bit_cycles = round(values[("transmitter", "clk_freq")] / values[("transmitter", "baud_rate")])\n'),
    ("dg-half-period-as-period", DG, '        return 2 * values[("top", "clock_half_period")], paths\n',
     '        return values[("top", "clock_half_period")], paths\n'),
    ("dg-bit-rate-parity-ignored", DG, "        if first % 2 == 0:\n",
     "        if False:\n"),
    ("dg-sampling-condition-always", DG, "    if tick_cycles < 1:\n        return False\n",
     "    return True\n"),
    ("dg-sampling-upper-bound-inclusive", DG, "+ tick_cycles - 1 < (bit + 1) * bit_cycles",
     "+ tick_cycles - 1 <= (bit + 1) * bit_cycles"),
    ("dg-sampling-lower-bound-dropped", DG, "    return all(bit * bit_cycles <= (middle + oversample * bit) * tick_cycles\n               and (middle",
     "    return all((middle"),
    ("dg-harness-samples-rising-edge", DG, '        f"    always @(negedge {clk}) begin",\n',
     '        f"    always @(posedge {clk}) begin",\n'),
    ("dg-end-cycle-hard-coded", DG, '        f"        if (ecad_cycle == {end}) begin",\n',
     '        "        if (ecad_cycle == 20836) begin",\n'),
    ("dg-byte-count-hard-coded", DG, '        f"            if (ecad_received < {count}) begin",\n',
     '        "            if (ecad_received < 2) begin",\n'),
    ("dg-marker-dropped", DG, '        \'            if (ecad_framing_errors > 0 || ecad_missing == 0) $display("ECAD_METRIC rx_framing_errors %0d", \'\n'
     '        \'ecad_framing_errors);\',\n',
     ""),
    ("dg-rtl-not-verbatim", DG, '                    "text": leaf.text},\n',
     '                    "text": leaf.text.encode("ascii", "replace").decode("ascii")},\n'),
    ("dg-top-hash-not-bound", DG, '        return source("design_annotation", path, digests[path])\n',
     '        return source("design_annotation", path)\n'),
    ("dg-overrides-not-written", DG, '    return f"    {hdl[\'module\']} #({overrides}) {hdl[\'instance\'].rsplit(\'.\', 1)[1]} ({connections});"\n',
     '    return f"    {hdl[\'module\']} {hdl[\'instance\'].rsplit(\'.\', 1)[1]} ({connections});"\n'),
    # the digital domain beyond design §10: the rules and V2 checks this implementation adds or names
    ("dg-even-first-byte-accepted", DG, '    if localparams["TX_BYTE_0"][0] % 2 == 0:\n',
     "    if False:\n"),
    ("dg-oversample-literal-unchecked", DG, '    if "OVERSAMPLE" not in design.leaves[receiver.module].literal_localparams:\n',
     "    if False:\n"),
    ("dg-rule-c4-unchecked", DG, "        if overridden != parameters:\n",
     "        if False:\n"),
    ("dg-v2-rtl-prefix-unchecked", DG, "                if number > len(lines) or lines[number - 1] != want:\n",
     "                if False:\n"),
    ("dg-v2-harness-read-back-ignored", DG, "            if read[what] != want:\n",
     "            if False:\n"),
    ("dg-v2-writer-equality-ignored", DG, "        if harness != own:\n",
     "        if False:\n"),
    ("dg-v2-text-hash-unchecked", DG, '            elif "text" in hdl and hashlib.sha256(hdl["text"].encode("utf-8")).hexdigest() != sources[hdl["source"]]:\n',
     "            elif False:\n"),
    ("dg-v2-citation-unchecked", DG, '            if (facet["status"] != Status.SPECIFIED.value or facet["source"]["ref"] != origin\n',
     '            if (False and facet["source"]["ref"] != origin\n'),
    ("dg-v2-harness-position-unchecked", DG, "            if found != HARNESS_SEPARATOR:\n",
     "            if False:\n"),
    # the digital review (CS-1): a byte that never arrives counts 8 bit errors, and no framing count of 0 stands for it
    ("dg-missing-bytes-not-counted", DG,
     '''        '            $display("ECAD_METRIC rx_bit_errors %0d", ecad_bit_errors + 8 * ecad_missing);',\n''',
     '''        '            $display("ECAD_METRIC rx_bit_errors %0d", ecad_bit_errors);',\n'''),
    ("dg-framing-reported-while-bytes-missing", DG,
     '''        '            if (ecad_framing_errors > 0 || ecad_missing == 0) $display("ECAD_METRIC rx_framing_errors %0d", '\n''',
     '''        '            $display("ECAD_METRIC rx_framing_errors %0d", '\n'''),
    ("dg-awaited-count-hard-coded", DG, '        f"            if (ecad_received < {count}) ecad_missing = {count} - ecad_received;",\n',
     '        "            if (ecad_received < 2) ecad_missing = 2 - ecad_received;",\n'),
    ("dg-v2-awaited-not-compared", DG, '            "bytes awaited": len(sent),\n', ""),
    ("vg-harness-awaited-count-unbound", VG, r'ecad_missing = \1 - ecad_received;")', r'ecad_missing = [0-9]+ - ecad_received;")'),
    # the digital review (HT-1): the clock is compared in whole Hz, within 1 Hz of what the harness drives
    ("dg-clock-tolerance-inclusive", DG, "not abs(2 * half_ns * clock - 10**9) < 2 * half_ns:",
     "not abs(2 * half_ns * clock - 10**9) <= 2 * half_ns:"),
    ("dg-clock-compared-in-seconds", DG,
     "            if half_ns is not None and not abs(2 * half_ns * clock - 10**9) < 2 * half_ns:\n",
     "            if half is not None and abs(2 * half * clock - 1) > 1e-9:\n"),
    # the digital review (CS-4): a parameter the harness's unsized decimal cannot hold is refused at extraction
    ("dg-parameter-above-max-decimal-accepted", DG, "            if number > verilog.MAX_DECIMAL:\n",
     "            if False:\n"),
    ("dg-parameter-bound-off-by-one", DG, "            if number > verilog.MAX_DECIMAL:\n",
     "            if number >= verilog.MAX_DECIMAL:\n"),
    # the digital domain: the registry
    ("digital-unregistered", DR, ',\n                                      "digital": DigitalAdapter()}',
     "}"),
    # REUSE-1: a copied source is bound to its origin by hash
    ("reuse-origin-unchecked", D, '        problem = _citation_problem(f"{artifact[\'path\']}\'s origin", origin["path"], origin["sha256"])\n        if problem:\n            problems.append(problem)\n',
     ""),
    ("reuse-copy-unchecked", D, '        if _sha256(item.read(artifact["path"])) != origin["sha256"]:\n',
     "        if False:\n"),
    ("reuse-origin-inside-item-allowed", D, '        if _lies_within((REPOSITORY_ROOT / origin["path"]).resolve(), item.root):\n',
     "        if False:\n"),
    # the digital review (CS-3): the item's directory is compared by file identity, not by spelling
    ("reuse-origin-inside-compared-by-spelling", D, "            if os.path.samefile(ancestor, directory):\n",
     "            if ancestor == directory:\n"),
    # the format rules of the hdl member, the digital facet and copied_from
    ("schema-hdl-any-version", MS, '"then": {"properties": {"model_version": {"const": "1.2.0"}}}',
     '"then": {}'),
    ("annotations-digital-any-version", AS, '"const": "1.2.0"',
     '"enum": ["1.0.0", "1.1.0", "1.2.0"]'),
    ("provenance-copy-version-rule-dropped", PS, '"then": {"properties": {"provenance_version": {"const": "1.1.0"}}}',
     '"then": {}'),
    # digital: the sample's own files (each rebuilt, so a behavioural test must kill it)
    ("item-baud-rate-changed", DT, "    localparam BAUD_RATE          = 115_200;",
     "    localparam BAUD_RATE          = 230_400;"),
    ("item-byte-changed", DT, "TX_BYTE_1    = 8'hCA;",
     "TX_BYTE_1    = 8'hC5;"),
    ("item-limit-tightened", DQ, '"value": 117504.0',
     '"value": 115000.0'),
    ("item-illustrative-cleared", DQ, '"unit": "bits",\n      "source": {\n        "kind": "requirement",\n        "ref": "example requirement for the uart_loopback_001 MVP, chosen to exercise the pipeline; not a customer, interface or certification requirement; no standard or peer device was consulted"\n      },\n      "illustrative": true',
     '"unit": "bits",\n      "source": {\n        "kind": "requirement",\n        "ref": "example requirement for the uart_loopback_001 MVP, chosen to exercise the pipeline; not a customer, interface or certification requirement; no standard or peer device was consulted"\n      },\n      "illustrative": false'),
    ("item-operator-flipped", DQ, '"operator": ">=",\n      "limit": {\n        "value": 112896.0',
     '"operator": "<=",\n      "limit": {\n        "value": 112896.0'),
    ("item-device-limit-invented", DA, '"value": null,\n            "unit": "s",\n            "status": "UNKNOWN"',
     '"value": 1e-08,\n            "unit": "s",\n            "status": "SPECIFIED"'),
    ("item-origin-digest-changed", DP, '"copied_from": {"path": "rtl/uart_tx.v", "sha256": "5be9e1bdd20b37a3b79cb40c98fbfe241e8d6faca5ecb443b0e93378d7b4f01a"}',
     '"copied_from": {"path": "rtl/uart_tx.v", "sha256": "c1bebcc6e894e86abd4b39af5501031b8c817f4395048ef65059eebfb710ab81"}'),
    ("item-artifact-type-changed", DP, '"artifact_type": "hdl_source"',
     '"artifact_type": "other"'),
    # the digital review (HT-6): the requirement on a one-instant metric says the instant
    ("item-unknown-outputs-title-overstated", DQ,
     '"title": "No output is unknown at the first falling clock edge after reset is released"',
     '"title": "No output is unknown once reset is released"'),
    # the origins REUSE-1 binds are never converted on checkout
    ("rtl-origin-converted-on-checkout", GA, "rtl/uart_tx.v -text\n",
     ""),
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
            if relative.startswith("datasets/"):
                # The manifest hashes every file of a dataset item, so without a
                # rebuild any edit there is "killed" by the integrity check
                # alone. Re-hashing makes a behavioural test catch it, or not.
                item = "/".join(Path(relative).parts[:3])
                rebuilt = subprocess.run([sys.executable, "tools/cad_dataset.py", "build", item], cwd=copy,
                                         capture_output=True, text=True, timeout=1800)
                if rebuilt.returncode != 0:
                    return name, "HARNESS", f"rebuilding {item} failed: {rebuilt.stderr.strip()[-200:]}"
                for command in (["git", "add", "-A"], ["git", "-c", "user.name=mutation", "-c",
                                "user.email=mutation@localhost", "commit", "-q", "-m", "mutant"]):
                    subprocess.run(command, cwd=copy, check=True, capture_output=True, timeout=300)
        environment = dict(os.environ, ECAD_REQUIRE_CAD_TOOLS="1", ECAD_REQUIRE_SPICE_TOOLS="1",
                           ECAD_REQUIRE_HDL_TOOLS="1", PYTHONDONTWRITEBYTECODE="1")
        for suite in (FAST, ADAPTER, NETLIST, NGSPICE, ELECTRICAL, VERILOG, HDLAD, DIGITAL, SPICE, ICARUS, SLOW):
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
    print(f"baseline green; running {len(selected)} mutants", flush=True)
    outcomes = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for name, outcome, detail in pool.map(lambda mutant: run(*mutant), selected):
            outcomes.append((name, outcome, detail))
            print(f"{outcome:9s} {name:36s} {detail}", flush=True)
    killed = sum(outcome == "KILLED" for _, outcome, _ in outcomes)
    print(f"\n{killed} of {len(outcomes)} mutants killed")
    return 0 if killed == len(outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
