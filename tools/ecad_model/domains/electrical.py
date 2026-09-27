"""The electrical domain: a SPICE netlist, an ngspice deck, closed-form references.

The netlist is the source of truth, read by the strict grammar of
ecad_model.spice. Everything the dataset runner must not know about the
electrical domain lives here: how the netlist and its annotations become the
engineering model (each element a component whose circuit member records its
terminals), which network the domain validates, the deck ngspice runs, the
nine metrics and their closed-form references, and the checks of V1 and V2.
ngspice never sees the netlist: it runs a deck written from the model, so the
chain is netlist -> engineering model -> deck -> simulator.

One network class is validated, and nothing else is accepted: a supply that
ramps once from 0 V, a fuse (its cold resistance only), a precharge resistor
with a voltage-controlled bypass switch, a bulk capacitor with an optional
series resistance, a constant-current load that steps on, and a fault switch
that shorts the rail. Every stimulus is a piecewise-linear source in the
netlist, so one transient covers the whole sequence and each scenario is a
window of it: `startup` up to the fault command, `steady_state` at the fault
command, `output_short` at the end of the fault window.

Every metric is SIMPLIFIED: ideal sources, the fuse as a fixed resistance,
ideal switches, a capacitor with a series resistance only, a constant-current
load, no temperature and no parasitics. The references are computed from the
model's values alone, on a code path independent of the deck and the
simulator, so a writer or simulator error shows up as a golden mismatch.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .. import CIRCUIT_MODEL_VERSION, spice
from ..builder import SCHEMA_ID, index_unknowns, resolve
from ..importers.base import ExtractionError, UnsupportedFormat, regular_file
from ..quantity import Status, is_null, quantity, source
from ..requirements import ReferenceBlocked
from ..schemas import validate as validate_schema
from .base import CaseTarget, DerivedFile, Extraction, Metric, SourceArtifact

VERSION = "1.0.0"  # of this adapter's derived outputs: the deck's analysis and measurements, and the case target
MODEL_BUILDER_VERSION = "1.0.0"  # of the engineering models extract() writes

# Method constants, versioned by VERSION and written into the hash-bound deck.
TSTEP = 1e-06  # s
TMAX = 1e-06  # s; the i2t integration error grows with it (1.7e-7 at 1 us on the committed sample)
FAULT_WINDOW_S = 0.01  # how long the rail stays shorted before the last sample
CHARGED_FRACTION = 0.9  # the rail is charged once it reaches this fraction of the supply
SETTLE_TIME_CONSTANTS = 30  # a steady form applies only this many time constants after the last change
MAX_STEPS = 1_000_000  # T_END / TMAX may not exceed it (resource guard)

# Every metric the deck measures, in the order the deck declares them.
METRICS = {
    "inrush_peak_current_a": Metric("A", "SIMPLIFIED", "peak supply current while the precharge resistor limits it"),
    "inrush_i2t_a2s": Metric("A^2*s", "SIMPLIFIED", "integral of the squared supply current until the bypass is commanded"),
    "bus_charge_time_s": Metric("s", "SIMPLIFIED", "time the rail first reaches CHARGED_FRACTION of the supply"),
    "bus_voltage_at_bypass_v": Metric("V", "SIMPLIFIED", "rail voltage when the bypass is commanded"),
    "bus_peak_voltage_v": Metric("V", "SIMPLIFIED", "highest rail voltage before the fault is commanded"),
    "steady_bus_voltage_v": Metric("V", "SIMPLIFIED", "rail voltage under the load when the fault is commanded"),
    "steady_input_current_a": Metric("A", "SIMPLIFIED", "supply current under the load when the fault is commanded"),
    "steady_fuse_power_w": Metric("W", "SIMPLIFIED", "power in the fuse's resistance under the load"),
    "fault_input_current_a": Metric("A", "SIMPLIFIED", "supply current at the end of the fault window; prospective, "
                                                       "since the fuse never opens"),
}
# The one scenario, a window of the transient, each metric is measured in.
METRIC_SCENARIO = {
    "inrush_peak_current_a": "startup", "inrush_i2t_a2s": "startup", "bus_charge_time_s": "startup",
    "bus_voltage_at_bypass_v": "startup", "bus_peak_voltage_v": "startup", "steady_bus_voltage_v": "steady_state",
    "steady_input_current_a": "steady_state", "steady_fuse_power_w": "steady_state",
    "fault_input_current_a": "output_short",
}
# The metric each closed form computes.
DERIVATION_METRIC = {
    "precharge_peak_current": "inrush_peak_current_a", "precharge_i2t": "inrush_i2t_a2s",
    "precharge_charge_time": "bus_charge_time_s", "precharge_bus_voltage": "bus_voltage_at_bypass_v",
    "settled_no_load_bus_voltage": "bus_peak_voltage_v", "steady_bus_voltage": "steady_bus_voltage_v",
    "steady_input_current": "steady_input_current_a", "steady_fuse_power": "steady_fuse_power_w",
    "settled_fault_input_current": "fault_input_current_a",
}

# Every electrical facet a model of this domain may carry, with its unit.
FACET_UNITS = {
    "resistance": "ohm", "on_resistance": "ohm", "off_resistance": "ohm",
    "capacitance": "F",
    "waveform_time": "s",
    "waveform_voltage": "V", "threshold_voltage": "V", "hysteresis_voltage": "V", "voltage_rating": "V",
    "supply_voltage": "V",
    "waveform_current": "A", "current_rating": "A", "breaking_capacity": "A", "ripple_current_rating": "A",
    "rated_current": "A", "input_ripple_current": "A",
    "power_rating": "W", "rated_power": "W",
    "melting_i2t": "A^2*s",
    "pulse_energy_rating": "J",
    "switching_frequency": "Hz",
}
# The facets the netlist states: the deck is written from these and nothing else.
NETLIST_FACETS = frozenset({"resistance", "capacitance", "waveform_time", "waveform_voltage", "waveform_current",
                            "on_resistance", "off_resistance", "threshold_voltage", "hysteresis_voltage"})
ELEMENT_KINDS = {"resistor": "resistor", "capacitor": "capacitor", "voltage_source": "voltage_source",
                 "current_source": "current_source", "voltage_controlled_switch": "switch"}
NETWORK_CLASS = "the series-precharge supply-input network the electrical domain validates"


@dataclass(frozen=True)
class Roles:
    """The components of the series-precharge supply-input network, by role.

    input_node is the supply's positive node, junction the node between the
    fuse and the precharge resistor, and rail the node the precharge
    resistor and its bypass feed. esr is None when the capacitor goes
    straight to ground.
    """

    supply: Dict[str, Any]
    fuse: Dict[str, Any]
    limiter: Dict[str, Any]
    bypass: Dict[str, Any]
    bypass_command: Dict[str, Any]
    capacitor: Dict[str, Any]
    esr: Optional[Dict[str, Any]]
    load: Dict[str, Any]
    fault: Dict[str, Any]
    fault_command: Dict[str, Any]
    input_node: str
    junction: str
    rail: str


def _n(value: float) -> str:
    """A number as the deck writes it: repr, which reads back as the same float."""
    return repr(float(value))


def _par(a: float, b: float) -> float:
    return a * b / (a + b)


def _circuit(model: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [component for component in model["components"] if "circuit" in component]


def _main(component: Dict[str, Any]) -> Tuple[str, str]:
    terminals = component["circuit"]["terminals"]
    return terminals["p"], terminals["n"]


def _other(component: Dict[str, Any], node: str) -> str:
    p, n = _main(component)
    return n if p == node else p


def _points(component: Dict[str, Any], level: str) -> List[Tuple[Any, Any]]:
    """A source's waveform as (time, level) pairs; empty when it has none."""
    facets = component["domains"].get("electrical", {})
    times = facets.get("waveform_time", {}).get("value")
    levels = facets.get(level, {}).get("value")
    if not isinstance(times, list) or not isinstance(levels, list) or len(times) != len(levels):
        return []
    return list(zip(times, levels))


