"""The digital domain on datasets/cad/uart_loopback_001, with no simulator.

The sample is the 8N1 UART pair of rtl/ -- source/uart_tx.v and
source/uart_rx.v are byte copies of rtl/uart_tx.v and rtl/uart_rx.v -- wired
transmitter to receiver by a declarative top, source/tb_uart_loopback.v.
These tests need neither a CAD kernel nor Icarus Verilog. Where a case must
"run", a stand-in for the Icarus adapter answers the simulation file with
one of RECORDED_STDOUT, read through the real adapter's own parser: the
output Icarus Verilog 13.0 printed through the real adapter on macOS arm64
on 2026-09-29 (identical over two runs, empty stderr) for the simulation
file as the review's CS-1 change writes it, whose ECAD_METRIC lines are
identical on Icarus 11.0 (apt 11.0-1.1, ubuntu:22.04 arm64, 2026-09-29).
tests/unit/test_digital_icarus.py runs the real Icarus.

Expected values are typed by hand from the source texts and the closed forms
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
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

ITEM = REPO_ROOT / "datasets" / "cad" / "uart_loopback_001"
SAMPLE = "datasets/cad/uart_loopback_001"
TB, TX, RX = "source/tb_uart_loopback.v", "source/uart_tx.v", "source/uart_rx.v"
SIM = "derived/digital/uart_loopback_001.v"
TB_REF, TX_REF, RX_REF = f"{SAMPLE}/{TB}", f"{SAMPLE}/{TX}", f"{SAMPLE}/{RX}"
ANNOTATIONS_REF = f"{SAMPLE}/design/annotations.json"
TB_SHA256 = "2962c844a2191ab756ad190e184365ab1893650ae67fee5a078b610ff7719fed"
TX_SHA256 = "5be9e1bdd20b37a3b79cb40c98fbfe241e8d6faca5ecb443b0e93378d7b4f01a"
RX_SHA256 = "c1bebcc6e894e86abd4b39af5501031b8c817f4395048ef65059eebfb710ab81"
SIM_SHA256 = "597eebf2679d10a236d344a6df5ff5d0fb4573ca0a863cf1b94bfdde3a94fd83"
LICENSE_SHA256 = "2779b5d4987171210e3c18f461e4ee832426c3c52ca3e53a7dce23af057c4c0a"
EMPTY_SET = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
DEVICE_LIMIT = "components/target_device/domains/digital/min_clock_period"
NOT_A_PART = "not a rating or measurement of any part"
DESCRIPTION = ("the UART 8N1 loopback only (a transmitter and a receiver with the port and parameter interfaces of "
               "rtl/uart_tx.v and rtl/uart_rx.v, wired transmitter to receiver by a declarative top): reset, "
               "frame-timing and byte-recovery metrics from one Icarus Verilog run of a harness written from the "
               "model, compared with closed-form references")
METRICS = ("clock_period_s", "tx_idle_after_reset", "tx_bit_cycles", "tx_bit_rate_bd", "tx_frame_cycles",
           "rx_bytes_received", "rx_bit_errors", "rx_framing_errors", "outputs_unknown_after_reset")


def _stdout(values: Sequence[str], finished_at: str) -> str:
    return "".join(f"ECAD_METRIC {name} {value}\n" for name, value in zip(METRICS, values)) + (
        f"{SIM}:353: $finish called at {finished_at} (1ps)\n")


# Icarus Verilog 13.0, macOS arm64, 2026-09-29, through the real adapter; identical
# ECAD_METRIC lines on 11.0, ubuntu:22.04 arm64. The committed file, BAUD_RATE =
# 230_400, and CLK_HALF_PERIOD_NS = 25 with CLK_FREQ = 20_000_000, whose one
# missing byte counts 8 of its 15 bit errors.
RECORDED_STDOUT = {
    "committed": _stdout(("2e-08", "1", "434", "115207.3732718894", "4340", "2", "0", "0", "0"), "416720000"),
    "baud230400": _stdout(("2e-08", "1", "217", "230414.74654377881", "2170", "2", "0", "0", "0"), "208400000"),
    "clk20m": _stdout(("4.9999999999999998e-08", "1", "173", "115606.93641618497", "1730", "1", "15", "1", "0"),
                      "415400000"),
}
# Typed from the committed lines above.
RECORDED_METRICS = {"clock_period_s": 2e-08, "tx_idle_after_reset": 1.0, "tx_bit_cycles": 434.0,
                    "tx_bit_rate_bd": 115207.3732718894, "tx_frame_cycles": 4340.0, "rx_bytes_received": 2.0,
                    "rx_bit_errors": 0.0, "rx_framing_errors": 0.0, "outputs_unknown_after_reset": 0.0}
TB_SOURCE = {"kind": "design_annotation", "ref": TB_REF, "sha256": TB_SHA256}
RX_SOURCE = {"kind": "design_annotation", "ref": RX_REF, "sha256": RX_SHA256}
# Every value the sources state (design §1.6): the line of the file that states it, and the model's quantity.
STATED = {
    ("tb_uart_loopback", "clock_half_period"): (TB, 26, "    localparam CLK_HALF_PERIOD_NS = 10;", 1e-08, "s", TB_SOURCE,
                                                f"CLK_HALF_PERIOD_NS = 10 as {TB}:26 states it, in its 1 ns time unit; "
                                                f"{NOT_A_PART}"),
    ("tb_uart_loopback", "reset_cycles"): (TB, 29, "    localparam RESET_CYCLES       = 4;", 4, "cycles", TB_SOURCE,
                                           f"RESET_CYCLES = 4 as {TB}:29 states it; {NOT_A_PART}"),
    ("tb_uart_loopback", "tx_bytes"): (TB, 30, "    localparam [7:0] TX_BYTE_0    = 8'h35;", [53, 202], "1", TB_SOURCE,
                                       f"TX_BYTE_0 = 53, TX_BYTE_1 = 202 as {TB}:30-31 state them; {NOT_A_PART}"),
    ("u_tx", "clk_freq"): (TB, 27, "    localparam CLK_FREQ           = 50_000_000;", 50000000, "Hz", TB_SOURCE,
                           f"u_tx CLK_FREQ = CLK_FREQ = 50000000 as {TB}:27 and :43 state it; {NOT_A_PART}"),
    ("u_tx", "baud_rate"): (TB, 28, "    localparam BAUD_RATE          = 115_200;", 115200, "Bd", TB_SOURCE,
                            f"u_tx BAUD_RATE = BAUD_RATE = 115200 as {TB}:28 and :43 state it; {NOT_A_PART}"),
    ("u_rx", "clk_freq"): (TB, 27, "    localparam CLK_FREQ           = 50_000_000;", 50000000, "Hz", TB_SOURCE,
                           f"u_rx CLK_FREQ = CLK_FREQ = 50000000 as {TB}:27 and :48 state it; {NOT_A_PART}"),
    ("u_rx", "baud_rate"): (TB, 28, "    localparam BAUD_RATE          = 115_200;", 115200, "Bd", TB_SOURCE,
                            f"u_rx BAUD_RATE = BAUD_RATE = 115200 as {TB}:28 and :48 state it; {NOT_A_PART}"),
    ("u_rx", "oversample"): (RX, 23, "    localparam OVERSAMPLE    = 16;", 16, "1", RX_SOURCE,
                             f"OVERSAMPLE = 16 as {RX}:23 states it; {NOT_A_PART}"),
}
SIGNALS = {"clk": {"kind": "reg", "width": 1}, "line": {"kind": "wire", "width": 1},
           "rst_n": {"kind": "reg", "width": 1}, "rx_data": {"kind": "wire", "width": 8},
           "rx_error": {"kind": "wire", "width": 1}, "rx_valid": {"kind": "wire", "width": 1},
           "tx_data": {"kind": "reg", "width": 8}, "tx_ready": {"kind": "wire", "width": 1},
           "tx_valid": {"kind": "reg", "width": 1}}
TX_PORTS = {"clk": {"direction": "input", "width": 1, "signal": "clk"},
            "rst_n": {"direction": "input", "width": 1, "signal": "rst_n"},
            "tx_data": {"direction": "input", "width": 8, "signal": "tx_data"},
            "tx_valid": {"direction": "input", "width": 1, "signal": "tx_valid"},
            "tx_ready": {"direction": "output", "width": 1, "signal": "tx_ready"},
            "tx": {"direction": "output", "width": 1, "signal": "line"}}
RX_PORTS = {"clk": {"direction": "input", "width": 1, "signal": "clk"},
            "rst_n": {"direction": "input", "width": 1, "signal": "rst_n"},
            "rx": {"direction": "input", "width": 1, "signal": "line"},
            "rx_data": {"direction": "output", "width": 8, "signal": "rx_data"},
            "rx_valid": {"direction": "output", "width": 1, "signal": "rx_valid"},
            "rx_error": {"direction": "output", "width": 1, "signal": "rx_error"}}
PARAMETERS = {"BAUD_RATE": "baud_rate", "CLK_FREQ": "clk_freq"}
FIXTURE_SOURCE = {"kind": "design_annotation", "ref": "tests/unit/test_digital_domain.py"}


def _path(component: str, facet: str) -> str:
    return f"components/{component}/domains/digital/{facet}"


# What each closed form reads (design §5.2), typed from its formula.
LINK = [_path("u_tx", "clk_freq"), _path("u_tx", "baud_rate"), _path("u_rx", "clk_freq"), _path("u_rx", "baud_rate"),
        _path("u_rx", "oversample")]
REFERENCE_INPUTS = {
    "clock_period": [_path("tb_uart_loopback", "clock_half_period")],
    "idle_high_after_reset": [_path("tb_uart_loopback", "reset_cycles")],
    "bit_period_cycles": [_path("u_tx", "clk_freq"), _path("u_tx", "baud_rate"), _path("tb_uart_loopback", "tx_bytes")],
    "bit_rate": [_path("u_tx", "clk_freq"), _path("u_tx", "baud_rate"), _path("tb_uart_loopback", "tx_bytes"),
                 _path("tb_uart_loopback", "clock_half_period")],
    "frame_cycles": [_path("u_tx", "clk_freq"), _path("u_tx", "baud_rate")],
    "bytes_sent": [_path("tb_uart_loopback", "tx_bytes"), *LINK],
    "lossless_loopback": LINK,
    "no_framing_errors": LINK,
}
# Every value the sources state: what each simulated metric depends on (the byte count rests on the bytes).
STATED_PATHS = sorted(_path(component, facet) for component, facet in STATED)


def _closed_forms(h: float, bytes_sent: Sequence[int], tx: Tuple[int, int], rx: Tuple[int, int, int]) -> Dict[str, float]:
    """The eight forms of the design (§5.2), written out independently of the adapter.

    tx is (CLK_FREQ, BAUD_RATE), rx (CLK_FREQ, BAUD_RATE, OVERSAMPLE); a form
    that does not apply is left out.
    """
    d_t = tx[0] // tx[1]
    d_r = rx[0] // (rx[1] * rx[2])
    middle = rx[2] // 2
    w = d_r >= 1 and all(b * d_t <= (middle + rx[2] * b) * d_r and (middle + rx[2] * b) * d_r + d_r - 1 < (b + 1) * d_t
                         for b in range(10))
    forms = {"clock_period": 2 * h, "idle_high_after_reset": 1.0, "frame_cycles": 10.0 * d_t}
    if bytes_sent[0] % 2:
        forms.update(bit_period_cycles=float(d_t), bit_rate=1 / (2 * h * d_t))
    if w:
        forms.update(bytes_sent=float(len(bytes_sent)), lossless_loopback=0.0, no_framing_errors=0.0)
    return forms


def _model() -> Dict[str, Any]:
    return json.loads((ITEM / "derived" / "engineering_model.json").read_bytes())


def _component(model: Dict[str, Any], component_id: str) -> Dict[str, Any]:
    return next(c for c in model["components"] if c["component_id"] == component_id)


def _set(model: Dict[str, Any], *changes: Tuple[str, str, Any]) -> Dict[str, Any]:
    """A copy of the model with digital values changed, each (component, facet, value) (a fixture)."""
    changed = copy.deepcopy(model)
    for component_id, facet, value in changes:
        _component(changed, component_id)["domains"]["digital"][facet]["value"] = value
    return changed


def _adapter() -> Any:
    from ecad_model.domains.digital import DigitalAdapter

    return DigitalAdapter()


def _scratch():
    return tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-")


Edits = Dict[str, Union[Tuple[str, str], List[Tuple[str, str]]]]


def _copy(directory: str, edits: Optional[Edits] = None, rebuild: bool = True, uncopied: Sequence[str] = ()) -> Path:
    """A fixture copy of the sample with text replacements in the named files, each old text once.

    uncopied names the RTL copies whose copied_from is dropped: a modified
    file is no copy of its origin.
    """
    from ecad_model.dataset import build

    item = Path(directory) / "uart_loopback_001"
    shutil.copytree(ITEM, item)
    for relative, changes in (edits or {}).items():
        path = item / relative
        data = path.read_bytes()
        for old, new in changes if isinstance(changes, list) else [changes]:
            if data.count(old.encode()) != 1:
                raise AssertionError(f"{relative}: expected {old!r} exactly once")
            data = data.replace(old.encode(), new.encode())
        path.write_bytes(data)
    if uncopied:
        _edit_json(item / "source" / "provenance.json", lambda document: [
            artifact.pop("copied_from") for artifact in document["artifacts"] if artifact["path"] in uncopied])
    if rebuild:
        build(item)
    return item


def _edit_json(path: Path, change: Callable[[Any], Any]) -> None:
    document = json.loads(path.read_bytes())
    change(document)
    path.write_bytes((json.dumps(document, indent=2) + "\n").encode())


def _stand_in(stdout: str = RECORDED_STDOUT["committed"], refuse: bool = False, runs: Optional[List[str]] = None):
    """The Icarus adapter replaced by one that answers every case with a
    recorded stdout, read through the real adapter's parser against what the
    inputs declare; or, with refuse, one that fails the test if any case
    reaches it. runs records each case it answered. Test-only."""
    from ecad_validation.adapters.base import Adapter, AdapterResult, Capability
    from ecad_validation.adapters.hdl import declared_metrics, parse_metrics
    from ecad_validation.models import ExecutionStatus, Verdict

    class StandInIcarus(Adapter):
        name = "iverilog"

        def capability(self):
            return Capability(adapter="iverilog", available=True, version="stand-in 0")

        def run(self, request):
            if refuse:
                raise AssertionError(f"{request.input_files} reached Icarus")
            if runs is not None:
                runs.append(request.case_id)
            declared, _ = declared_metrics([path.read_bytes().decode("utf-8") for path in request.input_files])
            metrics, _ = parse_metrics(stdout, declared)
            return AdapterResult(adapter="iverilog", execution_status=ExecutionStatus.COMPLETED, verdict=Verdict.PASS,
                                 reason_code="RTL_TESTBENCH_PASSED", summary="stand-in: Icarus 13.0's recorded output",
                                 command=["vvp", "simulation.vvp"], tool_version="stand-in 0", stdout=stdout,
                                 metrics=dict(metrics))

    return mock.patch.dict("ecad_validation.cases.ADAPTERS", {"iverilog": StandInIcarus})


def _no_icarus():
    """The real Icarus adapter, reporting Icarus not installed wherever the test runs."""
    from ecad_validation.adapters.base import Capability

    return mock.patch("ecad_validation.adapters.hdl.probe_iverilog",
                      return_value=Capability(adapter="iverilog", available=False, reason="TOOL_NOT_INSTALLED"))


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


def _outcomes(checks: Dict[str, Dict[str, Any]], prefix: str) -> Dict[str, Tuple[str, str]]:
    return {check_id: _outcome(check) for check_id, check in checks.items() if check_id.startswith(prefix)}


def _requirement(requirement_id: str, component: str, metric: str, operator: str, limit: Any, unit: str,
                 illustrative: bool = True, **extra: Any) -> Dict[str, Any]:
    return {"requirement_id": requirement_id, "title": f"test fixture {requirement_id}", "domain": "digital",
            "component": component, "metric": metric, "scenario": {"name": "loopback"}, "operator": operator,
            "limit": limit if isinstance(limit, dict) else {"value": limit}, "unit": unit,
            "illustrative": illustrative,
            "source": {"kind": "requirement", "ref": "tests/unit/test_digital_domain.py: a fixture, not a requirement"},
            **extra}


def _rebuild(item: Path) -> None:
    from ecad_model.dataset import build

    build(item)


def _add_requirements(item: Path, *requirements: Dict[str, Any]) -> None:
    _edit_json(item / "requirements" / "requirements.json",
               lambda document: document["requirements"].extend(requirements))
    _rebuild(item)


def _device_limit(document: Dict[str, Any]) -> Dict[str, Any]:
    return document["components_without_cad"][0]["domains"]["digital"]


# The committed verdicts (design §6.2): every reference passes, six illustrative requirements warn.
V3_PASSED = {f"v3.REF-DIG-00{n}": ("PASS", "GOLDEN_COMPARISON_PASSED") for n in range(1, 9)}
V4_WARNED = {f"v4.REQ-DIG-00{n}": ("WARNING", "WITHIN_ILLUSTRATIVE_LIMIT") for n in range(1, 7)}
V4_BLOCKED = {"v4.REQ-DIG-007": ("BLOCKED", "MISSING_REQUIRED_INPUT")}


class TestModel(unittest.TestCase):
    def test_every_testbench_value_is_specified_by_its_file_and_names_no_part(self):
        model = _model()
        for relative, digest in ((TB, TB_SHA256), (TX, TX_SHA256), (RX, RX_SHA256)):
            self.assertEqual(hashlib.sha256((ITEM / relative).read_bytes()).hexdigest(), digest)
        for (component, facet), (relative, line, text, value, unit, origin, note) in STATED.items():
            with self.subTest(component=component, facet=facet):
                self.assertEqual((ITEM / relative).read_bytes().decode().split("\n")[line - 1], text)
                self.assertEqual(_component(model, component)["domains"]["digital"][facet],
                                 {"value": value, "unit": unit, "status": "SPECIFIED", "source": origin, "note": note})
        self.assertEqual(_component(model, "tb_uart_loopback")["domains"]["digital"]["tx_bytes"]["value"], [53, 202])
        lines = (ITEM / TB).read_bytes().decode().split("\n")
        # The overrides that pass CLK_FREQ and BAUD_RATE to each instance, and the second byte.
        self.assertEqual([lines[42], lines[47], lines[30]],
                         ["    uart_tx #(.CLK_FREQ(CLK_FREQ), .BAUD_RATE(BAUD_RATE)) u_tx (",
                          "    uart_rx #(.CLK_FREQ(CLK_FREQ), .BAUD_RATE(BAUD_RATE)) u_rx (",
                          "    localparam [7:0] TX_BYTE_1    = 8'hCA;"])

    def test_the_only_null_value_is_the_unselected_device_s_clock_limit(self):
        model = _model()
        note = ("no target device is selected and the design has not been synthesised, so the shortest clock period "
                "it would meet is unknown")
        self.assertEqual(model["unknowns"], [{"path": DEVICE_LIMIT, "status": "UNKNOWN", "needed_by": ["digital"],
                                              "note": note}])
        statuses = {}
        for component in model["components"]:
            for facet, value in component["domains"]["digital"].items():
                statuses[_path(component["component_id"], facet)] = value["status"]
        self.assertEqual(set(statuses.values()), {"SPECIFIED", "DERIVED", "UNKNOWN"})
        self.assertEqual(sorted(path for path, status in statuses.items() if status == "SPECIFIED"), STATED_PATHS)
        self.assertEqual(_component(model, "tb_uart_loopback")["domains"]["digital"]["byte_count"], {
            "value": 2, "unit": "1", "status": "DERIVED",
            "source": {"kind": "computation",
                       "ref": "ecad_model.domains.digital 1.0.0: the number of TX_BYTE_i localparams"},
            "derived_from": [_path("tb_uart_loopback", "tx_bytes")]})
        self.assertEqual(_component(model, "target_device")["domains"]["digital"]["min_clock_period"], {
            "value": None, "unit": "s", "status": "UNKNOWN",
            "source": {"kind": "design_annotation", "ref": ANNOTATIONS_REF}, "note": note})

    def test_the_model_holds_the_hierarchy_ports_and_verbatim_rtl(self):
        model = _model()
        self.assertEqual(model["model_version"], "1.2.0")
        self.assertEqual(model["design"], {"design_id": "uart_loopback_001", "name": "tb_uart_loopback",
                                           "revision": "1.0", "sources": [
                                               {"path": TB_REF, "format": "verilog", "sha256": TB_SHA256},
                                               {"path": TX_REF, "format": "verilog", "sha256": TX_SHA256},
                                               {"path": RX_REF, "format": "verilog", "sha256": RX_SHA256}]})
        self.assertEqual([(c["component_id"], c["name"], c["kind"]) for c in model["components"]], [
            ("tb_uart_loopback", "tb_uart_loopback (declarative top)", "other"),
            ("u_tx", "u_tx (uart_tx, source/uart_tx.v)", "other"),
            ("u_rx", "u_rx (uart_rx, source/uart_rx.v)", "other"),
            ("target_device", "the FPGA or ASIC this RTL would be implemented on (none is selected)", "other")])
        for component in model["components"]:
            with self.subTest(component["component_id"]):
                self.assertEqual({key: component[key] for key in ("cad_ref", "material", "geometry", "physical",
                                                                  "placement")}, dict.fromkeys(
                    ("cad_ref", "material", "geometry", "physical", "placement")))
        self.assertEqual(_component(model, "tb_uart_loopback")["hdl"],
                         {"module": "tb_uart_loopback", "source": TB_REF, "ports": {}, "signals": SIGNALS})
        for component_id, module, relative, digest, ports in (("u_tx", "uart_tx", TX, TX_SHA256, TX_PORTS),
                                                              ("u_rx", "uart_rx", RX, RX_SHA256, RX_PORTS)):
            with self.subTest(component_id):
                hdl = dict(_component(model, component_id)["hdl"])
                text = hdl.pop("text")
                self.assertEqual(hdl, {"module": module, "instance": f"tb_uart_loopback.{component_id}",
                                       "source": f"{SAMPLE}/{relative}", "parameters": PARAMETERS, "ports": ports})
                self.assertEqual(hashlib.sha256(text.encode("utf-8")).hexdigest(), digest)
                self.assertEqual(text.encode("utf-8"), (ITEM / relative).read_bytes())
        self.assertNotIn("hdl", _component(model, "target_device"))
        top = {"kind": "design_annotation", "ref": TB_REF, "sha256": TB_SHA256}
        annotations = {"kind": "design_annotation", "ref": ANNOTATIONS_REF,
                       "sha256": hashlib.sha256((ITEM / "design" / "annotations.json").read_bytes()).hexdigest()}
        self.assertEqual(model["relationships"], [
            {"relation": "contains", "from": "uart_loopback_001", "to": "tb_uart_loopback", "source": top},
            {"relation": "contains", "from": "tb_uart_loopback", "to": "u_tx", "source": top},
            {"relation": "contains", "from": "tb_uart_loopback", "to": "u_rx", "source": top},
            {"relation": "constrained_by", "from": "tb_uart_loopback", "to": "target_device", "source": annotations}])
        self.assertEqual((model["joints"], "gravity" in model["design"]), ([], False))

    def test_annotations_add_components_but_never_geometry_or_netlist_elements(self):
        from ecad_model.dataset import build

        def without_device(document: Dict[str, Any]) -> None:
            document.update(annotations_version="1.1.0", components_without_cad=[], relationships=[],
                            circuit_elements={"R1": {"name": "a resistor", "kind": "resistor"}})

        for label, change, expected in (
            ("materials", lambda d: d["materials"].update(steel={"name": "steel", "density": {
                "value": 7850.0, "unit": "kg/m^3", "status": "SPECIFIED", "source": FIXTURE_SOURCE}}),
             "the annotations give materials, which describe CAD geometry HDL does not have"),
            ("circuit elements", without_device,
             "the annotations give circuit_elements, which describe netlist elements HDL does not have"),
            ("a component declared twice", lambda d: d["components_without_cad"][0].update(component_id="u_tx"),
             "component 'u_tx' is declared twice"),
            ("a relationship to nothing", lambda d: d["relationships"][0].update(to="board"),
             "relationship names unknown component 'board'"),
        ):
            with self.subTest(label), _scratch() as directory:
                item = _copy(directory, rebuild=False)
                _edit_json(item / "design" / "annotations.json", change)
                with self.assertRaisesRegex(ValueError, expected):
                    build(item)

    def test_an_hdl_member_needs_format_1_2_0(self):
        from ecad_model.schemas import validate as validate_schema

        model = _model()
        validate_schema(model, "engineering-model/v1/engineering-model")

        def changed(change: Callable[[Dict[str, Any]], Any]) -> Dict[str, Any]:
            document = copy.deepcopy(model)
            change(document)
            return document

        def hdl(component_id: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
            return lambda document: _component(document, component_id)["hdl"]

        invalid = {
            "an hdl member in format 1.0.0": changed(lambda d: d.update(model_version="1.0.0")),
            "an hdl member in format 1.1.0": changed(lambda d: d.update(model_version="1.1.0")),
            "an instance without its text": changed(lambda d: hdl("u_tx")(d).pop("text")),
            "an instance without its parameters": changed(lambda d: hdl("u_tx")(d).pop("parameters")),
            "an instance port without its signal": changed(lambda d: hdl("u_rx")(d)["ports"]["rx"].pop("signal")),
            "an instance with signals": changed(lambda d: hdl("u_tx")(d).update(signals={})),
            "a top with a port": changed(lambda d: hdl("tb_uart_loopback")(d).update(
                ports={"clk": {"direction": "input", "width": 1}})),
            "a top without signals": changed(lambda d: hdl("tb_uart_loopback")(d).pop("signals")),
            "a top with text": changed(lambda d: hdl("tb_uart_loopback")(d).update(text="x")),
            "a name reserved for the harness": changed(lambda d: hdl("u_tx")(d).update(module="ecad_tx")),
            "an instance that is not a hierarchical path": changed(lambda d: hdl("u_tx")(d).update(instance="u_tx")),
            "a width of 65": changed(lambda d: hdl("tb_uart_loopback")(d)["signals"]["clk"].update(width=65)),
            "a member the format does not define": changed(lambda d: hdl("u_tx")(d).update(clock="clk")),
        }
        for label, document in invalid.items():
            with self.subTest(label), self.assertRaises(ValueError):
                validate_schema(document, "engineering-model/v1/engineering-model")
        annotations = json.loads((ITEM / "design" / "annotations.json").read_bytes())
        validate_schema(annotations, "engineering-model/v1/design-annotations")
        for version in ("1.0.0", "1.1.0"):
            with self.subTest(annotations=version), self.assertRaisesRegex(ValueError, "annotations_version"):
                validate_schema({**annotations, "annotations_version": version}, "engineering-model/v1/design-annotations")
        provenance = json.loads((ITEM / "source" / "provenance.json").read_bytes())
        validate_schema(provenance, "cad-dataset/v1/source-provenance")
        with self.assertRaisesRegex(ValueError, "provenance_version"):
            validate_schema({**provenance, "provenance_version": "1.0.0"}, "cad-dataset/v1/source-provenance")
        uncopied = copy.deepcopy(provenance)
        for artifact in uncopied["artifacts"]:
            artifact.pop("copied_from", None)
        for version in ("1.0.0", "1.1.0"):
            validate_schema({**uncopied, "provenance_version": version}, "cad-dataset/v1/source-provenance")
        with self.assertRaisesRegex(ValueError, "copied_from"):
            artifact = uncopied["artifacts"][1]
            validate_schema({**uncopied, "artifacts": [{**artifact, "copied_from": {"path": "rtl/uart_tx.v"}}]},
                            "cad-dataset/v1/source-provenance")
        # The committed samples of the other domains are still valid.
        for sample, version in (("robotic_joint_001", "1.0.0"), ("servo_supply_001", "1.1.0")):
            with self.subTest(sample):
                other = REPO_ROOT / "datasets" / "cad" / sample
                document = json.loads((other / "derived" / "engineering_model.json").read_bytes())
                self.assertEqual(document["model_version"], version)
                validate_schema(document, "engineering-model/v1/engineering-model")
                validate_schema(json.loads((other / "design" / "annotations.json").read_bytes()),
                                "engineering-model/v1/design-annotations")
                validate_schema(json.loads((other / "source" / "provenance.json").read_bytes()),
                                "cad-dataset/v1/source-provenance")


SPARE = "`timescale 1ns / 1ps\nmodule spare #(parameter WIDTH = 1) (input wire clk, output reg q);\n" \
        "    always @(posedge clk) q <= !q;\nendmodule\n"
U_RX = ("    uart_rx #(.CLK_FREQ(CLK_FREQ), .BAUD_RATE(BAUD_RATE)) u_rx (\n"
        "        .clk(clk), .rst_n(rst_n), .rx(line),\n"
        "        .rx_data(rx_data), .rx_valid(rx_valid), .rx_error(rx_error)\n"
        "    );\n")
HEADER_PARAMETERS = "    parameter BAUD_RATE = 115_200\n) ("
EXTRA_PARAMETER = "    parameter BAUD_RATE = 115_200,\n    parameter STOP_BITS = 1\n) ("
REJECTED = "not the UART 8N1 loopback the digital domain validates: rule"


class TestClassAndSanity(unittest.TestCase):
    def test_only_the_uart_8n1_loopback_is_accepted(self):
        """Each rule broken once, on a fixture copy: V1 refuses the source by name and no case reaches Icarus."""
        spare = [("    wire       rx_error;\n", "    wire       rx_error;\n    wire       spare_q;\n"),
                 ("\nendmodule\n", "\n    spare #(.WIDTH(1)) u_spare (.clk(clk), .q(spare_q));\n\nendmodule\n")]
        copies: Dict[str, Tuple[Edits, str]] = {
            "C1: a third instance": ({TB: spare}, "rule C1: the top instantiates u_tx (uart_tx), u_rx (uart_rx), "
                                                  "u_spare (spare); the class is exactly two instances"),
            "C1: one instance": ({TB: (U_RX, "")}, "rule C1: the top instantiates u_tx (uart_tx);"),
            "C2: a transmitter with a third parameter": (
                {TX: (HEADER_PARAMETERS, EXTRA_PARAMETER)},
                "rule C2: no instance's module declares exactly the transmitter's interface, inputs clk:1, rst_n:1, "
                "tx_data:8, tx_valid:1; outputs tx_ready:1, tx:1; parameters BAUD_RATE, CLK_FREQ: u_tx's uart_tx "
                "declares inputs clk:1, rst_n:1, tx_data:8, tx_valid:1; outputs tx_ready:1, tx:1; parameters "
                "BAUD_RATE, CLK_FREQ, STOP_BITS"),
            "C3: a receiver with a third parameter": (
                {RX: (HEADER_PARAMETERS, EXTRA_PARAMETER)},
                "rule C3: u_rx's uart_rx declares inputs clk:1, rst_n:1, rx:1; outputs rx_data:8, rx_valid:1, "
                "rx_error:1; parameters BAUD_RATE, CLK_FREQ, STOP_BITS, not exactly the receiver's interface"),
            "C3: an OVERSAMPLE that is not a literal": (
                {RX: ("localparam OVERSAMPLE    = 16;", "localparam OVERSAMPLE    = 8 + 8;")},
                "rule C3: uart_rx declares no localparam OVERSAMPLE = <decimal literal>"),
            "C4: one parameter overridden": (
                {TB: ("uart_tx #(.CLK_FREQ(CLK_FREQ), .BAUD_RATE(BAUD_RATE)) u_tx", "uart_tx #(.CLK_FREQ(CLK_FREQ)) u_tx")},
                "rule C4: u_tx overrides CLK_FREQ; each instance overrides both CLK_FREQ and BAUD_RATE"),
            # Review CS-4: a sized top localparam can hold what the harness's unsized decimal cannot.
            "C4: a parameter above 2^31 - 1": (
                {TB: ("CLK_FREQ           = 50_000_000;", "CLK_FREQ           = 64'd2147483648;")},
                "rule C4: u_tx CLK_FREQ = CLK_FREQ = 2147483648 is above 2147483647: the harness states each parameter "
                "as an unsized decimal, which Verilog guarantees only as a 32-bit signed integer"),
            "C5: rx fed from tx_valid": (
                {TB: (".rx(line)", ".rx(tx_valid)")},
                "rule C5: the line, which the transmitter's tx and the receiver's rx share, must be one wire that "
                "connects u_tx.tx and u_rx.rx and no other port; line is a wire that connects u_tx.tx"),
            "C5: the receiver's clock and reset swapped": (
                {TB: (".clk(clk), .rst_n(rst_n), .rx(line),", ".clk(rst_n), .rst_n(clk), .rx(line),")},
                "rule C5: the clock must be one reg that connects u_tx.clk and u_rx.clk and no other port; clk is a "
                "reg that connects u_rx.rst_n, u_tx.clk"),
            "C5: a signal that connects nothing": (
                {TB: ("    wire       rx_error;\n", "    wire       rx_error;\n    wire       spare;\n")},
                "rule C5: spare is declared but connects no port"),
            "C6: an inert localparam": (
                {TB: ("    localparam RESET_CYCLES       = 4;\n",
                      "    localparam RESET_CYCLES       = 4;\n    localparam UNUSED             = 3;\n")},
                "rule C6: UNUSED is stated but used by nothing the class reads"),
            "C6: TX_BYTE_0 missing": (
                {TB: ("TX_BYTE_0    = 8'h35;", "TX_BYTE_2    = 8'h35;")},
                "rule C6: the top states 2 localparams named TX_BYTE_*; the bytes sent are TX_BYTE_0 .. "
                "TX_BYTE_{N-1}, consecutive"),
            # Icarus 13.0 measured 1302 cycles (38402.46 Bd) on this copy: the start bit and bit 0. REQ-DIG-001
            # would FAIL a line that runs at 115207 Bd, so the copy is refused before anything runs.
            "C6: an even first byte": (
                {TB: ("TX_BYTE_0    = 8'h35;", "TX_BYTE_0    = 8'h34;")},
                "rule C6: TX_BYTE_0 = 52 is even: the harness measures a bit as the line's first low run"),
            "C6: no reset": (
                {TB: ("RESET_CYCLES       = 4;", "RESET_CYCLES       = 0;")},
                "rule C6: the top states no localparam RESET_CYCLES = <decimal literal of at least 1>"),
            "a width mismatch": ({TB: ("    reg  [7:0] tx_data;", "    reg  [6:0] tx_data;")},
                                 f"{{here}}/{TB}:43: u_tx.tx_data is 8 bits wide and tx_data is 7"),
            "two drivers": ({TB: (".rx_valid(rx_valid)", ".rx_valid(tx_ready)")},
                            f"{{here}}/{TB}:37: wire tx_ready is driven by u_tx.tx_ready and u_rx.rx_valid"),
        }
        for label, (edits, expected) in copies.items():
            with self.subTest(label), _scratch() as directory:
                item = _copy(directory, edits, rebuild=False, uncopied=[path for path in edits if path != TB])
                if label == "C1: a third instance":
                    (item / "source" / "spare.v").write_bytes(SPARE.encode())
                    _edit_json(item / "source" / "provenance.json", lambda document: document["artifacts"].append(
                        {"path": "source/spare.v", "format": "verilog"}))
                if label == "C1: one instance":
                    _edit_json(item / "source" / "provenance.json", lambda document: document.update(
                        artifacts=[a for a in document["artifacts"] if a["path"] != RX]))
                with mock.patch("ecad_validation.adapters.hdl.HDLAdapter.run", side_effect=AssertionError("ran")):
                    receipt, _ = _validate(item, _stand_in(refuse=True))
                v1 = _checks(receipt)["v1.digital.extraction-and-sanity"]
                here = item.relative_to(REPO_ROOT).as_posix()
                self.assertEqual(_outcome(v1), ("FAIL", "SOURCE_REJECTED"))
                self.assertIn(expected.replace("{here}", here), v1["findings"][0])
                if expected.startswith("rule"):
                    self.assertTrue(v1["findings"][0].startswith(f"{here}/{TB}: {REJECTED} {expected[5:7]}: "),
                                    v1["findings"][0])

    def test_v1_refuses_impossible_values_units_and_clocks(self):
        adapter = _adapter()
        model = _model()
        self.assertEqual(adapter.sanity_problems(model), [])
        tb, tx, rx = "tb_uart_loopback", "u_tx", "u_rx"

        def facet(changed: Dict[str, Any], component_id: str, name: str) -> Dict[str, Any]:
            return _component(changed, component_id)["domains"]["digital"][name]

        def with_unit(unit: str) -> Dict[str, Any]:
            changed = copy.deepcopy(model)
            facet(changed, tb, "clock_half_period")["unit"] = unit
            return changed

        def with_facet(name: str) -> Dict[str, Any]:
            changed = copy.deepcopy(model)
            _component(changed, tb)["domains"]["digital"][name] = {"value": 1.0, "unit": "1", "status": "SPECIFIED",
                                                                   "source": FIXTURE_SOURCE}
            return changed

        def with_limit(value: float) -> Dict[str, Any]:
            changed = copy.deepcopy(model)
            facet(changed, "target_device", "min_clock_period").update(value=value, status="SPECIFIED",
                                                                       source=FIXTURE_SOURCE)
            return changed

        cases = {
            "an unknown facet": (with_facet("jitter"), ["tb_uart_loopback: jitter is not in the digital facet vocabulary"]),
            "a half period in ns": (with_unit("ns"), ["tb_uart_loopback: clock_half_period is in ns, not the "
                                                      "vocabulary's s"]),
            "no half period": (_set(model, (tb, "clock_half_period", 0.0)),
                               ["tb_uart_loopback: clock_half_period 0.0 is not positive"]),
            "no reset": (_set(model, (tb, "reset_cycles", 0)), ["tb_uart_loopback: reset_cycles 0 is not an integer of at "
                                                                "least 1"]),
            "a fractional reset": (_set(model, (tb, "reset_cycles", 1.5)),
                                   ["tb_uart_loopback: reset_cycles 1.5 is not an integer of at least 1"]),
            "no byte": (_set(model, (tb, "tx_bytes", [])), ["tb_uart_loopback: tx_bytes [] is not 1 to 16 integers from 0 "
                                                            "to 255"]),
            "a byte of 256": (_set(model, (tb, "tx_bytes", [53, 256])),
                              ["tb_uart_loopback: tx_bytes [53, 256] is not 1 to 16 integers from 0 to 255"]),
            "seventeen bytes": (_set(model, (tb, "tx_bytes", [1] * 17), (tb, "byte_count", 17)),
                                [f"tb_uart_loopback: tx_bytes {[1] * 17!r} is not 1 to 16 integers from 0 to 255"]),
            "a stale byte count": (_set(model, (tb, "byte_count", 3)),
                                   ["tb_uart_loopback: byte_count 3 is not the 2 bytes tx_bytes holds"]),
            "a clock of 0 Hz": (_set(model, (tx, "clk_freq", 0)),
                                ["u_tx: clk_freq 0 and baud_rate 115200 are not both positive integers"]),
            "a fractional baud rate": (_set(model, (rx, "baud_rate", 115200.5)),
                                       ["u_rx: clk_freq 50000000 and baud_rate 115200.5 are not both positive integers"]),
            "a baud rate above the clock": (_set(model, (tx, "baud_rate", 60000000)),
                                            ["u_tx: baud_rate 60000000 Bd is above clk_freq 50000000 Hz"]),
            "an odd oversample": (_set(model, (rx, "oversample", 15)),
                                  ["u_rx: oversample 15 is not an even integer of at least 2"]),
            "no oversample": (_set(model, (rx, "oversample", 0)),
                              ["u_rx: oversample 0 is not an even integer of at least 2"]),
            "a device limit that is not positive": (with_limit(-1e-09),
                                                    ["target_device: min_clock_period -1e-09 is not positive"]),
            "the 40 MHz copy": (_set(model, (tx, "clk_freq", 40000000), (rx, "clk_freq", 40000000)), [
                "u_tx CLK_FREQ 40000000 Hz is not the frequency of its clock (half period 1e-08 s, 50000000 Hz)",
                "u_rx CLK_FREQ 40000000 Hz is not the frequency of its clock (half period 1e-08 s, 50000000 Hz)"]),
            # Review HT-1: a 6 ns clock runs at 166 666 666.67 Hz, which no whole-Hz CLK_FREQ names exactly; the
            # integers either side of it are its frequency to whole Hz, and the next ones out are not.
            "a 6 ns clock told 166666667 Hz": (
                _set(model, (tb, "clock_half_period", 3e-09), (tx, "clk_freq", 166666667), (rx, "clk_freq", 166666667)),
                []),
            "a 6 ns clock told 166666666 Hz": (
                _set(model, (tb, "clock_half_period", 3e-09), (tx, "clk_freq", 166666666), (rx, "clk_freq", 166666666)),
                []),
            "a 6 ns clock told 166666668 Hz": (
                _set(model, (tb, "clock_half_period", 3e-09), (tx, "clk_freq", 166666668), (rx, "clk_freq", 166666667)),
                ["u_tx CLK_FREQ 166666668 Hz is not the frequency of its clock (half period 3e-09 s, 166666666.667 Hz)"]),
            "a 6 ns clock told 166666665 Hz": (
                _set(model, (tb, "clock_half_period", 3e-09), (tx, "clk_freq", 166666667), (rx, "clk_freq", 166666665)),
                ["u_rx CLK_FREQ 166666665 Hz is not the frequency of its clock (half period 3e-09 s, 166666666.667 Hz)"]),
            # 20 ns is exactly 50 MHz: 1 Hz off is off.
            "50000001 Hz at 20 ns": (_set(model, (tx, "clk_freq", 50000001)), [
                "u_tx CLK_FREQ 50000001 Hz is not the frequency of its clock (half period 1e-08 s, 50000000 Hz)"]),
            "a 1 MHz clock at 115200 Bd": (
                _set(model, (tb, "clock_half_period", 5e-07), (tx, "clk_freq", 1000000), (rx, "clk_freq", 1000000)),
                ["u_rx: CLK_FREQ // (BAUD_RATE * OVERSAMPLE) = 1000000 // (115200 * 16) is 0: the receiver's divider "
                 "is 0, so it never samples"]),
        }
        for label, (changed, expected) in cases.items():
            with self.subTest(label):
                self.assertEqual(adapter.sanity_problems(changed), expected)
        known = with_limit(1e-08)
        self.assertEqual(adapter.sanity_problems(known), [], "a positive known device limit is sane")

    def test_a_parameter_is_at_most_what_an_unsized_decimal_holds(self):
        """Review CS-4: 2^31 - 1 is written into the harness; 2^31 and 5e9 are refused at extraction, where before
        the harness took them and V2's reader of it refused the file build had written."""
        from ecad_model.dataset import build
        from ecad_model.importers import ExtractionError

        with _scratch() as directory:
            item = _copy(directory, {TB: ("CLK_FREQ           = 50_000_000;", "CLK_FREQ           = 64'd2147483647;")})
            harness = (item / SIM).read_text()
        self.assertIn("    uart_tx #(.BAUD_RATE(115200), .CLK_FREQ(2147483647)) u_tx (", harness)
        for literal, number in (("64'd2147483648", "2147483648"), ("64'd5000000000", "5000000000")):
            with self.subTest(literal), _scratch() as directory:
                item = _copy(directory, {TB: ("CLK_FREQ           = 50_000_000;", f"CLK_FREQ           = {literal};")},
                             rebuild=False)
                with self.assertRaises(ExtractionError) as caught:
                    build(item)
                self.assertEqual(caught.exception.kind, "rejected")
                self.assertIn(f"{item.relative_to(REPO_ROOT).as_posix()}/{TB}: {REJECTED} C4: u_tx CLK_FREQ = CLK_FREQ = "
                              f"{number} is above 2147483647", str(caught.exception))
                self.assertFalse((item / SIM).read_bytes().count(number.encode()), "nothing was written")

    def test_the_resource_guard_refuses_a_run_longer_than_max_cycles(self):
        """END = 4 + 4 * 12 * T: 50e6 // 1200 = 41666 gives 1 999 972 cycles; 50e6 // 1199 = 41701 gives 2 001 652."""
        from ecad_model.dataset import build
        from ecad_model.importers import ExtractionError

        with _scratch() as directory:
            item = _copy(directory, {TB: ("BAUD_RATE          = 115_200;", "BAUD_RATE          = 1_200;")})
            harness = (item / SIM).read_text()
            self.assertIn("        if (ecad_cycle == 1999972) begin\n", harness)
        with _scratch() as directory:
            item = _copy(directory, {TB: ("BAUD_RATE          = 115_200;", "BAUD_RATE          = 1_199;")}, rebuild=False)
            with self.assertRaises(ExtractionError) as caught:
                build(item)
        self.assertEqual(caught.exception.kind, "rejected")
        self.assertIn(f"{item.relative_to(REPO_ROOT).as_posix()}/{TB}: {REJECTED} C7: the run lasts END = 2001652 "
                      "cycles, more than 2000000", str(caught.exception))


