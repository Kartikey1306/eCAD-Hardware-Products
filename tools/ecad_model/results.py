"""Per-requirement validation results: one record per V3/V4 check of a run.

The v1 receipt says, gate by gate, what passed. A result says, requirement by
requirement, what was measured against what, by which simulator at which
version, on which inputs with which statuses, and which evidence proves it.
Every field is copied or computed from the run -- the receipt, the compiled
cases, each check's hash-bound execution record, the engineering model --
and none is synthesised: a missing simulator version stays null, and the
schema forbids a PASS without one.

The inputs a result lists are the transitive derived_from leaves of the model
quantities its metric depends on (and of its limit, when the limit is one),
each with its status, so a DERIVED mass that rests on an ESTIMATED density is
shown as resting on it. The same leaves decide the propagation rule
(propagate()): a null-status leaf blocks the check, an AI_ASSUMPTION leaf
makes a V4 verdict INCONCLUSIVE.
"""

from __future__ import annotations

import hashlib
import platform
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .builder import resolve
from .quantity import is_null

VERSION = "1.0.0"
RESULTS_SCHEMA = "https://embeddedos.org/schemas/engineering-model/v1/validation-results.schema.json"


def _is_model_path(reference: str) -> bool:
    return ":" not in reference and reference.split("/", 1)[0] in ("components", "joints", "design")


def input_leaves(model: Dict[str, Any], paths: Sequence[str]) -> List[Dict[str, str]]:
    """The quantities the given model paths ultimately rest on, with their statuses.

    A leaf is a quantity none of whose derived_from entries is another model
    quantity: a CAD-derived volume, an annotated density, a specified limit.

    Args:
        model: The engineering model.
        paths: Model quantity paths.

    Returns:
        {"path", "status"} for every leaf, sorted by path.

    Example:
        >>> import json; from pathlib import Path
        >>> item = Path(__file__).resolve().parents[2] / "datasets/cad/robotic_joint_001"
        >>> model = json.loads((item / "derived/engineering_model.json").read_text())
        >>> [leaf["status"] for leaf in input_leaves(model, ["components/link/physical/mass"])]
        ['DERIVED', 'ESTIMATED']
    """
    seen, leaves, stack = set(), {}, list(paths)
    while stack:
        path = stack.pop()
        if path in seen:
            continue
        seen.add(path)
        quantity = resolve(model, path)
        parents = [ref for ref in quantity.get("derived_from", []) if _is_model_path(ref)]
        if parents:
            stack.extend(parents)
        else:
            leaves[path] = quantity["status"]
    return [{"path": path, "status": leaves[path]} for path in sorted(leaves)]


def propagate(leaves: Sequence[Dict[str, str]], verdict: str) -> Optional[Tuple[str, str, List[str]]]:
    """What a check's inputs make of its verdict, before any other rewrite.

    Applied in order, the first that applies wins: a null-status leaf makes
    the check BLOCKED (MISSING_REQUIRED_INPUT); an AI_ASSUMPTION leaf turns a
    PASS or FAIL into INCONCLUSIVE (INPUT_IS_AI_ASSUMPTION), because a value a
    model proposed can neither qualify nor condemn a design.

    Returns:
        (verdict, reason_code, findings), or None when the inputs change nothing.

    Example:
        >>> propagate([{"path": "components/a/material/density", "status": "AI_ASSUMPTION"}], "PASS")[:2]
        ('INCONCLUSIVE', 'INPUT_IS_AI_ASSUMPTION')
        >>> propagate([{"path": "components/a/material/density", "status": "ESTIMATED"}], "PASS") is None
        True
    """
    missing = [f"{leaf['status']}: {leaf['path']}" for leaf in leaves if is_null(leaf["status"])]
    if missing:
        return "BLOCKED", "MISSING_REQUIRED_INPUT", missing
    assumed = [f"AI_ASSUMPTION: {leaf['path']}" for leaf in leaves if leaf["status"] == "AI_ASSUMPTION"]
    if assumed and verdict in ("PASS", "FAIL"):
        return "INCONCLUSIVE", "INPUT_IS_AI_ASSUMPTION", assumed
    return None


def environment(tools: Sequence[Dict[str, Any]], constraints: Optional[bytes]) -> Dict[str, Any]:
    """Where a run happened, without host paths: OS, architecture, interpreter,
    the pinned dependency set, and the version of every tool the receipt records."""
    return {
        "os": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "constraints_sha256": hashlib.sha256(constraints).hexdigest() if constraints is not None else None,
        "tools": {tool["tool_id"]: tool["version"] for tool in tools},
    }


def _scenario_inputs(requirement_id: str, scenario: Mapping[str, Any]) -> List[Dict[str, str]]:
    """Scenario parameters that override the model, e.g. a rated payload mass,
    listed as inputs of their own: their value comes from the requirement."""
    return [{"path": f"scenario/{key}", "status": "SPECIFIED", "source": f"requirement {requirement_id}"}
            for key in sorted(scenario) if key != "name"]


