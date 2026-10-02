"""The digital domain: synchronous RTL, a harness Icarus Verilog runs, closed-form references.

The Verilog sources are the source of truth, read by the strict grammar of
ecad_model.verilog. Everything the dataset runner must not know about the
digital domain lives here: how the sources and their annotations become the
engineering model (each module instance a component whose hdl member records
its module, ports and parameters, and carries the module's text verbatim),
which design class the domain validates, the one simulation file Icarus runs,
the nine metrics and their closed-form references, and the checks of V1 and
V2. Icarus never compiles the sources: it compiles a file written from the
model -- each leaf module's text as the model carries it, bound to its source
by hash, then a harness -- so the chain is sources -> engineering model ->
simulation file -> simulator.

One design class is validated, and nothing else is accepted: the UART 8N1
loopback, a transmitter and a receiver with the port and parameter
interfaces of rtl/uart_tx.v and rtl/uart_rx.v, wired transmitter to receiver
by a declarative top. The top states the clock half-period, the reset
length, the parameters each instance receives and the bytes sent, and holds
no behaviour: the harness this module writes drives the clock and the
stimulus and makes every measurement, sampling each signal on the falling
clock edge, half a cycle after the rising edge the design acts on.

Every metric is SIMPLIFIED: the simulation is exact at the logic level of the
RTL as written, and idealises the hardware -- a jitter-free clock, zero gate
and wire delay, no setup or hold, no metastability, an ideal line. The
references are computed from the model's values and the class's interface
contract alone (D_t = CLK_FREQ // BAUD_RATE, D_r = CLK_FREQ // (BAUD_RATE *
OVERSAMPLE)), never from the RTL's own localparam expressions, so the RTL is
not checked against itself.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple, Union

from .. import HDL_MODEL_VERSION, verilog
from ..builder import SCHEMA_ID, index_unknowns, resolve
from ..importers.base import ExtractionError, UnsupportedFormat, regular_file
from ..quantity import Status, is_null, quantity, source
from ..requirements import ReferenceBlocked
from ..schemas import validate as validate_schema
from .base import CaseTarget, DerivedFile, Extraction, Metric, SourceArtifact

VERSION = "1.0.0"  # of this adapter's derived outputs: the simulation file, its harness and the case target
MODEL_BUILDER_VERSION = "1.0.0"  # of the engineering models extract() writes

# Method constants, versioned by VERSION and written into the hash-bound simulation file.
FRAME_BITS = 10  # 8N1: a start bit, 8 data bits, a stop bit
RUN_BITS_PER_FRAME = 12  # a frame and its turnaround, in the run length END
MIN_BIT_CYCLES = 16  # the floor of a bit period in END
MAX_CYCLES = 2_000_000  # END may not exceed it (resource guard, rule C7)
MAX_BYTES = 16  # the most TX_BYTE_i a top may state (rule C6)
CASE_TIMEOUT_S = 60  # per Icarus step: the compile and the run each get it
HARNESS_TASKS = verilog.HARNESS_TASKS  # the only system identifiers the harness uses
HARNESS_SEPARATOR = "// ---- harness ----"

# Every metric the harness measures, in the order it prints them.
METRICS = {
    "clock_period_s": Metric("s", "SIMPLIFIED", "time between the harness clock's first two rising edges"),
    "tx_idle_after_reset": Metric("1", "SIMPLIFIED", "1 if the line and tx_ready are high at the first falling edge "
                                                     "after reset is released, else 0"),
    "tx_bit_cycles": Metric("cycles", "SIMPLIFIED", "clock cycles of the line's first low run: the start bit, when the "
                                                    "first byte is odd"),
    "tx_bit_rate_bd": Metric("Bd", "SIMPLIFIED", "1 / the simulated duration of that low run"),
    "tx_frame_cycles": Metric("cycles", "SIMPLIFIED", "clock cycles tx_ready stays low for the first byte"),
    "rx_bytes_received": Metric("1", "SIMPLIFIED", "rx_valid pulses before the run ends"),
    "rx_bit_errors": Metric("bits", "SIMPLIFIED", "bits of the bytes sent not received as sent: each bit that differs "
                                                  "between a byte sent and the byte received in its place, and all 8 "
                                                  "of each byte sent that never arrived"),
    "rx_framing_errors": Metric("1", "SIMPLIFIED", "rx_error pulses before the run ends; not reported when there are "
                                                   "none and a byte sent never arrived"),
    "outputs_unknown_after_reset": Metric("1", "SIMPLIFIED", "outputs with an X or Z bit at the first falling edge "
                                                             "after reset is released (4-state simulation only)"),
}
# The metric each closed form computes.
DERIVATION_METRIC = {
    "clock_period": "clock_period_s", "idle_high_after_reset": "tx_idle_after_reset",
    "bit_period_cycles": "tx_bit_cycles", "bit_rate": "tx_bit_rate_bd", "frame_cycles": "tx_frame_cycles",
    "bytes_sent": "rx_bytes_received", "lossless_loopback": "rx_bit_errors", "no_framing_errors": "rx_framing_errors",
}
# Every digital facet a model of this domain may carry, with its unit.
FACET_UNITS = {
    "clock_half_period": "s", "min_clock_period": "s",
    "reset_cycles": "cycles",
    "tx_bytes": "1", "byte_count": "1", "oversample": "1",
    "clk_freq": "Hz",
    "baud_rate": "Bd",
}
# The class's interface: each port's direction and width, and the parameters, with the facet that holds each.
TRANSMITTER_PORTS = {"clk": ("input", 1), "rst_n": ("input", 1), "tx_data": ("input", 8), "tx_valid": ("input", 1),
                     "tx_ready": ("output", 1), "tx": ("output", 1)}
RECEIVER_PORTS = {"clk": ("input", 1), "rst_n": ("input", 1), "rx": ("input", 1), "rx_data": ("output", 8),
                  "rx_valid": ("output", 1), "rx_error": ("output", 1)}
PARAMETER_FACETS = {"BAUD_RATE": "baud_rate", "CLK_FREQ": "clk_freq"}
TOP_FACETS = ("clock_half_period", "reset_cycles", "tx_bytes", "byte_count")
NETWORK_CLASS = "the UART 8N1 loopback the digital domain validates"
_NOT_A_PART = "not a rating or measurement of any part"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9]")  # a component id's first character (hardware-validation identifier)

# (instance name, module, ports {name: (direction, width)}, parameters, overridden parameters,
# connections {port: signal}): an instance as the class rules see it, in a source or in a model.
_Shape = Tuple[str, str, Dict[str, Tuple[str, int]], FrozenSet[str], FrozenSet[str], Dict[str, str]]


@dataclass(frozen=True)
class Roles:
    """The components and signals of the UART 8N1 loopback, by role.

    top, transmitter and receiver are the model's components; the rest are
    the names of the top's signals: the clock and reset both instances share,
    the transmitter's data and valid inputs and ready output, the line from
    the transmitter's tx to the receiver's rx, and the receiver's outputs.
    """

    top: Dict[str, Any]
    transmitter: Dict[str, Any]
    receiver: Dict[str, Any]
    clock: str
    reset: str
    data: str
    valid: str
    ready: str
    line: str
    rx_data: str
    rx_valid: str
    rx_error: str


def _refusal(where: str, rule: str, why: str) -> ExtractionError:
    return ExtractionError("rejected", f"{where}: not {NETWORK_CLASS}: rule {rule}: {why}")


def _interface(ports: Dict[str, Tuple[str, int]], parameters: FrozenSet[str]) -> str:
    """An interface as the refusals print it: "inputs clk:1, ...; outputs ...; parameters ..."."""
    parts = [f"{direction}s " + ", ".join(f"{name}:{width}" for name, (way, width) in ports.items() if way == direction)
             for direction in ("input", "output") if any(way == direction for way, _ in ports.values())]
    return "; ".join([*parts, "parameters " + (", ".join(sorted(parameters)) or "none")])


def _roles(where: str, instances: Sequence[_Shape], kinds: Dict[str, str]) -> Tuple[int, int, Dict[str, str]]:
    """Rules C1, C2, C3's interface, C4's parameter set and C5 on instances seen in a source or in a model.

    Returns:
        (the transmitter's index, the receiver's index, each signal role's signal name).
    """
    parameters = frozenset(PARAMETER_FACETS)
    if len(instances) != 2 or instances[0][1] == instances[1][1]:
        found = ", ".join(f"{name} ({module})" for name, module, *_ in instances) or "nothing"
        raise _refusal(where, "C1", f"the top instantiates {found}; the class is exactly two instances of two "
                                    "different modules, a transmitter and a receiver")
    transmitters = [index for index, shape in enumerate(instances)
                    if shape[2] == TRANSMITTER_PORTS and shape[3] == parameters]
    if not transmitters:
        found = "; ".join(f"{name}'s {module} declares {_interface(ports, declared)}"
                          for name, module, ports, declared, *_ in instances)
        raise _refusal(where, "C2", f"no instance's module declares exactly the transmitter's interface, "
                                    f"{_interface(TRANSMITTER_PORTS, parameters)}: {found}")
    tx = transmitters[0]
    rx = 1 - tx
    name, module, ports, declared, _, _ = instances[rx]
    if ports != RECEIVER_PORTS or declared != parameters:
        raise _refusal(where, "C3", f"{name}'s {module} declares {_interface(ports, declared)}, not exactly the "
                                    f"receiver's interface, {_interface(RECEIVER_PORTS, parameters)}")
    for name, _, _, _, overridden, _ in instances:
        if overridden != parameters:
            raise _refusal(where, "C4", f"{name} overrides {', '.join(sorted(overridden)) or 'nothing'}; each instance "
                                        "overrides both CLK_FREQ and BAUD_RATE by name, with a top localparam or a "
                                        "decimal literal")
    tx_name, tx_ports = instances[tx][0], instances[tx][5]
    rx_name, rx_ports = instances[rx][0], instances[rx][5]
    users: Dict[str, List[str]] = {}
    for name, connections in ((tx_name, tx_ports), (rx_name, rx_ports)):
        for port, signal in connections.items():
            users.setdefault(signal, []).append(f"{name}.{port}")

    def only(signal: str, kind: str, ports: Sequence[str], role: str) -> str:
        if sorted(users.get(signal, [])) != sorted(ports) or kinds.get(signal) != kind:
            raise _refusal(where, "C5", f"{role} must be one {kind} that connects {' and '.join(ports)} and no other "
                                        f"port; {signal} is a {kinds.get(signal, 'undeclared signal')} that connects "
                                        f"{', '.join(sorted(users.get(signal, [])))}")
        return signal

    # The line first: a receiver fed from any other signal is named as a line that is not shared.
    signals = {
        "line": only(tx_ports["tx"], "wire", [f"{tx_name}.tx", f"{rx_name}.rx"],
                     "the line, which the transmitter's tx and the receiver's rx share,"),
        "clock": only(tx_ports["clk"], "reg", [f"{tx_name}.clk", f"{rx_name}.clk"], "the clock"),
        "reset": only(tx_ports["rst_n"], "reg", [f"{tx_name}.rst_n", f"{rx_name}.rst_n"], "the reset"),
        "data": only(tx_ports["tx_data"], "reg", [f"{tx_name}.tx_data"], "the transmitter's data"),
        "valid": only(tx_ports["tx_valid"], "reg", [f"{tx_name}.tx_valid"], "the transmitter's valid"),
        "ready": only(tx_ports["tx_ready"], "wire", [f"{tx_name}.tx_ready"], "the transmitter's ready"),
        "rx_data": only(rx_ports["rx_data"], "wire", [f"{rx_name}.rx_data"], "the receiver's data"),
        "rx_valid": only(rx_ports["rx_valid"], "wire", [f"{rx_name}.rx_valid"], "the receiver's valid"),
        "rx_error": only(rx_ports["rx_error"], "wire", [f"{rx_name}.rx_error"], "the receiver's error"),
    }
    unconnected = sorted(set(kinds) - set(users))
    if unconnected:
        raise _refusal(where, "C5", f"{', '.join(unconnected)} is declared but connects no port; every declared signal "
                                    "is connected")
    return tx, rx, signals


def _classify(design: verilog.Design) -> Tuple[verilog.Instance, verilog.Instance]:
    """Rules C1-C6 on the elaborated sources: (the transmitter's instance, the receiver's)."""
    top = design.top
    shapes: List[_Shape] = []
    for instance in top.instances:
        leaf = design.leaves[instance.module]
        shapes.append((instance.name, instance.module, {p.name: (p.direction, p.width) for p in leaf.ports},
                       frozenset(leaf.parameters), frozenset(instance.overrides), dict(instance.connections)))
    tx, rx, _ = _roles(top.path, shapes, {name: kind for name, (kind, _, _) in top.signals.items()})
    transmitter, receiver = top.instances[tx], top.instances[rx]
    if "OVERSAMPLE" not in design.leaves[receiver.module].literal_localparams:
        raise _refusal(top.path, "C3", f"{receiver.module} declares no localparam OVERSAMPLE = <decimal literal>, the "
                                       "receiver's ticks per bit")
    localparams = top.localparams
    # A sized top localparam may hold up to 64 bits, but the harness writes each parameter as an unsized decimal.
    for instance in (transmitter, receiver):
        for parameter, value in sorted(instance.overrides.items()):
            number = localparams[value][0] if isinstance(value, str) else value
            if number > verilog.MAX_DECIMAL:
                raise _refusal(top.path, "C4", f"{instance.name} {parameter} = {value} = {number} is above "
                                               f"{verilog.MAX_DECIMAL}: the harness states each parameter as an unsized "
                                               "decimal, which Verilog guarantees only as a 32-bit signed integer")
    count = sum(name.startswith("TX_BYTE_") for name in localparams)
    stated = [f"TX_BYTE_{index}" for index in range(count)]
    if not 1 <= count <= MAX_BYTES or set(stated) - set(localparams):
        raise _refusal(top.path, "C6", f"the top states {count} localparams named TX_BYTE_*; the bytes sent are "
                                       f"TX_BYTE_0 .. TX_BYTE_{{N-1}}, consecutive, with 1 <= N <= {MAX_BYTES}")
    for name in ("CLK_HALF_PERIOD_NS", "RESET_CYCLES"):
        if name not in localparams or localparams[name][1] is not None or localparams[name][0] < 1:
            raise _refusal(top.path, "C6", f"the top states no localparam {name} = <decimal literal of at least 1>")
    for name in stated:
        if localparams[name][1] != 8:
            raise _refusal(top.path, "C6", f"localparam {name}: a byte sent is localparam [7:0] {name} = <8-bit "
                                            "sized literal>")
    # The harness times a bit as the line's first low run. With bit 0 low that run is the start bit and bit 0,
    # so the bit-rate metric would not be a bit rate, and a requirement on it would FAIL a design that is right.
    if localparams["TX_BYTE_0"][0] % 2 == 0:
        raise _refusal(top.path, "C6", f"TX_BYTE_0 = {localparams['TX_BYTE_0'][0]} is even: the harness measures "
                                       "a bit as the line's first low run, which is the start bit alone only when "
                                       "the first byte's bit 0 is 1")
    named = {value for instance in top.instances for value in instance.overrides.values() if isinstance(value, str)}
    inert = sorted(set(localparams) - {"CLK_HALF_PERIOD_NS", "RESET_CYCLES", *stated} - named)
    if inert:
        raise _refusal(top.path, "C6", f"{', '.join(inert)} is stated but used by nothing the class reads: the top "
                                       "holds no inert data")
    return transmitter, receiver


def _refuse_name(path: str, name: str, line: Optional[int] = None) -> None:
    if not _IDENTIFIER.match(name):
        where = f"{path}:{line}" if line is not None else path
        raise ExtractionError("rejected", f"{where}: {name}: a name starting with _ cannot be a component id of the "
                                          "engineering model")


def build_loopback_model(design: verilog.Design, annotations: Dict[str, Any], *, sample: str,
                         digests: Dict[str, str], annotations_ref: str, annotations_sha256: str) -> Dict[str, Any]:
    """Build the engineering model of an elaborated UART 8N1 loopback and its annotations.

    The top is one component, whose facets are the values its localparams
    state: the clock half-period (in seconds, from its 1 ns time unit), the
    reset length, the bytes sent, and their count, DERIVED. Each instance is
    one component, in the top's order, whose facets are the parameter values
    the top passes it; the receiver's also carries its module's OVERSAMPLE.
    Each value is SPECIFIED by the file that states it, cited by hash. Each
    instance's hdl member carries its module's text verbatim. The annotations
    add components with no HDL, such as a target device; they never restate
    a value a source states.

    Args:
        design: What verilog.elaborate() returned for the sources, whose
            paths are repository paths.
        annotations: An engineering-model/v1/design-annotations document.
        sample: The item's repository path; names and notes give the files
            relative to it.
        digests: The sha256 of each source's bytes, by repository path, in
            the provenance's order: design.sources.
        annotations_ref: Repository path of the annotations.
        annotations_sha256: Digest of the annotation bytes.

    Returns:
        An engineering-model/v1/engineering-model document of format 1.2.0.

    Raises:
        ExtractionError: Of kind "rejected": the design is not the UART 8N1
            loopback (rules C1-C6, each named), or a module or instance name
            cannot be a component id.
        ValueError: The annotations describe CAD geometry or circuit
            elements, declare a component twice, or relate a component that
            does not exist.

    Example:
        >>> from pathlib import Path
        >>> item = Path(__file__).resolve().parents[3] / "datasets/cad/uart_loopback_001"
        >>> sample = "datasets/cad/uart_loopback_001"
        >>> files = {f"{sample}/source/{name}": (item / "source" / name).read_bytes()
        ...          for name in ("tb_uart_loopback.v", "uart_tx.v", "uart_rx.v")}
        >>> design = verilog.elaborate([verilog.parse_source(data, path) for path, data in files.items()])
        >>> annotations = {"design_id": "uart_loopback_001", "materials": {}, "parts": {}, "joints": [],
        ...                "attachments": [], "components_without_cad": [], "relationships": []}
        >>> model = build_loopback_model(design, annotations, sample=sample, annotations_ref="a.json",
        ...                              annotations_sha256="0" * 64,
        ...                              digests={path: hashlib.sha256(data).hexdigest() for path, data in files.items()})
        >>> [(c["component_id"], c["hdl"]["module"]) for c in model["components"]]
        [('tb_uart_loopback', 'tb_uart_loopback'), ('u_tx', 'uart_tx'), ('u_rx', 'uart_rx')]
        >>> model["components"][0]["domains"]["digital"]["tx_bytes"]["value"], model["model_version"]
        ([53, 202], '1.2.0')
    """
    for key in ("materials", "parts", "joints", "attachments"):
        if annotations[key]:
            raise ValueError(f"the annotations give {key}, which describe CAD geometry HDL does not have")
    if "circuit_elements" in annotations:
        raise ValueError("the annotations give circuit_elements, which describe netlist elements HDL does not have")
    transmitter, receiver = _classify(design)
    top = design.top

    def relative(path: str) -> str:
        return path[len(sample) + 1:] if path.startswith(f"{sample}/") else path

    def stated_by(path: str) -> Dict[str, str]:
        return source("design_annotation", path, digests[path])

    _refuse_name(top.path, top.name)
    here = relative(top.path)
    localparams = top.localparams
    half, reset = localparams["CLK_HALF_PERIOD_NS"], localparams["RESET_CYCLES"]
    count = sum(name.startswith("TX_BYTE_") for name in localparams)
    sent = [localparams[f"TX_BYTE_{index}"] for index in range(count)]
    lines = f"{sent[0][2]}" if count == 1 else f"{sent[0][2]}-{sent[-1][2]}"
    bytes_note = ", ".join(f"TX_BYTE_{index} = {value}" for index, (value, _, _) in enumerate(sent))
    tx_bytes_path = f"components/{top.name}/domains/digital/tx_bytes"
    sent_values: List[Union[int, float]] = [value for value, _, _ in sent]
    components: List[Dict[str, Any]] = [{
        "component_id": top.name, "name": f"{top.name} (declarative top)", "kind": "other",
        "cad_ref": None, "material": None, "geometry": None, "physical": None, "placement": None,
        "hdl": {"module": top.name, "source": top.path, "ports": {},
                "signals": {name: {"kind": kind, "width": width} for name, (kind, width, _) in top.signals.items()}},
        "domains": {"digital": {
            "clock_half_period": quantity(
                half[0] / 1e9, "s", Status.SPECIFIED, stated_by(top.path),
                note=f"CLK_HALF_PERIOD_NS = {half[0]} as {here}:{half[2]} states it, in its 1 ns time unit; {_NOT_A_PART}"),
            "reset_cycles": quantity(reset[0], "cycles", Status.SPECIFIED, stated_by(top.path),
                                     note=f"RESET_CYCLES = {reset[0]} as {here}:{reset[2]} states it; {_NOT_A_PART}"),
            "tx_bytes": quantity(sent_values, "1", Status.SPECIFIED, stated_by(top.path),
                                 note=f"{bytes_note} as {here}:{lines} "
                                      f"{'states it' if count == 1 else 'state them'}; {_NOT_A_PART}"),
            "byte_count": quantity(count, "1", Status.DERIVED,
                                   source("computation", f"ecad_model.domains.digital {MODEL_BUILDER_VERSION}: the "
                                                         "number of TX_BYTE_i localparams"),
                                   derived_from=[tx_bytes_path]),
        }},
    }]
    for instance in top.instances:
        _refuse_name(top.path, instance.name, instance.line)
        leaf = design.leaves[instance.module]
        facets: Dict[str, Any] = {}
        for parameter, value in sorted(instance.overrides.items()):
            if isinstance(value, str):
                number, _, line = localparams[value]
                note = (f"{instance.name} {parameter} = {value} = {number} as {here}:{line} and :{instance.line} "
                        f"state it; {_NOT_A_PART}")
            else:
                number, note = value, (f"{instance.name} {parameter} = {value} as {here}:{instance.line} states it; "
                                       f"{_NOT_A_PART}")
            facet = PARAMETER_FACETS[parameter]
            facets[facet] = quantity(number, FACET_UNITS[facet], Status.SPECIFIED, stated_by(top.path), note=note)
        if instance is receiver:
            oversample, line = leaf.literal_localparams["OVERSAMPLE"]
            facets["oversample"] = quantity(oversample, "1", Status.SPECIFIED, stated_by(leaf.path),
                                            note=f"OVERSAMPLE = {oversample} as {relative(leaf.path)}:{line} states "
                                                 f"it; {_NOT_A_PART}")
        components.append({
            "component_id": instance.name, "name": f"{instance.name} ({leaf.name}, {relative(leaf.path)})",
            "kind": "other", "cad_ref": None, "material": None, "geometry": None, "physical": None, "placement": None,
            "hdl": {"module": leaf.name, "instance": f"{top.name}.{instance.name}", "source": leaf.path,
                    "parameters": {parameter: PARAMETER_FACETS[parameter] for parameter in sorted(instance.overrides)},
                    "ports": {port.name: {"direction": port.direction, "width": port.width,
                                          "signal": instance.connections[port.name]} for port in leaf.ports},
                    "text": leaf.text},
            "domains": {"digital": facets},
        })
    known_ids = [component["component_id"] for component in components]
    for extra in annotations["components_without_cad"]:
        if extra["component_id"] in known_ids:
            raise ValueError(f"component {extra['component_id']!r} is declared twice")
        known_ids.append(extra["component_id"])
        components.append({
            "component_id": extra["component_id"], "name": extra["name"], "kind": extra["kind"],
            "cad_ref": None, "material": None, "geometry": None, "physical": None, "placement": None,
            "domains": {name: dict(facet) for name, facet in extra["domains"].items()},
        })
    if len(set(known_ids)) != len(known_ids):
        raise ValueError(f"component {next(i for i in known_ids if known_ids.count(i) > 1)!r} is declared twice")
    design_id = annotations["design_id"]
    relationships = [{"relation": "contains", "from": design_id, "to": top.name, "source": stated_by(top.path)}]
    relationships += [{"relation": "contains", "from": top.name, "to": instance.name, "source": stated_by(top.path)}
                      for instance in top.instances]
    annotation_source = source("design_annotation", annotations_ref, annotations_sha256)
    for relation in annotations["relationships"]:
        for key in ("from", "to"):
            if relation[key] not in known_ids:
                raise ValueError(f"relationship names unknown component {relation[key]!r}")
        relationships.append({**relation, "source": annotation_source})
    model = {
        "$schema": SCHEMA_ID,
        "model_version": HDL_MODEL_VERSION,
        "design": {"design_id": design_id, "name": top.name, "revision": "1.0",
                   "sources": [{"path": path, "format": "verilog", "sha256": digest} for path, digest in digests.items()]},
        "components": components,
        "joints": [],
        "relationships": relationships,
        "unknowns": [],
    }
    model["unknowns"] = index_unknowns(model)
    return model


def loopback_roles(model: Dict[str, Any]) -> Roles:
    """Find each component's and signal's role in the one design class this domain validates.

    Rules, each named when the model breaks it:
      C1  one top (an hdl member with no instance) and exactly two
          instances, of two different modules;
      C2  one instance's module declares exactly the transmitter's interface:
          inputs clk:1, rst_n:1, tx_data:8, tx_valid:1, outputs tx_ready:1,
          tx:1, parameters CLK_FREQ and BAUD_RATE;
      C3  the other declares exactly the receiver's: inputs clk:1, rst_n:1,
          rx:1, outputs rx_data:8, rx_valid:1, rx_error:1, the same
          parameters, and carries its module's OVERSAMPLE;
      C4  each instance overrides both parameters, each held by its facet
          (clk_freq, baud_rate);
      C5  one reg drives both clk ports, one reg both rst_n ports; regs drive
          tx_data and tx_valid alone; the transmitter's tx and the
          receiver's rx share one wire, the line, and nothing else; each
          other output drives a wire of its own; every signal is connected;
      C6  the top carries the clock half-period, the reset length, the bytes
          and their count.
    The extraction also refuses what only the sources show (an OVERSAMPLE
    that is not a decimal literal, a parameter value above
    verilog.MAX_DECIMAL, inert or misnumbered localparams, an even first
    byte) and the resource guard C7.

    Args:
        model: An engineering model of this domain.

    Returns:
        The roles.

    Raises:
        ExtractionError: Of kind "rejected", naming the rule the model
            breaks: it is not the design class this domain validates.

    Example:
        >>> import json; from pathlib import Path
        >>> item = Path(__file__).resolve().parents[3] / "datasets/cad/uart_loopback_001"
        >>> roles = loopback_roles(json.loads((item / "derived/engineering_model.json").read_text(encoding="utf-8")))
        >>> roles.transmitter["component_id"], roles.receiver["component_id"], roles.line, roles.clock
        ('u_tx', 'u_rx', 'line', 'clk')
    """
    hdl = [component for component in model["components"] if "hdl" in component]
    tops = [component for component in hdl if "instance" not in component["hdl"]]
    where = tops[0]["hdl"]["source"] if len(tops) == 1 else model["design"]["sources"][0]["path"]
    if len(tops) != 1:
        raise _refusal(where, "C1", f"{len(tops)} components have an hdl member with no instance; the class has "
                                    "exactly one top")
    top = tops[0]
    instances = [component for component in hdl if "instance" in component["hdl"]]
    shapes: List[_Shape] = [(
        component["component_id"], component["hdl"]["module"],
        {name: (port["direction"], port["width"]) for name, port in component["hdl"]["ports"].items()},
        # A model records the parameters the top overrides, which rule C4 requires to be all of them.
        frozenset(component["hdl"]["parameters"]), frozenset(component["hdl"]["parameters"]),
        {name: port["signal"] for name, port in component["hdl"]["ports"].items()},
    ) for component in instances]
    tx, rx, signals = _roles(where, shapes, {name: signal["kind"] for name, signal in top["hdl"]["signals"].items()})
    for component in instances:
        facets = component["domains"].get("digital", {})
        if component["hdl"]["parameters"] != PARAMETER_FACETS or not set(PARAMETER_FACETS.values()) <= set(facets):
            raise _refusal(where, "C4", f"{component['component_id']} holds its parameters as "
                                        f"{component['hdl']['parameters']!r} with facets {sorted(facets)}; the class "
                                        f"holds them as {PARAMETER_FACETS!r}")
    if "oversample" not in instances[rx]["domains"].get("digital", {}):
        raise _refusal(where, "C3", f"{instances[rx]['component_id']} carries no oversample, its module's OVERSAMPLE")
    missing = [name for name in TOP_FACETS if name not in top["domains"].get("digital", {})]
    if missing:
        raise _refusal(where, "C6", f"the top {top['component_id']} carries no {', '.join(missing)}")
    return Roles(top, instances[tx], instances[rx], **signals)


def _value(component: Dict[str, Any], facet: str) -> Any:
    return component["domains"]["digital"][facet]["value"]


def _divider(component: Dict[str, Any]) -> int:
    """T = CLK_FREQ // BAUD_RATE: the clock cycles of one bit, by the class's interface contract."""
    return _value(component, "clk_freq") // _value(component, "baud_rate")


def end_cycle(model: Dict[str, Any]) -> int:
    """The cycle the harness ends on: END = RESET_CYCLES + (N + 2) * RUN_BITS_PER_FRAME * max(T_tx, T_rx, MIN_BIT_CYCLES).

    T_x = CLK_FREQ // BAUD_RATE of each instance, and N the bytes sent: every
    frame, and two idle frames after the last one, fit before it, so a
    spurious byte after the last is still counted.

    Args:
        model: An engineering model of this domain.

    Returns:
        END, in clock cycles after the first rising edge.

    Raises:
        ExtractionError: Of kind "rejected", rule C7: a CLK_FREQ or
            BAUD_RATE is not a positive integer, so the run has no length.

    Example:
        >>> import json; from pathlib import Path
        >>> item = Path(__file__).resolve().parents[3] / "datasets/cad/uart_loopback_001"
        >>> end_cycle(json.loads((item / "derived/engineering_model.json").read_text(encoding="utf-8")))
        20836
    """
    roles = loopback_roles(model)
    for component in (roles.transmitter, roles.receiver):
        for facet in ("clk_freq", "baud_rate"):
            value = _value(component, facet)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise _refusal(roles.top["hdl"]["source"], "C7",
                               f"{component['component_id']} {facet} {value!r} is not a positive integer, so the run "
                               "has no length")
    bit = max(_divider(roles.transmitter), _divider(roles.receiver), MIN_BIT_CYCLES)
    return _value(roles.top, "reset_cycles") + (len(_value(roles.top, "tx_bytes")) + 2) * RUN_BITS_PER_FRAME * bit


def _declaration(kind: str, width: int, name: str) -> str:
    span = f"[{width - 1}:0] " if width > 1 else "      "
    # The adapter drives every reg from a known value; the design's outputs drive the wires.
    initial = "" if kind == "wire" else " = 1'b0" if width == 1 else f" = {width}'d0"
    return f"    {kind:<4} {span}{name}{initial};"


def _instance_line(component: Dict[str, Any]) -> str:
    hdl = component["hdl"]
    overrides = ", ".join(f".{parameter}({int(_value(component, facet))})"
                          for parameter, facet in sorted(hdl["parameters"].items()))
    connections = ", ".join(f".{port}({entry['signal']})" for port, entry in sorted(hdl["ports"].items()))
    return f"    {hdl['module']} #({overrides}) {hdl['instance'].rsplit('.', 1)[1]} ({connections});"


def write_harness(model: Dict[str, Any]) -> str:
    """The harness Icarus runs after the leaves, written from the engineering model alone.

    It declares the top's signals (each reg starting at 0), instantiates both
    leaves with the parameter values the model holds, drives the clock from
    the half-period, holds reset for the reset length, offers each byte when
    tx_ready is high, and measures the nine metrics, sampling every signal on
    the falling clock edge. At END it prints one ``ECAD_METRIC <name> <value>``
    line per metric it observed -- a metric never observed is not printed --
    and finishes. A byte sent that never arrived counts all 8 of its bits in
    rx_bit_errors, and rx_framing_errors is not printed when it is 0 and a
    byte never arrived: a count of 0 then says nothing about the frames the
    receiver never finished. Its only system identifiers are $display,
    $finish and $realtime. Signals, parameters and connections are written
    sorted by name.

    Args:
        model: An engineering model of this domain.

    Returns:
        The harness text: ASCII, LF line ends, from its `timescale line to its
        endmodule.

    Raises:
        ExtractionError: The model is not the design class this domain
            validates (see loopback_roles), or rule C7.

    Example:
        >>> import json; from pathlib import Path
        >>> item = Path(__file__).resolve().parents[3] / "datasets/cad/uart_loopback_001"
        >>> harness = write_harness(json.loads((item / "derived/engineering_model.json").read_text(encoding="utf-8")))
        >>> harness.splitlines()[18], harness.splitlines()[21]
        ('    always #10 clk = ~clk;', '        repeat (4) @(posedge clk);')
    """
    roles = loopback_roles(model)
    top = roles.top
    sent = _value(top, "tx_bytes")
    count, end = len(sent), end_cycle(model)
    clk, ready, line = roles.clock, roles.ready, roles.line
    signals = sorted(top["hdl"]["signals"].items())
    lines = ["`timescale 1ns / 1ps", "", "module ecad_harness;", ""]
    lines += [_declaration(signal["kind"], signal["width"], name) for name, signal in signals]
    lines += ["", _instance_line(roles.transmitter), _instance_line(roles.receiver), "",
              "    // ecad: clock, stimulus and measurements",
              f"    always #{round(_value(top, 'clock_half_period') * 1e9)} {clk} = ~{clk};", "",
              "    initial begin",
              f"        repeat ({_value(top, 'reset_cycles')}) @(posedge {clk});",
              f"        {roles.reset} <= 1'b1;"]
    for value in sent:
        lines += [f"        @(posedge {clk});",
                  f"        while (!{ready}) @(posedge {clk});",
                  f"        {roles.data} <= 8'd{value};",
                  f"        {roles.valid} <= 1'b1;",
                  f"        @(posedge {clk});",
                  f"        {roles.valid} <= 1'b0;"]
    lines += [
        "    end",
        "",
        "    integer    ecad_cycle = 0;",
        "    realtime   ecad_first_rise = -1.0;",
        "    realtime   ecad_second_rise = -1.0;",
        f"    always @(posedge {clk}) begin",
        "        ecad_cycle <= ecad_cycle + 1;",
        "        if (ecad_first_rise < 0.0) ecad_first_rise = $realtime;",
        "        else if (ecad_second_rise < 0.0) ecad_second_rise = $realtime;",
        "    end",
        "",
        "    reg        ecad_line_before = 1'b1;",
        "    reg        ecad_ready_before = 1'b1;",
        "    integer    ecad_idle_after_reset = -1;",
        "    integer    ecad_unknown_after_reset = -1;",
        "    integer    ecad_start_fall = -1;",
        "    integer    ecad_start_rise = -1;",
        "    realtime   ecad_start_fall_at = 0.0;",
        "    realtime   ecad_start_rise_at = 0.0;",
        "    integer    ecad_busy_from = -1;",
        "    integer    ecad_busy_to = -1;",
        "    integer    ecad_received = 0;",
        "    integer    ecad_bit_errors = 0;",
        "    integer    ecad_framing_errors = 0;",
        "    integer    ecad_missing = 0;",
        "    integer    ecad_k;",
        f"    reg  [7:0] ecad_expected [0:{count - 1}];",
        "    reg  [7:0] ecad_difference;",
        "    initial begin",
        *(f"        ecad_expected[{index}] = 8'd{value};" for index, value in enumerate(sent)),
        "    end",
        "",
        "    // Every signal is sampled on the falling clock edge, half a cycle after the rising edge the design acts on.",
        f"    always @(negedge {clk}) begin",
        f"        if (ecad_idle_after_reset < 0 && {roles.reset} === 1'b1) begin",
        f"            ecad_idle_after_reset = ({line} === 1'b1 && {ready} === 1'b1) ? 1 : 0;",
        f"            ecad_unknown_after_reset = (^{ready} === 1'bx) + (^{line} === 1'bx) + (^{roles.rx_data} === 1'bx)",
        f"                                       + (^{roles.rx_valid} === 1'bx) + (^{roles.rx_error} === 1'bx);",
        "        end",
        f"        if (ecad_start_fall < 0 && ecad_line_before === 1'b1 && {line} === 1'b0) begin",
        "            ecad_start_fall = ecad_cycle;",
        "            ecad_start_fall_at = $realtime;",
        f"        end else if (ecad_start_fall >= 0 && ecad_start_rise < 0 && {line} === 1'b1) begin",
        "            ecad_start_rise = ecad_cycle;",
        "            ecad_start_rise_at = $realtime;",
        "        end",
        f"        if (ecad_busy_from < 0 && ecad_ready_before === 1'b1 && {ready} === 1'b0) ecad_busy_from = ecad_cycle;",
        f"        else if (ecad_busy_from >= 0 && ecad_busy_to < 0 && {ready} === 1'b1) ecad_busy_to = ecad_cycle;",
        f"        if ({roles.rx_valid} === 1'b1) begin",
        f"            if (ecad_received < {count}) begin",
        f"                ecad_difference = {roles.rx_data} ^ ecad_expected[ecad_received];",
        "                for (ecad_k = 0; ecad_k < 8; ecad_k = ecad_k + 1)",
        "                    if (ecad_difference[ecad_k] !== 1'b0) ecad_bit_errors = ecad_bit_errors + 1;",
        "            end",
        "            ecad_received = ecad_received + 1;",
        "        end",
        f"        if ({roles.rx_error} === 1'b1) ecad_framing_errors = ecad_framing_errors + 1;",
        f"        ecad_line_before = {line};",
        f"        ecad_ready_before = {ready};",
        f"        if (ecad_cycle == {end}) begin",
        '            $display("ECAD_METRIC clock_period_s %.17g", (ecad_second_rise - ecad_first_rise) / 1.0e9);',
        '            if (ecad_idle_after_reset >= 0) $display("ECAD_METRIC tx_idle_after_reset %0d", '
        'ecad_idle_after_reset);',
        "            if (ecad_start_rise >= 0) begin",
        '                $display("ECAD_METRIC tx_bit_cycles %0d", ecad_start_rise - ecad_start_fall);',
        '                $display("ECAD_METRIC tx_bit_rate_bd %.17g", 1.0e9 / (ecad_start_rise_at - '
        'ecad_start_fall_at));',
        "            end",
        '            if (ecad_busy_to >= 0) $display("ECAD_METRIC tx_frame_cycles %0d", ecad_busy_to - ecad_busy_from);',
        '            $display("ECAD_METRIC rx_bytes_received %0d", ecad_received);',
        "            // A byte sent that never arrived counts its 8 bits as errors, and a framing-error count of 0 is",
        "            // not reported while a byte is missing: it says nothing of frames the receiver never finished.",
        f"            if (ecad_received < {count}) ecad_missing = {count} - ecad_received;",
        '            $display("ECAD_METRIC rx_bit_errors %0d", ecad_bit_errors + 8 * ecad_missing);',
        '            if (ecad_framing_errors > 0 || ecad_missing == 0) $display("ECAD_METRIC rx_framing_errors %0d", '
        'ecad_framing_errors);',
        '            if (ecad_unknown_after_reset >= 0) $display("ECAD_METRIC outputs_unknown_after_reset %0d", '
        'ecad_unknown_after_reset);',
        "            $finish;",
        "        end",
        "    end",
        "",
        "endmodule",
    ]
    return "\n".join(lines) + "\n"


def _leaves(model: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [component for component in model["components"] if "instance" in component.get("hdl", {})]


def _separator(component: Dict[str, Any]) -> str:
    hdl = component["hdl"]
    return f"// ---- {hdl['source']} sha256 {hashlib.sha256(hdl['text'].encode('utf-8')).hexdigest()} ----"


def _prefix(model: Dict[str, Any]) -> List[Tuple[str, str]]:
    """The simulation file's lines before the harness, each with what it is: (line, whose)."""
    design = model["design"]
    lines = [(f"// {design['design_id']}: the RTL of {design['name']} verbatim, then the harness the digital domain "
              "writes from the model", "the header"),
             (f"// written by ecad_model.domains.digital {VERSION} from derived/engineering_model.json; regenerate with "
              "build, never edit", "the header")]
    for component in _leaves(model):
        whose = f"{component['component_id']}'s text, {component['hdl']['source']}"
        lines.append((_separator(component), f"the separator before {whose}"))
        lines += [(text, whose) for text in component["hdl"]["text"].split("\n")[:-1]]
    return lines


def write_simulation(model: Dict[str, Any]) -> bytes:
    """The one file Icarus compiles, written from the engineering model alone.

    Two header comments, then for each instance in model order a separator
    naming its source and the sha256 of its text, followed by that text as
    the model carries it -- its module's source, verbatim -- then the harness
    separator and the harness (see write_harness).

    Args:
        model: An engineering model of this domain.

    Returns:
        The file's bytes: UTF-8 (non-ASCII only in the RTL's comments), LF
        line ends.

    Raises:
        ExtractionError: The model is not the design class this domain
            validates (see loopback_roles), or rule C7.

    Example:
        >>> import json; from pathlib import Path
        >>> item = Path(__file__).resolve().parents[3] / "datasets/cad/uart_loopback_001"
        >>> simulation = write_simulation(json.loads((item / "derived/engineering_model.json").read_text(encoding="utf-8")))
        >>> simulation.decode().splitlines()[241]
        '// ---- harness ----'
        >>> simulation == (item / "derived/digital/uart_loopback_001.v").read_bytes()
        True
    """
    harness = write_harness(model)
    return ("".join(f"{line}\n" for line, _ in _prefix(model)) + f"{HARNESS_SEPARATOR}\n" + harness).encode("utf-8")


# The facets each closed form reads, by role.
_LINK = (("transmitter", "clk_freq"), ("transmitter", "baud_rate"), ("receiver", "clk_freq"),
         ("receiver", "baud_rate"), ("receiver", "oversample"))
INPUTS = {
    "clock_period": (("top", "clock_half_period"),),
    "idle_high_after_reset": (("top", "reset_cycles"),),
    "bit_period_cycles": (("transmitter", "clk_freq"), ("transmitter", "baud_rate"), ("top", "tx_bytes")),
    "bit_rate": (("transmitter", "clk_freq"), ("transmitter", "baud_rate"), ("top", "tx_bytes"),
                 ("top", "clock_half_period")),
    "frame_cycles": (("transmitter", "clk_freq"), ("transmitter", "baud_rate")),
    "bytes_sent": (("top", "tx_bytes"), *_LINK),
    "lossless_loopback": _LINK,
    "no_framing_errors": _LINK,
}


def sampling_holds(bit_cycles: int, tick_cycles: int, oversample: int) -> bool:
    """Condition W: whether the receiver samples every bit of a frame inside that bit.

    The receiver detects a start at the first of its ticks (every D_r
    cycles, free-running from reset) at which its synchronised line is low,
    at a phase phi in [0, D_r - 1] after the line's edge, and samples bit b
    (0 confirms the start, 1-8 are data, 9 is the stop) at (SP + OS*b)*D_r
    cycles after that, SP = OS // 2. For every phase every sample lies inside
    its bit of D_t cycles when, for every b of the frame,
    b*D_t <= (SP + OS*b)*D_r and (SP + OS*b)*D_r + D_r - 1 < (b + 1)*D_t.
    The stop sample then lies in the stop bit, so the receiver is idle
    before the next start and every byte meets the same condition. W is
    sufficient, not necessary: a design it refuses may still recover bytes.

    Args:
        bit_cycles: D_t, the transmitter's clock cycles per bit.
        tick_cycles: D_r, the receiver's clock cycles per tick.
        oversample: OS, the receiver's ticks per bit.

    Returns:
        Whether W holds; never for a receiver whose divider is 0.

    Example:
        >>> sampling_holds(434, 27, 16), sampling_holds(413, 27, 16), sampling_holds(434, 0, 16)
        (True, False, False)
    """
    if tick_cycles < 1:
        return False
    middle = oversample // 2
    return all(bit * bit_cycles <= (middle + oversample * bit) * tick_cycles
               and (middle + oversample * bit) * tick_cycles + tick_cycles - 1 < (bit + 1) * bit_cycles
               for bit in range(FRAME_BITS))


def _inputs(model: Dict[str, Any], derivation: str) -> Tuple[Dict[Tuple[str, str], Any], List[str],
                                                              List[Dict[str, str]]]:
    """(value by (role, facet), the paths read, the null-status ones) for one closed form."""
    if derivation not in INPUTS:
        raise ValueError(f"unknown derivation {derivation!r}")
    roles = loopback_roles(model)
    values: Dict[Tuple[str, str], Any] = {}
    paths: List[str] = []
    missing: List[Dict[str, str]] = []
    for role, facet in INPUTS[derivation]:
        path = f"components/{getattr(roles, role)['component_id']}/domains/digital/{facet}"
        item = resolve(model, path)
        paths.append(path)
        if is_null(item["status"]):
            missing.append({"path": path, "status": item["status"]})
        values[(role, facet)] = item["value"]
    return values, paths, missing


def reference_value(model: Dict[str, Any], derivation: str,
                    scenario: Optional[Dict[str, Any]] = None) -> Tuple[float, List[str]]:
    """Compute one closed-form reference value from the engineering model.

    With h the clock half-period, D_t = CLK_FREQ // BAUD_RATE of the
    transmitter, D_r = CLK_FREQ // (BAUD_RATE * OVERSAMPLE) of the receiver
    and N the bytes sent:

      clock_period           2h;
      idle_high_after_reset  1: the 8N1 idle level is mark;
      bit_period_cycles      D_t, if the first byte is odd;
      bit_rate               1 / (2h * D_t), if the first byte is odd;
      frame_cycles           FRAME_BITS * D_t;
      bytes_sent             N, if W holds (see sampling_holds);
      lossless_loopback      0 bits in error or lost, if W holds;
      no_framing_errors      0, if W holds.

    The harness measures the line's first low run: with an odd first byte
    that is the start bit alone, with an even one the start bit and bit 0.
    It counts all 8 bits of a byte that never arrived as bits in error, and
    reports no framing-error count of 0 while a byte is missing, so the last
    two forms' 0 also says that every byte arrived.

    Args:
        model: An engineering model of this domain.
        derivation: One of the eight names above.
        scenario: The case's scenario; it carries only its name, so it is
            not read.

    Returns:
        (value in SI units, model paths the value was computed from).

    Raises:
        ReferenceBlocked: An input has a null status (its paths and statuses
            are attached), or the form does not apply to this design: the
            first byte is even, or W fails (nothing is attached).
        ValueError: The derivation name is not recognised.

    Example:
        >>> import json; from pathlib import Path
        >>> item = Path(__file__).resolve().parents[3] / "datasets/cad/uart_loopback_001"
        >>> model = json.loads((item / "derived/engineering_model.json").read_text(encoding="utf-8"))
        >>> reference_value(model, "bit_period_cycles")[0], round(reference_value(model, "bit_rate")[0], 6)
        (434.0, 115207.373272)
    """
    values, paths, missing = _inputs(model, derivation)
    if missing:
        raise ReferenceBlocked(f"{derivation} needs quantities that have no value", missing)

    def not_applicable(why: str) -> ReferenceBlocked:
        return ReferenceBlocked(f"{derivation} does not apply to this design: {why}", [])

    if derivation == "clock_period":
        return 2 * values[("top", "clock_half_period")], paths
    if derivation == "idle_high_after_reset":
        return 1.0, paths
    bit_cycles = values[("transmitter", "clk_freq")] // values[("transmitter", "baud_rate")]
    if derivation in ("bit_period_cycles", "bit_rate"):
        first = values[("top", "tx_bytes")][0]
        if first % 2 == 0:
            raise not_applicable(f"the first byte, {first}, is even, so the line's first low run is the start bit and "
                                 "bit 0 together")
        if derivation == "bit_period_cycles":
            return float(bit_cycles), paths
        return 1 / (2 * values[("top", "clock_half_period")] * bit_cycles), paths
    if derivation == "frame_cycles":
        return float(FRAME_BITS * bit_cycles), paths
    oversample = values[("receiver", "oversample")]
    per_tick = values[("receiver", "baud_rate")] * oversample
    tick_cycles = values[("receiver", "clk_freq")] // per_tick if per_tick > 0 else 0
    if not sampling_holds(bit_cycles, tick_cycles, oversample):
        raise not_applicable(f"with D_t = {bit_cycles} and D_r = {tick_cycles} cycles, {oversample} ticks per bit, "
                             "some phase puts a sample outside its bit (condition W)")
    if derivation == "bytes_sent":
        return float(len(values[("top", "tx_bytes")])), paths
    return 0.0, paths


def _positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


class DigitalAdapter:
    """The UART 8N1 loopback in Verilog, simulated with Icarus Verilog."""

    domain = "digital"
    formats = frozenset({"verilog"})
    description = ("the UART 8N1 loopback only (a transmitter and a receiver with the port and parameter interfaces of "
                   "rtl/uart_tx.v and rtl/uart_rx.v, wired transmitter to receiver by a declarative top): reset, "
                   "frame-timing and byte-recovery metrics from one Icarus Verilog run of a harness written from the "
                   "model, compared with closed-form references")

    def simulation_path(self, sample_id: str) -> str:
        return f"derived/digital/{sample_id}.v"

    def extract(self, root: Path, sources: Sequence[SourceArtifact], annotations: Dict[str, Any],
                refs: Dict[str, str]) -> Extraction:
        """Read the Verilog sources with the strict grammar and build the engineering model from them.

        Raises:
            ExtractionError: Of kind "rejected": a source is not a regular
                file within the size limit or is outside the grammar, the
                design does not elaborate, is not the UART 8N1 loopback, or
                its run would exceed MAX_CYCLES (rule C7). None of these
                reaches Icarus.
            ValueError: A source is not Verilog, there are more than
                verilog.MAX_MODULES sources, or the annotations are inconsistent
                with the design.
        """
        foreign = [f"{artifact.path} ({artifact.format})" for artifact in sources if artifact.format != "verilog"]
        if foreign:
            raise ValueError(f"the digital domain reads verilog sources only, not {', '.join(foreign)}")
        # Too few sources is the design's fault, refused on its content by the
        # grammar or rule C1; too many is refused before any is read.
        if len(sources) > verilog.MAX_MODULES:
            raise ValueError(f"the digital domain reads at most {verilog.MAX_MODULES} verilog sources, found {len(sources)}")
        parsed = []
        digests: Dict[str, str] = {}
        for artifact in sources:
            path = root / artifact.path
            ref = f"{refs['sample']}/{artifact.path}"
            try:
                regular_file(path, verilog.MAX_SOURCE_BYTES)
            except UnsupportedFormat as exc:
                raise ExtractionError("rejected", f"{ref}: {exc}") from exc
            data = path.read_bytes()
            digests[ref] = hashlib.sha256(data).hexdigest()
            parsed.append(verilog.parse_source(data, ref))
        design = verilog.elaborate(parsed)
        model = build_loopback_model(design, annotations, sample=refs["sample"], digests=digests,
                                     annotations_ref=refs["annotations"], annotations_sha256=refs["annotations_sha256"])
        # The resource guard is a refusal, not a V1 finding: V1's findings do
        # not stop the cases, so only here does it keep a run from starting.
        end = end_cycle(model)
        if end > MAX_CYCLES:
            raise _refusal(design.top.path, "C7", f"the run lasts END = {end} cycles, more than {MAX_CYCLES}")
        return Extraction(model=model, producer=("ecad_model.domains.digital",
                                                 f"{MODEL_BUILDER_VERSION} (ecad_model.verilog {verilog.VERSION})"))

    def write_models(self, model: Dict[str, Any], sample_id: str) -> List[DerivedFile]:
        return [DerivedFile(
            path=self.simulation_path(sample_id), data=write_simulation(model), role="domain_model",
            media_type="text/x-verilog", producer="ecad_model.domains.digital", version=VERSION,
            derived_from=("derived/engineering_model.json",), comparator="exact")]

    def case_target(self, sample_id: str) -> CaseTarget:
        # Every case runs the same file: the one scenario is the whole run.
        return CaseTarget(adapter="iverilog", inputs=(self.simulation_path(sample_id),), arguments=lambda scenario: [],
                          timeout_seconds=CASE_TIMEOUT_S)

    def reference_value(self, model: Dict[str, Any], derivation: str,
                        scenario: Dict[str, Any]) -> Tuple[float, List[str]]:
        return reference_value(model, derivation, scenario)

    def metrics(self) -> Dict[str, Metric]:
        return dict(METRICS)

    def check_requirements(self, requirements: Dict[str, Any]) -> None:
        """Every scenario and derivation must be one this domain implements, and
        each reference must compare the metric its derivation computes.

        Raises:
            ValueError: A scenario or derivation is not in the digital
                vocabulary (schemas/engineering-model/v1/digital-vocabulary),
                or a derivation is paired with the wrong metric.
        """
        validate_schema({
            "scenarios": [entry["scenario"] for entry in (*requirements["reference_values"], *requirements["requirements"])],
            "derivations": [entry["derivation"] for entry in requirements["reference_values"]],
        }, "engineering-model/v1/digital-vocabulary")
        for reference in requirements["reference_values"]:
            if DERIVATION_METRIC[reference["derivation"]] != reference["metric"]:
                raise ValueError(f"{reference['reference_id']}: {reference['derivation']} computes "
                                 f"{DERIVATION_METRIC[reference['derivation']]}, not {reference['metric']}")

    def dependencies(self, model: Dict[str, Any], metric: str, scenario: Dict[str, Any]) -> List[str]:
        """The model quantities a simulated metric depends on.

        Coarse on purpose: every digital value of the top and the instances,
        since every case runs the one harness written from all of them.
        """
        return sorted(f"components/{c['component_id']}/domains/digital/{name}"
                      for c in model["components"] if "hdl" in c for name in c["domains"].get("digital", {}))

    def reference_inputs(self, model: Dict[str, Any], derivation: str, scenario: Dict[str, Any]) -> List[str]:
        """The model paths a reference derivation reads, whether or not it applies."""
        return _inputs(model, derivation)[1]

    def document_schemas(self) -> Dict[str, str]:
        return {}  # no extraction file: the model is built from the sources directly

    def components_for(self, model: Dict[str, Any], metric: str) -> List[str]:
        """The source modules a metric depends on: the transmitter for its own
        metrics, both instances for what the receiver reports, the top for the clock."""
        roles = loopback_roles(model)
        if metric == "clock_period_s":
            return [f"{roles.top['component_id']} (top)"]
        named = [f"{c['component_id']} ({c['hdl']['module']})" for c in (roles.transmitter, roles.receiver)]
        return named[:1] if metric.startswith("tx_") else sorted(named)

    def simulation_files(self, root: Path) -> List[str]:
        return []  # the simulation file is derived; no script runs

    def sanity_problems(self, model: Dict[str, Any]) -> List[str]:
        """Why the design's values or units are impossible, or its clock is not the one its instances are told.

        An instance's CLK_FREQ is its clock's when it is within 1 Hz of the
        frequency the harness drives, 10^9 / (2 N) Hz for the half period of
        N whole ns that ``always #N`` writes: that frequency rounded down or
        up to whole Hz. The comparison is in integers, |2 N CLK_FREQ - 10^9|
        < 2 N, so no floating-point rounding decides it.
        """
        problems = []
        for component in model["components"]:
            for name, facet in component["domains"].get("digital", {}).items():
                unit = FACET_UNITS.get(name)
                if unit is None:
                    problems.append(f"{component['component_id']}: {name} is not in the digital facet vocabulary")
                elif facet["unit"] != unit:
                    problems.append(f"{component['component_id']}: {name} is in {facet['unit']}, not the "
                                    f"vocabulary's {unit}")
                elif name == "min_clock_period" and not is_null(facet["status"]) and not (
                        isinstance(facet["value"], (int, float)) and not isinstance(facet["value"], bool)
                        and facet["value"] > 0):
                    problems.append(f"{component['component_id']}: min_clock_period {facet['value']!r} is not positive")
        # The resource guard (END <= MAX_CYCLES) is applied by extract: a V1
        # problem does not stop the cases running, so here it would bound nothing.
        roles = loopback_roles(model)
        top = roles.top["component_id"]
        half, reset, sent = (_value(roles.top, name) for name in ("clock_half_period", "reset_cycles", "tx_bytes"))
        if isinstance(half, bool) or not isinstance(half, (int, float)) or not half > 0:
            problems.append(f"{top}: clock_half_period {half!r} is not positive")
            half = None
        half_ns = None if half is None else round(half * 1e9)  # N of the harness's `always #N`
        if not _positive_integer(reset):
            problems.append(f"{top}: reset_cycles {reset!r} is not an integer of at least 1")
        if (not isinstance(sent, list) or not 1 <= len(sent) <= MAX_BYTES
                or not all(isinstance(b, int) and not isinstance(b, bool) and 0 <= b <= 255 for b in sent)):
            problems.append(f"{top}: tx_bytes {sent!r} is not 1 to {MAX_BYTES} integers from 0 to 255")
        elif _value(roles.top, "byte_count") != len(sent):
            problems.append(f"{top}: byte_count {_value(roles.top, 'byte_count')!r} is not the {len(sent)} bytes "
                            "tx_bytes holds")
        for component in (roles.transmitter, roles.receiver):
            label = component["component_id"]
            clock, rate = _value(component, "clk_freq"), _value(component, "baud_rate")
            if not _positive_integer(clock) or not _positive_integer(rate):
                problems.append(f"{label}: clk_freq {clock!r} and baud_rate {rate!r} are not both positive integers")
                continue
            if rate > clock:
                problems.append(f"{label}: baud_rate {rate} Bd is above clk_freq {clock} Hz")
            if half_ns is not None and not abs(2 * half_ns * clock - 10**9) < 2 * half_ns:
                problems.append(f"{label} CLK_FREQ {clock} Hz is not the frequency of its clock (half period {half!r} "
                                f"s, {1 / (2 * half):.12g} Hz)")
        oversample = _value(roles.receiver, "oversample")
        label = roles.receiver["component_id"]
        if not _positive_integer(oversample) or oversample < 2 or oversample % 2:
            problems.append(f"{label}: oversample {oversample!r} is not an even integer of at least 2")
        else:
            clock, rate = _value(roles.receiver, "clk_freq"), _value(roles.receiver, "baud_rate")
            if _positive_integer(clock) and _positive_integer(rate) and clock // (rate * oversample) < 1:
                problems.append(f"{label}: CLK_FREQ // (BAUD_RATE * OVERSAMPLE) = {clock} // ({rate} * {oversample}) "
                                "is 0: the receiver's divider is 0, so it never samples")
        return problems

    def invariant_problems(self, model: Dict[str, Any], extraction_files: Dict[str, Any],
                           domain_models: Dict[str, bytes]) -> List[str]:
        """The simulation file is the model's RTL verbatim, then the harness this
        adapter writes from the model, read back by form and compared value by
        value; every source value cites the file that states it, by hash."""
        from ecad_validation.adapters.hdl import declared_metrics

        problems: List[str] = []
        roles = loopback_roles(model)
        sources = {entry["path"]: entry["sha256"] for entry in model["design"]["sources"]}
        for path, data in domain_models.items():
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                problems.append(f"{path}: not UTF-8 text: {exc}")
                continue
            lines = text.split("\n")
            prefix = _prefix(model)
            for number, (want, whose) in enumerate(prefix, start=1):
                if number > len(lines) or lines[number - 1] != want:
                    got = lines[number - 1] if number <= len(lines) else None
                    problems.append(f"{path}:{number}: {got!r} is not line {number} of what the model holds "
                                    f"({whose}): {want!r}")
                    break
            # Nothing may sit between the model's RTL and the harness: a line there is neither, and Icarus compiles it.
            found = lines[len(prefix)] if len(lines) > len(prefix) else None
            if found != HARNESS_SEPARATOR:
                problems.append(f"{path}:{len(prefix) + 1}: {found!r} is not {HARNESS_SEPARATOR!r}, the line that "
                                "follows the model's RTL")
            separators = [index for index, line in enumerate(lines) if line == HARNESS_SEPARATOR]
            if not separators:
                problems.append(f"{path}: no {HARNESS_SEPARATOR!r} line: the harness cannot be found")
                continue
            start = separators[-1] + 1
            harness = "\n".join(lines[start:])
            problems += self._harness_problems(model, roles, path, harness, start)
            declared, twice = declared_metrics([text])
            if declared != list(METRICS) or twice:
                problems.append(f"{path}: declares the metrics {declared}"
                                + (f" and {twice} more than once" if twice else "")
                                + f", not {list(METRICS)} once each")
        for component in model["components"]:
            hdl = component.get("hdl")
            if hdl is None:
                continue
            label = component["component_id"]
            if hdl["source"] not in sources:
                problems.append(f"{label}: its source {hdl['source']} is not one of design.sources")
            elif "text" in hdl and hashlib.sha256(hdl["text"].encode("utf-8")).hexdigest() != sources[hdl["source"]]:
                problems.append(f"{label}: hdl.text is not the bytes of {hdl['source']} that design.sources records")
        top = roles.top["hdl"]["source"]
        stated = [(roles.top, name, top) for name in ("clock_half_period", "reset_cycles", "tx_bytes")]
        stated += [(component, name, top) for component in (roles.transmitter, roles.receiver)
                   for name in PARAMETER_FACETS.values()]
        stated.append((roles.receiver, "oversample", roles.receiver["hdl"]["source"]))
        for component, name, origin in stated:
            facet = component["domains"]["digital"][name]
            if (facet["status"] != Status.SPECIFIED.value or facet["source"]["ref"] != origin
                    or facet["source"].get("sha256") != sources.get(origin)):
                problems.append(f"{component['component_id']}: {name} is not SPECIFIED by {origin} cited by its hash")
        return problems

    def _harness_problems(self, model: Dict[str, Any], roles: Roles, path: str, harness: str,
                          offset: int) -> List[str]:
        """How the harness, read back by form, differs from what the model calls for."""
        problems = []
        try:
            # The reader counts lines from its first; blank lines put its line numbers on the file's.
            view = verilog.read_harness("\n" * offset + harness, path)
        except verilog.HdlRefused as exc:
            return [f"{path}: the harness is not one this adapter writes: {exc}"]
        top = roles.top
        sent = _value(top, "tx_bytes")
        signals = {name: (signal["kind"], signal["width"]) for name, signal in top["hdl"]["signals"].items()}
        instances = [(c["hdl"]["module"], c["hdl"]["instance"].rsplit(".", 1)[1],
                      {parameter: _value(c, facet) for parameter, facet in c["hdl"]["parameters"].items()},
                      {port: entry["signal"] for port, entry in c["hdl"]["ports"].items()})
                     for c in (roles.transmitter, roles.receiver)]
        expected: Dict[str, Any] = {
            "signals": signals,
            "initial values": {name: 0 for name, (kind, _) in signals.items() if kind == "reg"},
            "instances": instances,
            "clock": roles.clock,
            "half period": round(_value(top, "clock_half_period") * 1e9),
            "reset cycles": _value(top, "reset_cycles"),
            "stimulus": [(roles.data, value) for value in sent],
            "expected bytes": list(sent),
            "expected array size": len(sent),
            "bytes compared": len(sent),
            "bytes awaited": len(sent),
            "end cycle": end_cycle(model),
            "metrics": list(METRICS),
        }
        read = {
            "signals": {name: (kind, width) for name, (kind, width, _) in view.signals.items()},
            "initial values": dict(view.initial_values),
            "instances": [(i.module, i.name, dict(i.overrides), dict(i.connections)) for i in view.instances],
            "clock": view.clock,
            "half period": view.half_period,
            "reset cycles": view.reset_cycles,
            "stimulus": list(view.stimulus),
            "expected bytes": list(view.expected),
            "expected array size": view.expected_size,
            "bytes compared": view.compared,
            "bytes awaited": view.awaited,
            "end cycle": view.end_cycle,
            "metrics": list(view.metrics),
        }
        for what, want in expected.items():
            if read[what] != want:
                problems.append(f"{path}: the harness's {what} {read[what]!r} != the model's {want!r}")
        unexpected = sorted(set(view.system_identifiers) - HARNESS_TASKS)
        if unexpected:
            problems.append(f"{path}: the harness uses {', '.join(unexpected)}")
        own = write_harness(model)
        if harness != own:
            written, found = own.split("\n"), harness.split("\n")
            index = next((n for n, (a, b) in enumerate(zip(written, found)) if a != b), min(len(written), len(found)))
            problems.append(f"{path}:{offset + index + 1}: the harness differs from the one this adapter writes from the "
                            f"model: {found[index] if index < len(found) else None!r}, not "
                            f"{written[index] if index < len(written) else None!r}")
        return problems
