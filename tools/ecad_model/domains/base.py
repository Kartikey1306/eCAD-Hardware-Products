"""The interface an engineering domain implements to join the dataset pipeline.

The dataset runner (ecad_model.dataset) knows nothing about any simulator,
file format or domain model. A domain adapter supplies all of it:

    input requirements   formats          which source artefacts it reads
    engineering model    extract()        the model (and any raw extraction) from them
    domain model         write_models()   the files its simulator runs on
    simulator            case_target()    the tool adapter and inputs of each case
    reference values     reference_value() closed-form references for V3
    metrics              metrics()        every metric it produces, with unit and fidelity
    V1 / V2              sanity_problems(), invariant_problems()

Running cases and deciding verdicts stay with the existing case engine and its
deterministic comparators, so no adapter can decide whether 4.8 <= 5.0.

Stable since the electrical domain: two production domains use it, one
CAD-first (mechanical) and one artefact-first (electrical). Changes since the
foundation: `Extraction.producer`. A further change lists its reason and the
matching change to every registered adapter and to the test fixture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, List, Protocol, Sequence, Tuple

FIDELITIES = frozenset({"EXACT_GEOMETRY", "REDUCED_ORDER", "SIMPLIFIED", "EMPIRICAL"})
MEDIA_TYPES = {".json": "application/json", ".xml": "application/xml", ".step": "application/step",
               ".py": "text/x-python", ".v": "text/x-verilog", ".sv": "text/x-systemverilog",
               ".cir": "text/x-spice", ".md": "text/markdown"}
COMPARATORS = frozenset({"json", "numeric_attributes", "exact"})


@dataclass(frozen=True)
class SourceArtifact:
    """One source artefact of a sample, as its provenance declares it."""

    path: str    # sample-relative
    format: str  # e.g. "step", "verilog"


@dataclass(frozen=True)
class DerivedFile:
    """A file the pipeline generates, with everything the manifest records about it.

    comparator says how reproduction is judged: "json" compares numbers within
    tolerance, "numeric_attributes" compares an XML text exactly outside its
    numeric attribute values, "exact" compares bytes.
    """

    path: str
    data: bytes
    role: str
    media_type: str
    producer: str
    version: str
    derived_from: Tuple[str, ...]
    comparator: str = "json"

    def __post_init__(self) -> None:
        if self.comparator not in COMPARATORS:
            raise ValueError(f"{self.path}: unknown comparator {self.comparator!r}")


@dataclass(frozen=True)
class Metric:
    """A metric a domain's cases produce: its unit and the fidelity of the model behind it."""

    unit: str
    fidelity: str
    description: str = ""

    def __post_init__(self) -> None:
        if self.fidelity not in FIDELITIES:
            raise ValueError(f"unknown model fidelity {self.fidelity!r}")


@dataclass
class Extraction:
    """What a domain reads from a sample: its raw extraction files and the model.

    producer is the (tool, version) that wrote the model, recorded as the
    model's producer and as the manifest's versions.engineering_model. It
    has no default, so no adapter inherits another domain's producer.
    """

    model: Dict[str, Any]
    producer: Tuple[str, str]
    files: List[DerivedFile] = field(default_factory=list)
    tools: List[Dict[str, Any]] = field(default_factory=list)  # receipt tool records of what shaped it


@dataclass(frozen=True)
class CaseTarget:
    """How a compiled case runs: the tool adapter, its inputs, and its arguments."""

    adapter: str
    inputs: Tuple[str, ...]
    arguments: Callable[[Dict[str, Any]], List[str]]
    timeout_seconds: int = 300


class DomainAdapter(Protocol):
    domain: str
    formats: FrozenSet[str]
    description: str  # what the domain validates, for the manifest's AVAILABLE reason

    def extract(self, root: Path, sources: Sequence[SourceArtifact], annotations: Dict[str, Any],
                refs: Dict[str, str]) -> Extraction: ...

    def write_models(self, model: Dict[str, Any], sample_id: str) -> List[DerivedFile]: ...

    def case_target(self, sample_id: str) -> CaseTarget: ...

    def reference_value(self, model: Dict[str, Any], derivation: str,
                        scenario: Dict[str, Any]) -> Tuple[float, List[str]]: ...

    def metrics(self) -> Dict[str, Metric]: ...

    def sanity_problems(self, model: Dict[str, Any]) -> List[str]: ...

    def invariant_problems(self, model: Dict[str, Any], extraction_files: Dict[str, Any],
                           domain_models: Dict[str, bytes]) -> List[str]: ...

    def simulation_files(self, root: Path) -> List[str]: ...

    def document_schemas(self) -> Dict[str, str]: ...  # schema of each extraction file, checked at V0

    def check_requirements(self, requirements: Dict[str, Any]) -> None: ...  # raises on scenarios or derivations it lacks

    def dependencies(self, model: Dict[str, Any], metric: str,
                     scenario: Dict[str, Any]) -> List[str]: ...  # model paths a simulated metric depends on

    def reference_inputs(self, model: Dict[str, Any], derivation: str,
                         scenario: Dict[str, Any]) -> List[str]: ...  # model paths a reference derivation reads

    def components_for(self, model: Dict[str, Any], metric: str) -> List[str]: ...  # source parts a metric depends on
