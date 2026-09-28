"""The electrical domain on datasets/cad/servo_supply_001, with no simulator.

The sample is a 48 V servo-drive supply input written as a SPICE netlist:
fuse, precharge resistor with a bypass switch, bulk capacitor with its
series resistance, a constant-current load and a fault switch. These tests
need neither a CAD kernel nor ngspice. Where a case must "run", a stand-in
for the ngspice adapter answers every deck with RECORDED_STDOUT, the output
ngspice-47 printed for the committed deck on macOS arm64 on 2026-09-27
(identical over two runs, empty stderr), read through the real adapter's
own parser. tests/unit/test_electrical_spice.py runs the real ngspice.

Expected values are typed by hand from the netlist text and the closed forms
written out in this file, never obtained by calling the code under test.
Every copy of the sample a test changes is labelled a fixture and lives in a
scratch directory; nothing here edits the committed item.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

ITEM = REPO_ROOT / "datasets" / "cad" / "servo_supply_001"
MECHANICAL_ITEM = REPO_ROOT / "datasets" / "cad" / "robotic_joint_001"
NETLIST = "source/servo_supply_001.cir"
DECK_PATH = "derived/electrical/servo_supply_001.cir"
NETLIST_REF = "datasets/cad/servo_supply_001/source/servo_supply_001.cir"
ANNOTATIONS_REF = "datasets/cad/servo_supply_001/design/annotations.json"
NETLIST_SHA256 = "838cde196936a321bdca5e41eca4a91902b4ee0a8f1fe8dcc86401a7a3ef3344"
SHEET = "eRobotics_CAD_Design/robot_components/product_datasheet.md"
SHEET_SHA256 = "f6e4502a3a93112aab7fcd91c9c9242c1227cde8d21c6614dabbab2291094f8c"
LICENSE_SHA256 = "2779b5d4987171210e3c18f461e4ee832426c3c52ca3e53a7dce23af057c4c0a"
EMPTY_SET = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

# The deck of the design (§4.2), typed from the netlist and the adapter's templates.
DECK = (
    "* servo_supply_001: 48 V servo-drive supply input -- fuse, precharge limiter with bypass, bulk capacitor, drive load\n"
    "* written by ecad_model.domains.electrical 1.0.0 from derived/engineering_model.json; regenerate with build, never edit\n"
    "V_IN n_in 0 PWL(0.0 0.0 0.0001 48.0)\n"
    "R_F1 n_in n_f 0.02\n"
    "R_PRE n_f n_bus 10.0\n"
    "S_BYP n_f n_bus n_byp 0 SW_BYP\n"
    "V_BYP n_byp 0 PWL(0.0 0.0 0.03 0.0 0.030001 5.0)\n"
    "C_BULK n_bus n_esr 0.00047\n"
    "R_ESR n_esr 0 0.05\n"
    "I_LOAD n_bus 0 PWL(0.0 0.0 0.04 0.0 0.0401 4.16667)\n"
    "S_FLT n_bus 0 n_fc 0 SW_FLT\n"
    "V_FLT n_fc 0 PWL(0.0 0.0 0.1 0.0 0.100001 5.0)\n"
    ".model SW_BYP SW(RON=0.01 ROFF=1000000000.0 VT=2.5 VH=0.0)\n"
    ".model SW_FLT SW(RON=0.1 ROFF=1000000000.0 VT=2.5 VH=0.0)\n"
    ".options noacct\n"
    ".tran 1e-06 0.11 0.0 1e-06\n"
    ".meas tran inrush_peak_current_a MAX par('-i(V_IN)') FROM=0.0 TO=0.03\n"
    ".meas tran inrush_i2t_a2s INTEG par('i(V_IN)*i(V_IN)') FROM=0.0 TO=0.03\n"
    ".meas tran bus_charge_time_s WHEN v(n_bus)=43.2 RISE=1\n"
    ".meas tran bus_voltage_at_bypass_v FIND v(n_bus) AT=0.03\n"
    ".meas tran bus_peak_voltage_v MAX v(n_bus) FROM=0.0 TO=0.1\n"
    ".meas tran steady_bus_voltage_v FIND v(n_bus) AT=0.1\n"
    ".meas tran steady_input_current_a FIND par('-i(V_IN)') AT=0.1\n"
    ".meas tran steady_fuse_power_w FIND par('(v(n_in)-v(n_f))*(-i(V_IN))') AT=0.1\n"
    ".meas tran fault_input_current_a FIND par('-i(V_IN)') AT=0.11\n"
    ".end\n"
)
DECK_SHA256 = "2840fc040b30a626891a347bb447a242f81ce97cd23aa415a6e32c7ef4451d30"
# ngspice-47, macOS arm64, 2026-09-27: `ngspice -b` on DECK, byte for byte.
RECORDED_STDOUT = (
    "\n"
    "Note: No compatibility mode selected!\n"
    "\n"
    "\n"
    "Circuit: * servo_supply_001: 48 v servo-drive supply input -- fuse, precharge limiter with bypass, bulk capacitor, drive load\n"
    "\n"
    "Doing analysis at TEMP = 27.000000 and TNOM = 27.000000\n"
    "\n"
    "Using SPARSE 1.3 as Direct Linear Solver\n"
    "\n"
    "No. of Data Rows : 110053\n"
    "\n"
    "  Measurements for Transient Analysis\n"
    "\n"
    "inrush_peak_current_a=  4.71663e+00 at=  1.00000e-04\n"
    "inrush_i2t_a2s      =   5.33906e-02 from=  0.00000e+00 to=  3.00000e-02\n"
    "bus_charge_time_s   =   1.09244e-02\n"
    "bus_voltage_at_bypass_v=  4.79147e+01\n"
    "bus_peak_voltage_v  =  4.80000e+01 at=  4.00000e-02\n"
    "steady_bus_voltage_v=  4.78750e+01\n"
    "steady_input_current_a=  4.16667e+00\n"
    "steady_fuse_power_w =  3.47223e-01\n"
    "fault_input_current_a=  3.72465e+02\n"
    "\n"
    "\n"
)
# Typed from the lines above.
RECORDED_METRICS = {
    "inrush_peak_current_a": 4.71663, "inrush_i2t_a2s": 0.0533906, "bus_charge_time_s": 0.0109244,
    "bus_voltage_at_bypass_v": 47.9147, "bus_peak_voltage_v": 48.0, "steady_bus_voltage_v": 47.875,
    "steady_input_current_a": 4.16667, "steady_fuse_power_w": 0.347223, "fault_input_current_a": 372.465,
}
# The netlist's values in SI units, read by hand: 20m is 0.02, 470u is 0.00047, 1g is 1e9.
NETLIST_VALUES: Dict[str, Dict[str, Any]] = {
    "v_in": {"waveform_time": [0.0, 0.0001], "waveform_voltage": [0.0, 48.0]},
    "r_f1": {"resistance": 0.02},
    "r_pre": {"resistance": 10.0},
    "s_byp": {"on_resistance": 0.01, "off_resistance": 1e9, "threshold_voltage": 2.5, "hysteresis_voltage": 0.0},
    "v_byp": {"waveform_time": [0.0, 0.03, 0.030001], "waveform_voltage": [0.0, 0.0, 5.0]},
    "c_bulk": {"capacitance": 0.00047},
    "r_esr": {"resistance": 0.05},
    "i_load": {"waveform_time": [0.0, 0.04, 0.0401], "waveform_current": [0.0, 0.0, 4.16667]},
    "s_flt": {"on_resistance": 0.1, "off_resistance": 1e9, "threshold_voltage": 2.5, "hysteresis_voltage": 0.0},
    "v_flt": {"waveform_time": [0.0, 0.1, 0.100001], "waveform_voltage": [0.0, 0.0, 5.0]},
}
UNITS = {"waveform_time": "s", "waveform_voltage": "V", "waveform_current": "A", "resistance": "ohm",
         "capacitance": "F", "on_resistance": "ohm", "off_resistance": "ohm", "threshold_voltage": "V",
         "hysteresis_voltage": "V"}
CIRCUIT = {
    "v_in": ("V_IN", "voltage_source", {"p": "n_in", "n": "0"}, None),
    "r_f1": ("R_F1", "resistor", {"p": "n_in", "n": "n_f"}, None),
    "r_pre": ("R_PRE", "resistor", {"p": "n_f", "n": "n_bus"}, None),
    "s_byp": ("S_BYP", "voltage_controlled_switch", {"p": "n_f", "n": "n_bus", "cp": "n_byp", "cn": "0"}, "SW_BYP"),
    "v_byp": ("V_BYP", "voltage_source", {"p": "n_byp", "n": "0"}, None),
    "c_bulk": ("C_BULK", "capacitor", {"p": "n_bus", "n": "n_esr"}, None),
    "r_esr": ("R_ESR", "resistor", {"p": "n_esr", "n": "0"}, None),
    "i_load": ("I_LOAD", "current_source", {"p": "n_bus", "n": "0"}, None),
    "s_flt": ("S_FLT", "voltage_controlled_switch", {"p": "n_bus", "n": "0", "cp": "n_fc", "cn": "0"}, "SW_FLT"),
    "v_flt": ("V_FLT", "voltage_source", {"p": "n_fc", "n": "0"}, None),
}
KINDS = {"v_in": "voltage_source", "r_f1": "fuse", "r_pre": "resistor", "s_byp": "switch", "v_byp": "voltage_source",
         "c_bulk": "capacitor", "r_esr": "resistor", "i_load": "current_source", "s_flt": "switch",
         "v_flt": "voltage_source", "drive": "motor_driver"}
# The closed forms of the design (§5.3), to the 12 significant figures the golden cases store.
CLOSED_FORMS = {
    "precharge_peak_current": 4.71663002764, "precharge_i2t": 0.0533907676223,
    "precharge_charge_time": 0.0109244343789, "precharge_bus_voltage": 47.9147188794,
    "settled_no_load_bus_voltage": 47.9999999986, "steady_bus_voltage": 47.8750415236,
    "steady_input_current": 4.16667004787, "steady_fuse_power": 0.347222785757,
    "settled_fault_input_current": 372.464522495,
}
# Rule C5's other branch: the bulk capacitor straight to ground, so R_E = 0.
# The four precharge forms move; the settled forms read R_E only to decide
# whether the rail has settled, so their values stay. Typed from _closed_forms
# below at R_E = 0 (the design's own closed-form script gives the same digits).
NO_ESR = ("C_BULK n_bus n_esr 470u\nR_ESR n_esr 0 50m\n", "C_BULK n_bus 0 470u\n")
NO_ESR_CLOSED_FORMS = {**CLOSED_FORMS, "precharge_peak_current": 4.7399171105, "precharge_i2t": 0.0536553201,
                       "precharge_charge_time": 0.0108938826039, "precharge_bus_voltage": 47.9169573916}


def _path(component: str, facet: str) -> str:
    return f"components/{component}/domains/electrical/{facet}"


PRECHARGE_INPUTS = [_path("v_in", "waveform_time"), _path("v_in", "waveform_voltage"), _path("r_f1", "resistance"),
                    _path("r_pre", "resistance"), _path("s_byp", "off_resistance"), _path("r_esr", "resistance"),
                    _path("c_bulk", "capacitance")]
CLOSED_INPUTS = [_path("v_in", "waveform_voltage"), _path("r_f1", "resistance"), _path("r_pre", "resistance"),
                 _path("s_byp", "on_resistance"), _path("c_bulk", "capacitance"), _path("r_esr", "resistance")]
STEADY_INPUTS = [*CLOSED_INPUTS, _path("s_flt", "off_resistance"), _path("i_load", "waveform_time"),
                 _path("i_load", "waveform_current"), _path("v_flt", "waveform_time")]
# What each closed form reads, typed from its formula.
REFERENCE_INPUTS = {
    "precharge_peak_current": PRECHARGE_INPUTS,
    "precharge_i2t": [*PRECHARGE_INPUTS, _path("v_byp", "waveform_time")],
    "precharge_charge_time": [*PRECHARGE_INPUTS, _path("v_byp", "waveform_time")],
    "precharge_bus_voltage": [*PRECHARGE_INPUTS, _path("v_byp", "waveform_time")],
    "settled_no_load_bus_voltage": [*CLOSED_INPUTS, _path("s_flt", "off_resistance"), _path("i_load", "waveform_time"),
                                    _path("v_byp", "waveform_time"), _path("v_byp", "waveform_voltage"),
                                    _path("s_byp", "threshold_voltage"), _path("s_byp", "hysteresis_voltage")],
    "steady_bus_voltage": STEADY_INPUTS,
    "steady_input_current": STEADY_INPUTS,
    "steady_fuse_power": STEADY_INPUTS,
    "settled_fault_input_current": [*CLOSED_INPUTS, _path("s_flt", "on_resistance"), _path("i_load", "waveform_current"),
                                    _path("v_flt", "waveform_time"), _path("v_flt", "waveform_voltage"),
                                    _path("s_flt", "threshold_voltage"), _path("s_flt", "hysteresis_voltage")],
}
UNKNOWNS = [
    (_path("c_bulk", "ripple_current_rating"), "UNKNOWN"), (_path("c_bulk", "voltage_rating"), "UNKNOWN"),
    (_path("drive", "input_ripple_current"), "UNSPECIFIED"), (_path("drive", "switching_frequency"), "UNSPECIFIED"),
    (_path("r_f1", "breaking_capacity"), "UNKNOWN"), (_path("r_f1", "current_rating"), "UNKNOWN"),
    (_path("r_f1", "melting_i2t"), "UNKNOWN"), (_path("r_pre", "power_rating"), "UNKNOWN"),
    (_path("r_pre", "pulse_energy_rating"), "UNKNOWN"), (_path("s_byp", "current_rating"), "UNKNOWN"),
]
FIXTURE_SOURCE = {"kind": "design_annotation", "ref": "tests/unit/test_electrical_domain.py"}


def _closed_forms(p: Dict[str, float]) -> Dict[str, float]:
    """The nine forms of the design (§5.2), written out independently of the adapter."""
    def par(a: float, b: float) -> float:
        return a * b / (a + b)

    volts, ramp, cap = p["V"], p["tr"], p["C"]
    r1 = p["RF"] + par(p["RP"], p["RoffB"]) + p["RE"]
    tau1, slope = r1 * cap, volts / ramp
    decay = 1 - math.exp(-ramp / tau1)
    left = volts - slope * (ramp - tau1 * decay)  # A = V - v_C(t_r)
    below = left * (1 - p["RE"] / r1)
    rc = p["RF"] + par(p["RP"], p["RonB"])
    v_ss = (volts - p["IL"] * rc) / (1 + rc / p["RoffF"])
    i_ss = (volts - v_ss) / rc
    v_inf = (volts / rc - p["IL"]) / (1 / rc + 1 / p["RonF"])
    return {
        "precharge_peak_current": cap * slope * decay,
        "precharge_i2t": (cap * slope) ** 2 * (ramp - 2 * tau1 * decay + tau1 / 2 * (1 - math.exp(-2 * ramp / tau1)))
        + (left / r1) ** 2 * tau1 / 2 * (1 - math.exp(-2 * (p["tb"] - ramp) / tau1)),
        "precharge_charge_time": ramp + tau1 * math.log(below / (0.1 * volts)),
        "precharge_bus_voltage": volts - below * math.exp(-(p["tb"] - ramp) / tau1),
        "settled_no_load_bus_voltage": volts * p["RoffF"] / (p["RoffF"] + rc),
        "steady_bus_voltage": v_ss,
        "steady_input_current": i_ss,
        "steady_fuse_power": i_ss ** 2 * p["RF"],
        "settled_fault_input_current": (volts - v_inf) / rc,
    }


# The committed netlist's values, typed from its text.
PARAMETERS = {"V": 48.0, "tr": 0.0001, "RF": 0.02, "RP": 10.0, "RonB": 0.01, "RoffB": 1e9, "RE": 0.05, "C": 0.00047,
              "IL": 4.16667, "RonF": 0.1, "RoffF": 1e9, "tb": 0.03}


def _model() -> Dict[str, Any]:
    return json.loads((ITEM / "derived" / "engineering_model.json").read_bytes())


def _component(model: Dict[str, Any], component_id: str) -> Dict[str, Any]:
    return next(c for c in model["components"] if c["component_id"] == component_id)


def _set(model: Dict[str, Any], component_id: str, facet: str, value: Any) -> Dict[str, Any]:
    """A copy of the model with one electrical value changed (a fixture)."""
    changed = copy.deepcopy(model)
    _component(changed, component_id)["domains"]["electrical"][facet]["value"] = value
    return changed


def _adapter() -> Any:
    from ecad_model.domains.electrical import ElectricalAdapter

    return ElectricalAdapter()


def _scratch():
    return tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-")


def _copy(directory: str, edits: Optional[Dict[str, Tuple[str, str]]] = None, rebuild: bool = True) -> Path:
    """A fixture copy of the sample, with one text replacement in each named file."""
    from ecad_model.dataset import build

    item = Path(directory) / "servo_supply_001"
    shutil.copytree(ITEM, item)
    for relative, (old, new) in (edits or {}).items():
        path = item / relative
        data = path.read_bytes()
        if data.count(old.encode()) != 1:
            raise AssertionError(f"{relative}: expected {old!r} exactly once")
        path.write_bytes(data.replace(old.encode(), new.encode()))
    if rebuild:
        build(item)
    return item


def _edit_json(path: Path, change: Callable[[Any], None]) -> None:
    document = json.loads(path.read_bytes())
    change(document)
    path.write_bytes((json.dumps(document, indent=2) + "\n").encode())


def _annotated(document: Dict[str, Any], designator: str) -> Dict[str, Any]:
    return document["circuit_elements"][designator]["domains"]["electrical"]


def _stand_in(stdout: str = RECORDED_STDOUT, refuse: bool = False):
    """The ngspice adapter replaced by one that answers every deck with a
    recorded stdout, read through the real adapter's parser; or, with
    refuse, one that fails the test if any case reaches it. Test-only."""
    from ecad_validation.adapters.base import Adapter, AdapterResult, Capability
    from ecad_validation.adapters.ngspice import declared_measurements, parse_measurements
    from ecad_validation.models import ExecutionStatus, Verdict

    class StandInNgspice(Adapter):
        name = "ngspice"

        def capability(self):
            return Capability(adapter="ngspice", available=True, version="stand-in 0")

        def run(self, request):
            if refuse:
                raise AssertionError(f"{request.input_files} reached ngspice")
            deck = request.input_files[0]
            declared, _ = declared_measurements(deck.read_bytes().decode("utf-8"))
            metrics, _ = parse_measurements(stdout, "", declared)
            return AdapterResult(adapter="ngspice", execution_status=ExecutionStatus.COMPLETED, verdict=Verdict.PASS,
                                 reason_code="TOOL_EXITED_ZERO", summary="stand-in: ngspice-47's recorded output",
                                 command=["ngspice", "-b", deck.relative_to(request.product_root).as_posix()],
                                 tool_version="stand-in 0", stdout=stdout, metrics=dict(metrics))

    return mock.patch.dict("ecad_validation.cases.ADAPTERS", {"ngspice": StandInNgspice})


def _no_ngspice():
    """The real ngspice adapter, reporting ngspice not installed wherever the test runs."""
    from ecad_validation.adapters.base import Capability

    return mock.patch("ecad_validation.adapters.ngspice.probe_executable",
                      return_value=Capability(adapter="ngspice", available=False, reason="TOOL_NOT_INSTALLED"))


def _validate(item: Path, simulator: Any = None) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    from ecad_model.dataset import validate

    with tempfile.TemporaryDirectory() as output, (simulator if simulator is not None else _stand_in()):
        run = Path(output) / "run"
        receipt = validate(item, run)
        results = json.loads((run / "results.json").read_bytes()) if (run / "results.json").exists() else None
    return receipt, results


def _checks(receipt: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {c["check_id"]: c for g in receipt["gates"] for c in g["checks"]}


def _outcome(check: Dict[str, Any]) -> Tuple[str, str]:
    return check["verdict"], check["reason_code"]


def _requirement(requirement_id: str, component: str, metric: str, scenario: str, operator: str, limit: Any,
                 unit: str, illustrative: bool = True, **extra: Any) -> Dict[str, Any]:
    return {"requirement_id": requirement_id, "title": f"test fixture {requirement_id}", "domain": "electrical",
            "component": component, "metric": metric, "scenario": {"name": scenario}, "operator": operator,
            "limit": limit if isinstance(limit, dict) else {"value": limit}, "unit": unit,
            "illustrative": illustrative,
            "source": {"kind": "requirement", "ref": "tests/unit/test_electrical_domain.py: a fixture, not a requirement"},
            **extra}


def _rebuild(item: Path) -> None:
    from ecad_model.dataset import build

    build(item)


def _add_requirements(item: Path, *requirements: Dict[str, Any]) -> None:
    _edit_json(item / "requirements" / "requirements.json",
               lambda document: document["requirements"].extend(requirements))
    _rebuild(item)


class TestModel(unittest.TestCase):
    def test_every_netlist_value_is_specified_by_the_netlist_and_names_no_part(self):
        model = _model()
        self.assertEqual(hashlib.sha256((ITEM / NETLIST).read_bytes()).hexdigest(), NETLIST_SHA256)
        self.assertEqual(model["model_version"], "1.1.0")
        self.assertEqual(model["design"]["sources"], [{"path": NETLIST_REF, "format": "spice", "sha256": NETLIST_SHA256}])
        self.assertEqual(model["design"]["name"], "servo_supply_001: 48 V servo-drive supply input -- fuse, precharge "
                                                  "limiter with bypass, bulk capacitor, drive load")
        self.assertNotIn("gravity", model["design"])
        # Netlist order, then the component the annotations add.
        self.assertEqual([c["component_id"] for c in model["components"]], [*CIRCUIT, "drive"])
        netlist = {"kind": "design_annotation", "ref": NETLIST_REF, "sha256": NETLIST_SHA256}
        for component in model["components"]:
            cid = component["component_id"]
            with self.subTest(cid):
                self.assertEqual(component["kind"], KINDS[cid])
                self.assertEqual([component[key] for key in ("cad_ref", "material", "geometry", "physical", "placement")],
                                 [None] * 5)
                if cid == "drive":
                    self.assertNotIn("circuit", component)
                    continue
                designator, element, terminals, model_name = CIRCUIT[cid]
                expected_circuit = {"designator": designator, "element": element, "terminals": terminals}
                if model_name:
                    expected_circuit["model"] = model_name
                self.assertEqual(component["circuit"], expected_circuit)
                facets = component["domains"]["electrical"]
                stated = {name: facet for name, facet in facets.items() if facet["source"]["ref"] == NETLIST_REF}
                self.assertEqual({name: facet["value"] for name, facet in stated.items()}, NETLIST_VALUES[cid])
                for name, facet in stated.items():
                    self.assertEqual(facet, {"value": NETLIST_VALUES[cid][name], "unit": UNITS[name],
                                             "status": "SPECIFIED", "source": netlist,
                                             "note": f"{designator} {name} as the netlist states it, not a rating of any part"})
        contains = [(r["relation"], r["from"], r["to"], r["source"]) for r in model["relationships"] if r["relation"] == "contains"]
        self.assertEqual(contains, [("contains", "servo_supply_001", cid, netlist) for cid in CIRCUIT])

    def test_no_rating_of_an_unselected_part_has_a_value(self):
        model = _model()
        self.assertEqual([(u["path"], u["status"], u["needed_by"]) for u in model["unknowns"]],
                         [(path, status, ["electrical"]) for path, status in UNKNOWNS])
        annotations = {"kind": "design_annotation", "ref": ANNOTATIONS_REF}
        sheet = {"kind": "product_specification", "ref": SHEET, "sha256": SHEET_SHA256}
        units = {"ripple_current_rating": "A", "voltage_rating": "V", "input_ripple_current": "A",
                 "switching_frequency": "Hz", "breaking_capacity": "A", "current_rating": "A", "melting_i2t": "A^2*s",
                 "power_rating": "W", "pulse_energy_rating": "J"}
        for path, status in UNKNOWNS:
            with self.subTest(path):
                _, cid, _, _, facet = path.split("/")
                quantity = _component(model, cid)["domains"]["electrical"][facet]
                self.assertEqual((quantity["value"], quantity["unit"], quantity["status"]), (None, units[facet], status))
                self.assertEqual(quantity["source"], sheet if cid == "drive" else annotations)
                self.assertTrue(quantity["note"])
        statuses = set()

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                if {"value", "status", "source"} <= node.keys():
                    statuses.add(node["status"])
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(model["components"])
        self.assertEqual(statuses, {"SPECIFIED", "UNKNOWN", "UNSPECIFIED"},
                         "nothing is MEASURED, SIMULATED, ESTIMATED, DERIVED or AI_ASSUMPTION")

    def test_the_supply_traces_to_the_product_sheet(self):
        self.assertEqual(hashlib.sha256((REPO_ROOT / SHEET).read_bytes()).hexdigest(), SHEET_SHA256)
        model = _model()
        drive = _component(model, "drive")["domains"]["electrical"]
        sheet = {"kind": "product_specification", "ref": SHEET, "sha256": SHEET_SHA256}
        for facet, value, unit in (("supply_voltage", 48.0, "V"), ("rated_current", 5.0, "A"), ("rated_power", 200.0, "W")):
            with self.subTest(facet):
                self.assertEqual((drive[facet]["value"], drive[facet]["unit"], drive[facet]["status"], drive[facet]["source"]),
                                 (value, unit, "SPECIFIED", sheet))
        self.assertIn({"relation": "powered_by", "from": "drive", "to": "v_in",
                       "source": {"kind": "design_annotation", "ref": ANNOTATIONS_REF,
                                  "sha256": hashlib.sha256((ITEM / "design" / "annotations.json").read_bytes()).hexdigest()}},
                      model["relationships"])
        self.assertEqual(_adapter().invariant_problems(model, {}, {DECK_PATH: DECK.encode()}), [])
        # A supply voltage the sheet does not state leaves nothing to compare.
        unstated = copy.deepcopy(model)
        _component(unstated, "drive")["domains"]["electrical"]["supply_voltage"].update(value=None, status="UNSPECIFIED")
        self.assertEqual(_adapter().invariant_problems(unstated, {}, {DECK_PATH: DECK.encode()}), [])
        with _scratch() as directory:
            item = _copy(directory, {NETLIST: ("V_IN n_in 0 PWL(0 0 100u 48)", "V_IN n_in 0 PWL(0 0 100u 60)")})
            receipt, _ = _validate(item)
        invariants = _checks(receipt)["v2.electrical.model-invariants"]
        self.assertEqual(_outcome(invariants), ("FAIL", "DOMAIN_MODEL_INCONSISTENT"))
        self.assertIn(f"v_in settles at 60.0 V, but drive, which it powers, is supplied at 48.0 V ({SHEET})",
                      invariants["findings"])

    def test_a_circuit_member_needs_format_1_1_0(self):
        from ecad_model.schemas import validate as validate_schema

        model = _model()
        validate_schema(model, "engineering-model/v1/engineering-model")
        mechanical = json.loads((MECHANICAL_ITEM / "derived" / "engineering_model.json").read_bytes())
        validate_schema(mechanical, "engineering-model/v1/engineering-model")

        def circuit(cid: str, change: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
            changed = copy.deepcopy(model)
            change(_component(changed, cid)["circuit"])
            return changed

        def first_kind(document: Dict[str, Any], kind: str) -> Dict[str, Any]:
            changed = copy.deepcopy(document)
            changed["components"][0]["kind"] = kind
            return changed

        refused = {
            "a circuit member in format 1.0.0": {**model, "model_version": "1.0.0"},
            "an electrical kind in format 1.0.0": first_kind(mechanical, "resistor"),
            "a designator letter that is not its element's": circuit("r_pre", lambda c: c.update(element="capacitor")),
            "a switch without a control terminal": circuit("s_byp", lambda c: c["terminals"].pop("cp")),
            "a switch without a model": circuit("s_byp", lambda c: c.pop("model")),
            "a resistor with a model": circuit("r_pre", lambda c: c.update(model="SW_BYP")),
            "a resistor with a control terminal": circuit("r_pre", lambda c: c["terminals"].update(cp="n_byp")),
            "the node gnd": circuit("r_esr", lambda c: c["terminals"].update(n="gnd")),
            "a par() node": circuit("r_esr", lambda c: c["terminals"].update(n="pa_0")),
            "an upper-case node": circuit("r_esr", lambda c: c["terminals"].update(p="N_ESR")),
            "a node without the n_ prefix": circuit("r_esr", lambda c: c["terminals"].update(p="esr")),
            "the node time, which a .meas reads as the time axis": circuit("r_esr", lambda c: c["terminals"].update(p="time")),
            "a model without the SW_ prefix": circuit("s_byp", lambda c: c.update(model="TEMPER")),
            "a lower-case designator": circuit("r_esr", lambda c: c.update(designator="r_esr")),
            "an unknown terminal": circuit("r_esr", lambda c: c["terminals"].update(g="0")),
        }
        for label, document in refused.items():
            with self.subTest(label), self.assertRaises(ValueError):
                validate_schema(document, "engineering-model/v1/engineering-model")
        validate_schema({**first_kind(mechanical, "resistor"), "model_version": "1.1.0"},
                        "engineering-model/v1/engineering-model")

        annotations = json.loads((ITEM / "design" / "annotations.json").read_bytes())
        validate_schema(annotations, "engineering-model/v1/design-annotations")
        validate_schema({**{k: v for k, v in annotations.items() if k != "circuit_elements"}, "annotations_version": "1.0.0"},
                        "engineering-model/v1/design-annotations")

        def element(change: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
            changed = copy.deepcopy(annotations)
            change(changed["circuit_elements"])
            return changed

        for label, document in {
            "circuit_elements in format 1.0.0": {**annotations, "annotations_version": "1.0.0"},
            "a lower-case designator key": element(lambda e: e.update(r_x={"name": "x", "kind": "resistor"})),
            "an unknown element kind": element(lambda e: e["R_ESR"].update(kind="inductor")),
            "an unknown element member": element(lambda e: e["R_ESR"].update(value=0.05)),
        }.items():
            with self.subTest(label), self.assertRaises(ValueError):
                validate_schema(document, "engineering-model/v1/design-annotations")

    def test_annotations_add_names_kinds_and_ratings_but_never_netlist_values(self):
        from ecad_model import spice
        from ecad_model.domains.electrical import build_circuit_model

        netlist = spice.parse_netlist((ITEM / NETLIST).read_bytes(), NETLIST_REF)
        committed = json.loads((ITEM / "design" / "annotations.json").read_bytes())

        def built(change: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
            annotations = copy.deepcopy(committed)
            change(annotations)
            return build_circuit_model(netlist, annotations, netlist_ref=NETLIST_REF, netlist_sha256=NETLIST_SHA256,
                                       annotations_ref=ANNOTATIONS_REF, annotations_sha256="0" * 64)

        restated = {"value": 0.02, "unit": "ohm", "status": "SPECIFIED", "source": FIXTURE_SOURCE}
        for label, change, message in (
            ("a value the netlist states", lambda a: _annotated(a, "R_F1").update(resistance=restated),
             "R_F1: resistance declared twice: the netlist states it"),
            ("a netlist value the element does not carry", lambda a: _annotated(a, "C_BULK").update(resistance=restated),
             "C_BULK: resistance is a netlist value, which only the netlist states"),
            ("an element the netlist does not declare",
             lambda a: a["circuit_elements"].update(R_X={"name": "x", "kind": "resistor"}),
             "the annotations describe R_X, which the netlist does not declare"),
            ("a component id a designator already has",
             lambda a: a["components_without_cad"][0].update(component_id="r_f1"), "component 'r_f1' is declared twice"),
            ("a relationship to nothing", lambda a: a["relationships"][0].update(to="v_nowhere"),
             "relationship names unknown component 'v_nowhere'"),
            ("CAD parts", lambda a: a["parts"].update(x={"component_id": "x", "kind": "other", "material": "m"}),
             "the annotations give parts, which describe CAD geometry a netlist does not have"),
        ):
            with self.subTest(label), self.assertRaisesRegex(ValueError, message):
                built(change)
        unannotated = built(lambda a: [a["circuit_elements"].pop(d) for d in ("V_IN", "R_ESR", "C_BULK", "I_LOAD", "S_FLT")])
        self.assertEqual([(c["component_id"], c["name"], c["kind"]) for c in unannotated["components"]
                          if c["component_id"] in ("v_in", "r_esr", "c_bulk", "i_load", "s_flt")],
                         [("v_in", "V_IN", "voltage_source"), ("c_bulk", "C_BULK", "capacitor"),
                          ("r_esr", "R_ESR", "resistor"), ("i_load", "I_LOAD", "current_source"),
                          ("s_flt", "S_FLT", "switch")])
        # Through the pipeline, a restated value is an invalid input, never a silent override.
        with _scratch() as directory:
            item = _copy(directory, rebuild=False)
            _edit_json(item / "design" / "annotations.json", lambda a: _annotated(a, "R_F1").update(resistance=restated))
            receipt, _ = _validate(item, _stand_in(refuse=True))
        v1 = _checks(receipt)["v1.electrical.extraction-and-sanity"]
        self.assertEqual(_outcome(v1), ("FAIL", "DATASET_INPUT_INVALID"))
        self.assertIn("R_F1: resistance declared twice", v1["findings"][0])

    def test_the_adapter_reads_exactly_one_spice_source(self):
        from ecad_model.domains.base import SourceArtifact

        annotations = (ITEM / "design" / "annotations.json").read_bytes()
        refs = {"sample": "datasets/cad/servo_supply_001", "annotations": ANNOTATIONS_REF,
                "annotations_sha256": hashlib.sha256(annotations).hexdigest()}
        netlist = SourceArtifact(NETLIST, "spice")
        for label, sources, found in (("none", [], 0), ("only a STEP file", [SourceArtifact("source/x.step", "step")], 0),
                                      ("two", [netlist, SourceArtifact("source/second.cir", "spice")], 2)):
            with self.subTest(label), self.assertRaisesRegex(
                    ValueError, f"^the electrical domain reads exactly one spice source, found {found}$"):
                _adapter().extract(ITEM, sources, json.loads(annotations), refs)


class TestNetworkAndSanity(unittest.TestCase):
    def test_only_the_series_precharge_supply_network_is_accepted(self):
        from ecad_model.dataset import build
        from ecad_model.importers import ExtractionError

        for label, (old, new), rule in (
            ("C1: the supply steps instead of ramping once", ("V_IN n_in 0 PWL(0 0 100u 48)", "V_IN n_in 0 PWL(0 0 100u 48 200u 48)"), "C1"),
            ("C2: the input node feeds a second element", (".end\n", "R_X n_in 0 1k\n.end\n"), "C2"),
            ("C3: the junction feeds a third element", (".end\n", "R_X n_f 0 1k\n.end\n"), "C3"),
            ("C3: C_BULK moved to n_f", ("C_BULK n_bus n_esr 470u", "C_BULK n_f n_esr 470u"), "C3"),
            ("C4: the bypass command is not one step", ("V_BYP n_byp 0 PWL(0 0 30m 0 30.001m 5)",
                                                        "V_BYP n_byp 0 PWL(0 0 30m 0 30.001m 5 40m 0)"), "C4"),
            ("C5: a second capacitor on the rail", (".end\n", "C_X n_bus 0 1u\n.end\n"), "C5"),
            ("C5: the series resistance's node feeds a third element", (".end\n", "R_X n_esr 0 1k\n.end\n"), "C5"),
            ("C5: the bulk capacitor is not on the rail",
             ("C_BULK n_bus n_esr 470u\nR_ESR n_esr 0 50m", "C_BULK n_esr 0 470u\nR_ESR n_esr 0 50m"), "C5"),
            ("C6: the load ramps instead of stepping", ("I_LOAD n_bus 0 PWL(0 0 40m 0 40.1m 4.16667)",
                                                        "I_LOAD n_bus 0 PWL(0 0 40m 4.16667)"), "C6"),
            ("C7: the fault switch is turned round", ("S_FLT n_bus 0 n_fc 0 SW_FLT", "S_FLT 0 n_bus n_fc 0 SW_FLT"), "C7"),
            ("C8: an element with no role", (".end\n", "R_X n_bus 0 1k\n.end\n"), "C8"),
        ):
            with self.subTest(label), _scratch() as directory:
                item = _copy(directory, {NETLIST: (old, new)}, rebuild=False)
                with self.assertRaises(ExtractionError) as raised:
                    build(item)
                self.assertEqual(raised.exception.kind, "rejected")
                self.assertIn(f"{NETLIST}: not the series-precharge supply-input network the electrical domain "
                              f"validates: rule {rule}:", str(raised.exception))
        # The deck writes the title as "* <title>" on a line of at most 1024
        # characters: 1022 fit, 1023 do not.
        title = "servo_supply_001: 48 V servo-drive supply input -- fuse, precharge limiter with bypass, bulk capacitor, drive load"
        for length, refused in ((1022, False), (1023, True)):
            with self.subTest(title=length), _scratch() as directory:
                item = _copy(directory, {NETLIST: (title, "t" * length)}, rebuild=False)
                if refused:
                    with self.assertRaisesRegex(ExtractionError, f"{NETLIST}:1: the title is 1023 characters"):
                        build(item)
                else:
                    build(item)
                    self.assertEqual(_adapter().invariant_problems(
                        json.loads((item / "derived" / "engineering_model.json").read_bytes()), {},
                        {DECK_PATH: (item / DECK_PATH).read_bytes()}), [])
        # A netlist over the parser's limit is refused before it is read.
        with _scratch() as directory:
            item = _copy(directory, rebuild=False)
            with (item / NETLIST).open("ab") as netlist:
                netlist.write(b"*" * (1 << 20))
            with self.assertRaises(ExtractionError) as raised:
                build(item)
            self.assertEqual(raised.exception.kind, "rejected")
            self.assertIn(f"exceeds the {1 << 20}-byte input limit", str(raised.exception))
        # The resource guard is a refusal too: 1.01 s of 1 us steps is more than a million.
        with _scratch() as directory:
            item = _copy(directory, {NETLIST: ("V_FLT n_fc 0 PWL(0 0 100m 0 100.001m 5)",
                                               "V_FLT n_fc 0 PWL(0 0 1 0 1.000001 5)")}, rebuild=False)
            with self.assertRaisesRegex(ExtractionError, "more than 1000000"):
                build(item)
            receipt, _ = _validate(item, _stand_in(refuse=True))
        v1 = _checks(receipt)["v1.electrical.extraction-and-sanity"]
        self.assertEqual(_outcome(v1), ("FAIL", "SOURCE_REJECTED"))
        self.assertIn("steps of 1e-06 s, more than 1000000", v1["findings"][0])

    def test_v1_refuses_impossible_values_units_and_sequences(self):
        adapter = _adapter()
        model = _model()
        self.assertEqual(adapter.sanity_problems(model), [])

        def with_facet(cid: str, facet: str, change: Dict[str, Any]) -> Dict[str, Any]:
            changed = copy.deepcopy(model)
            electrical = _component(changed, cid)["domains"]["electrical"]
            electrical[facet] = {**electrical.get(facet, {"value": 1.0, "status": "SPECIFIED", "source": FIXTURE_SOURCE}),
                                 **change}
            return changed

        for label, changed, problem in (
            ("a facet outside the vocabulary", with_facet("c_bulk", "inductance", {"unit": "H"}),
             "c_bulk: inductance is not in the electrical facet vocabulary"),
            ("a rating in mV", with_facet("c_bulk", "voltage_rating", {"unit": "mV"}),
             "c_bulk: voltage_rating is in mV, not the vocabulary's V"),
            ("a netlist value in the wrong unit", with_facet("r_pre", "resistance", {"unit": "kohm"}),
             "r_pre: resistance is in kohm, not the vocabulary's ohm"),
            ("a known rating that is not positive", _set(model, "drive", "rated_current", 0.0),
             "drive: rated_current 0.0 is not a positive number"),
            ("a zero resistance", _set(model, "r_esr", "resistance", 0.0), "R_ESR: resistance 0.0 is not positive"),
            ("a negative capacitance", _set(model, "c_bulk", "capacitance", -1e-06),
             "C_BULK: capacitance -1e-06 is not positive"),
            ("a zero on resistance", _set(model, "s_flt", "on_resistance", 0.0), "S_FLT: on_resistance 0.0 is not positive"),
            ("an off resistance below the on resistance", _set(model, "s_byp", "off_resistance", 0.005),
             "S_BYP: off_resistance 0.005 is not above on_resistance 0.01"),
            ("a negative hysteresis", _set(model, "s_flt", "hysteresis_voltage", -0.5),
             "S_FLT: hysteresis_voltage -0.5 is negative"),
            ("a switch that starts closed", _set(model, "s_byp", "threshold_voltage", 0.0),
             "S_BYP: threshold_voltage 0.0 is not above hysteresis_voltage 0.0, so the switch does not start open"),
            ("a command that never closes its switch", _set(model, "v_flt", "waveform_voltage", [0.0, 0.0, 2.5]),
             "V_FLT: its high level 2.5 V does not exceed S_FLT's VT + VH = 2.5 V, so the switch never closes"),
            ("a ramp that ends after the bypass command", _set(model, "v_in", "waveform_time", [0.0, 0.05]),
             "the supply ramp ends at 0.05 s, not before the bypass command at 0.03 s"),
            ("a load on only after the fault command", _set(model, "i_load", "waveform_time", [0.0, 0.04, 0.2]),
             "the load is fully on at 0.2 s, not before the fault command at 0.1 s"),
        ):
            with self.subTest(label):
                self.assertEqual(adapter.sanity_problems(changed), [problem])
        late = adapter.sanity_problems(_set(model, "v_byp", "waveform_time", [0.0, 0.045, 0.045001]))
        self.assertEqual(len(late), 1)
        self.assertRegex(late[0], r"^the bypass closes at 0\.04500\d+ s, not before the load steps on at 0\.04 s$")
        # Through the pipeline: V1 FAIL, with the finding.
        with _scratch() as directory:
            item = _copy(directory, {NETLIST: ("SW(RON=10m ROFF=1g VT=2.5 VH=0)", "SW(RON=2g ROFF=1g VT=2.5 VH=0)")})
            receipt, _ = _validate(item)
        v1 = _checks(receipt)["v1.electrical.extraction-and-sanity"]
        self.assertEqual(_outcome(v1), ("FAIL", "DOMAIN_SANITY_FAILED"))
        self.assertEqual(v1["findings"], ["S_BYP: off_resistance 1000000000.0 is not above on_resistance 2000000000.0"])


class TestDeck(unittest.TestCase):
    def test_the_deck_is_the_model_with_the_adapters_analysis_and_measurements(self):
        from ecad_model.domains.electrical import write_deck

        self.assertEqual(hashlib.sha256(DECK.encode()).hexdigest(), DECK_SHA256)
        self.assertEqual(write_deck(_model()), DECK.encode())
        self.assertEqual((ITEM / DECK_PATH).read_bytes(), DECK.encode())
        [written] = _adapter().write_models(_model(), "servo_supply_001")
        self.assertEqual((written.path, written.data, written.role, written.media_type, written.producer, written.version,
                          written.derived_from, written.comparator),
                         (DECK_PATH, DECK.encode(), "domain_model", "text/x-spice", "ecad_model.domains.electrical",
                          "1.0.0", ("derived/engineering_model.json",), "exact"))
        target = _adapter().case_target("servo_supply_001")
        self.assertEqual((target.adapter, target.inputs, target.arguments({"name": "startup"}), target.timeout_seconds),
                         ("ngspice", (DECK_PATH,), [], 300))

    def test_v2_names_every_way_a_deck_can_disagree_with_its_model(self):
        adapter = _adapter()
        model = _model()

        def problems(old: str, new: str, changed: Optional[Dict[str, Any]] = None) -> List[str]:
            self.assertEqual(DECK.count(old), 1, old)
            return adapter.invariant_problems(changed or model, {}, {DECK_PATH: DECK.replace(old, new).encode()})

        self.assertEqual(adapter.invariant_problems(model, {}, {DECK_PATH: DECK.encode()}), [])
        last_meas = ".meas tran fault_input_current_a FIND par('-i(V_IN)') AT=0.11\n"
        for label, (old, new), expected in (
            ("a changed value", ("R_PRE n_f n_bus 10.0", "R_PRE n_f n_bus 1.0"),
             f"{DECK_PATH}:5: R_PRE values {{'resistance': 1.0}} != the model's {{'resistance': 10.0}}"),
            ("a swapped terminal", ("R_F1 n_in n_f 0.02", "R_F1 n_f n_in 0.02"), f"{DECK_PATH}:4: R_F1 terminals"),
            ("a dropped element", ("I_LOAD n_bus 0 PWL(0.0 0.0 0.04 0.0 0.0401 4.16667)\n", ""),
             f"{DECK_PATH}: 9 elements, but the model has 10"),
            ("a missing measurement", (last_meas, ""), f"{DECK_PATH}: 10 lines follow the circuit, not the adapter's 11"),
            ("an extra measurement", (last_meas, last_meas + ".meas tran extra_v FIND v(n_bus) AT=0.05\n"),
             f"{DECK_PATH}: 12 lines follow the circuit, not the adapter's 11"),
            ("a duplicated measurement", (last_meas, last_meas + last_meas),
             f"{DECK_PATH}: the deck is not one this adapter writes"),
            ("a flipped current sign", ("MAX par('-i(V_IN)')", "MAX par('i(V_IN)')"),
             f"{DECK_PATH}: the adapter's line 3 is \".meas tran inrush_peak_current_a MAX par('i(V_IN)') FROM=0.0 TO=0.03\""),
            ("a changed analysis", (".tran 1e-06 0.11 0.0 1e-06", ".tran 1e-06 0.11 0.0 1e-05"),
             f"{DECK_PATH}: the adapter's line 2 is '.tran 1e-06 0.11 0.0 1e-05', not '.tran 1e-06 0.11 0.0 1e-06'"),
            ("a control block", (".end\n", ".control\nshell touch pwned\n.endc\n.end\n"),
             f"{DECK_PATH}: the deck is not one this adapter writes"),
            ("a changed title", ("* servo_supply_001: 48 V", "* servo_supply_001: 60 V"), f"{DECK_PATH}: the title line is"),
        ):
            with self.subTest(label):
                found = problems(old, new)
                self.assertTrue(any(problem.startswith(expected) for problem in found), found)
        unbound = copy.deepcopy(model)
        _component(unbound, "r_pre")["domains"]["electrical"]["resistance"]["source"]["sha256"] = "0" * 64
        self.assertEqual(adapter.invariant_problems(unbound, {}, {DECK_PATH: DECK.encode()}),
                         [f"r_pre: resistance does not cite the netlist {NETLIST_REF} by its hash"])


class TestReferences(unittest.TestCase):
    def test_references_are_the_closed_forms_written_out_here(self):
        from ecad_model.domains.electrical import reference_value

        adapter = _adapter()
        model = _model()
        written_out = _closed_forms(PARAMETERS)
        undersized = _closed_forms({**PARAMETERS, "RP": 1.0})
        small = _set(model, "r_pre", "resistance", 1.0)
        for derivation, stored in CLOSED_FORMS.items():
            with self.subTest(derivation):
                value, used = reference_value(model, derivation, {"name": "startup"})
                self.assertEqual(float(f"{value:.12g}"), stored)
                self.assertLessEqual(abs(value - written_out[derivation]), 1e-12 * abs(written_out[derivation]))
                self.assertEqual(sorted(used), sorted(REFERENCE_INPUTS[derivation]))
                self.assertEqual(len(used), len(set(used)))
                self.assertEqual(sorted(adapter.reference_inputs(model, derivation, {"name": "startup"})),
                                 sorted(REFERENCE_INPUTS[derivation]))
                value = reference_value(small, derivation)[0]
                self.assertLessEqual(abs(value - undersized[derivation]), 1e-12 * abs(undersized[derivation]))
        # The design's closed form for the undersized precharge resistor (§6.4).
        self.assertLessEqual(abs(reference_value(small, "precharge_peak_current")[0] - 40.6811962), 1e-7)
        self.assertEqual(sorted(adapter.dependencies(model, "inrush_peak_current_a", {"name": "startup"})),
                         sorted(_path(cid, facet) for cid, values in NETLIST_VALUES.items() for facet in values))
        self.assertEqual(adapter.components_for(model, "fault_input_current_a"),
                         sorted(f"{cid} ({designator})" for cid, (designator, _, _, _) in CIRCUIT.items()))
        with self.assertRaisesRegex(ValueError, "unknown derivation 'precharge_energy'"):
            reference_value(model, "precharge_energy")

    def test_the_bulk_capacitor_may_go_straight_to_ground(self):
        """Rule C5's other branch: with no series resistance every closed form is
        the written-out one at R_E = 0, and none reads a resistance that is not there."""
        from ecad_model.dataset import build
        from ecad_model.domains.electrical import reference_value, supply_input_roles

        adapter = _adapter()
        with _scratch() as directory:
            item = _copy(directory, {NETLIST: NO_ESR}, rebuild=False)
            _edit_json(item / "design" / "annotations.json", lambda document: document["circuit_elements"].pop("R_ESR"))
            build(item)
            model = json.loads((item / "derived" / "engineering_model.json").read_bytes())
            deck = (item / DECK_PATH).read_bytes()
        roles = supply_input_roles(model)
        self.assertIsNone(roles.esr)
        self.assertEqual((roles.capacitor["circuit"]["terminals"], roles.rail), ({"p": "n_bus", "n": "0"}, "n_bus"))
        self.assertEqual(deck, DECK.replace("C_BULK n_bus n_esr 0.00047\nR_ESR n_esr 0 0.05\n",
                                            "C_BULK n_bus 0 0.00047\n").encode())
        self.assertEqual(adapter.sanity_problems(model), [])
        self.assertEqual(adapter.invariant_problems(model, {}, {DECK_PATH: deck}), [])
        written_out = _closed_forms({**PARAMETERS, "RE": 0.0})
        for derivation, stored in NO_ESR_CLOSED_FORMS.items():
            with self.subTest(derivation):
                value, used = reference_value(model, derivation, {"name": "startup"})
                self.assertEqual(float(f"{value:.12g}"), stored)
                self.assertLessEqual(abs(value - written_out[derivation]), 1e-12 * abs(written_out[derivation]))
                self.assertEqual(sorted(used), sorted(path for path in REFERENCE_INPUTS[derivation]
                                                      if path != _path("r_esr", "resistance")))

    def test_a_reference_does_not_apply_where_its_assumptions_fail(self):
        from ecad_model.domains.electrical import reference_value
        from ecad_model.requirements import ReferenceBlocked, compile_cases

        adapter = _adapter()
        model = _model()
        early = _set(model, "v_byp", "waveform_time", [0.0, 0.005, 0.005001])
        slow_ramp = _set(_set(model, "v_in", "waveform_time", [0.0, 0.06]), "v_byp", "waveform_time", [0.0, 0.07, 0.070001])
        for label, changed, derivations, why in (
            ("the rail crosses 90 % after the bypass", early, ["precharge_charge_time"], "after the bypass is commanded"),
            ("the rail crosses 90 % during the ramp", slow_ramp, ["precharge_charge_time"], "during the supply ramp"),
            ("the rail has not settled before the load", _set(model, "i_load", "waveform_time", [0.0, 0.0305, 0.0306]),
             ["settled_no_load_bus_voltage"], "between the bypass closing and the load stepping on"),
            ("the rail has not settled before the fault", _set(model, "i_load", "waveform_time", [0.0, 0.04, 0.0995]),
             ["steady_bus_voltage", "steady_input_current", "steady_fuse_power"],
             "between the load stepping on and the fault command"),
            ("the fault window is too short to settle", _set(model, "v_flt", "waveform_time", [0.0, 0.1, 0.1198]),
             ["settled_fault_input_current"], "between the fault switch closing and the end of the window"),
        ):
            for derivation in derivations:
                with self.subTest(label, derivation=derivation), self.assertRaises(ReferenceBlocked) as raised:
                    reference_value(changed, derivation)
                self.assertEqual(raised.exception.paths, [], "a form that does not apply lacks no input")
                self.assertIn(f"{derivation} does not apply to this design", str(raised.exception))
                self.assertIn(why, str(raised.exception))
        # The early bypass still has every other reference.
        requirements = json.loads((ITEM / "requirements" / "requirements.json").read_bytes())
        golden, _, blocked = compile_cases(early, requirements, adapter.case_target("servo_supply_001"),
                                           adapter.reference_value, adapter.metrics())
        self.assertEqual([c["id"] for c in golden["cases"]], [f"REF-EL-00{n}" for n in (1, 2, 4, 5, 6, 7, 8, 9)])
        self.assertEqual([(b["id"], b["gate"], b["missing_inputs"]) for b in blocked if b["gate"] == "V3"],
                         [("REF-EL-003", "V3", [])])
        # A null input is a missing input, with its path and status.
        null = copy.deepcopy(model)
        _component(null, "c_bulk")["domains"]["electrical"]["capacitance"].update(value=None, status="UNKNOWN")
        with self.assertRaises(ReferenceBlocked) as raised:
            reference_value(null, "precharge_peak_current")
        self.assertEqual(raised.exception.paths, [{"path": _path("c_bulk", "capacitance"), "status": "UNKNOWN"}])

    def test_each_metric_has_one_scenario_and_each_derivation_its_metric(self):
        from ecad_model.dataset import build

        adapter = _adapter()
        committed = json.loads((ITEM / "requirements" / "requirements.json").read_bytes())
        adapter.check_requirements(committed)
        self.assertEqual({name: metric.unit for name, metric in adapter.metrics().items()},
                         {"inrush_peak_current_a": "A", "inrush_i2t_a2s": "A^2*s", "bus_charge_time_s": "s",
                          "bus_voltage_at_bypass_v": "V", "bus_peak_voltage_v": "V", "steady_bus_voltage_v": "V",
                          "steady_input_current_a": "A", "steady_fuse_power_w": "W", "fault_input_current_a": "A"})
        self.assertEqual({metric.fidelity for metric in adapter.metrics().values()}, {"SIMPLIFIED"})

        def changed(kind: str, index: int, change: Dict[str, Any]) -> Dict[str, Any]:
            document = copy.deepcopy(committed)
            document[kind][index].update(change)
            return document

        for label, document, message in (
            ("an unknown scenario", changed("requirements", 0, {"scenario": {"name": "cold_start"}}), "cold_start"),
            ("a scenario with parameters", changed("requirements", 0, {"scenario": {"name": "startup", "load_a": 2.0}}),
             "load_a"),
            ("an unknown derivation", changed("reference_values", 0, {"derivation": "precharge_energy"}),
             "precharge_energy"),
            ("a derivation compared with another metric",
             changed("reference_values", 0, {"metric": "bus_charge_time_s", "unit": "s"}),
             "REF-EL-001: precharge_peak_current computes inrush_peak_current_a, not bus_charge_time_s"),
            ("a metric asked for in another scenario", changed("requirements", 3, {"scenario": {"name": "startup"}}),
             "REQ-EL-004: steady_bus_voltage_v is measured in the steady_state scenario, not startup"),
            ("a reference in another scenario", changed("reference_values", 8, {"scenario": {"name": "steady_state"}}),
             "REF-EL-009: fault_input_current_a is measured in the output_short scenario, not steady_state"),
        ):
            with self.subTest(label), self.assertRaisesRegex(ValueError, message):
                adapter.check_requirements(document)
        with _scratch() as directory:
            item = _copy(directory, rebuild=False)
            _edit_json(item / "requirements" / "requirements.json",
                       lambda document: document["requirements"][3].update(scenario={"name": "startup"}))
            receipt, _ = _validate(item, _stand_in(refuse=True))
            v1 = _checks(receipt)["v1.electrical.extraction-and-sanity"]
            self.assertEqual(_outcome(v1), ("FAIL", "DATASET_INPUT_INVALID"))
            self.assertIn("is measured in the steady_state scenario, not startup", v1["findings"][0])
            _edit_json(item / "requirements" / "requirements.json",
                       lambda document: document["requirements"][3].update(scenario={"name": "steady_state"}))
            _edit_json(item / "requirements" / "requirements.json",
                       lambda document: document["requirements"][0].update(unit="mA"))
            with self.assertRaisesRegex(ValueError, "REQ-EL-001: unit mA != the unit of inrush_peak_current_a, A"):
                build(item)


class TestSample(unittest.TestCase):
    def test_the_model_names_the_adapter_that_built_it(self):
        manifest = json.loads((ITEM / "dataset-item.json").read_bytes())
        [model] = [d for d in manifest["derived"] if d["artifact"]["path"] == "derived/engineering_model.json"]
        self.assertEqual(model["producer"], {"tool": "ecad_model.domains.electrical", "version": "1.0.0 (ecad_model.spice 1.0.0)"})
        self.assertEqual(manifest["versions"]["engineering_model"], "1.0.0 (ecad_model.spice 1.0.0)")
        self.assertEqual(manifest["versions"]["domain_models"], {"electrical": "ecad_model.domains.electrical 1.0.0"})
        mechanical = json.loads((MECHANICAL_ITEM / "dataset-item.json").read_bytes())
        [model] = [d for d in mechanical["derived"] if d["artifact"]["path"] == "derived/engineering_model.json"]
        self.assertEqual(model["producer"], {"tool": "ecad_model.builder", "version": "1.0.0"})
        self.assertEqual(mechanical["versions"]["engineering_model"], "1.0.0")

    def test_the_committed_sample_checks_and_rebuilds_to_the_same_bytes(self):
        from ecad_model.dataset import build, check

        self.assertEqual(check(ITEM), [])

        def files(root: Path) -> Dict[str, bytes]:
            return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}

        with _scratch() as directory:
            item = _copy(directory, rebuild=False)
            written = build(item)
            rebuilt = files(item)
            build(item)
            again = files(item)
            here = item.relative_to(REPO_ROOT).as_posix().encode()
        committed = files(ITEM)
        self.assertEqual(again, rebuilt, "a build is deterministic")
        self.assertEqual(sorted(rebuilt), sorted(committed))
        # The model and the manifest record the item's own repository path, the
        # manifest also the model's digest and the item's; nothing else differs.
        moved = {relative: data.replace(here, b"datasets/cad/servo_supply_001") for relative, data in rebuilt.items()}

        def unhashed(data: bytes) -> Dict[str, Any]:
            manifest = json.loads(data)
            manifest.pop("hash")
            for entry in manifest["derived"]:
                if entry["artifact"]["path"] == "derived/engineering_model.json":
                    entry["artifact"].pop("sha256"), entry["artifact"].pop("size_bytes")
            return manifest

        for relative in committed:
            with self.subTest(relative):
                if relative == "dataset-item.json":
                    self.assertEqual(unhashed(moved[relative]), unhashed(committed[relative]))
                else:
                    self.assertEqual(moved[relative], committed[relative])
        self.assertEqual(written, ["derived/engineering_model.json", DECK_PATH, "validation/golden/cases.json",
                                   "validation/corners/cases.json", "dataset-item.json"])
        manifest = json.loads(committed["dataset-item.json"])
        status = {d["domain"]: d for d in manifest["domains"]}
        self.assertEqual(status["electrical"]["status"], "AVAILABLE")
        self.assertTrue(status["electrical"]["reason"].startswith("the series-precharge supply-input network only"))
        self.assertIn("requirements resting on components/c_bulk/domains/electrical/ripple_current_rating (UNKNOWN)",
                      status["electrical"]["reason"])
        self.assertEqual(status["mechanical"]["status"], "NOT_APPLICABLE")
        self.assertEqual({d: s["status"] for d, s in status.items() if d not in ("electrical", "mechanical")},
                         dict.fromkeys(("digital", "pcb", "power_electronics", "control", "electromagnetic", "thermal",
                                        "full_system"), "NOT_IMPLEMENTED"))
        lineage = {d["artifact"]["path"]: d["derived_from"] for d in manifest["derived"]}
        self.assertEqual(lineage["derived/engineering_model.json"], [NETLIST, "design/annotations.json"])
        self.assertEqual(lineage[DECK_PATH], ["derived/engineering_model.json"])
        self.assertEqual((manifest["domain"], manifest["artifact_type"], manifest["versions"]["extraction"],
                          manifest["versions"]["simulation"], manifest["created_at"], manifest["collected_at"]),
                         ("electrical", "spice_netlist", "none", EMPTY_SET, "2026-09-27", "2026-09-27"))
        self.assertEqual(manifest["source"]["artifacts"], [{"path": NETLIST, "format": "spice", "sha256": NETLIST_SHA256,
                                                            "size_bytes": 1300, "media_type": "text/x-spice"}])
        self.assertEqual(manifest["inputs"]["simulation"], [])
        self.assertEqual(manifest["source"]["license"]["license_text"], {"path": "LICENSE", "sha256": LICENSE_SHA256})
        # The one entry the electrical adapter changes in the mechanical sample's manifest (§8.3).
        mechanical = {d["domain"]: d for d in json.loads((MECHANICAL_ITEM / "dataset-item.json").read_bytes())["domains"]}
        self.assertEqual(mechanical["electrical"], {
            "domain": "electrical", "status": "NOT_APPLICABLE",
            "reason": "the electrical adapter reads spice, which this sample does not have; this sample also lacks "
                      "components/actuator/domains/electrical/torque_constant (UNKNOWN), "
                      "components/actuator/domains/electrical/winding_resistance (UNKNOWN)"})

    def test_the_cited_product_sheet_and_licence_are_rehashed(self):
        from ecad_model.dataset import build, check

        def sheet_digest(document: Dict[str, Any]) -> None:
            document["components_without_cad"][0]["domains"]["electrical"]["rated_current"]["source"]["sha256"] = "0" * 64

        def licence_digest(document: Dict[str, Any]) -> None:
            document["license"]["license_text"]["sha256"] = "1" * 64

        for label, relative, change, problem in (
            ("the product sheet", "design/annotations.json", sheet_digest,
             f"cited source {SHEET} has changed since it was cited"),
            ("the licence", "source/provenance.json", licence_digest, "licence text LICENSE has changed since it was cited"),
        ):
            with self.subTest(label), _scratch() as directory:
                item = _copy(directory, rebuild=False)
                _edit_json(item / relative, change)
                build(item)
                self.assertEqual(check(item), [problem])

    def test_dataset_bytes_are_never_converted_on_checkout(self):
        listed = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files", "-co", "--exclude-standard", "-z", "--",
                                 "datasets/cad"], check=True, capture_output=True, timeout=60).stdout.decode()
        files = sorted({name for name in listed.split("\0") if name}) + ["LICENSE", SHEET]
        self.assertIn(f"datasets/cad/servo_supply_001/{NETLIST}", files)
        attributes = subprocess.run(["git", "-C", str(REPO_ROOT), "check-attr", "text", "-z", "--", *files],
                                    check=True, capture_output=True, timeout=60).stdout.decode().split("\0")
        found = dict(zip(attributes[0::3], attributes[2::3]))
        self.assertEqual(found, dict.fromkeys(files, "unset"))


class TestReceipt(unittest.TestCase):
    """One validation of the committed sample, with ngspice-47's recorded output."""

    @classmethod
    def setUpClass(cls):
        from ecad_model.dataset import regenerate_results, validate

        cls.scratch = tempfile.TemporaryDirectory()
        run = Path(cls.scratch.name) / "run"
        with _stand_in():
            cls.receipt = validate(ITEM, run)
        cls.written = (run / "results.json").read_bytes()
        cls.results = {r["check_id"]: r for r in json.loads(cls.written)["results"]}
        cls.regenerated = regenerate_results(ITEM, run)
        cls.output = run

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_the_committed_sample_validates_as_designed_with_recorded_ngspice_output(self):
        from ecad_validation.contract import validate_document

        from ecad_model.schemas import validate as validate_schema

        validate_document(REPO_ROOT, "validation-receipt.schema.json", self.receipt)
        validate_schema(json.loads(self.written), "engineering-model/v1/validation-results")
        checks = _checks(self.receipt)
        # v0.pinned-clean-source depends on the checkout, not the sample.
        for check_id, outcome in (("v0.dataset-schemas-and-hashes", ("PASS", "DATASET_SCHEMAS_VALID")),
                                  ("v0.dataset-input-immutability", ("PASS", "VALIDATION_INPUT_UNCHANGED")),
                                  ("v1.electrical.extraction-and-sanity", ("PASS", "DOMAIN_SANITY_PASSED")),
                                  ("v2.dataset-reproduction", ("PASS", "DERIVATION_REPRODUCED")),
                                  ("v2.electrical.model-invariants", ("PASS", "DOMAIN_MODEL_CONSISTENT"))):
            with self.subTest(check_id):
                self.assertEqual(_outcome(checks[check_id]), outcome, checks[check_id]["findings"])
        gates = {g["gate"]: g["verdict"] for g in self.receipt["gates"]}
        self.assertEqual([gates[gate] for gate in ("V1", "V2", "V3", "V4")], ["PASS", "PASS", "PASS", "BLOCKED"])
        self.assertEqual((self.receipt["overall_verdict"], self.receipt["eligible_for_ebuild"]), ("BLOCKED", False))
        references = {f"v3.REF-EL-00{n}": derivation for n, derivation in enumerate(CLOSED_FORMS, start=1)}
        for check_id, derivation in references.items():
            with self.subTest(check_id):
                self.assertEqual(_outcome(checks[check_id]), ("PASS", "GOLDEN_COMPARISON_PASSED"))
                self.assertEqual(checks[check_id]["metrics"], RECORDED_METRICS)
                self.assertEqual(self.results[check_id]["expected_value"], CLOSED_FORMS[derivation])
        for n, (value, limit) in enumerate(((4.71663, 10.0), (47.9147, 45.6), (4.16667, 5.0), (47.875, 47.0)), start=1):
            with self.subTest(requirement=n):
                row = self.results[f"v4.REQ-EL-00{n}"]
                self.assertEqual(_outcome(checks[f"v4.REQ-EL-00{n}"]), ("WARNING", "WITHIN_ILLUSTRATIVE_LIMIT"))
                self.assertEqual((row["measured_value"], row["expected_value"], row["simulator_version"]),
                                 (value, limit, "stand-in 0"))
        for n, limit, measured in ((5, _path("c_bulk", "voltage_rating"), 48.0),
                                   (6, _path("r_f1", "melting_i2t"), 0.0533906),
                                   (7, _path("r_f1", "breaking_capacity"), 372.465)):
            with self.subTest(blocked=n):
                check = checks[f"v4.REQ-EL-00{n}"]
                self.assertEqual(_outcome(check), ("BLOCKED", "MISSING_REQUIRED_INPUT"))
                self.assertEqual(check["findings"][0], f"UNKNOWN: {limit}")
                row = self.results[f"v4.REQ-EL-00{n}"]
                # The measured side is borrowed from the first check that ran the same deck.
                self.assertEqual((row["measured_value"], row["measured_by"], row["expected_value"], row["simulator"]),
                                 (measured, "v3.REF-EL-001", None, None))
        self.assertEqual(len(self.results), 16)
        self.assertEqual({row["model_fidelity"] for row in self.results.values()}, {"SIMPLIFIED"})
        [tool] = [t for t in self.receipt["tools"] if t["tool_id"] == "ngspice"]
        self.assertEqual(tool["version"], "stand-in 0")

    def test_results_trace_source_to_evidence_and_regenerate_identically(self):
        model = _model()
        manifest = json.loads((ITEM / "dataset-item.json").read_bytes())
        self.assertEqual({model["design"]["sources"][0]["sha256"], manifest["source"]["artifacts"][0]["sha256"]},
                         {NETLIST_SHA256})
        limits = {"v4.REQ-EL-005": _path("c_bulk", "voltage_rating"), "v4.REQ-EL-006": _path("r_f1", "melting_i2t"),
                  "v4.REQ-EL-007": _path("r_f1", "breaking_capacity")}
        checks = _checks(self.receipt)
        for check_id, row in self.results.items():
            with self.subTest(check_id):
                self.assertTrue(row["inputs"])
                for entry in row["inputs"]:
                    expected = "UNKNOWN" if entry["path"] == limits.get(check_id) else "SPECIFIED"
                    self.assertEqual(entry["status"], expected, entry["path"])
                self.assertEqual(row["cad_components"],
                                 sorted(f"{cid} ({designator})" for cid, (designator, _, _, _) in CIRCUIT.items()))
                if check_id not in limits:
                    self.assertIn(DECK_SHA256, [e["sha256"] for e in checks[check_id]["evidence"]],
                                  "the deck the case ran on is part of its evidence")
                    self.assertEqual(row["configuration"]["command"], ["ngspice", "-b", DECK_PATH])
                for evidence in checks[check_id]["evidence"]:
                    stored = self.output / "evidence" / "sha256" / evidence["sha256"]
                    self.assertEqual(hashlib.sha256(stored.read_bytes()).hexdigest(), evidence["sha256"])
        self.assertEqual(self.regenerated, self.written)