class TestSimulationFile(unittest.TestCase):
    def test_the_simulation_file_is_the_rtl_verbatim_then_the_harness(self):
        from tests.unit.test_verilog_source import HARNESS, SIMULATION_HEADER

        from ecad_model.domains.digital import write_simulation

        data = (ITEM / SIM).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), SIM_SHA256)
        self.assertEqual(write_simulation(_model()), data)
        expected = (SIMULATION_HEADER + f"// ---- {TX_REF} sha256 {TX_SHA256} ----\n"
                    + (ITEM / TX).read_bytes().decode("utf-8") + f"// ---- {RX_REF} sha256 {RX_SHA256} ----\n"
                    + (ITEM / RX).read_bytes().decode("utf-8") + HARNESS)
        self.assertEqual(data.decode("utf-8"), expected)
        lines = data.decode("utf-8").split("\n")
        self.assertEqual((len(data), len(lines) - 1), (13240, 357))
        self.assertEqual([number for number, line in enumerate(lines, start=1) if line.startswith("// ---- ")],
                         [3, 115, 242])
        with _scratch() as directory:
            item = _copy(directory, {TB: [("BAUD_RATE          = 115_200;", "BAUD_RATE          = 9_600;"),
                                          ("    localparam [7:0] TX_BYTE_1    = 8'hCA;\n",
                                           "    localparam [7:0] TX_BYTE_1    = 8'hCA;\n"
                                           "    localparam [7:0] TX_BYTE_2    = 8'h5A;\n")]})
            three = (item / SIM).read_text()
        self.assertIn("\n".join(["        repeat (4) @(posedge clk);", "        rst_n <= 1'b1;",
                                 *(line for value in (53, 202, 90) for line in (
                                     "        @(posedge clk);", "        while (!tx_ready) @(posedge clk);",
                                     f"        tx_data <= 8'd{value};", "        tx_valid <= 1'b1;",
                                     "        @(posedge clk);", "        tx_valid <= 1'b0;")),
                                 "    end"]), three)
        self.assertIn("    reg  [7:0] ecad_expected [0:2];\n", three)
        self.assertIn("        ecad_expected[0] = 8'd53;\n        ecad_expected[1] = 8'd202;\n"
                      "        ecad_expected[2] = 8'd90;\n    end\n", three)
        self.assertIn("            if (ecad_received < 3) begin\n", three)
        self.assertIn("            if (ecad_received < 3) ecad_missing = 3 - ecad_received;\n", three)
        # END = 4 + (3 + 2) * 12 * (50e6 // 9600 = 5208)
        self.assertIn("        if (ecad_cycle == 312484) begin\n", three)
        self.assertIn("    uart_tx #(.BAUD_RATE(9600), .CLK_FREQ(50000000)) u_tx (", three)

    def test_v2_names_every_way_the_simulation_file_can_disagree_with_its_model(self):
        adapter = _adapter()
        model = _model()
        data = (ITEM / SIM).read_bytes()
        self.assertEqual(adapter.invariant_problems(model, {}, {SIM: data}), [])
        display = ('            if (ecad_framing_errors > 0 || ecad_missing == 0) $display("ECAD_METRIC rx_framing_errors %0d", '
                   'ecad_framing_errors);\n')
        edits = {
            # uart_tx.v line 53 is line 56 of the file: two header lines and a separator come first.
            "one RTL byte": ("1'b1;   // Idle line is high", "1'b0;   // Idle line is high",
                             f"{SIM}:56: \"            tx       <= 1'b0;   // Idle line is high\" is not line 56 of what "
                             f"the model holds (u_tx's text, {TX_REF})"),
            "the half period": ("always #10 clk", "always #11 clk", "the harness's half period 11 != the model's 10"),
            "an override": ("uart_tx #(.BAUD_RATE(115200)", "uart_tx #(.BAUD_RATE(115201)",
                            "the harness's instances [('uart_tx', 'u_tx', {'BAUD_RATE': 115201,"),
            "a stimulus byte": ("tx_data <= 8'd53;", "tx_data <= 8'd52;",
                                "the harness's stimulus [('tx_data', 52), ('tx_data', 202)] != the model's"),
            "an expected byte": ("ecad_expected[1] = 8'd202;", "ecad_expected[1] = 8'd203;",
                                 "the harness's expected bytes [53, 203] != the model's [53, 202]"),
            "the end": ("ecad_cycle == 20836", "ecad_cycle == 20835", "the harness's end cycle 20835 != the model's 20836"),
            "the bytes a missing one is counted against": (
                "if (ecad_received < 2) ecad_missing = 2 - ecad_received;",
                "if (ecad_received < 1) ecad_missing = 1 - ecad_received;", "the harness's bytes awaited 1 != the model's 2"),
            "a dropped $display": (display, "", "declares the metrics ['clock_period_s'"),
            "a duplicated $display": (display, display + display, "and ['rx_framing_errors'] more than once"),
            "an inserted $fopen": ("            $finish;\n", '            $fopen("x");\n            $finish;\n',
                                   "the harness is not one this adapter writes"),
            "a swapped connection": ("u_rx (.clk(clk), .rst_n(rst_n), .rx(line)", "u_rx (.clk(clk), .rst_n(rst_n), .rx(tx_valid)",
                                     "'rx': 'tx_valid'"),
            # Only the writer's own text says where the harness samples: nothing the reader reads changes.
            "the sampling edge": ("    always @(negedge clk) begin", "    always @(posedge clk) begin",
                                  f"{SIM}:312: the harness differs from the one this adapter writes from the model: "
                                  "'    always @(posedge clk) begin', not '    always @(negedge clk) begin'"),
            "a wrong separator hash": (f"sha256 {RX_SHA256}", f"sha256 {TX_SHA256}",
                                       "is not line 115 of what the model holds (the separator before u_rx's text"),
            # The RTL and the harness each still match: only the line between them is foreign.
            "a line between the RTL and the harness": (
                "// ---- harness ----\n", "wire ecad_extra;\n// ---- harness ----\n",
                f"{SIM}:242: 'wire ecad_extra;' is not '// ---- harness ----', the line that follows the model's RTL"),
        }
        for label, (old, new, expected) in edits.items():
            with self.subTest(label):
                text = data.decode("utf-8")
                self.assertEqual(text.count(old), 1, old)
                problems = adapter.invariant_problems(model, {}, {SIM: text.replace(old, new).encode("utf-8")})
                self.assertTrue(any(expected in problem for problem in problems), problems)
        for label, component, name, change, expected in (
            ("a facet sha that is not the top's", "u_tx", "clk_freq", {"sha256": RX_SHA256},
             f"u_tx: clk_freq is not SPECIFIED by {TB_REF} cited by its hash"),
            ("an oversample citing the top", "u_rx", "oversample", {"ref": TB_REF, "sha256": TB_SHA256},
             f"u_rx: oversample is not SPECIFIED by {RX_REF} cited by its hash"),
            ("the top's hash under another file's name", "u_rx", "clk_freq", {"ref": TX_REF},
             f"u_rx: clk_freq is not SPECIFIED by {TB_REF} cited by its hash"),
            ("a value the top states, estimated", "u_tx", "baud_rate", {"status": "ESTIMATED", "note": "fixture"},
             f"u_tx: baud_rate is not SPECIFIED by {TB_REF} cited by its hash"),
        ):
            with self.subTest(label):
                changed = copy.deepcopy(model)
                facet = _component(changed, component)["domains"]["digital"][name]
                if "status" in change:
                    facet.update(change)
                else:
                    facet["source"].update(change)
                self.assertEqual(adapter.invariant_problems(changed, {}, {SIM: data}), [expected])
        changed = copy.deepcopy(model)
        _component(changed, "u_tx")["hdl"]["text"] += "\n"
        problems = adapter.invariant_problems(changed, {}, {SIM: data})
        self.assertIn(f"u_tx: hdl.text is not the bytes of {TX_REF} that design.sources records", problems)


