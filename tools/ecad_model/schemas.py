"""Validate documents against the engineering-model and cad-dataset schemas."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Tuple

from jsonschema import Draft7Validator, FormatChecker, RefResolver

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FAMILIES = ("engineering-model/v1", "cad-dataset/v1", "hardware-validation/v1")


@lru_cache(maxsize=1)
def _store() -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    """Load every schema in every family, keyed by file name and by $id.

    The engineering-model family reuses hardware-validation/v1 identifiers,
    paths and hashes by absolute $id, so all families share one resolver
    store and no reference is ever fetched over the network.
    """
    by_name: Dict[str, Dict[str, Any]] = {}
    by_id: Dict[str, Dict[str, Any]] = {}
    for family in FAMILIES:
        for path in sorted((REPOSITORY_ROOT / "schemas" / family).glob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            by_name[f"{family}/{path.name}"] = schema
            by_id[schema["$id"]] = schema
    return by_name, by_id


def validate(document: Dict[str, Any], schema: str) -> None:
    """Validate a document against one of the repository's JSON schemas.

    Args:
        document: The parsed JSON document.
        schema: Schema path without its suffix, e.g.
            "engineering-model/v1/engineering-model".

    Raises:
        ValueError: The schema does not exist, or the document violates it.
            The message names up to ten violations with their paths.

    Example:
        >>> validate({}, "engineering-model/v1/design-annotations")  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        ValueError: engineering-model/v1/design-annotations.schema.json validation failed: <root>: ...
    """
    by_name, by_id = _store()
    key = f"{schema}.schema.json"
    if key not in by_name:
        raise ValueError(f"schema is missing: {key}")
    validator = Draft7Validator(
        by_name[key],
        resolver=RefResolver.from_schema(by_name[key], store=by_id),
        format_checker=FormatChecker(),
    )
    try:
        errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
        detail = "; ".join(
            f"{'/'.join(str(item) for item in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors[:10]
        )
    except RecursionError:
        # A document nested deeper than the validator can walk (or describe) is
        # malformed input, reported like any other violation.
        raise ValueError(f"{key} validation failed: the document is nested too deeply to check") from None
    if errors:
        raise ValueError(f"{key} validation failed: {detail}")
