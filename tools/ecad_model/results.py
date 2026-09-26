"""Per-requirement validation results: one record per requirement and reference of a run.

The v1 receipt says, gate by gate, what passed. A result says, requirement by
requirement, what was measured against what, by which simulator at which
version, on which inputs with which statuses, and which evidence proves it.
Every field is copied or computed from what the run recorded -- the receipt,
the compiled cases, each check's hash-bound execution record, the environment
record the run stored as evidence, and the engineering model whose digest the
run bound -- and none is synthesised: a missing simulator version stays null,
and the schema forbids a PASS without one.

The inputs a result lists are what the model quantities its metric depends on
(and its limit, when the limit is one) ultimately rest on: every quantity on
the way whose status is not DERIVED, and every DERIVED quantity with no model
inputs of its own, such as a CAD-derived volume. A DERIVED mass that rests on
an ESTIMATED density is therefore shown resting on it, and an AI_ASSUMPTION
that itself names a parent is never walked past. The same inputs decide the
propagation rule (propagate()).
"""

from __future__ import annotations

import hashlib
import platform
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from .builder import resolve
from .quantity import is_null

VERSION = "1.0.0"
RESULTS_SCHEMA = "https://embeddedos.org/schemas/engineering-model/v1/validation-results.schema.json"

# The case engine's reason codes for a corner case whose metrics it compared
# with the limits. Only such a verdict is a judgement on the design, so only
# such a verdict is withheld when it rests on an AI_ASSUMPTION.
COMPARATOR_CODES = frozenset({"CORNER_LIMITS_PASSED", "CORNER_LIMITS_FAILED"})


def _is_model_path(reference: str) -> bool:
    return ":" not in reference and reference.split("/", 1)[0] in ("components", "joints", "design")


def input_leaves(model: Dict[str, Any], paths: Sequence[str]) -> Tuple[List[Dict[str, str]], List[str]]:
    """What the given model paths ultimately rest on, with the statuses that decide it.

    Args:
        model: The engineering model.
        paths: Model quantity paths.

    Returns:
        (inputs, unresolved): {"path", "status"} for every quantity on the way
        whose status is not DERIVED and every DERIVED quantity with no model
        inputs, sorted by path; and every path, given or named in a
        derived_from, that resolves to no quantity, sorted. Nothing is
        raised for a path that does not resolve: the caller decides what an
        input it cannot establish means.

    Example:
        >>> import json; from pathlib import Path
        >>> item = Path(__file__).resolve().parents[2] / "datasets/cad/robotic_joint_001"
        >>> model = json.loads((item / "derived/engineering_model.json").read_text())
        >>> found, unresolved = input_leaves(model, ["components/link/physical/mass", "components/ghost/physical/mass"])
        >>> [leaf["status"] for leaf in found], unresolved
        (['DERIVED', 'ESTIMATED'], ['components/ghost/physical/mass'])
    """
    seen, found, unresolved, stack = set(), {}, set(), list(paths)
    while stack:
        path = stack.pop()
        if path in seen:
            continue
        seen.add(path)
        try:
            quantity = resolve(model, path)
        except KeyError:
            unresolved.add(path)
            continue
        parents = [ref for ref in quantity.get("derived_from", []) if _is_model_path(ref)]
        stack.extend(parents)
        if not parents or quantity["status"] != "DERIVED":
            found[path] = quantity["status"]
    return [{"path": path, "status": found[path]} for path in sorted(found)], sorted(unresolved)


def _quantities(model: Dict[str, Any]) -> Iterator[Tuple[str, Dict[str, Any]]]:
    """Every quantity in the model, with the path resolve() accepts for it."""
    def walk(node: Any, path: str) -> Iterator[Tuple[str, Dict[str, Any]]]:
        if isinstance(node, dict):
            if {"value", "unit", "status", "source"} <= node.keys():
                yield path, node
                return
            for key, value in node.items():
                yield from walk(value, f"{path}/{key}")
    for collection, key in (("components", "component_id"), ("joints", "joint_id")):
        for entry in model.get(collection, []):
            yield from walk({k: v for k, v in entry.items() if k != key}, f"{collection}/{entry[key]}")
    yield from walk(model.get("design", {}), "design")