class TestReferences(unittest.TestCase):
    def test_references_are_the_closed_forms_written_out_here(self):
        adapter = _adapter()
        model = _model()
        committed = {"clock_period": 2e-08, "idle_high_after_reset": 1.0, "bit_period_cycles": 434.0,
                     "bit_rate": 115207.3732718894, "frame_cycles": 4340.0, "bytes_sent": 2.0,
                     "lossless_loopback": 0.0, "no_framing_errors": 0.0}
        self.assertEqual(_closed_forms(1e-08, [53, 202], (50000000, 115200), (50000000, 115200, 16)), committed)
        variants = {
            "committed": (model, committed),
            "230400 Bd": (_set(model, ("u_tx", "baud_rate", 230400), ("u_rx", "baud_rate", 230400)),
                          {**committed, "bit_period_cycles": 217.0, "bit_rate": 230414.74654377881, "frame_cycles": 2170.0}),
            "three bytes at 9600 Bd": (
                _set(model, ("u_tx", "baud_rate", 9600), ("u_rx", "baud_rate", 9600),
                     ("tb_uart_loopback", "tx_bytes", [53, 202, 90]), ("tb_uart_loopback", "byte_count", 3)),
                {**committed, "bit_period_cycles": 5208.0, "bit_rate": 9600.614439324117, "frame_cycles": 52080.0,
                 "bytes_sent": 3.0}),
            # 50e6 / 115000 = 434.78: the divider floors to 434, it does not round to 435.
            "115000 Bd": (_set(model, ("u_tx", "baud_rate", 115000)), {**committed}),
        }
        for label, (changed, expected) in variants.items():
            for derivation, value in expected.items():
                with self.subTest(label, derivation=derivation):
                    computed, inputs = adapter.reference_value(changed, derivation, {"name": "loopback"})
                    self.assertLessEqual(abs(computed - value), 1e-12 * abs(value), f"{computed!r} != {value!r}")
                    self.assertEqual(set(inputs), set(REFERENCE_INPUTS[derivation]))
                    self.assertEqual(set(adapter.reference_inputs(changed, derivation, {"name": "loopback"})),
                                     set(REFERENCE_INPUTS[derivation]))
        self.assertEqual(set(REFERENCE_INPUTS), set(committed))
        from ecad_model.requirements import ReferenceBlocked

        unknown = copy.deepcopy(model)
        _component(unknown, "u_tx")["domains"]["digital"]["baud_rate"].update(value=None, status="UNKNOWN", note="fixture")
        with self.assertRaises(ReferenceBlocked) as caught:
            adapter.reference_value(unknown, "frame_cycles", {"name": "loopback"})
        self.assertEqual(caught.exception.paths, [{"path": _path("u_tx", "baud_rate"), "status": "UNKNOWN"}])
        with self.assertRaisesRegex(ValueError, "unknown derivation 'baud_error'"):
            adapter.reference_value(model, "baud_error", {"name": "loopback"})

    def test_a_reference_does_not_apply_where_its_assumptions_fail(self):
        from ecad_model.requirements import ReferenceBlocked

        adapter = _adapter()
        model = _model()

        def applies(changed: Dict[str, Any], derivation: str) -> bool:
            try:
                adapter.reference_value(changed, derivation, {"name": "loopback"})
            except ReferenceBlocked as exc:
                self.assertEqual(exc.paths, [], "a form that does not apply names no missing input")
                self.assertIn(f"{derivation} does not apply to this design", str(exc))
                return False
            return True

        even = _set(model, ("tb_uart_loopback", "tx_bytes", [52, 202]))
        for derivation in ("bit_period_cycles", "bit_rate"):
            with self.subTest(derivation):
                self.assertFalse(applies(even, derivation))
                self.assertTrue(applies(model, derivation))
        with self.assertRaisesRegex(ReferenceBlocked, "the first byte, 52, is even"):
            adapter.reference_value(even, "bit_rate", {"name": "loopback"})
        self.assertTrue(applies(even, "frame_cycles"))

        def link(bit_cycles: int, tick_cycles: int) -> Dict[str, Any]:
            """D_t = CLK_FREQ // 1 on the transmitter, D_r = CLK_FREQ // (1 * 16) on the receiver."""
            return _set(model, ("u_tx", "clk_freq", bit_cycles), ("u_tx", "baud_rate", 1),
                        ("u_rx", "clk_freq", 16 * tick_cycles), ("u_rx", "baud_rate", 1))

        # W's bounds for b = 9, SP = 8: 9 * D_t <= 152 * D_r and 152 * D_r + D_r - 1 < 10 * D_t.
        edges = {(152, 10): False, (153, 10): True, (168, 10): True, (169, 10): False,
                 (107, 7): False, (108, 7): True, (413, 27): False, (414, 27): True, (434, 27): True}
        for (bit_cycles, tick_cycles), holds in edges.items():
            for derivation in ("bytes_sent", "lossless_loopback", "no_framing_errors"):
                with self.subTest(bit_cycles=bit_cycles, tick_cycles=tick_cycles, derivation=derivation):
                    self.assertEqual(applies(link(bit_cycles, tick_cycles), derivation), holds)
                    self.assertTrue(applies(link(bit_cycles, tick_cycles), "frame_cycles"))
        # 20 MHz: D_t = 173, D_r = 10, and 9 * 173 = 1557 > 1520. A 1 MHz receiver: D_r = 0, it never samples.
        slow = _set(model, ("tb_uart_loopback", "clock_half_period", 2.5e-08), ("u_tx", "clk_freq", 20000000),
                    ("u_rx", "clk_freq", 20000000))
        stopped = _set(model, ("u_rx", "clk_freq", 1000000))
        for label, changed in (("20 MHz", slow), ("a receiver divider of 0", stopped)):
            with self.subTest(label):
                self.assertFalse(applies(changed, "bytes_sent"))
                self.assertTrue(applies(changed, "clock_period"))
        with self.assertRaisesRegex(ReferenceBlocked, "D_t = 173 and D_r = 10 cycles, 16 ticks per bit"):
            adapter.reference_value(slow, "bytes_sent", {"name": "loopback"})

    def test_each_metric_has_its_scenario_and_each_derivation_its_metric(self):
        from ecad_model.dataset import build

        def reference(document: Dict[str, Any]) -> Dict[str, Any]:
            return document["reference_values"][2]  # REF-DIG-003, bit_period_cycles on tx_bit_cycles

        for label, change, expected in (
            ("an unknown scenario", lambda d: reference(d).update(scenario={"name": "startup"}),
             "scenarios/2/name: 'startup' is not one of \\['loopback'\\]"),
            ("a scenario with parameters", lambda d: d["requirements"][0].update(
                scenario={"name": "loopback", "baud_rate": 9600}), "Additional properties are not allowed"),
            ("an unknown derivation", lambda d: reference(d).update(derivation="baud_error"),
             "'baud_error' is not one of"),
            ("a derivation paired with the wrong metric", lambda d: reference(d).update(metric="tx_frame_cycles"),
             "REF-DIG-003: bit_period_cycles computes tx_bit_cycles, not tx_frame_cycles"),
            ("a unit that is not the metric's", lambda d: d["reference_values"][0].update(unit="ms"),
             "REF-DIG-001: unit ms != the unit of clock_period_s, s"),
            ("a metric the domain does not produce", lambda d: d["requirements"][0].update(metric="baud_error_ppm"),
             "REQ-DIG-001: the domain produces no metric 'baud_error_ppm'"),
        ):
            with self.subTest(label), _scratch() as directory:
                item = _copy(directory, rebuild=False)
                _edit_json(item / "requirements" / "requirements.json", change)
                with self.assertRaisesRegex(ValueError, expected):
                    build(item)