def _is_ramp(points: Sequence[Tuple[Any, Any]]) -> bool:
    """(0, 0), (t, v) with t > 0 and v > 0."""
    return len(points) == 2 and points[0] == (0.0, 0.0) and points[1][0] > 0 and points[1][1] > 0


def _is_step(points: Sequence[Tuple[Any, Any]]) -> bool:
    """(0, 0), (t0, 0), (t1, h) with 0 < t0 < t1 and h > 0."""
    return (len(points) == 3 and points[0] == (0.0, 0.0) and points[1][1] == 0.0
            and 0 < points[1][0] < points[2][0] and points[2][1] > 0)


def supply_input_roles(model: Dict[str, Any]) -> Roles:
    """Find each component's role in the one network class this domain validates.

    Rules, each named when it is broken:
      C1  exactly one voltage source from ground ramps once, (0, 0) to
          (t_r, V) with t_r, V > 0: the supply; its p node is the input node;
      C2  the input node connects only the supply and one resistor, the fuse,
          whose other end (the junction) is not ground;
      C3  the junction connects only the fuse, one resistor (the precharge
          limiter) and one switch on its p/n pair (the bypass), and both end
          on one rail node other than ground;
      C4  the bypass's cn is ground, and its cp node connects only to it and
          one voltage source from ground stepping (0, 0), (t_b, 0), (t_b + e_b,
          h_b) with t_b, e_b, h_b > 0: the bypass command;
      C5  exactly one capacitor has a terminal on the rail; its other end is
          ground, or a node whose only other element is a resistor to ground
          (its series resistance);
      C6  exactly one current source from the rail to ground (the load),
          stepping (0, 0), (t_l0, 0), (t_l1, I_L) with 0 < t_l0 < t_l1, I_L > 0;
      C7  exactly one other switch from the rail to ground with cn on ground
          (the fault), commanded like the bypass;
      C8  no other element.

    Args:
        model: An engineering model of this domain.

    Returns:
        The roles.

    Raises:
        ExtractionError: Of kind "rejected", naming the rule the circuit
            breaks: the netlist is not a network this domain validates.

    Example:
        >>> import json; from pathlib import Path
        >>> item = Path(__file__).resolve().parents[3] / "datasets/cad/servo_supply_001"
        >>> roles = supply_input_roles(json.loads((item / "derived/engineering_model.json").read_text()))
        >>> roles.fuse["component_id"], roles.rail, roles.esr["component_id"]
        ('r_f1', 'n_bus', 'r_esr')
    """
    path = model["design"]["sources"][0]["path"]

    def refuse(rule: str, why: str) -> ExtractionError:
        return ExtractionError("rejected", f"{path}: not {NETWORK_CLASS}: rule {rule}: {why}")

    circuit = _circuit(model)
    at: Dict[str, List[str]] = {}
    for component in circuit:
        for terminal, node in component["circuit"]["terminals"].items():
            at.setdefault(node, []).append(f"{component['circuit']['designator']}.{terminal}")

    def of(element: str) -> List[Dict[str, Any]]:
        return [c for c in circuit if c["circuit"]["element"] == element]

    def commanded(switch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        control = switch["circuit"]["terminals"]
        sources = [c for c in of("voltage_source") if _main(c) == (control["cp"], "0")]
        if (control["cn"] != "0" or control["cp"] == "0" or len(sources) != 1 or len(at[control["cp"]]) != 2
                or not _is_step(_points(sources[0], "waveform_voltage"))):
            return None
        return sources[0]

    supplies = [c for c in of("voltage_source") if _main(c)[1] == "0" and _is_ramp(_points(c, "waveform_voltage"))]
    if len(supplies) != 1:
        raise refuse("C1", f"{len(supplies)} voltage sources from ground ramp once from (0, 0) to a positive level; "
                           "exactly one, the supply, must")
    supply = supplies[0]
    input_node = _main(supply)[0]

    fuses = [c for c in of("resistor") if input_node in _main(c)]
    if len(fuses) != 1 or len(at[input_node]) != 2 or _other(fuses[0], input_node) == "0":
        raise refuse("C2", f"node {input_node} connects {', '.join(sorted(at[input_node]))}; it must connect only "
                           "the supply and one resistor to a node other than ground, the fuse")
    fuse = fuses[0]
    junction = _other(fuse, input_node)

    limiters = [c for c in of("resistor") if c is not fuse and junction in _main(c)]
    bypasses = [c for c in of("voltage_controlled_switch") if junction in _main(c)]
    if (len(limiters) != 1 or len(bypasses) != 1 or len(at[junction]) != 3
            or _other(limiters[0], junction) == "0" or _other(bypasses[0], junction) != _other(limiters[0], junction)):
        raise refuse("C3", f"node {junction} connects {', '.join(sorted(at[junction]))}; it must connect only the "
                           "fuse, one resistor (the precharge limiter) and one switch (its bypass), both ending on "
                           "one rail node other than ground")
    limiter, bypass = limiters[0], bypasses[0]
    rail = _other(limiter, junction)

    bypass_command = commanded(bypass)
    if bypass_command is None:
        raise refuse("C4", f"the bypass {bypass['circuit']['designator']} must have cn on ground, and cp driven only by "
                           "one voltage source from ground that steps once: (0, 0), (t_b, 0), (t_b + e_b, h_b) with "
                           "t_b, e_b, h_b > 0")

    capacitors = [c for c in of("capacitor") if rail in _main(c)]
    if len(capacitors) != 1:
        raise refuse("C5", f"{len(capacitors)} capacitors on the rail {rail}; exactly one, the bulk capacitor, must be")
    capacitor = capacitors[0]
    far = _other(capacitor, rail)
    esr: Optional[Dict[str, Any]] = None
    if far != "0":
        series = [c for c in of("resistor") if far in _main(c) and _other(c, far) == "0"]
        if len(series) != 1 or len(at[far]) != 2:
            raise refuse("C5", f"node {far} connects {', '.join(sorted(at[far]))}; the bulk capacitor goes to ground, "
                               "or to a node whose only other element is a resistor to ground, its series resistance")
        esr = series[0]

    loads = [c for c in of("current_source") if _main(c) == (rail, "0")]
    if len(loads) != 1 or not _is_step(_points(loads[0], "waveform_current")):
        raise refuse("C6", f"exactly one current source must go from the rail {rail} to ground, the load, stepping "
                           "once: (0, 0), (t_l0, 0), (t_l1, I_L) with 0 < t_l0 < t_l1 and I_L > 0")
    load = loads[0]

    faults = [c for c in of("voltage_controlled_switch") if c is not bypass and _main(c) == (rail, "0")]
    fault_command = commanded(faults[0]) if len(faults) == 1 else None
    if fault_command is None:
        raise refuse("C7", f"exactly one switch other than the bypass must go from the rail {rail} to ground, the "
                           "fault, with cn on ground and cp driven only by one voltage source from ground that steps "
                           "once: (0, 0), (t_f, 0), (t_f + e_f, h_f) with t_f, e_f, h_f > 0")
    fault = faults[0]

    roles = [supply, fuse, limiter, bypass, bypass_command, capacitor, *([esr] if esr else []), load, fault,
             fault_command]
    extra = [c["circuit"]["designator"] for c in circuit if not any(c is role for role in roles)]
    if extra:
        raise refuse("C8", f"{', '.join(extra)} has no role in it")
    return Roles(supply, fuse, limiter, bypass, bypass_command, capacitor, esr, load, fault, fault_command,
                 input_node, junction, rail)


def _value(component: Dict[str, Any], facet: str) -> Any:
    return component["domains"]["electrical"][facet]["value"]


def _windows(roles: Roles) -> Tuple[float, float, float, float]:
    """(T_BYP, T_FLT, T_END, the charge level): where the deck samples."""
    t_byp = _value(roles.bypass_command, "waveform_time")[1]
    t_flt = _value(roles.fault_command, "waveform_time")[1]
    return t_byp, t_flt, t_flt + FAULT_WINDOW_S, CHARGED_FRACTION * _value(roles.supply, "waveform_voltage")[1]


def _section(roles: Roles) -> List[str]:
    """The deck's own lines after the circuit: options, the analysis, and the nine measurements."""
    t_byp, t_flt, t_end, level = _windows(roles)
    supply = roles.supply["circuit"]["designator"]
    # A voltage source's current is negative while it sources: -i() is the supply current.
    current = f"par('-i({supply})')"
    rail = f"v({roles.rail})"
    measured = {
        "inrush_peak_current_a": f"MAX {current} FROM=0.0 TO={_n(t_byp)}",
        "inrush_i2t_a2s": f"INTEG par('i({supply})*i({supply})') FROM=0.0 TO={_n(t_byp)}",
        "bus_charge_time_s": f"WHEN {rail}={_n(level)} RISE=1",
        "bus_voltage_at_bypass_v": f"FIND {rail} AT={_n(t_byp)}",
        "bus_peak_voltage_v": f"MAX {rail} FROM=0.0 TO={_n(t_flt)}",
        # Sampled at T_FLT, a PWL breakpoint: the fault switch closes only after it.
        "steady_bus_voltage_v": f"FIND {rail} AT={_n(t_flt)}",
        "steady_input_current_a": f"FIND {current} AT={_n(t_flt)}",
        "steady_fuse_power_w": f"FIND par('(v({roles.input_node})-v({roles.junction}))*(-i({supply}))') AT={_n(t_flt)}",
        "fault_input_current_a": f"FIND {current} AT={_n(t_end)}",
    }
    return [".options noacct", f".tran {_n(TSTEP)} {_n(t_end)} 0.0 {_n(TMAX)}",
            *(f".meas tran {name} {measured[name]}" for name in METRICS)]


def _element(component: Dict[str, Any]) -> spice.Element:
    circuit = component["circuit"]
    values = {name: facet["value"] for name, facet in component["domains"]["electrical"].items()
              if name in NETLIST_FACETS}
    return spice.Element(circuit["designator"], circuit["element"], dict(circuit["terminals"]), values,
                         circuit.get("model"), 0)


def write_deck(model: Dict[str, Any]) -> bytes:
    r"""The deck ngspice runs, written from the engineering model alone.

    A title comment, a comment saying what wrote it, one line per circuit
    component in model order, each switch's .model card, `.options noacct`
    (which removes the run statistics, so stdout is identical run to run),
    one transient to T_END with a fixed TMAX, the nine measurements, `.end`.
    Every number is a model value, or a sum or product of model values and
    this module's constants, written with repr.

    Args:
        model: An engineering model of this domain.

    Returns:
        The deck's bytes: ASCII, LF line ends.

    Raises:
        ExtractionError: The circuit is not the network class this domain
            validates (see supply_input_roles).

    Example:
        >>> import json; from pathlib import Path
        >>> item = Path(__file__).resolve().parents[3] / "datasets/cad/servo_supply_001"
        >>> deck = write_deck(json.loads((item / "derived/engineering_model.json").read_text()))
        >>> deck.decode().splitlines()[15]
        '.tran 1e-06 0.11 0.0 1e-06'
        >>> deck == (item / "derived/electrical/servo_supply_001.cir").read_bytes()
        True
    """
    roles = supply_input_roles(model)
    netlist = spice.Netlist(model["design"]["name"], tuple(_element(c) for c in _circuit(model)), {})
    lines = [
        f"* {model['design']['name']}",
        f"* written by ecad_model.domains.electrical {VERSION} from derived/engineering_model.json; "
        "regenerate with build, never edit",
        *spice.write_elements(netlist),
        *_section(roles),
        ".end",
    ]
    return ("\n".join(lines) + "\n").encode("ascii")


# The facets each closed form reads, by role; ("esr", ...) is skipped when the
# capacitor goes straight to ground.
_PRECHARGE = (("supply", "waveform_time"), ("supply", "waveform_voltage"), ("fuse", "resistance"),
              ("limiter", "resistance"), ("bypass", "off_resistance"), ("esr", "resistance"),
              ("capacitor", "capacitance"))
_CLOSED = (("supply", "waveform_voltage"), ("fuse", "resistance"), ("limiter", "resistance"),
           ("bypass", "on_resistance"))
_SETTLING = (("capacitor", "capacitance"), ("esr", "resistance"))
_STEADY = (*_CLOSED, ("fault", "off_resistance"), ("load", "waveform_time"), ("load", "waveform_current"),
           ("fault_command", "waveform_time"), *_SETTLING)
INPUTS = {
    "precharge_peak_current": _PRECHARGE,
    "precharge_i2t": (*_PRECHARGE, ("bypass_command", "waveform_time")),
    "precharge_charge_time": (*_PRECHARGE, ("bypass_command", "waveform_time")),
    "precharge_bus_voltage": (*_PRECHARGE, ("bypass_command", "waveform_time")),
    "settled_no_load_bus_voltage": (*_CLOSED, ("fault", "off_resistance"), ("load", "waveform_time"),
                                    ("bypass_command", "waveform_time"), ("bypass_command", "waveform_voltage"),
                                    ("bypass", "threshold_voltage"), ("bypass", "hysteresis_voltage"), *_SETTLING),
    "steady_bus_voltage": _STEADY,
    "steady_input_current": _STEADY,
    "steady_fuse_power": _STEADY,
    "settled_fault_input_current": (*_CLOSED, ("fault", "on_resistance"), ("load", "waveform_current"),
                                    ("fault_command", "waveform_time"), ("fault_command", "waveform_voltage"),
                                    ("fault", "threshold_voltage"), ("fault", "hysteresis_voltage"), *_SETTLING),
}


def _settled(span: float, tau: float) -> bool:
    """Whether a window of this length lets a first-order response settle to within e^-30."""
    return span >= SETTLE_TIME_CONSTANTS * tau


def _inputs(model: Dict[str, Any], derivation: str) -> Tuple[Roles, Dict[Tuple[str, str], Any], List[str],
                                                              List[Dict[str, str]]]:
    """(roles, value by (role, facet), the paths read, the null-status ones) for one closed form."""
    if derivation not in INPUTS:
        raise ValueError(f"unknown derivation {derivation!r}")
    roles = supply_input_roles(model)
    values: Dict[Tuple[str, str], Any] = {}
    paths: List[str] = []
    missing: List[Dict[str, str]] = []
    for role, facet in INPUTS[derivation]:
        component = getattr(roles, role)
        if component is None:
            continue
        path = f"components/{component['component_id']}/domains/electrical/{facet}"
        item = resolve(model, path)
        paths.append(path)
        if is_null(item["status"]):
            missing.append({"path": path, "status": item["status"]})
        values[(role, facet)] = item["value"]
    return roles, values, paths, missing


def reference_value(model: Dict[str, Any], derivation: str,
                    scenario: Optional[Dict[str, Any]] = None) -> Tuple[float, List[str]]:
    """Compute one closed-form reference value from the engineering model.

    With par(a, b) = ab/(a + b), R1 = R_F + par(R_P, R_off,B) + R_E, tau1 =
    R1*C, k = V/t_r and R_c = R_F + par(R_P, R_on,B):

      precharge_peak_current       C*k*(1 - e^(-t_r/tau1)), at the end of the ramp;
      precharge_i2t                the integral of i^2 over the ramp and the
                                   exponential decay after it, up to T_BYP;
      precharge_charge_time        t_r + tau1*ln(A(1 - R_E/R1)/((1 - f)V)), A = V - v_C(t_r);
      precharge_bus_voltage        V - A(1 - R_E/R1)e^(-(T_BYP - t_r)/tau1);
      settled_no_load_bus_voltage  V*R_off,F/(R_off,F + R_c);
      steady_bus_voltage           v_ss = (V - I_L*R_c)/(1 + R_c/R_off,F);
      steady_input_current         (V - v_ss)/R_c;
      steady_fuse_power            i_ss^2 * R_F;
      settled_fault_input_current  (V - v_inf)/R_c, v_inf = (V/R_c - I_L)/(1/R_c + 1/R_on,F).

    The precharge forms neglect the fault switch's off resistance across the
    rail: it draws at most V/R_off,F, 4.8e-8 A on the committed sample, below
    the tightest current tolerance by 2000x.

    Args:
        model: An engineering model of this domain.
        derivation: One of the nine names above.
        scenario: The case's scenario; a scenario carries only its name, so
            it is not read.

    Returns:
        (value in SI units, model paths the value was computed from).

    Raises:
        ReferenceBlocked: An input has a null status (its paths and statuses
            are attached), or the form does not apply to this design: the
            precharge crossing happens during the ramp or after T_BYP, or a
            window is shorter than SETTLE_TIME_CONSTANTS time constants
            (nothing is attached).
        ValueError: The derivation name is not recognised.

    Example:
        >>> import json; from pathlib import Path
        >>> item = Path(__file__).resolve().parents[3] / "datasets/cad/servo_supply_001"
        >>> model = json.loads((item / "derived/engineering_model.json").read_text())
        >>> round(reference_value(model, "precharge_peak_current")[0], 6)
        4.71663
        >>> round(reference_value(model, "settled_fault_input_current", {"name": "output_short"})[0], 3)
        372.465
    """
    roles, values, paths, missing = _inputs(model, derivation)
    if missing:
        raise ReferenceBlocked(f"{derivation} needs quantities that have no value", missing)
    supply_voltage = values[("supply", "waveform_voltage")][1]
    r_f = values[("fuse", "resistance")]
    r_p = values[("limiter", "resistance")]
    r_e = values.get(("esr", "resistance"), 0.0)
    c = values[("capacitor", "capacitance")]

    def not_applicable(why: str) -> ReferenceBlocked:
        return ReferenceBlocked(f"{derivation} does not apply to this design: {why}", [])

    if derivation.startswith("precharge_"):
        t_r = values[("supply", "waveform_time")][1]
        r1 = r_f + _par(r_p, values[("bypass", "off_resistance")]) + r_e
        tau1 = r1 * c
        k = supply_voltage / t_r
        if derivation == "precharge_peak_current":
            # The current rises during the ramp and decays after it.
            return c * k * (1 - math.exp(-t_r / tau1)), paths
        t_byp = values[("bypass_command", "waveform_time")][1]
        a = supply_voltage - k * (t_r - tau1 * (1 - math.exp(-t_r / tau1)))
        if derivation == "precharge_i2t":
            ramp = (c * k) ** 2 * (t_r - 2 * tau1 * (1 - math.exp(-t_r / tau1))
                                   + tau1 / 2 * (1 - math.exp(-2 * t_r / tau1)))
            return ramp + (a / r1) ** 2 * tau1 / 2 * (1 - math.exp(-2 * (t_byp - t_r) / tau1)), paths
        # After the ramp the rail follows V - A(1 - R_E/R1)e^(-(t - t_r)/tau1), rising.
        below = a * (1 - r_e / r1)
        if derivation == "precharge_bus_voltage":
            return supply_voltage - below * math.exp(-(t_byp - t_r) / tau1), paths
        if not below > (1 - CHARGED_FRACTION) * supply_voltage:
            raise not_applicable("the rail reaches the charge level during the supply ramp")
        crossing = t_r + tau1 * math.log(below / ((1 - CHARGED_FRACTION) * supply_voltage))
        if crossing > t_byp:
            raise not_applicable(f"the precharge would reach the charge level at {crossing!r} s, after the bypass "
                                 f"is commanded at {t_byp!r} s")
        return crossing, paths

    r_c = r_f + _par(r_p, values[("bypass", "on_resistance")])
    if derivation == "settled_no_load_bus_voltage":
        r_off_f = values[("fault", "off_resistance")]
        command_time, command_level = (values[("bypass_command", name)] for name in ("waveform_time", "waveform_voltage"))
        closes = command_time[1] + (command_time[2] - command_time[1]) * (
            values[("bypass", "threshold_voltage")] + values[("bypass", "hysteresis_voltage")]) / command_level[2]
        tau2 = c * (r_e + _par(r_c, r_off_f))
        if not _settled(values[("load", "waveform_time")][1] - closes, tau2):
            raise not_applicable("the rail has not settled between the bypass closing and the load stepping on")
        return supply_voltage * r_off_f / (r_off_f + r_c), paths
    if derivation == "settled_fault_input_current":
        r_on_f = values[("fault", "on_resistance")]
        command_time, command_level = (values[("fault_command", name)] for name in ("waveform_time", "waveform_voltage"))
        closes = command_time[1] + (command_time[2] - command_time[1]) * (
            values[("fault", "threshold_voltage")] + values[("fault", "hysteresis_voltage")]) / command_level[2]
        tau_f = c * (r_e + _par(r_c, r_on_f))
        if not _settled(command_time[1] + FAULT_WINDOW_S - closes, tau_f):
            raise not_applicable("the rail has not settled between the fault switch closing and the end of the window")
        v_inf = (supply_voltage / r_c - values[("load", "waveform_current")][2]) / (1 / r_c + 1 / r_on_f)
        return (supply_voltage - v_inf) / r_c, paths
    r_off_f = values[("fault", "off_resistance")]
    load = values[("load", "waveform_current")][2]
    tau2 = c * (r_e + _par(r_c, r_off_f))
    if not _settled(values[("fault_command", "waveform_time")][1] - values[("load", "waveform_time")][2], tau2):
        raise not_applicable("the rail has not settled between the load stepping on and the fault command")
    v_ss = (supply_voltage - load * r_c) / (1 + r_c / r_off_f)
    if derivation == "steady_bus_voltage":
        return v_ss, paths
    i_ss = (supply_voltage - v_ss) / r_c
    if derivation == "steady_input_current":
        return i_ss, paths
    return i_ss ** 2 * r_f, paths


def _netlist_facets(element: spice.Element, origin: Dict[str, str]) -> Dict[str, Any]:
    # Where a value came from is the netlist's to say, in its own comments;
    # what holds for every netlist is that its grammar states no ratings.
    return {
        name: quantity(value, FACET_UNITS[name], Status.SPECIFIED, origin,
                       note=f"{element.designator} {name} as the netlist states it, not a rating of any part")
        for name, value in element.values.items()
    }


def build_circuit_model(netlist: spice.Netlist, annotations: Dict[str, Any], *, netlist_ref: str,
                        netlist_sha256: str, annotations_ref: str, annotations_sha256: str) -> Dict[str, Any]:
    """Build the engineering model of a parsed netlist and its annotations.

    Each element becomes a component, in netlist order, whose id is its
    designator in lower case and whose circuit member records its element,
    terminals and model. Its values are SPECIFIED by the netlist, which is
    cited by hash. The annotations add names, kinds and the ratings of the
    parts the elements stand for, and components with no element, such as
    a product the circuit supplies; they never restate a netlist value.

    Args:
        netlist: The parsed netlist.
        annotations: An engineering-model/v1/design-annotations document.
        netlist_ref: Repository path of the netlist.
        netlist_sha256: Digest of the netlist's bytes.
        annotations_ref: Repository path of the annotations.
        annotations_sha256: Digest of the annotation bytes.

    Returns:
        An engineering-model/v1/engineering-model document of format 1.1.0.

    Raises:
        ValueError: The annotations describe CAD geometry, an element the
            netlist does not declare or a component twice, restate or add
            a netlist value, or relate a component that does not exist.

    Example:
        >>> netlist = spice.parse_netlist(b"rc\\nV1 a 0 PWL(0 0 1u 5)\\nR1 a 0 1k\\n.end\\n", "rc.cir")
        >>> annotations = {"design_id": "rc", "materials": {}, "parts": {}, "joints": [], "attachments": [],
        ...                "circuit_elements": {"R1": {"name": "load resistor", "kind": "resistor"}},
        ...                "components_without_cad": [], "relationships": []}
        >>> model = build_circuit_model(netlist, annotations, netlist_ref="rc.cir", netlist_sha256="0" * 64,
        ...                             annotations_ref="a.json", annotations_sha256="1" * 64)
        >>> [(c["component_id"], c["name"], c["kind"]) for c in model["components"]]
        [('v1', 'V1', 'voltage_source'), ('r1', 'load resistor', 'resistor')]
        >>> model["components"][1]["domains"]["electrical"]["resistance"]["value"], model["model_version"]
        (1000.0, '1.1.0')
    """
    netlist_source = source("design_annotation", netlist_ref, netlist_sha256)
    annotation_source = source("design_annotation", annotations_ref, annotations_sha256)
    for key in ("materials", "parts", "joints", "attachments"):
        if annotations[key]:
            raise ValueError(f"the annotations give {key}, which describe CAD geometry a netlist does not have")
    described = annotations.get("circuit_elements", {})
    undeclared = sorted(set(described) - {element.designator for element in netlist.elements})
    if undeclared:
        raise ValueError(f"the annotations describe {', '.join(undeclared)}, which the netlist does not declare")
    components: List[Dict[str, Any]] = []
    for element in netlist.elements:
        annotated = described.get(element.designator, {})
        stated = _netlist_facets(element, netlist_source)
        domains = {name: dict(facet) for name, facet in annotated.get("domains", {}).items()}
        added = domains.get("electrical", {})
        twice = sorted(set(stated) & set(added))
        if twice:
            raise ValueError(f"{element.designator}: {', '.join(twice)} declared twice: the netlist states it, "
                             "so the annotations may not")
        # A netlist value the element does not carry would sit in the model
        # unread: the deck is written from the netlist's values alone.
        foreign = sorted((set(added) - set(stated)) & NETLIST_FACETS)
        if foreign:
            raise ValueError(f"{element.designator}: {', '.join(foreign)} is a netlist value, which only the "
                             "netlist states; the annotations may not add one")
        domains["electrical"] = {**stated, **added}
        circuit: Dict[str, Any] = {"designator": element.designator, "element": element.element,
                                   "terminals": dict(element.terminals)}
        if element.model is not None:
            circuit["model"] = element.model
        components.append({
            "component_id": element.designator.lower(),
            "name": annotated.get("name", element.designator),
            "kind": annotated.get("kind", ELEMENT_KINDS[element.element]),
            "cad_ref": None, "material": None, "geometry": None, "physical": None, "placement": None,
            "circuit": circuit,
            "domains": domains,
        })
    known_ids = {component["component_id"] for component in components}
    for extra in annotations["components_without_cad"]:
        if extra["component_id"] in known_ids:
            raise ValueError(f"component {extra['component_id']!r} is declared twice")
        known_ids.add(extra["component_id"])
        components.append({
            "component_id": extra["component_id"], "name": extra["name"], "kind": extra["kind"],
            "cad_ref": None, "material": None, "geometry": None, "physical": None, "placement": None,
            "domains": {name: dict(facet) for name, facet in extra["domains"].items()},
        })
    design_id = annotations["design_id"]
    relationships = [{"relation": "contains", "from": design_id, "to": component["component_id"],
                      "source": netlist_source} for component in components if "circuit" in component]
    for relation in annotations["relationships"]:
        for key in ("from", "to"):
            if relation[key] not in known_ids:
                raise ValueError(f"relationship names unknown component {relation[key]!r}")
        relationships.append({**relation, "source": annotation_source})
    model = {
        "$schema": SCHEMA_ID,
        "model_version": CIRCUIT_MODEL_VERSION,
        "design": {"design_id": design_id, "name": netlist.title, "revision": "1.0",
                   "sources": [{"path": netlist_ref, "format": "spice", "sha256": netlist_sha256}]},
        "components": components,
        "joints": [],
        "relationships": relationships,
        "unknowns": [],
    }
    model["unknowns"] = index_unknowns(model)
    return model


class ElectricalAdapter:
    """The series-precharge supply-input network in a SPICE netlist, simulated with ngspice."""

    domain = "electrical"
    formats = frozenset({"spice"})
    description = ("the series-precharge supply-input network only (a supply ramp, a fuse's cold resistance, a "
                   "precharge resistor with a bypass switch, a bulk capacitor with its series resistance, a "
                   "constant-current load and a fault switch): inrush, precharge, steady-state and output-short "
                   "metrics from one ngspice transient, compared with closed-form references")

    def deck_path(self, sample_id: str) -> str:
        return f"derived/electrical/{sample_id}.cir"

    def extract(self, root: Path, sources: Sequence[SourceArtifact], annotations: Dict[str, Any],
                refs: Dict[str, str]) -> Extraction:
        """Read the netlist with the strict grammar and build the engineering model from it.

        Raises:
            ExtractionError: Of kind "rejected": the netlist is not a regular
                file within the size limit, is outside the grammar, has a
                title the deck cannot carry, is not the network class this
                domain validates, or its transient would need more than
                MAX_STEPS steps (spec §26). None of these reaches ngspice.
            ValueError: Not exactly one spice source, or the annotations are
                inconsistent with the netlist.
        """
        netlists = [artifact for artifact in sources if artifact.format == "spice"]
        if len(netlists) != 1:
            raise ValueError(f"the electrical domain reads exactly one spice source, found {len(netlists)}")
        path = root / netlists[0].path
        netlist_ref = f"{refs['sample']}/{netlists[0].path}"
        try:
            regular_file(path, spice.MAX_NETLIST_BYTES)
        except UnsupportedFormat as exc:
            raise ExtractionError("rejected", f"{netlist_ref}: {exc}") from exc
        data = path.read_bytes()
        netlist = spice.parse_netlist(data, netlist_ref)
        if len(netlist.title) + 2 > spice.MAX_LINE_CHARS:
            raise ExtractionError("rejected", f"{netlist_ref}:1: the title is {len(netlist.title)} characters; the "
                                              f"deck writes it as '* <title>', and a line holds {spice.MAX_LINE_CHARS}")
        model = build_circuit_model(
            netlist, annotations, netlist_ref=netlist_ref, netlist_sha256=hashlib.sha256(data).hexdigest(),
            annotations_ref=refs["annotations"], annotations_sha256=refs["annotations_sha256"])
        roles = supply_input_roles(model)  # a netlist outside the class never reaches ngspice
        # The resource guard is a refusal, not a V1 finding: V1's findings do
        # not stop the cases, so only here does it keep a run from starting.
        steps = _windows(roles)[2] / TMAX
        if steps > MAX_STEPS:
            raise ExtractionError("rejected", f"{netlist_ref}: the transient to the end of the fault window needs "
                                              f"{steps!r} steps of {TMAX!r} s, more than {MAX_STEPS}")
        return Extraction(model=model, producer=("ecad_model.domains.electrical",
                                                 f"{MODEL_BUILDER_VERSION} (ecad_model.spice {spice.VERSION})"))

    def write_models(self, model: Dict[str, Any], sample_id: str) -> List[DerivedFile]:
        return [DerivedFile(
            path=self.deck_path(sample_id), data=write_deck(model), role="domain_model", media_type="text/x-spice",
            producer="ecad_model.domains.electrical", version=VERSION,
            derived_from=("derived/engineering_model.json",), comparator="exact")]

    def case_target(self, sample_id: str) -> CaseTarget:
        # Every case runs the same deck: a scenario is a window of its one transient.
        return CaseTarget(adapter="ngspice", inputs=(self.deck_path(sample_id),), arguments=lambda scenario: [])

    def reference_value(self, model: Dict[str, Any], derivation: str,
                        scenario: Dict[str, Any]) -> Tuple[float, List[str]]:
        return reference_value(model, derivation, scenario)

    def metrics(self) -> Dict[str, Metric]:
        return dict(METRICS)

    def check_requirements(self, requirements: Dict[str, Any]) -> None:
        """Every scenario and derivation must be one this domain implements,
        each metric must be asked for in the scenario it is measured in, and
        each reference must compare the metric its derivation computes.

        Raises:
            ValueError: A scenario or derivation is not in the electrical
                vocabulary (schemas/engineering-model/v1/electrical-vocabulary),
                or a metric or derivation is paired with the wrong scenario
                or metric.
        """
        validate_schema({
            "scenarios": [entry["scenario"] for entry in (*requirements["reference_values"], *requirements["requirements"])],
            "derivations": [entry["derivation"] for entry in requirements["reference_values"]],
        }, "engineering-model/v1/electrical-vocabulary")
        for entry in (*requirements["reference_values"], *requirements["requirements"]):
            entry_id = entry.get("reference_id", entry.get("requirement_id"))
            window = METRIC_SCENARIO.get(entry["metric"])
            if window is not None and entry["scenario"]["name"] != window:
                raise ValueError(f"{entry_id}: {entry['metric']} is measured in the {window} scenario, "
                                 f"not {entry['scenario']['name']}")
        for reference in requirements["reference_values"]:
            if DERIVATION_METRIC[reference["derivation"]] != reference["metric"]:
                raise ValueError(f"{reference['reference_id']}: {reference['derivation']} computes "
                                 f"{DERIVATION_METRIC[reference['derivation']]}, not {reference['metric']}")

    def dependencies(self, model: Dict[str, Any], metric: str, scenario: Dict[str, Any]) -> List[str]:
        """The model quantities a simulated metric depends on.

        Coarse on purpose: every value the netlist states for every circuit
        component, since every case runs the one deck written from all of
        them. Ratings are not simulated, so they are not dependencies.
        """
        return sorted(f"components/{c['component_id']}/domains/electrical/{name}"
                      for c in _circuit(model) for name in c["domains"].get("electrical", {})
                      if name in NETLIST_FACETS)

    def reference_inputs(self, model: Dict[str, Any], derivation: str, scenario: Dict[str, Any]) -> List[str]:
        """The model paths a reference derivation reads, whether or not it applies."""
        return _inputs(model, derivation)[2]

    def document_schemas(self) -> Dict[str, str]:
        return {}  # no extraction file: the model is built from the netlist directly

    def components_for(self, model: Dict[str, Any], metric: str) -> List[str]:
        """Every circuit component, as "<id> (<designator>)": every metric comes from the whole circuit."""
        return sorted(f"{c['component_id']} ({c['circuit']['designator']})" for c in _circuit(model))

    def simulation_files(self, root: Path) -> List[str]:
        return []  # the deck is derived; no script runs

    def sanity_problems(self, model: Dict[str, Any]) -> List[str]:
        """Why the circuit's values, units or sequence are impossible for the deck's windows, if they are."""
        problems = []
        for component in model["components"]:
            for name, facet in component["domains"].get("electrical", {}).items():
                unit = FACET_UNITS.get(name)
                if unit is None:
                    problems.append(f"{component['component_id']}: {name} is not in the electrical facet vocabulary")
                elif facet["unit"] != unit:
                    problems.append(f"{component['component_id']}: {name} is in {facet['unit']}, not the "
                                    f"vocabulary's {unit}")
                elif name not in NETLIST_FACETS and not is_null(facet["status"]):
                    value = facet["value"]
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
                        problems.append(f"{component['component_id']}: {name} {value!r} is not a positive number")
        for component in _circuit(model):
            label = component["circuit"]["designator"]
            facets = {name: facet["value"] for name, facet in component["domains"]["electrical"].items()
                      if name in NETLIST_FACETS}
            for name in ("resistance", "capacitance", "on_resistance"):
                if name in facets and not facets[name] > 0:
                    problems.append(f"{label}: {name} {facets[name]!r} is not positive")
            if component["circuit"]["element"] == "voltage_controlled_switch":
                if not facets["off_resistance"] > facets["on_resistance"]:
                    problems.append(f"{label}: off_resistance {facets['off_resistance']!r} is not above "
                                    f"on_resistance {facets['on_resistance']!r}")
                if not facets["hysteresis_voltage"] >= 0:
                    problems.append(f"{label}: hysteresis_voltage {facets['hysteresis_voltage']!r} is negative")
                if not facets["threshold_voltage"] > facets["hysteresis_voltage"]:
                    problems.append(f"{label}: threshold_voltage {facets['threshold_voltage']!r} is not above "
                                    f"hysteresis_voltage {facets['hysteresis_voltage']!r}, so the switch does not "
                                    "start open")
        # The resource guard (T_END / TMAX <= MAX_STEPS) is applied by extract:
        # a V1 problem does not stop the cases running, so here it would bound nothing.
        roles = supply_input_roles(model)
        closes = {}
        for switch, command in ((roles.bypass, roles.bypass_command), (roles.fault, roles.fault_command)):
            times, levels = _value(command, "waveform_time"), _value(command, "waveform_voltage")
            on = _value(switch, "threshold_voltage") + _value(switch, "hysteresis_voltage")
            if not levels[2] > on:
                problems.append(f"{command['circuit']['designator']}: its high level {levels[2]!r} V does not exceed "
                                f"{switch['circuit']['designator']}'s VT + VH = {on!r} V, so the switch never closes")
            closes[switch["component_id"]] = times[1] + (times[2] - times[1]) * on / levels[2]
        t_r = _value(roles.supply, "waveform_time")[1]
        t_b = _value(roles.bypass_command, "waveform_time")[1]
        load_times = _value(roles.load, "waveform_time")
        t_f = _value(roles.fault_command, "waveform_time")[1]
        if not t_r < t_b:
            problems.append(f"the supply ramp ends at {t_r!r} s, not before the bypass command at {t_b!r} s")
        if not closes[roles.bypass["component_id"]] < load_times[1]:
            problems.append(f"the bypass closes at {closes[roles.bypass['component_id']]!r} s, not before the load "
                            f"steps on at {load_times[1]!r} s")
        if not load_times[2] < t_f:
            problems.append(f"the load is fully on at {load_times[2]!r} s, not before the fault command at {t_f!r} s")
        return problems

    def invariant_problems(self, model: Dict[str, Any], extraction_files: Dict[str, Any],
                           domain_models: Dict[str, bytes]) -> List[str]:
        """The deck is the model's circuit plus exactly the adapter's lines; every
        netlist value cites the netlist; a supply matches the sheet of what it powers."""
        problems = []
        circuit = _circuit(model)
        for path, deck in domain_models.items():
            try:
                written, section = spice.read_deck(deck, path)
            except spice.NetlistRefused as exc:
                problems.append(f"{path}: the deck is not one this adapter writes: {exc}")
                continue
            if written.title != f"* {model['design']['name']}":
                problems.append(f"{path}: the title line is {written.title!r}, not the design's name")
            if len(written.elements) != len(circuit):
                problems.append(f"{path}: {len(written.elements)} elements, but the model has {len(circuit)}")
            for component, element in zip(circuit, written.elements):
                expected = _element(component)
                for field in ("designator", "element", "terminals", "model", "values"):
                    if getattr(element, field) != getattr(expected, field):
                        problems.append(f"{path}:{element.line}: {element.designator} {field} "
                                        f"{getattr(element, field)!r} != the model's {getattr(expected, field)!r}")
            own = _section(supply_input_roles(model))
            for index, (line, want) in enumerate(zip(section, own)):
                if line != want:
                    problems.append(f"{path}: the adapter's line {index + 1} is {line!r}, not {want!r}")
            if len(section) != len(own):
                problems.append(f"{path}: {len(section)} lines follow the circuit, not the adapter's {len(own)}")
        netlist = model["design"]["sources"][0]
        for component in circuit:
            for name, facet in component["domains"]["electrical"].items():
                if name in NETLIST_FACETS and (facet["source"].get("sha256") != netlist["sha256"]
                                               or facet["source"]["ref"] != netlist["path"]):
                    problems.append(f"{component['component_id']}: {name} does not cite the netlist "
                                    f"{netlist['path']} by its hash")
        by_id = {component["component_id"]: component for component in model["components"]}
        for relation in model["relationships"]:
            if relation["relation"] != "powered_by":
                continue
            powered, supply = by_id.get(relation["from"]), by_id.get(relation["to"])
            stated = (powered or {}).get("domains", {}).get("electrical", {}).get("supply_voltage")
            if (stated is None or is_null(stated["status"]) or supply is None
                    or supply.get("circuit", {}).get("element") != "voltage_source"):
                continue
            final = _value(supply, "waveform_voltage")[-1]
            if final != stated["value"]:
                problems.append(f"{relation['to']} settles at {final!r} V, but {relation['from']}, which it powers, "
                                f"is supplied at {stated['value']!r} V ({stated['source']['ref']})")
        return problems