def lineage_problems(model: Dict[str, Any]) -> List[str]:
    """Why the model's recorded lineage cannot be followed, if it cannot.

    Every derived_from entry that names a model quantity must resolve, and no
    quantity may rest, directly or through others, on itself: either would
    leave the inputs of whatever depends on it unestablished.

    Example:
        >>> import json; from pathlib import Path
        >>> item = Path(__file__).resolve().parents[2] / "datasets/cad/robotic_joint_001"
        >>> lineage_problems(json.loads((item / "derived/engineering_model.json").read_text()))
        []
    """
    problems = []
    graph: Dict[str, List[str]] = {}
    for path, quantity in _quantities(model):
        parents = [ref for ref in quantity.get("derived_from", []) if _is_model_path(ref)]
        graph[path] = parents
    for path, parents in sorted(graph.items()):
        for parent in parents:
            if parent not in graph:
                problems.append(f"{path}: derived_from names {parent}, which is not a quantity in the model")
    # Iterative depth-first search: grey while on the stack, black when done.
    colour: Dict[str, int] = {}
    for start in sorted(graph):
        if colour.get(start):
            continue
        stack: List[Tuple[str, int]] = [(start, 0)]
        colour[start] = 1
        while stack:
            node, index = stack.pop()
            parents = [p for p in graph.get(node, []) if p in graph]
            if index < len(parents):
                stack.append((node, index + 1))
                parent = parents[index]
                if colour.get(parent) == 1:
                    problems.append(f"{parent}: its derived_from lineage leads back to itself")
                elif not colour.get(parent):
                    colour[parent] = 1
                    stack.append((parent, 0))
            else:
                colour[node] = 2
    return problems


def propagate(inputs: Sequence[Dict[str, str]], unresolved: Sequence[str], verdict: str,
              reason_code: Optional[str]) -> Optional[Tuple[str, str, List[str]]]:
    """What a check's inputs make of its verdict, before any other rewrite.

    Applied in order, the first that applies wins:

    1. a null-status input makes the check BLOCKED (MISSING_REQUIRED_INPUT),
       whatever it was;
    2. an input that does not resolve makes it INCONCLUSIVE
       (INPUT_NOT_RESOLVABLE), unless it was already BLOCKED;
    3. an AI_ASSUMPTION input turns the comparator's PASS or FAIL into
       INCONCLUSIVE (INPUT_IS_AI_ASSUMPTION): a value a model proposed can
       neither qualify nor condemn a design. A verdict the comparator did not
       reach -- a crash, a missing tool -- says nothing about the design and
       keeps its own reason.

    Returns:
        (verdict, reason_code, findings), or None when the inputs change nothing.

    Example:
        >>> propagate([{"path": "components/a/material/density", "status": "AI_ASSUMPTION"}], [],
        ...           "PASS", "CORNER_LIMITS_PASSED")[:2]
        ('INCONCLUSIVE', 'INPUT_IS_AI_ASSUMPTION')
        >>> propagate([{"path": "components/a/material/density", "status": "AI_ASSUMPTION"}], [],
        ...           "FAIL", "ADAPTER_EXECUTION_ERROR") is None
        True
        >>> propagate([{"path": "components/a/material/density", "status": "ESTIMATED"}], [],
        ...           "PASS", "CORNER_LIMITS_PASSED") is None
        True
    """
    missing = [f"{leaf['status']}: {leaf['path']}" for leaf in inputs if is_null(leaf["status"])]
    if missing:
        return "BLOCKED", "MISSING_REQUIRED_INPUT", missing
    if unresolved and verdict != "BLOCKED":
        return "INCONCLUSIVE", "INPUT_NOT_RESOLVABLE", [f"input not resolvable in the model: {path}" for path in unresolved]
    assumed = [f"AI_ASSUMPTION: {leaf['path']}" for leaf in inputs if leaf["status"] == "AI_ASSUMPTION"]
    if assumed and verdict in ("PASS", "FAIL") and reason_code in COMPARATOR_CODES:
        return "INCONCLUSIVE", "INPUT_IS_AI_ASSUMPTION", assumed
    return None


def run_environment(constraints: Optional[bytes]) -> Dict[str, Any]:
    """Where a run happens, without host paths: OS, architecture, interpreter,
    and the digest of the pinned dependency set. validate() stores it as
    hash-bound evidence, and results are built from that record, so they
    describe the run, never the process that regenerates them."""
    return {
        "os": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "constraints_sha256": hashlib.sha256(constraints).hexdigest() if constraints is not None else None,
    }