class TestSample(unittest.TestCase):
    def test_the_model_names_the_adapter_that_built_it(self):
        manifest = json.loads((ITEM / "dataset-item.json").read_bytes())
        [model] = [d for d in manifest["derived"] if d["artifact"]["path"] == "derived/engineering_model.json"]
        self.assertEqual(model["producer"], {"tool": "ecad_model.domains.digital",
                                             "version": "1.0.0 (ecad_model.verilog 1.0.0)"})
        self.assertEqual(manifest["versions"]["engineering_model"], "1.0.0 (ecad_model.verilog 1.0.0)")
        self.assertEqual(manifest["versions"]["domain_models"], {"digital": "ecad_model.domains.digital 1.0.0"})

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
        # The model, the simulation file and the manifest record the item's own
        # repository path, the manifest also their digests and the item's; nothing else differs.
        moved = {relative: data.replace(here, SAMPLE.encode()) for relative, data in rebuilt.items()}

        def unhashed(data: bytes) -> Dict[str, Any]:
            manifest = json.loads(data)
            manifest.pop("hash")
            for entry in manifest["derived"]:
                if entry["artifact"]["path"] in ("derived/engineering_model.json", SIM):
                    entry["artifact"].pop("sha256"), entry["artifact"].pop("size_bytes")
            return manifest

        for relative in committed:
            with self.subTest(relative):
                if relative == "dataset-item.json":
                    self.assertEqual(unhashed(moved[relative]), unhashed(committed[relative]))
                else:
                    self.assertEqual(moved[relative], committed[relative])
        self.assertEqual(written, ["derived/engineering_model.json", SIM, "validation/golden/cases.json",
                                   "validation/corners/cases.json", "dataset-item.json"])
        manifest = json.loads(committed["dataset-item.json"])
        status = {d["domain"]: d for d in manifest["domains"]}
        self.assertEqual(status.pop("digital"), {
            "domain": "digital", "status": "AVAILABLE",
            "reason": f"{DESCRIPTION}; requirements resting on {DEVICE_LIMIT} (UNKNOWN) are BLOCKED"})
        self.assertEqual(status.pop("mechanical"), {
            "domain": "mechanical", "status": "NOT_APPLICABLE",
            "reason": "the mechanical adapter reads step, which this sample does not have"})
        self.assertEqual(status.pop("electrical"), {
            "domain": "electrical", "status": "NOT_APPLICABLE",
            "reason": "the electrical adapter reads spice, which this sample does not have"})
        self.assertEqual({d: s["status"] for d, s in status.items()},
                         dict.fromkeys(("pcb", "power_electronics", "control", "electromagnetic", "thermal",
                                        "full_system"), "NOT_IMPLEMENTED"))
        lineage = {d["artifact"]["path"]: d["derived_from"] for d in manifest["derived"]}
        self.assertEqual(lineage["derived/engineering_model.json"], [TB, TX, RX, "design/annotations.json"])
        self.assertEqual(lineage[SIM], ["derived/engineering_model.json"])
        [simulation] = [d for d in manifest["derived"] if d["artifact"]["path"] == SIM]
        self.assertEqual((simulation["role"], simulation["domain"], simulation["artifact"]["sha256"],
                          simulation["artifact"]["media_type"], simulation["producer"]),
                         ("domain_model", "digital", SIM_SHA256, "text/x-verilog",
                          {"tool": "ecad_model.domains.digital", "version": "1.0.0"}))
        self.assertEqual((manifest["domain"], manifest["title"], manifest["artifact_type"],
                          manifest["versions"]["extraction"], manifest["versions"]["simulation"], manifest["created_at"],
                          manifest["collected_at"]),
                         ("digital", "tb_uart_loopback", "hdl_source", "none", EMPTY_SET, "2026-09-27", "2026-09-27"))
        self.assertEqual(manifest["source"]["artifacts"], [
            {"path": TB, "format": "verilog", "sha256": TB_SHA256, "size_bytes": 2152, "media_type": "text/x-verilog"},
            {"path": TX, "format": "verilog", "sha256": TX_SHA256, "size_bytes": 3367, "media_type": "text/x-verilog"},
            {"path": RX, "format": "verilog", "sha256": RX_SHA256, "size_bytes": 4195, "media_type": "text/x-verilog"}])
        self.assertEqual(manifest["inputs"]["simulation"], [])
        self.assertEqual(manifest["source"]["license"]["license_text"], {"path": "LICENSE", "sha256": LICENSE_SHA256})
        self.assertEqual(manifest["source"]["origin"], {"kind": "self_authored",
                                                        "author": "EmbeddedOS (EoS) Research Foundation"})

    def test_the_unknown_outputs_requirement_names_the_one_instant_it_is_measured_at(self):
        """Review HT-6: outputs_unknown_after_reset samples the outputs once, at the first falling clock edge after
        reset is released, so REQ-DIG-006 says that instant rather than every instant after reset."""
        from ecad_model.domains.digital import METRICS

        document = json.loads((ITEM / "requirements" / "requirements.json").read_bytes())
        [requirement] = [r for r in document["requirements"] if r["requirement_id"] == "REQ-DIG-006"]
        self.assertEqual((requirement["metric"], requirement["title"]),
                         ("outputs_unknown_after_reset",
                          "No output is unknown at the first falling clock edge after reset is released"))
        self.assertEqual(METRICS["outputs_unknown_after_reset"].description,
                         "outputs with an X or Z bit at the first falling edge after reset is released (4-state "
                         "simulation only)")

    def test_hash_cited_rtl_is_never_converted_on_checkout(self):
        listed = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files", "-co", "--exclude-standard", "-z", "--",
                                 SAMPLE], check=True, capture_output=True, timeout=60).stdout.decode()
        files = sorted({name for name in listed.split("\0") if name}) + ["rtl/uart_tx.v", "rtl/uart_rx.v", "LICENSE"]
        self.assertIn(TX_REF, files)
        attributes = subprocess.run(["git", "-C", str(REPO_ROOT), "check-attr", "text", "-z", "--", *files],
                                    check=True, capture_output=True, timeout=60).stdout.decode().split("\0")
        found = dict(zip(attributes[0::3], attributes[2::3]))
        self.assertEqual(found, dict.fromkeys(files, "unset"))


