"""Deterministic requirements: compilation into the existing V3/V4 case format.

No model decides whether 4.8 N*m satisfies <= 5 N*m. Requirements compile into
the contract's case format, where its own comparators decide. Reference values
(V3) come from the domain's closed-form derivations, requirements (V4) bound a
metric the domain's cases produce. A limit, or a reference input, that has a
null status is not compiled at all: it is reported BLOCKED with the exact
missing paths and their statuses.

Nothing here knows a domain: which tool runs a case, on which inputs, and
which metrics exist with which units, all come from the domain adapter.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Sequence, Tuple

from .builder import resolve
from .quantity import is_null

VERSION = "1.0.0"  # of the compiled case documents
CASES_SCHEMA = "https://embeddedos.org/schemas/hardware-validation/v1/validation-cases.schema.json"

# The v1 receipt contract classifies checks into six domains that predate the
# engineering domains of issue #27. This mapping is a documented decision, not
# an equivalence.
CONTRACT_DOMAIN = {
    "mechanical": "integrated_physics",
    "electrical": "eda_circuit",
    "digital": "eda_circuit",
    "pcb": "physical_design",
    "power_electronics": "device_modeling",
    "control": "system_design",
    "electromagnetic": "device_modeling",
    "thermal": "integrated_physics",
    "full_system": "integrated_physics",
}


class ReferenceBlocked(ValueError):
    """A reference cannot be computed. paths lists the inputs that have no
    value, each {"path", "status"}; it is empty when the derivation itself does
    not apply to this design."""

    def __init__(self, message: str, paths: Sequence[Dict[str, str]]):
        super().__init__(message)
        self.paths = list(paths)


def _case(case_id: str, domain: str, target: Any, scenario: Dict[str, Any], requirement_id: str) -> Dict[str, Any]:
    return {
        "id": case_id,
        "adapter": target.adapter,
        "domain": CONTRACT_DOMAIN[domain],
        "inputs": list(target.inputs),
        "arguments": target.arguments(scenario),
        "timeout_seconds": target.timeout_seconds,
        "seed": 0,
        "requirement_ids": [requirement_id],
    }


def _check_unit(entry_id: str, metric: str, unit: str, metrics: Mapping[str, Any]) -> None:
    if metric not in metrics:
        raise ValueError(f"{entry_id}: the domain produces no metric {metric!r}")
    if metrics[metric].unit != unit:
        raise ValueError(f"{entry_id}: unit {unit} != the unit of {metric}, {metrics[metric].unit}")


def compile_cases(
    model: Dict[str, Any], requirements: Dict[str, Any], target: Any,
    reference_value: Callable[[Dict[str, Any], str, Dict[str, Any]], Tuple[float, List[str]]],
    metrics: Mapping[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """Compile requirements into V3 golden and V4 corner case documents.

    Case requirement_ids cite the contract's gate policies, which the v1
    requirements catalog defines; the engineering requirement each case
    implements is its case id, and the runner records both in the receipt.

    Args:
        model: The engineering model the limits and references resolve in.
        requirements: An engineering-requirements document.
        target: The domain's CaseTarget: tool adapter, inputs, arguments.
        reference_value: The domain's closed-form derivations.
        metrics: The domain's metric vocabulary; every requirement's and
            reference's unit must match its metric's.

    Returns:
        (golden cases, corner cases, blocked items). A blocked item names the
        requirement and the null-status model paths it rests on, each with
        its status; a reference whose derivation does not apply has none.

    Raises:
        ValueError: A unit differs from its metric's or its limit quantity's,
            a metric is one the domain does not produce, a limit quantity is
            not a single number, or two entries share an id (each id is a
            check id, and a result is keyed by it).

    Example:
        >>> import json; from pathlib import Path
        >>> from ecad_model.domains import adapter_for
        >>> item = Path(__file__).resolve().parents[2] / "datasets/cad/robotic_joint_001"
        >>> model = json.loads((item / "derived/engineering_model.json").read_text())
        >>> requirements = json.loads((item / "requirements/requirements.json").read_text())
        >>> mechanical = adapter_for("mechanical")
        >>> golden, corners, blocked = compile_cases(model, requirements, mechanical.case_target("joint"),
        ...                                          mechanical.reference_value, mechanical.metrics())
        >>> len(golden["cases"]) == len(requirements["reference_values"])
        True
        >>> unknown_limits = [r["requirement_id"] for r in requirements["requirements"]
        ...                   if "quantity" in r["limit"]
        ...                   and is_null(resolve(model, r["limit"]["quantity"])["status"])]
        >>> [entry["id"] for entry in blocked] == unknown_limits
        True
    """
    ids = [entry["reference_id"] for entry in requirements["reference_values"]] + [
        entry["requirement_id"] for entry in requirements["requirements"]]
    duplicated = sorted({entry_id for entry_id in ids if ids.count(entry_id) > 1})
    if duplicated:
        raise ValueError(f"reference and requirement ids must be unique: {', '.join(duplicated)} repeat")
    blocked: List[Dict[str, Any]] = []
    golden = []
    for reference in requirements["reference_values"]:
        _check_unit(reference["reference_id"], reference["metric"], reference["unit"], metrics)
        try:
            value, _used = reference_value(model, reference["derivation"], reference["scenario"])
        except ReferenceBlocked as exc:
            blocked.append(
                {"id": reference["reference_id"], "gate": "V3", "reason": str(exc), "missing_inputs": exc.paths}
            )
            continue
        case = _case(reference["reference_id"], reference["domain"], target, reference["scenario"], "POLICY:V3-GOLDEN")
        case["expected_metrics"] = {
            reference["metric"]: {"value": float(f"{value:.12g}"), "absolute_tolerance": reference["absolute_tolerance"]}
        }
        golden.append(case)

    corners = []
    for requirement in requirements["requirements"]:
        _check_unit(requirement["requirement_id"], requirement["metric"], requirement["unit"], metrics)
        limit = requirement["limit"]
        if "quantity" in limit:
            item = resolve(model, limit["quantity"])
            if is_null(item["status"]):
                blocked.append(
                    {
                        "id": requirement["requirement_id"],
                        "gate": "V4",
                        "reason": f"the limit is the model quantity {limit['quantity']}, which is {item['status']}",
                        "missing_inputs": [{"path": limit["quantity"], "status": item["status"]}],
                    }
                )
                continue
            if item["unit"] != requirement["unit"]:
                raise ValueError(
                    f"{requirement['requirement_id']}: limit unit {item['unit']} != requirement unit {requirement['unit']}"
                )
            bound = item["value"]
            if not isinstance(bound, (int, float)) or isinstance(bound, bool):
                raise ValueError(f"{requirement['requirement_id']}: the limit {limit['quantity']} is not a single number")
        else:
            bound = limit["value"]
        case = _case(
            requirement["requirement_id"], requirement["domain"], target, requirement["scenario"], "POLICY:V4-CORNER"
        )
        # The contract's limits are bare bounds, so a tolerance is folded into
        # the bound here; the requirement keeps the limit it states.
        tolerance = requirement.get("tolerance", 0.0)
        case["metric_limits"] = {
            requirement["metric"]: ({"maximum": bound + tolerance} if requirement["operator"] == "<="
                                    else {"minimum": bound - tolerance})
        }
        corners.append(case)

    def document(gate: str, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {"$schema": CASES_SCHEMA, "contract_version": "1.0.0", "gate": gate, "cases": cases}

    return document("V3", golden), document("V4", corners), blocked