def environment(recorded: Mapping[str, Any], tools: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """A result's environment: the run's stored record, plus the version of
    every tool the receipt records for the run (not only the one a check ran,
    which the result's own simulator and simulator_version name)."""
    return {**{key: recorded[key] for key in ("os", "machine", "python", "constraints_sha256")},
            "tools": {tool["tool_id"]: tool["version"] for tool in tools}}


def _scenario_inputs(label: str, scenario: Mapping[str, Any]) -> List[Dict[str, str]]:
    """Numeric scenario parameters that override the model, e.g. a rated
    payload mass, listed as inputs of their own: their value is stated by
    the requirement or reference, so they are SPECIFIED by it."""
    return [{"path": f"scenario/{key}", "status": "SPECIFIED", "source": label}
            for key in sorted(scenario)
            if key != "name" and isinstance(scenario[key], (int, float)) and not isinstance(scenario[key], bool)]


def _number(value: Any) -> Optional[float]:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def build_results(
    *, sample_id: str, receipt: Dict[str, Any], receipt_sha256: str, requirements: Dict[str, Any],
    model: Dict[str, Any], model_sha256: str, adapter: Any, cases: Dict[Tuple[str, str], Dict[str, Any]],
    executions: Dict[str, Dict[str, Any]], environment_record: Dict[str, Any],
) -> Dict[str, Any]:
    """One result per requirement and reference, each from the receipt check that decided it.

    That check is the requirement's own (v3.<id> or v4.<id>) or, when the run
    recorded none -- no case document, or no derivation to compile one from
    -- the gate-level check that stands in for all of them. Its verdict is
    the result's status; nothing is filled in for a requirement no check
    covers.

    Args:
        sample_id: The dataset item.
        receipt: The run's receipt, as written.
        receipt_sha256: The digest of the receipt's bytes.
        requirements: The engineering-requirements document.
        model: The committed engineering model the cases ran on.
        model_sha256: The digest of its bytes.
        adapter: The sample's domain adapter (metrics, dependencies, components).
        cases: Compiled case by (gate, case id), from the committed case documents.
        executions: Execution record by check id, from the checks' evidence.
        environment_record: environment() of the run.

    Returns:
        A document conforming to engineering-model/v1/validation-results.

    Raises:
        ValueError: No check in the receipt decided a requirement.
    """
    checks = {check["check_id"]: check for gate in receipt["gates"] for check in gate["checks"]}
    metrics = adapter.metrics()
    results = []
    for gate, entries, key, stand_ins in (
            ("V3", requirements["reference_values"], "reference_id", ("v3.golden-cases", "v3.golden-manifest")),
            ("V4", requirements["requirements"], "requirement_id", ("v4.corners-cases", "v4.corners-manifest"))):
        for entry in entries:
            entry_id, metric = entry[key], entry["metric"]
            own = f"{gate.lower()}.{entry_id}"
            check_id = own if own in checks else next((c for c in stand_ins if c in checks), None)
            if check_id is None:
                raise ValueError(f"no check in the receipt decided {entry_id}")
            check = checks[check_id]
            case = cases.get((gate, entry_id))
            measured = _number((check.get("metrics") or {}).get(metric))
            measured_by: Optional[str] = check_id if measured is not None else None
            findings = list(check.get("findings", []))
            if measured is None and (check.get("metrics") or {}).get(metric) is not None:
                findings.append(f"metric {metric} is not a number: {check['metrics'][metric]!r}")
            limit = entry.get("limit", {})
            null_limit = ("quantity" in limit and not _unresolvable(model, limit["quantity"])
                          and is_null(resolve(model, limit["quantity"])["status"]))
            if measured is None and gate == "V4" and check.get("verdict") == "BLOCKED" and null_limit:
                # A requirement blocked only on its limit still has a measured side
                # when another check ran the same metric with the same arguments.
                try:
                    arguments = adapter.case_target(sample_id).arguments(entry["scenario"])
                except (KeyError, IndexError, TypeError, ValueError, AttributeError):
                    arguments = None
                for other_id, other in sorted(checks.items()) if arguments is not None else []:
                    gate_name, _, other_case_id = other_id.partition(".")
                    other_case = cases.get((gate_name.upper(), other_case_id))
                    value = _number((other.get("metrics") or {}).get(metric))
                    if (other_id != check_id and value is not None and other_case
                            and other_case.get("arguments") == arguments):
                        measured, measured_by = value, other_id
                        break
            if gate == "V3":
                expected = (case.get("expected_metrics") or {}).get(metric) if case else None
                operator, tolerance = "within", entry["absolute_tolerance"]
                expected_value = expected["value"] if expected else None
                # What the golden comparator evaluates: |actual - value| <= tolerance.
                bound = {"value": expected["value"], "absolute_tolerance": expected["absolute_tolerance"]} if expected else None
                kind, illustrative, component = "reference", False, None
                label = f"reference {entry_id}"
            else:
                operator, tolerance = entry["operator"], entry.get("tolerance", 0.0)
                bound = (case.get("metric_limits") or {}).get(metric) if case else None
                if "value" in limit:
                    expected_value = limit["value"]
                elif _unresolvable(model, limit["quantity"]):
                    expected_value = None
                else:
                    expected_value = _number(resolve(model, limit["quantity"])["value"])
                kind = "illustrative requirement" if entry["illustrative"] else "requirement"
                illustrative, component = entry["illustrative"], entry["component"]
                label = f"requirement {entry_id}" + (" (illustrative)" if illustrative else "")
            try:
                # The adapter reads the committed model and the entry; for an
                # entry V1 refused, or a model it cannot read, it may fail.
                inputs, unresolved = input_leaves(model, _input_paths(adapter, model, gate, entry))
                cad_components = adapter.components_for(model, metric)
            except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
                inputs, unresolved, cad_components = [], [], []
                findings.append(f"the inputs could not be established: {type(exc).__name__}: {exc}")
            findings += [f"input not resolvable in the model: {path}" for path in unresolved
                         if f"input not resolvable in the model: {path}" not in findings]
            execution = executions.get(check_id) or {}
            results.append({
                "validation_id": f"{sample_id}:{gate.lower()}.{entry_id}",
                "check_id": check_id,
                "domain": entry["domain"],
                "kind": kind,
                "requirement": entry_id,
                "title": entry["title"],
                "source": entry["source"],
                "metric": metric,
                "component": component,
                "cad_components": cad_components,
                "illustrative": illustrative,
                "status": check["verdict"],
                "reason_code": check.get("reason_code"),
                "findings": findings,
                "measured_value": measured,
                "measured_by": measured_by,
                "expected_value": expected_value,
                "operator": operator,
                "applied_bound": bound,
                "unit": entry["unit"],
                "tolerance": tolerance,
                "simulator": execution.get("adapter") or None,
                "simulator_version": execution.get("tool_version") or None,
                "configuration": {"command": execution.get("command"),
                                  "scenario": entry["scenario"], "seed": case.get("seed") if case else None},
                "model_version": model["model_version"],
                "model_sha256": model_sha256,
                "model_fidelity": metrics[metric].fidelity if metric in metrics else None,
                "inputs": inputs + _scenario_inputs(label, entry["scenario"]),
                "timestamp": receipt["completed_at"],
                "input_hash": receipt["source"]["input_sha256"],
                "source_dirty": receipt["source"]["dirty"],
                "environment": environment_record,
                "receipt_sha256": receipt_sha256,
                "evidence": [{"evidence_id": e["evidence_id"], "sha256": e["sha256"]} for e in check.get("evidence", [])],
            })
    return {"$schema": RESULTS_SCHEMA, "results_version": VERSION, "sample_id": sample_id,
            "receipt_sha256": receipt_sha256, "results": results}


def _input_paths(adapter: Any, model: Dict[str, Any], gate: str, entry: Dict[str, Any]) -> List[str]:
    """The model paths an entry's check rests on: a reference's derivation
    inputs, or a requirement's metric dependencies and its limit quantity."""
    if gate == "V3":
        return list(adapter.reference_inputs(model, entry["derivation"], entry["scenario"]))
    limit = entry["limit"]
    return list(adapter.dependencies(model, entry["metric"], entry["scenario"])) + (
        [limit["quantity"]] if "quantity" in limit else [])


def _unresolvable(model: Dict[str, Any], path: str) -> bool:
    try:
        resolve(model, path)
    except KeyError:
        return True
    return False