class TestReceipt(unittest.TestCase):
    """One validation of the committed sample, with Icarus 13.0's recorded output."""

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

    def test_the_committed_sample_validates_as_designed_with_recorded_icarus_output(self):
        from ecad_validation.contract import validate_document

        from ecad_model.schemas import validate as validate_schema

        validate_document(REPO_ROOT, "validation-receipt.schema.json", self.receipt)
        validate_schema(json.loads(self.written), "engineering-model/v1/validation-results")
        checks = _checks(self.receipt)
        # v0.pinned-clean-source depends on the checkout, not the sample.
        for check_id, outcome in (("v0.dataset-schemas-and-hashes", ("PASS", "DATASET_SCHEMAS_VALID")),
                                  ("v0.dataset-input-immutability", ("PASS", "VALIDATION_INPUT_UNCHANGED")),
                                  ("v1.digital.extraction-and-sanity", ("PASS", "DOMAIN_SANITY_PASSED")),
                                  ("v2.dataset-reproduction", ("PASS", "DERIVATION_REPRODUCED")),
                                  ("v2.digital.model-invariants", ("PASS", "DOMAIN_MODEL_CONSISTENT"))):
            with self.subTest(check_id):
                self.assertEqual(_outcome(checks[check_id]), outcome, checks[check_id]["findings"])
        gates = {g["gate"]: g["verdict"] for g in self.receipt["gates"]}
        self.assertEqual([gates[gate] for gate in ("V1", "V2", "V3", "V4")], ["PASS", "PASS", "PASS", "BLOCKED"])
        self.assertEqual((self.receipt["overall_verdict"], self.receipt["eligible_for_ebuild"]), ("BLOCKED", False))
        self.assertEqual(_outcomes(checks, "v3."), V3_PASSED)
        self.assertEqual(_outcomes(checks, "v4."), {**V4_WARNED, **V4_BLOCKED})
        # The closed forms of §5.3 at the 12 significant figures the golden cases store.
        golden = {"v3.REF-DIG-001": 2e-08, "v3.REF-DIG-002": 1.0, "v3.REF-DIG-003": 434.0,
                  "v3.REF-DIG-004": 115207.373272, "v3.REF-DIG-005": 4340.0, "v3.REF-DIG-006": 2.0,
                  "v3.REF-DIG-007": 0.0, "v3.REF-DIG-008": 0.0}
        for check_id, value in golden.items():
            with self.subTest(check_id):
                self.assertEqual(checks[check_id]["metrics"], RECORDED_METRICS)
                self.assertEqual(self.results[check_id]["expected_value"], value)
                self.assertEqual(self.results[check_id]["measured_value"],
                                 RECORDED_METRICS[self.results[check_id]["metric"]])
        for n, (value, limit) in enumerate(((115207.3732718894, 112896.0), (115207.3732718894, 117504.0), (2.0, 2),
                                            (0.0, 0), (0.0, 0), (0.0, 0)), start=1):
            with self.subTest(requirement=n):
                row = self.results[f"v4.REQ-DIG-00{n}"]
                self.assertEqual((row["measured_value"], row["expected_value"], row["simulator_version"]),
                                 (value, limit, "stand-in 0"))
        blocked = checks["v4.REQ-DIG-007"]
        self.assertEqual(blocked["findings"][0], f"UNKNOWN: {DEVICE_LIMIT}")
        row = self.results["v4.REQ-DIG-007"]
        # The measured side is borrowed from the first sorted check that ran the same file.
        self.assertEqual((row["measured_value"], row["measured_by"], row["expected_value"], row["simulator"]),
                         (2e-08, "v3.REF-DIG-001", None, None))
        self.assertEqual(len(self.results), 15)
        self.assertEqual({row["model_fidelity"] for row in self.results.values()}, {"SIMPLIFIED"})
        [tool] = [t for t in self.receipt["tools"] if t["tool_id"] == "iverilog"]
        self.assertEqual(tool["version"], "stand-in 0")
        # 1.1.0: V0 re-hashes copied sources (REUSE-1), a behaviour of the runner that 1.0.0 did not have.
        [validator] = [t for t in self.receipt["tools"] if t["tool_id"] == "ecad-validator"]
        self.assertEqual(validator["version"], "1.1.0")
        derivations = {f"v3.REF-DIG-00{n}": d for n, d in enumerate(
            ("clock_period", "idle_high_after_reset", "bit_period_cycles", "bit_rate", "frame_cycles", "bytes_sent",
             "lossless_loopback", "no_framing_errors"), start=1)}
        for check_id, row in self.results.items():
            with self.subTest(inputs=check_id):
                expected = ([{"path": path, "status": "SPECIFIED"} for path in sorted(REFERENCE_INPUTS[derivations[check_id]])]
                            if check_id in derivations else [{"path": path, "status": "SPECIFIED"} for path in STATED_PATHS])
                if check_id == "v4.REQ-DIG-007":
                    expected = sorted([*expected, {"path": DEVICE_LIMIT, "status": "UNKNOWN"}], key=lambda i: i["path"])
                self.assertEqual(row["inputs"], expected)

    def test_results_trace_source_to_evidence_and_regenerate_identically(self):
        model = _model()
        manifest = json.loads((ITEM / "dataset-item.json").read_bytes())
        provenance = json.loads((ITEM / "source" / "provenance.json").read_bytes())
        for relative, origin, digest in ((TX, "rtl/uart_tx.v", TX_SHA256), (RX, "rtl/uart_rx.v", RX_SHA256)):
            with self.subTest(relative):
                [source] = [s for s in model["design"]["sources"] if s["path"] == f"{SAMPLE}/{relative}"]
                [artefact] = [a for a in manifest["source"]["artifacts"] if a["path"] == relative]
                [declared] = [a for a in provenance["artifacts"] if a["path"] == relative]
                self.assertEqual({source["sha256"], artefact["sha256"], declared["copied_from"]["sha256"],
                                  hashlib.sha256((ITEM / relative).read_bytes()).hexdigest(),
                                  hashlib.sha256((REPO_ROOT / origin).read_bytes()).hexdigest()}, {digest})
                self.assertEqual(declared["copied_from"]["path"], origin)
        checks = _checks(self.receipt)
        components = {"clock_period_s": ["tb_uart_loopback (top)"],
                      **dict.fromkeys(("tx_idle_after_reset", "tx_bit_cycles", "tx_bit_rate_bd", "tx_frame_cycles"),
                                      ["u_tx (uart_tx)"]),
                      **dict.fromkeys(("rx_bytes_received", "rx_bit_errors", "rx_framing_errors",
                                       "outputs_unknown_after_reset"), ["u_rx (uart_rx)", "u_tx (uart_tx)"])}
        for check_id, row in self.results.items():
            with self.subTest(check_id):
                self.assertEqual(row["cad_components"], components[row["metric"]])
                if check_id != "v4.REQ-DIG-007":
                    self.assertIn(SIM_SHA256, [e["sha256"] for e in checks[check_id]["evidence"]],
                                  "the simulation file the case ran on is part of its evidence")
                    self.assertEqual(row["configuration"]["command"], ["vvp", "simulation.vvp"])
                for evidence in checks[check_id]["evidence"]:
                    stored = self.output / "evidence" / "sha256" / evidence["sha256"]
                    self.assertEqual(hashlib.sha256(stored.read_bytes()).hexdigest(), evidence["sha256"])
        self.assertEqual(self.regenerated, self.written)


