"""Engineering domains, and the registry of the ones this platform can validate.

The registry is code, not data: a domain is AVAILABLE only if an adapter for
it is registered here. A sample never claims a status for itself; its
manifest records the status this registry gives it, and `check` regenerates
the manifest to catch a hand edit.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from .base import CaseTarget, DerivedFile, DomainAdapter, Extraction, Metric, SourceArtifact
from .digital import DigitalAdapter
from .electrical import ElectricalAdapter
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

REGISTRY: Dict[str, DomainAdapter] = {"mechanical": MechanicalAdapter(), "electrical": ElectricalAdapter(),
                                      "digital": DigitalAdapter()}


class DomainNotImplemented(ValueError):
    """No adapter for the domain is registered: nothing here can build a model from its artefacts."""


def adapter_for(domain: str, registry: Optional[Mapping[str, DomainAdapter]] = None) -> DomainAdapter:
    """The registered adapter for a sample's primary domain.

    Raises:
        DomainNotImplemented: No adapter for the domain is registered, so
            nothing here can build a model from the sample's artefacts.

    Example:
        >>> adapter_for("mechanical").formats, adapter_for("digital").formats
        (frozenset({'step'}), frozenset({'verilog'}))
    """
    adapters = REGISTRY if registry is None else registry
    if domain not in adapters:
        raise DomainNotImplemented(f"no {domain} adapter is registered in this platform: {domain} is NOT_IMPLEMENTED")
    return adapters[domain]


def domain_status(primary: str, sources: Sequence[SourceArtifact], unknowns: Sequence[Dict[str, Any]],
                  registry: Optional[Mapping[str, DomainAdapter]] = None) -> List[Dict[str, str]]:
    """Each domain's status for one sample, in the specification's words.

    AVAILABLE        the sample's primary domain, whose registered adapter
                     validates it from one of the sample's artefacts: the only
                     adapter the pipeline runs for a sample;
    NOT_APPLICABLE   an adapter exists but is not run for this sample: the
                     sample has no artefact it reads, or the domain is not the
                     sample's primary domain;
    NOT_IMPLEMENTED  no adapter for the domain exists in this platform.

    Each reason also lists the sample's null-status inputs for the domain.

    Args:
        primary: The sample's primary domain, from its provenance.
        sources: The sample's declared source artefacts.
        unknowns: The engineering model's unknowns index.
        registry: Domain adapters in place of the platform's (tests only).

    Example:
        >>> [s["status"] for s in domain_status("mechanical", [SourceArtifact("a.step", "step")], [])][:2]
        ['AVAILABLE', 'NOT_APPLICABLE']
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
        if adapter is not None and domain == primary and adapter.formats & formats:
            status, reason = "AVAILABLE", adapter.description
            if lacking:
                reason += "; requirements resting on " + ", ".join(lacking) + " are BLOCKED"
        else:
            if adapter is not None and not adapter.formats & formats:
                status = "NOT_APPLICABLE"
                reason = f"the {domain} adapter reads {', '.join(sorted(adapter.formats))}, which this sample does not have"
            elif adapter is not None:
                # Only the primary domain's adapter runs: its artefacts here are
                # validated by nothing, so the domain is not claimed.
                status = "NOT_APPLICABLE"
                reason = (f"the {domain} adapter runs only for samples whose primary domain is {domain}; "
                          f"this sample's is {primary}, so its {domain} artefacts are not validated")
            else:
                status, reason = "NOT_IMPLEMENTED", f"no {domain} validator exists in this platform yet"
            if lacking:
                reason += "; this sample also lacks " + ", ".join(lacking)
        statuses.append({"domain": domain, "status": status, "reason": reason})
    return statuses


__all__ = [
    "CaseTarget", "DOMAINS", "DerivedFile", "DomainAdapter", "DomainNotImplemented", "Extraction", "Metric", "REGISTRY",
    "SourceArtifact", "adapter_for", "domain_status",
]