class TestVerdicts(unittest.TestCase):
    def test_a_tightened_limit_fails_and_only_a_real_requirement_can_pass(self):
        with _scratch() as directory:
            item = _copy(directory, {"requirements/requirements.json": ('"value": 10.0', '"value": 4.0')})
            tightened = _checks(_validate(item)[0])["v4.REQ-EL-001"]
        self.assertEqual(_outcome(tightened), ("FAIL", "CORNER_LIMITS_FAILED"))
        self.assertEqual(tightened["findings"], ["inrush_peak_current_a: actual 4.71663 is above maximum 4.0"])
        with _scratch() as directory:
            item = _copy(directory, rebuild=False)
            _edit_json(item / "requirements" / "requirements.json",
                       lambda document: document["requirements"][0].update(illustrative=False))
            _rebuild(item)
            real = _checks(_validate(item)[0])["v4.REQ-EL-001"]
        self.assertEqual(_outcome(real), ("PASS", "CORNER_LIMITS_PASSED"))

    def test_the_limit_boundaries_are_exact(self):
        """The recorded 4.71663 and 47.9147 against limits one float away, with the
        tolerance folded into the bound for <= and >= alike."""
        below, above = math.nextafter(4.71663, 0.0), math.nextafter(47.9147, math.inf)
        with _scratch() as directory:
            item = _copy(directory, rebuild=False)
            _add_requirements(
                item,
                _requirement("REQ-EL-101", "r_pre", "inrush_peak_current_a", "startup", "<=", 4.71663, "A"),
                _requirement("REQ-EL-102", "r_pre", "inrush_peak_current_a", "startup", "<=", below, "A"),
                _requirement("REQ-EL-103", "r_pre", "inrush_peak_current_a", "startup", "<=", below, "A", tolerance=1e-9),
                _requirement("REQ-EL-104", "s_byp", "bus_voltage_at_bypass_v", "startup", ">=", 47.9147, "V"),
                _requirement("REQ-EL-105", "s_byp", "bus_voltage_at_bypass_v", "startup", ">=", above, "V"),
                _requirement("REQ-EL-106", "s_byp", "bus_voltage_at_bypass_v", "startup", ">=", above, "V", tolerance=1e-9))
            checks = _checks(_validate(item)[0])
        self.assertEqual({n: checks[f"v4.REQ-EL-{n}"]["verdict"] for n in range(101, 107)},
                         {101: "WARNING", 102: "FAIL", 103: "WARNING", 104: "WARNING", 105: "FAIL", 106: "WARNING"})

    def test_each_null_status_of_a_rating_blocks_with_its_status_and_path(self):
        from ecad_validation.contract import validate_document

        ratings = {
            "UNKNOWN": None,
            "UNSPECIFIED": {"value": None, "unit": "V", "status": "UNSPECIFIED",
                            "source": {"kind": "design_annotation", "ref": NETLIST_REF, "sha256": NETLIST_SHA256},
                            "note": "test fixture: the netlist, cited by hash, is silent on C1's voltage rating"},
            "NOT_AVAILABLE": {"value": None, "unit": "V", "status": "NOT_AVAILABLE", "source": FIXTURE_SOURCE,
                              "note": "test fixture: a rating that exists but cannot be used"},
        }
        for status, rating in ratings.items():
            with self.subTest(status), _scratch() as directory:
                item = _copy(directory, rebuild=rating is None)
                if rating is not None:
                    _edit_json(item / "design" / "annotations.json",
                               lambda document: _annotated(document, "C_BULK").update(voltage_rating=rating))
                    _rebuild(item)
                receipt, results = _validate(item)
                validate_document(REPO_ROOT, "validation-receipt.schema.json", receipt)
                check = _checks(receipt)["v4.REQ-EL-005"]
                self.assertEqual(_outcome(check), ("BLOCKED", "MISSING_REQUIRED_INPUT"))
                self.assertEqual(check["findings"][0], f"{status}: {_path('c_bulk', 'voltage_rating')}")
                assert results is not None
                [row] = [r for r in results["results"] if r["check_id"] == "v4.REQ-EL-005"]
                self.assertIn({"path": _path("c_bulk", "voltage_rating"), "status": status}, row["inputs"])

    def test_a_rating_passes_only_when_specified_and_real_and_never_when_ai_assumed(self):
        real = _requirement("REQ-EL-105", "c_bulk", "bus_peak_voltage_v", "startup", "<=",
                            {"quantity": _path("c_bulk", "voltage_rating")}, "V", illustrative=False)
        specified = {"value": 63.0, "unit": "V", "status": "SPECIFIED", "source": FIXTURE_SOURCE,
                     "note": "test fixture: a rating typed for this test, not a selected capacitor's"}
        for label, rating, outcomes in (
            ("specified", specified, {"v4.REQ-EL-005": ("WARNING", "WITHIN_ILLUSTRATIVE_LIMIT"),
                                      "v4.REQ-EL-105": ("PASS", "CORNER_LIMITS_PASSED")}),
            ("assumed, met", {"value": 63.0, "unit": "V", "status": "AI_ASSUMPTION", "source": {"kind": "ai", "ref": "fixture"}},
             {"v4.REQ-EL-105": ("INCONCLUSIVE", "INPUT_IS_AI_ASSUMPTION")}),
            ("assumed, violated", {"value": 40.0, "unit": "V", "status": "AI_ASSUMPTION", "source": {"kind": "ai", "ref": "fixture"}},
             {"v4.REQ-EL-105": ("INCONCLUSIVE", "INPUT_IS_AI_ASSUMPTION")}),
        ):
            with self.subTest(label), _scratch() as directory:
                item = _copy(directory, rebuild=False)
                _edit_json(item / "design" / "annotations.json",
                           lambda document: _annotated(document, "C_BULK").update(voltage_rating=rating))
                _add_requirements(item, real)
                checks = _checks(_validate(item)[0])
                for check_id, outcome in outcomes.items():
                    self.assertEqual(_outcome(checks[check_id]), outcome, checks[check_id]["findings"])

    def test_without_ngspice_every_case_is_blocked_and_the_receipt_holds(self):
        from ecad_validation.contract import validate_document

        receipt, results = _validate(ITEM, _no_ngspice())
        validate_document(REPO_ROOT, "validation-receipt.schema.json", receipt)
        checks = _checks(receipt)
        compiled = [f"v3.REF-EL-00{n}" for n in range(1, 10)] + [f"v4.REQ-EL-00{n}" for n in (1, 2, 3, 4)]
        for check_id in compiled:
            with self.subTest(check_id):
                self.assertEqual(_outcome(checks[check_id]), ("BLOCKED", "TOOL_NOT_INSTALLED"))
                self.assertEqual(checks[check_id]["tool_id"], "ecad-validator")
        self.assertEqual({_outcome(checks[f"v4.REQ-EL-00{n}"]) for n in (5, 6, 7)}, {("BLOCKED", "MISSING_REQUIRED_INPUT")})
        assert results is not None
        self.assertEqual(len(results["results"]), 16)
        self.assertEqual({r["simulator_version"] for r in results["results"]}, {None})
        self.assertNotIn("ngspice", {t["tool_id"] for t in receipt["tools"]})

    def test_a_refused_netlist_gives_a_receipt_and_never_reaches_ngspice(self):
        from ecad_validation.contract import validate_document

        with _scratch() as directory:
            item = _copy(directory, {NETLIST: (".end\n", ".control\nshell touch refused-netlist-ran\n.endc\n.end\n")},
                         rebuild=False)
            receipt, _ = _validate(item, _stand_in(refuse=True))
            self.assertEqual(list(Path(directory).rglob("refused-netlist-ran")), [])
        validate_document(REPO_ROOT, "validation-receipt.schema.json", receipt)
        checks = _checks(receipt)
        v1 = checks["v1.electrical.extraction-and-sanity"]
        self.assertEqual(_outcome(v1), ("FAIL", "SOURCE_REJECTED"))
        # .end is line 25 of the netlist, so the inserted .control is too.
        self.assertIn(f"{NETLIST}:25: .control: runs commands, including shell", v1["findings"][0])
        for check_id in ("v2.dataset-reproduction", "v2.electrical.model-invariants",
                         *(f"v3.REF-EL-00{n}" for n in range(1, 10)), *(f"v4.REQ-EL-00{n}" for n in range(1, 8))):
            with self.subTest(check_id):
                self.assertEqual(_outcome(checks[check_id]), ("BLOCKED", "DERIVATION_NOT_AVAILABLE"))

    def test_a_name_ngspice_reads_as_its_own_is_refused_before_ngspice_runs(self):
        """CS-1: a rail node named time made a .meas read the time axis, so a real
        limit on the bus peak passed at 0.1; a model named TEMPER crashed ngspice."""
        for label, old, new, refused in (
            ("the rail named time", b" n_bus", b" time", f"{NETLIST}:15: R_PRE: 'time' is not a node name"),
            ("the rail named all", b" n_bus", b" all", f"{NETLIST}:15: R_PRE: 'all' is not a node name"),
            ("the bypass model named TEMPER", b"SW_BYP", b"TEMPER", f"{NETLIST}:16: S_BYP: 'TEMPER' is not a model name"),
        ):
            with self.subTest(label), _scratch() as directory:
                item = _copy(directory, rebuild=False)
                netlist = item / NETLIST
                netlist.write_bytes(netlist.read_bytes().replace(old, new))
                receipt, _ = _validate(item, _stand_in(refuse=True))
                checks = _checks(receipt)
                v1 = checks["v1.electrical.extraction-and-sanity"]
                self.assertEqual(_outcome(v1), ("FAIL", "SOURCE_REJECTED"))
                self.assertIn(refused, v1["findings"][0])
                self.assertEqual({_outcome(checks[f"v4.REQ-EL-00{n}"]) for n in range(1, 8)},
                                 {("BLOCKED", "DERIVATION_NOT_AVAILABLE")})

    def test_a_deck_edited_without_a_rebuild_is_divergent_and_not_counted(self):
        with _scratch() as directory:
            item = _copy(directory, {DECK_PATH: ("R_PRE n_f n_bus 10.0", "R_PRE n_f n_bus 1.0")}, rebuild=False)
            receipt, _ = _validate(item)
        checks = _checks(receipt)
        reproduction = checks["v2.dataset-reproduction"]
        self.assertEqual(_outcome(reproduction), ("FAIL", "DERIVATION_DIVERGED"))
        self.assertIn(f"{DECK_PATH}: bytes differ from a fresh derivation", reproduction["findings"])
        for check_id in (*(f"v3.REF-EL-00{n}" for n in range(1, 10)), *(f"v4.REQ-EL-00{n}" for n in (1, 2, 3, 4))):
            with self.subTest(check_id):
                self.assertEqual(_outcome(checks[check_id]), ("BLOCKED", "COMMITTED_CASE_STALE"))
                self.assertIn(f"its input {DECK_PATH} no longer reproduces", checks[check_id]["findings"][0])
        self.assertEqual({_outcome(checks[f"v4.REQ-EL-00{n}"]) for n in (5, 6, 7)}, {("BLOCKED", "MISSING_REQUIRED_INPUT")})