class TestVerdicts(unittest.TestCase):
    def test_a_mutated_baud_rate_fails_only_the_bit_rate_requirement(self):
        """BAUD_RATE 115_200 -> 230_400: the design's FAIL, not the simulator's: every closed form still agrees."""
        with _scratch() as directory:
            item = _copy(directory, {TB: ("BAUD_RATE          = 115_200;", "BAUD_RATE          = 230_400;")})
            receipt, _ = _validate(item, _stand_in(RECORDED_STDOUT["baud230400"]))
        checks = _checks(receipt)
        for check_id in ("v1.digital.extraction-and-sanity", "v2.dataset-reproduction", "v2.digital.model-invariants"):
            self.assertEqual(checks[check_id]["verdict"], "PASS", checks[check_id]["findings"])
        self.assertEqual(_outcomes(checks, "v3."), V3_PASSED)
        self.assertEqual(_outcomes(checks, "v4."), {**V4_WARNED, **V4_BLOCKED,
                                                    "v4.REQ-DIG-002": ("FAIL", "CORNER_LIMITS_FAILED")})
        self.assertEqual(checks["v4.REQ-DIG-002"]["metrics"]["tx_bit_rate_bd"], 230414.74654377881)

    def test_a_mis_sampling_receiver_fails_on_the_bytes_and_its_references_do_not_apply(self):
        """20 MHz: D_r = 10 misses W, the receiver misreads, and V3 says the loopback forms do not apply."""
        with _scratch() as directory:
            item = _copy(directory, {TB: [("CLK_HALF_PERIOD_NS = 10;", "CLK_HALF_PERIOD_NS = 25;"),
                                          ("CLK_FREQ           = 50_000_000;", "CLK_FREQ           = 20_000_000;")]})
            receipt, _ = _validate(item, _stand_in(RECORDED_STDOUT["clk20m"]))
        checks = _checks(receipt)
        self.assertEqual(checks["v1.digital.extraction-and-sanity"]["verdict"], "PASS",
                         checks["v1.digital.extraction-and-sanity"]["findings"])
        self.assertEqual(_outcomes(checks, "v3."), {
            **{f"v3.REF-DIG-00{n}": ("PASS", "GOLDEN_COMPARISON_PASSED") for n in range(1, 6)},
            **{f"v3.REF-DIG-00{n}": ("BLOCKED", "REFERENCE_NOT_APPLICABLE") for n in (6, 7, 8)}})
        self.assertEqual(_outcomes(checks, "v4."), {
            **V4_WARNED, **V4_BLOCKED, **{f"v4.REQ-DIG-00{n}": ("FAIL", "CORNER_LIMITS_FAILED") for n in (3, 4, 5)}})
        self.assertEqual({metric: checks["v4.REQ-DIG-004"]["metrics"][metric]
                          for metric in ("rx_bytes_received", "rx_bit_errors", "rx_framing_errors")},
                         {"rx_bytes_received": 1.0, "rx_bit_errors": 15.0, "rx_framing_errors": 1.0})

    def test_the_limit_boundaries_are_exact(self):
        """The recorded 115207.3732718894 Bd against limits one float away; a tolerance is folded into the bound."""
        rate = 115207.3732718894
        above, below = math.nextafter(rate, math.inf), math.nextafter(rate, 0.0)
        with _scratch() as directory:
            item = _copy(directory, rebuild=False)
            _add_requirements(
                item,
                _requirement("REQ-DIG-101", "u_tx", "tx_bit_rate_bd", ">=", rate, "Bd"),
                _requirement("REQ-DIG-102", "u_tx", "tx_bit_rate_bd", ">=", above, "Bd"),
                _requirement("REQ-DIG-103", "u_tx", "tx_bit_rate_bd", "<=", rate, "Bd"),
                _requirement("REQ-DIG-104", "u_tx", "tx_bit_rate_bd", "<=", below, "Bd"),
                _requirement("REQ-DIG-105", "u_rx", "rx_bytes_received", ">=", 3, "1"),
                _requirement("REQ-DIG-106", "u_rx", "rx_bytes_received", ">=", 3, "1", tolerance=1))
            checks = _checks(_validate(item)[0])
        self.assertEqual({n: checks[f"v4.REQ-DIG-{n}"]["verdict"] for n in range(101, 107)},
                         {101: "WARNING", 102: "FAIL", 103: "WARNING", 104: "FAIL", 105: "FAIL", 106: "WARNING"})

    def test_each_null_status_of_the_device_limit_blocks_with_its_status_and_path(self):
        from ecad_validation.contract import validate_document

        limits = {
            "UNKNOWN": None,
            "UNSPECIFIED": {"value": None, "unit": "s", "status": "UNSPECIFIED",
                            "source": {"kind": "design_annotation", "ref": TB_REF, "sha256": TB_SHA256},
                            "note": "test fixture: the top, cited by hash, is silent on the device's clock limit"},
            "NOT_AVAILABLE": {"value": None, "unit": "s", "status": "NOT_AVAILABLE", "source": FIXTURE_SOURCE,
                              "note": "test fixture: a limit that exists but cannot be used"},
        }
        for status, limit in limits.items():
            with self.subTest(status), _scratch() as directory:
                item = _copy(directory, rebuild=limit is None)
                if limit is not None:
                    _edit_json(item / "design" / "annotations.json",
                               lambda document: _device_limit(document).update(min_clock_period=limit))
                    _rebuild(item)
                receipt, results = _validate(item)
                validate_document(REPO_ROOT, "validation-receipt.schema.json", receipt)
                check = _checks(receipt)["v4.REQ-DIG-007"]
                self.assertEqual(_outcome(check), ("BLOCKED", "MISSING_REQUIRED_INPUT"))
                self.assertEqual(check["findings"][0], f"{status}: {DEVICE_LIMIT}")
                assert results is not None
                [row] = [r for r in results["results"] if r["check_id"] == "v4.REQ-DIG-007"]
                self.assertIn({"path": DEVICE_LIMIT, "status": status}, row["inputs"])

    def test_the_device_limit_passes_only_when_specified_and_real_never_when_ai_assumed(self):
        real = _requirement("REQ-DIG-107", "tb_uart_loopback", "clock_period_s", ">=", {"quantity": DEVICE_LIMIT}, "s",
                            illustrative=False)
        specified = {"value": 1e-08, "unit": "s", "status": "SPECIFIED", "source": FIXTURE_SOURCE,
                     "note": "test fixture value, no real device"}
        for label, limit, outcomes in (
            ("specified", specified, {"v4.REQ-DIG-007": ("WARNING", "WITHIN_ILLUSTRATIVE_LIMIT"),
                                      "v4.REQ-DIG-107": ("PASS", "CORNER_LIMITS_PASSED")}),
            ("assumed, met", {"value": 1e-08, "unit": "s", "status": "AI_ASSUMPTION", "source": {"kind": "ai", "ref": "fixture"}},
             {"v4.REQ-DIG-107": ("INCONCLUSIVE", "INPUT_IS_AI_ASSUMPTION")}),
            ("assumed, violated", {"value": 5e-08, "unit": "s", "status": "AI_ASSUMPTION", "source": {"kind": "ai", "ref": "fixture"}},
             {"v4.REQ-DIG-107": ("INCONCLUSIVE", "INPUT_IS_AI_ASSUMPTION")}),
        ):
            with self.subTest(label), _scratch() as directory:
                item = _copy(directory, rebuild=False)
                _edit_json(item / "design" / "annotations.json",
                           lambda document: _device_limit(document).update(min_clock_period=limit))
                _add_requirements(item, real)
                checks = _checks(_validate(item)[0])
                for check_id, outcome in outcomes.items():
                    self.assertEqual(_outcome(checks[check_id]), outcome, checks[check_id]["findings"])

    def test_without_icarus_every_case_is_blocked_and_the_receipt_holds(self):
        from ecad_validation.contract import validate_document

        receipt, results = _validate(ITEM, _no_icarus())
        validate_document(REPO_ROOT, "validation-receipt.schema.json", receipt)
        checks = _checks(receipt)
        compiled = [f"v3.REF-DIG-00{n}" for n in range(1, 9)] + [f"v4.REQ-DIG-00{n}" for n in range(1, 7)]
        for check_id in compiled:
            with self.subTest(check_id):
                self.assertEqual(_outcome(checks[check_id]), ("BLOCKED", "TOOL_NOT_INSTALLED"))
                self.assertEqual(checks[check_id]["tool_id"], "ecad-validator")
        self.assertEqual(_outcome(checks["v4.REQ-DIG-007"]), ("BLOCKED", "MISSING_REQUIRED_INPUT"))
        assert results is not None
        self.assertEqual(len(results["results"]), 15)
        self.assertEqual({r["simulator_version"] for r in results["results"]}, {None})
        self.assertNotIn("iverilog", {t["tool_id"] for t in receipt["tools"]})

    def test_a_refused_source_gives_a_receipt_and_never_reaches_icarus(self):
        from ecad_validation.contract import validate_document

        timescale = "`timescale 1ns / 1ps\n"
        copies = {
            "`include": ({TB: (timescale, timescale + '`include "/etc/hosts"\n')},
                         f"{TB_REF}:23: `include: reads another file"),
            "$fopen": ({TB: ("    reg        clk;\n", '    reg        clk;\n    wire       log = $fopen("x.txt");\n')},
                       f"{TB_REF}:34: $fopen: opens, reads or writes files"),
            "defparam": ({TB: ("\nendmodule\n", "\n    defparam u_tx.CLK_FREQ = 7;\n\nendmodule\n")},
                         f"{TB_REF}:53: defparam: changes another scope or the simulator"),
            "a hierarchical write": ({TX: ("            tx_ready <= 1'b1;\n        end else begin",
                                           "            tb_uart_loopback.u_rx.rx_error <= 1'b1;\n        end else begin")},
                                     f"{TX_REF}:54: tb_uart_loopback.u_rx: a hierarchical reference"),
        }
        for label, (edits, expected) in copies.items():
            with self.subTest(label), _scratch() as directory:
                item = _copy(directory, edits, rebuild=False, uncopied=[path for path in edits if path != TB])
                receipt, _ = _validate(item, _stand_in(refuse=True))
                self.assertEqual([p for p in Path(directory).rglob("x.txt")], [])
                validate_document(REPO_ROOT, "validation-receipt.schema.json", receipt)
                checks = _checks(receipt)
                v1 = checks["v1.digital.extraction-and-sanity"]
                self.assertEqual(_outcome(v1), ("FAIL", "SOURCE_REJECTED"))
                self.assertTrue(v1["findings"][0].startswith(expected.replace(SAMPLE, item.relative_to(REPO_ROOT).as_posix())),
                                v1["findings"][0])
                for check_id in ("v2.dataset-reproduction", "v2.digital.model-invariants",
                                 *(f"v3.REF-DIG-00{n}" for n in range(1, 9)), *(f"v4.REQ-DIG-00{n}" for n in range(1, 8))):
                    self.assertEqual(_outcome(checks[check_id]), ("BLOCKED", "DERIVATION_NOT_AVAILABLE"), check_id)

    def test_a_simulation_file_edited_without_a_rebuild_is_divergent_and_not_counted(self):
        """The committed file runs before V2 calls it divergent (SEC-2, open): what ran is not counted."""
        runs: List[str] = []
        with _scratch() as directory:
            item = _copy(directory, {SIM: ("always #10 clk", "always #11 clk")}, rebuild=False)
            receipt, _ = _validate(item, _stand_in(runs=runs))
        checks = _checks(receipt)
        reproduction = checks["v2.dataset-reproduction"]
        self.assertEqual(_outcome(reproduction), ("FAIL", "DERIVATION_DIVERGED"))
        self.assertIn(f"{SIM}: bytes differ from a fresh derivation", reproduction["findings"])
        compiled = [f"v3.REF-DIG-00{n}" for n in range(1, 9)] + [f"v4.REQ-DIG-00{n}" for n in range(1, 7)]
        for check_id in compiled:
            with self.subTest(check_id):
                self.assertEqual(_outcome(checks[check_id]), ("BLOCKED", "COMMITTED_CASE_STALE"))
                self.assertIn(f"its input {SIM} no longer reproduces", checks[check_id]["findings"][0])
        self.assertEqual(_outcome(checks["v4.REQ-DIG-007"]), ("BLOCKED", "MISSING_REQUIRED_INPUT"))
        self.assertEqual(sorted(runs), sorted(check_id.split(".", 1)[1] for check_id in compiled),
                         "the stale committed cases were run, and only then not counted")

    def test_an_rtl_copy_edited_without_a_rebuild_is_caught_at_v0_and_v2_and_not_counted(self):
        with _scratch() as directory:
            item = _copy(directory, {TX: ("// UART Transmitter", "// UART transmitter")}, rebuild=False)
            receipt, _ = _validate(item)
        checks = _checks(receipt)
        v0 = checks["v0.dataset-schemas-and-hashes"]
        self.assertEqual(_outcome(v0), ("FAIL", "DATASET_SCHEMA_OR_HASH_INVALID"))
        self.assertIn(f"{TX} is not a byte-identical copy of rtl/uart_tx.v: its sha256 is not the one copied_from "
                      "records", v0["findings"])
        self.assertIn(f"{TX}: bytes do not match the recorded hash", v0["findings"])
        reproduction = checks["v2.dataset-reproduction"]
        self.assertEqual(_outcome(reproduction), ("FAIL", "DERIVATION_DIVERGED"))
        self.assertIn(f"{SIM}: bytes differ from a fresh derivation", reproduction["findings"])
        for check_id in (*(f"v3.REF-DIG-00{n}" for n in range(1, 9)), *(f"v4.REQ-DIG-00{n}" for n in range(1, 7))):
            with self.subTest(check_id):
                self.assertEqual(_outcome(checks[check_id]), ("BLOCKED", "COMMITTED_CASE_STALE"))

    def test_a_copied_source_is_bound_to_its_origin(self):
        """REUSE-1, through check and V0: each fixture copy is rebuilt, so only the binding can fail."""
        from ecad_model.dataset import build, check

        def copied_from(item: Path, path: str) -> None:
            _edit_json(item / "source" / "provenance.json", lambda document: document["artifacts"][1].update(
                copied_from={"path": path, "sha256": TX_SHA256}))

        with _scratch() as directory, _scratch() as elsewhere:
            origin = Path(elsewhere) / "uart_tx.v"
            origin.write_bytes((REPO_ROOT / "rtl" / "uart_tx.v").read_bytes())
            origin_ref = origin.relative_to(REPO_ROOT).as_posix()
            link: Optional[Path] = Path(elsewhere) / "outside.v"
            try:
                link.symlink_to("/etc/hosts")
            except (OSError, NotImplementedError):
                link = None  # no symlinks here (Windows without the privilege): that one case is not run
            cases: List[Tuple[str, Callable[[Path], None], Callable[[Path], None], str]] = [
                ("an origin edited", lambda item: copied_from(item, origin_ref),
                 lambda item: origin.write_bytes(b"// edited after the copy\n" + origin.read_bytes()),
                 f"{TX}'s origin {origin_ref} has changed since it was cited"),
                ("a copy edited", lambda item: (item / TX).write_bytes((item / TX).read_bytes() + b"// edited\n"),
                 lambda item: None,
                 f"{TX} is not a byte-identical copy of rtl/uart_tx.v: its sha256 is not the one copied_from records"),
                ("a missing origin", lambda item: copied_from(item, "rtl/uart_gone.v"), lambda item: None,
                 f"{TX}'s origin rtl/uart_gone.v does not exist"),
                ("an origin inside the item", lambda item: copied_from(item, f"{item.relative_to(REPO_ROOT).as_posix()}/{TX}"),
                 lambda item: None,
                 f"{TX}'s origin {{here}}/{TX} lies inside the item; a copy's origin is a repository file outside it"),
            ]
            if link is not None:
                outside = link.relative_to(REPO_ROOT).as_posix()
                cases.append(("an origin outside the repository", lambda item: copied_from(item, outside),
                              lambda item: None, f"{TX}'s origin {outside} lies outside the repository; it is not read"))
            # Review CS-3: where letter case does not tell two names apart, the item in capitals is the item.
            (Path(elsewhere) / "case-probe").write_bytes(b"")
            if (Path(elsewhere) / "CASE-PROBE").exists():
                cases.append(("an origin inside the item, spelled in capitals",
                              lambda item: copied_from(item, f"{item.parent.relative_to(REPO_ROOT).as_posix()}/"
                                                             f"UART_LOOPBACK_001/{TX}"),
                              lambda item: None,
                              f"{TX}'s origin {{parent}}/UART_LOOPBACK_001/{TX} lies inside the item; a copy's origin "
                              "is a repository file outside it"))
            for number, (label, before, after, expected) in enumerate(cases):
                with self.subTest(label):
                    item = Path(directory) / str(number) / "uart_loopback_001"
                    shutil.copytree(ITEM, item)
                    before(item)
                    build(item)
                    after(item)
                    problem = expected.replace("{here}", item.relative_to(REPO_ROOT).as_posix()).replace(
                        "{parent}", item.parent.relative_to(REPO_ROOT).as_posix())
                    self.assertEqual(check(item), [problem])
                    receipt, _ = _validate(item)
                    v0 = _checks(receipt)["v0.dataset-schemas-and-hashes"]
                    self.assertEqual(_outcome(v0), ("FAIL", "DATASET_SCHEMA_OR_HASH_INVALID"))
                    self.assertIn(problem, v0["findings"])
        with _scratch() as directory:
            item = _copy(directory, rebuild=False)
            _edit_json(item / "source" / "provenance.json", lambda document: document.update(provenance_version="1.0.0"))
            with self.assertRaisesRegex(ValueError, "provenance_version: '1.1.0' was expected"):
                check(item)


