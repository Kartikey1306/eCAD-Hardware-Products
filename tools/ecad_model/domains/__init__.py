"""Engineering domains, and the registry of the ones this platform can validate.

The registry is code, not data: a domain is AVAILABLE only if an adapter for
it is registered here. A sample never claims a status for itself; its
manifest records the status this registry gives it, and `check` regenerates
the manifest to catch a hand edit.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from .base import CaseTarget, DerivedFile, DomainAdapter, Extraction, Metric, SourceArtifact
from .mechanical import MechanicalAdapter

DOMAINS = (
    "mechanical",
    "electrical",
    "digital",
    "pcb",
    "power_electronics",
    "control",
    "electromagnetic",
    "thermal",
    "full_system",
)

REGISTRY: Dict[str, DomainAdapter] = {"mechanical": MechanicalAdapter()}


def adapter_for(domain: str, registry: Optional[Mapping[str, DomainAdapter]] = None) -> DomainAdapter:
    """The registered adapter for a sample's primary domain.

    Raises:
        ValueError: No adapter for the domain is registered, so nothing here
            can build a model from the sample's artefacts.

    Example:
        >>> adapter_for("mechanical").formats
        frozenset({'step'})
    """
    adapters = REGISTRY if registry is None else registry
    if domain not in adapters:
        raise ValueError(f"no {domain} adapter is registered in this platform: {domain} is NOT_IMPLEMENTED")
    return adapters[domain]


def domain_status(sources: Sequence[SourceArtifact], unknowns: Sequence[Dict[str, Any]],
                  registry: Optional[Mapping[str, DomainAdapter]] = None) -> List[Dict[str, str]]:
    """Each domain's status for one sample, in the specification's words.

    AVAILABLE        a registered adapter validates this domain from one of the
                     sample's artefacts;
    NOT_APPLICABLE   an adapter exists, but the sample has no artefact it reads;
    NOT_IMPLEMENTED  no adapter for the domain exists in this platform.

    Each reason also lists the sample's null-status inputs for the domain.

    Example:
        >>> [s["status"] for s in domain_status([SourceArtifact("a.step", "step")], [])][:2]
        ['AVAILABLE', 'NOT_IMPLEMENTED']
    """
    adapters = REGISTRY if registry is None else registry
    formats = {source.format for source in sources}
    missing: Dict[str, List[str]] = {}
    for entry in unknowns:
        for domain in entry["needed_by"]:
            missing.setdefault(domain, []).append(f"{entry['path']} ({entry['status']})")
    statuses = []
    for domain in DOMAINS:
        lacking = sorted(missing.get(domain, []))
        adapter = adapters.get(domain)
        if adapter is not None and adapter.formats & formats:
            status, reason = "AVAILABLE", adapter.description
            if lacking:
                reason += "; requirements resting on " + ", ".join(lacking) + " are BLOCKED"
        else:
            if adapter is not None:
                status = "NOT_APPLICABLE"
                reason = f"the {domain} adapter reads {', '.join(sorted(adapter.formats))}, which this sample does not have"
            else:
                status, reason = "NOT_IMPLEMENTED", f"no {domain} validator exists in this platform yet"
            if lacking:
                reason += "; this sample also lacks " + ", ".join(lacking)
        statuses.append({"domain": domain, "status": status, "reason": reason})
    return statuses


__all__ = [
    "CaseTarget", "DOMAINS", "DerivedFile", "DomainAdapter", "Extraction", "Metric", "REGISTRY",
    "SourceArtifact", "adapter_for", "domain_status",
]