class TestSimulatorRequirement(unittest.TestCase):
    def test_the_ngspice_requirement_turns_a_skip_into_a_failure(self):
        from ecad_validation.adapters.base import Capability

        from tests.unit.test_electrical_spice import require_ngspice

        for label, capability in (
            ("not installed", Capability(adapter="ngspice", available=False, reason="TOOL_NOT_INSTALLED")),
            ("installed, version unknown", Capability(adapter="ngspice", available=True, executable="/x/ngspice")),
        ):
            with self.subTest(label), mock.patch("ecad_validation.adapters.ngspice.probe_executable",
                                                 return_value=capability):
                with mock.patch.dict(os.environ, {"ECAD_REQUIRE_SPICE_TOOLS": ""}):
                    with self.assertRaises(unittest.SkipTest):
                        require_ngspice()
                with mock.patch.dict(os.environ, {"ECAD_REQUIRE_SPICE_TOOLS": "1"}):
                    with self.assertRaisesRegex(AssertionError, "ECAD_REQUIRE_SPICE_TOOLS=1 but"):
                        require_ngspice()
        installed = Capability(adapter="ngspice", available=True, executable="/x/ngspice", version="47")
        with mock.patch("ecad_validation.adapters.ngspice.probe_executable", return_value=installed), \
                mock.patch.dict(os.environ, {"ECAD_REQUIRE_SPICE_TOOLS": "1"}):
            self.assertEqual(require_ngspice(), installed)


if __name__ == "__main__":
    unittest.main()