class TestRegistryAndSimulator(unittest.TestCase):
    def test_the_icarus_requirement_turns_a_skip_into_a_failure(self):
        from ecad_validation.adapters.base import Capability

        from tests.unit.test_digital_icarus import require_icarus

        banner = "Icarus Verilog version 13.0 (stable) (v13_0)"
        for label, capability in (
            ("not installed", Capability(adapter="iverilog", available=False, reason="TOOL_NOT_INSTALLED")),
            ("installed, version unknown", Capability(adapter="iverilog", available=True, executable="/x/iverilog")),
            ("installed, not Icarus", Capability(adapter="iverilog", available=True, executable="/x/iverilog",
                                                 version="iverilog 13")),
        ):
            with self.subTest(label), mock.patch("ecad_validation.adapters.hdl.probe_iverilog", return_value=capability), \
                    mock.patch("ecad_validation.adapters.hdl.shutil.which", return_value="/x/vvp"):
                with mock.patch.dict(os.environ, {"ECAD_REQUIRE_HDL_TOOLS": ""}):
                    with self.assertRaises(unittest.SkipTest):
                        require_icarus()
                with mock.patch.dict(os.environ, {"ECAD_REQUIRE_HDL_TOOLS": "1"}):
                    with self.assertRaisesRegex(AssertionError, "ECAD_REQUIRE_HDL_TOOLS=1 but"):
                        require_icarus()
        installed = Capability(adapter="iverilog", available=True, executable="/x/iverilog", version=banner)
        with mock.patch("ecad_validation.adapters.hdl.probe_iverilog", return_value=installed), \
                mock.patch("ecad_validation.adapters.hdl.shutil.which", return_value="/x/vvp"), \
                mock.patch.dict(os.environ, {"ECAD_REQUIRE_HDL_TOOLS": "1"}):
            self.assertEqual(require_icarus(), installed)
        with mock.patch("ecad_validation.adapters.hdl.probe_iverilog", return_value=installed), \
                mock.patch("ecad_validation.adapters.hdl.shutil.which", return_value=None), \
                mock.patch.dict(os.environ, {"ECAD_REQUIRE_HDL_TOOLS": "1"}):
            with self.assertRaisesRegex(AssertionError, "VVP_NOT_INSTALLED"):
                require_icarus()

    def test_the_production_adapter_and_the_fixture_share_the_digital_slot(self):
        from tests.unit.test_domain_adapter import REQUIREMENT, VerilogFixtureAdapter, _digital_sample

        from ecad_model.domains import REGISTRY, adapter_for
        from ecad_model.domains.digital import DigitalAdapter

        self.assertIsInstance(REGISTRY["digital"], DigitalAdapter)
        self.assertIsInstance(adapter_for("digital"), DigitalAdapter)
        fixture = VerilogFixtureAdapter()
        self.assertIs(adapter_for("digital", {**REGISTRY, "digital": fixture}), fixture)
        with _scratch() as directory:
            item = _digital_sample(directory, [REQUIREMENT])
            requirements = json.loads((item / "requirements" / "requirements.json").read_bytes())
            requirements["requirements"][0]["scenario"] = {"name": "loopback"}
            (item / "requirements" / "requirements.json").write_bytes((json.dumps(requirements) + "\n").encode())
            receipt, _ = _validate(item, _stand_in(refuse=True))
        v1 = _checks(receipt)["v1.digital.extraction-and-sanity"]
        self.assertEqual(_outcome(v1), ("FAIL", "SOURCE_REJECTED"))
        self.assertIn("source/blinker.v:1: no `timescale 1ns / 1ps before 'module'", v1["findings"][0])


if __name__ == "__main__":
    unittest.main()
