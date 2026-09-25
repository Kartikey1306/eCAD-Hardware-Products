"""Engineering quantities that carry their own provenance.

A quantity is a plain dict so it serialises canonically, but it is only ever
built through these constructors, which enforce the rules the schema states:
UNKNOWN if and only if the value is null, and DERIVED only with named inputs.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Union

Number = Union[int, float]
Value = Union[None, Number, List[Number], List[List[Number]]]


class Status(str, Enum):
    MEASURED = "MEASURED"
    SPECIFIED = "SPECIFIED"
    DERIVED = "DERIVED"
    SIMULATED = "SIMULATED"
    ESTIMATED = "ESTIMATED"
    AI_ASSUMPTION = "AI_ASSUMPTION"
    UNKNOWN = "UNKNOWN"


def source(kind: str, ref: str, sha256: Optional[str] = None) -> Dict[str, str]:
    """Describe where a value came from.

    Args:
        kind: One of the source kinds in engineering-model/v1/common.schema.json
            (cad, datasheet, design_annotation, requirement, handbook, ...).
        ref: What was consulted: a repository path, or a named reference.
        sha256: Digest of the referenced bytes, when they are a file.

    Returns:
        A source object for a quantity.

    Example:
        >>> source("datasheet", "robot_components/product_datasheet.md")
        {'kind': 'datasheet', 'ref': 'robot_components/product_datasheet.md'}
    """
    value = {"kind": kind, "ref": ref}
    if sha256 is not None:
        value["sha256"] = sha256
    return value


def _finite(value: Value) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    return all(_finite(item) for item in value)


def quantity(
    value: Value,
    unit: str,
    status: Status,
    origin: Dict[str, str],
    *,
    derived_from: Iterable[str] = (),
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a quantity, refusing any combination the contract forbids.

    Args:
        value: A finite number, vector or matrix; None only when UNKNOWN.
        unit: Unit symbol, e.g. "kg", "N*m", "1" for dimensionless.
        status: Epistemic status of the value.
        origin: Where it came from, from source().
        derived_from: Model paths or artifact references it was computed
            from. Required, and non-empty, when status is DERIVED.
        note: Free-text context, e.g. why a value is UNKNOWN.

    Returns:
        The quantity as a plain dict, ready to serialise.

    Raises:
        ValueError: value is None without UNKNOWN (or the reverse), DERIVED
            names no inputs, or the value is not finite.

    Example:
        >>> quantity(2.5, "kg", Status.SPECIFIED, source("datasheet", "d.md"))["status"]
        'SPECIFIED'
        >>> quantity(None, "kg", Status.SPECIFIED, source("datasheet", "d.md"))
        Traceback (most recent call last):
        ...
        ValueError: a value is null if and only if its status is UNKNOWN (got SPECIFIED)
    """
    inputs = list(dict.fromkeys(derived_from))
    if (value is None) != (status is Status.UNKNOWN):
        raise ValueError(f"a value is null if and only if its status is UNKNOWN (got {status.value})")
    if status is Status.DERIVED and not inputs:
        raise ValueError("a DERIVED quantity must name the values it was derived from")
    if not _finite(value):
        raise ValueError(f"quantity value must be finite numbers, got {value!r}")
    result: Dict[str, Any] = {"value": value, "unit": unit, "status": status.value, "source": origin}
    if inputs:
        result["derived_from"] = inputs
    if note:
        result["note"] = note
    return result


def unknown(unit: str, origin: Dict[str, str], note: str) -> Dict[str, Any]:
    """A value nobody knows, with the reason recorded instead of a guess.

    Args:
        unit: The unit the value would have.
        origin: Who established that it is unknown.
        note: Why it is unknown, e.g. "no motor is selected".

    Returns:
        An UNKNOWN quantity whose value is None.

    Example:
        >>> unknown("N*m/A", source("design_annotation", "a.json"), "no motor is selected")["value"] is None
        True
    """
    return quantity(None, unit, Status.UNKNOWN, origin, note=note)


def rounded(value: Any, digits: int = 12) -> Any:
    """Round to significant digits so derived artifacts are stable across platforms.

    Args:
        value: A number, nested list of numbers, or None.
        digits: Significant digits to keep.

    Returns:
        The value with every number rounded; None stays None.

    Example:
        >>> rounded(0.1 + 0.2)
        0.3
        >>> rounded([[1/3, 2.0]], digits=3)
        [[0.333, 2.0]]
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value == 0:
            return 0.0
        return float(f"{value:.{digits}g}")
    return [rounded(item, digits) for item in value]

