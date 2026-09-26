"""Engineering quantities that carry their own provenance.

A quantity is a plain dict so it serialises canonically, but it is only ever
built through these constructors, which enforce the rules the schema states:
the value is null if and only if the status is a null status, each status
carries what makes it checkable, and DERIVED names its inputs.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

Number = Union[int, float]
Value = Union[None, Number, List[Number], List[List[Number]]]


class Status(str, Enum):
    MEASURED = "MEASURED"
    SPECIFIED = "SPECIFIED"
    DERIVED = "DERIVED"
    SIMULATED = "SIMULATED"
    ESTIMATED = "ESTIMATED"
    AI_ASSUMPTION = "AI_ASSUMPTION"
    UNKNOWN = "UNKNOWN"              # nobody has established it, including "not yet selected"
    UNSPECIFIED = "UNSPECIFIED"      # the governing source was consulted and is silent
    NOT_AVAILABLE = "NOT_AVAILABLE"  # exists in a source this project cannot access or use


# The statuses whose value is null. Every "is this value missing?" test in the
# package goes through is_null(), so a new null status cannot slip past one site.
NULL_STATUSES = frozenset({Status.UNKNOWN, Status.UNSPECIFIED, Status.NOT_AVAILABLE})

# What each status must carry for a checker, not only its author, to tell the
# statuses apart. Mirrored in engineering-model/v1/common.schema.json.
_NOTE_REQUIRED = frozenset({Status.UNKNOWN, Status.NOT_AVAILABLE, Status.ESTIMATED})
_SOURCE_KIND = {Status.MEASURED: "measurement", Status.SIMULATED: "simulation", Status.AI_ASSUMPTION: "ai"}


class MissingInput(ValueError):
    """A value a domain model needs has a null status.

    That is a missing input, not a defect in the design: validation reports it
    BLOCKED with MISSING_REQUIRED_INPUT, never FAIL. Domain model writers raise
    a subclass of it.

    Attributes:
        inputs: The null-status model quantities, each {"path", "status"}.
    """

    def __init__(self, message: str, inputs: Sequence[Dict[str, str]] = ()):
        super().__init__(message)
        self.inputs = [dict(entry) for entry in inputs]


def is_null(status: Union[Status, str]) -> bool:
    """True when a quantity of this status has no value.

    Args:
        status: A Status, or its string form as serialised.

    Returns:
        Whether the status is one of UNKNOWN, UNSPECIFIED and NOT_AVAILABLE.

    Example:
        >>> [is_null(s) for s in ("UNKNOWN", "UNSPECIFIED", "NOT_AVAILABLE", "ESTIMATED")]
        [True, True, True, False]
    """
    return Status(status) in NULL_STATUSES


def source(kind: str, ref: str, sha256: Optional[str] = None) -> Dict[str, str]:
    """Describe where a value came from.

    Args:
        kind: One of the source kinds in engineering-model/v1/common.schema.json
            (cad, datasheet, product_specification, design_annotation,
            requirement, handbook, ...). A datasheet is a manufacturer's; a
            product_specification is a first-party product sheet in this
            repository, which is design intent, not measured part data.
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
        value: A finite number, vector or matrix; None exactly when the
            status is a null status (UNKNOWN, UNSPECIFIED, NOT_AVAILABLE).
        unit: Unit symbol, e.g. "kg", "N*m", "1" for dimensionless.
        status: Epistemic status of the value.
        origin: Where it came from, from source().
        derived_from: Model paths or artifact references it was computed
            from. Required, and non-empty, when status is DERIVED.
        note: Free-text context. Required for UNKNOWN and NOT_AVAILABLE
            (why there is no value) and for ESTIMATED (what the estimate
            rests on).

    Returns:
        The quantity as a plain dict, ready to serialise.

    Raises:
        ValueError: value is None without a null status (or the reverse),
            DERIVED names no inputs, a status lacks what makes it checkable
            (a note; UNSPECIFIED's cited document hash; the source kind of
            MEASURED, SIMULATED or AI_ASSUMPTION), or the value is not finite.

    Example:
        >>> quantity(2.5, "kg", Status.SPECIFIED, source("datasheet", "d.md"))["status"]
        'SPECIFIED'
        >>> quantity(None, "kg", Status.SPECIFIED, source("datasheet", "d.md"))
        Traceback (most recent call last):
        ...
        ValueError: a value is null if and only if its status is UNKNOWN, UNSPECIFIED or NOT_AVAILABLE (got SPECIFIED)
    """
    inputs = list(dict.fromkeys(derived_from))
    if (value is None) != (status in NULL_STATUSES):
        raise ValueError("a value is null if and only if its status is UNKNOWN, UNSPECIFIED or NOT_AVAILABLE "
                         f"(got {status.value})")
    if status is Status.DERIVED and not inputs:
        raise ValueError("a DERIVED quantity must name the values it was derived from")
    if status in _NOTE_REQUIRED and not note:
        raise ValueError(f"a {status.value} quantity must say why in its note")
    if status is Status.UNSPECIFIED and "sha256" not in origin:
        raise ValueError("an UNSPECIFIED quantity must cite, by hash, the document that is silent on it")
    if status in _SOURCE_KIND and origin.get("kind") != _SOURCE_KIND[status]:
        raise ValueError(f"a {status.value} quantity must have source kind {_SOURCE_KIND[status]!r}")
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