def build_results(
    *, sample_id: str, receipt: Dict[str, Any], receipt_sha256: str, requirements: Dict[str, Any],
    model: Dict[str, Any], model_sha256: str, adapter: Any, cases: Dict[str, Dict[str, Any]],
    executions: Dict[str, Dict[str, Any]], environment_record: Dict[str, Any],
) -> Dict[str, Any]:
    """One result per requirement and reference, generated from a finished run.

    Args:
        sample_id: The dataset item.
        receipt: The run's receipt, as written.
        receipt_sha256: The digest of the receipt's bytes.
        requirements: The engineering-requirements document.
        model: The committed engineering model the cases ran on.
        model_sha256: The digest of its bytes.
        adapter: The sample's domain adapter (metrics, dependencies, components).
        cases: Compiled case by case id, from the committed case documents.
        executions: Execution record by check id, from the checks' evidence.
        environment_record: environment() of the run.

    Returns:
        A document conforming to engineering-model/v1/validation-results.
    """
    checks = {check["check_id"]: check for gate in receipt["gates"] for check in gate["checks"]}
    metrics = adapter.metrics()
    results = []
    for gate, entries, key in (("V3", requirements["reference_values"], "reference_id"),
                               ("V4", requirements["requirements"], "requirement_id")):
        for entry in entries:
            entry_id, metric = entry[key], entry["metric"]
            check_id = f"{gate.lower()}.{entry_id}"
            check = checks.get(check_id, {})
            case = cases.get(entry_id)
            measured = (check.get("metrics") or {}).get(metric)
            measured_by: Optional[str] = check_id if measured is not None else None
            if measured is None:
                # A requirement blocked only on its limit still has a measured side
                # when another check ran the same metric with the same arguments.
                arguments = adapter.case_target(sample_id).arguments(entry["scenario"])
                for other_id, other in sorted(checks.items()):
                    other_case = cases.get(other_id.split(".", 1)[-1])
                    value = (other.get("metrics") or {}).get(metric)
                    if other_id != check_id and value is not None and other_case and other_case["arguments"] == arguments:
                        measured, measured_by = value, other_id
                        break
            if gate == "V3":
                expected = case["expected_metrics"][metric] if case else None
                operator, tolerance = "within", entry["absolute_tolerance"]
                expected_value = expected["value"] if expected else None
                bound = ({"minimum": expected["value"] - tolerance, "maximum": expected["value"] + tolerance}
                         if expected else None)
                paths = adapter.reference_inputs(model, entry["derivation"], entry["scenario"])
                kind, illustrative, component = "reference", False, None
            else:
                operator, tolerance = entry["operator"], entry.get("tolerance", 0.0)
                bound = case["metric_limits"][metric] if case else None
                limit = entry["limit"]
                if "value" in limit:
                    expected_value = limit["value"]
                else:
                    quantity = resolve(model, limit["quantity"])
                    expected_value = quantity["value"]
                paths = adapter.dependencies(model, metric, entry["scenario"]) + (
                    [limit["quantity"]] if "quantity" in limit else [])
                kind = "illustrative requirement" if entry["illustrative"] else "requirement"
                illustrative, component = entry["illustrative"], entry["component"]
            execution = executions.get(check_id)
            results.append({
                "validation_id": f"{sample_id}:{check_id}",
                "check_id": check_id,
                "domain": entry["domain"],
                "kind": kind,
                "requirement": entry_id,
                "title": entry["title"],
                "source": entry["source"],
                "metric": metric,
                "component": component,
                "cad_components": adapter.components_for(model, metric),
                "illustrative": illustrative,
                "status": check.get("verdict", "NOT_RUN"),
                "reason_code": check.get("reason_code"),
                "findings": list(check.get("findings", [])),
                "measured_value": measured,
                "measured_by": measured_by,
                "expected_value": expected_value,
                "operator": operator,
                "applied_bound": bound,
                "unit": entry["unit"],
                "tolerance": tolerance,
                "simulator": execution["adapter"] if execution else None,
                "simulator_version": (execution or {}).get("tool_version") or None,
                "configuration": {"command": execution["command"] if execution else None,
                                  "scenario": entry["scenario"], "seed": case["seed"] if case else None},
                "model_version": model["model_version"],
                "model_sha256": model_sha256,
                "model_fidelity": metrics[metric].fidelity,
                "inputs": input_leaves(model, paths) + _scenario_inputs(entry_id, entry["scenario"]),
                "timestamp": receipt["completed_at"],
                "input_hash": receipt["source"]["input_sha256"],
                "source_dirty": receipt["source"]["dirty"],
                "environment": environment_record,
                "receipt_sha256": receipt_sha256,
                "evidence": [{"evidence_id": e["evidence_id"], "sha256": e["sha256"]} for e in check.get("evidence", [])],
            })
    return {"$schema": RESULTS_SCHEMA, "results_version": VERSION, "sample_id": sample_id,
            "receipt_sha256": receipt_sha256, "results": results}

