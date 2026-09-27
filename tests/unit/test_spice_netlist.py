"""The electrical domain's SPICE netlist grammar (tools/ecad_model/spice.py).

No simulator is needed. NETLIST is the committed servo_supply_001 netlist and
DECK the deck the electrical domain writes from it, both byte for byte. Every
expected element, value and line is typed by hand from those texts and the
SPICE scale factors, never obtained by calling the code under test.
"""

from __future__ import annotations

import doctest
import hashlib
import importlib
import math
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

spice = importlib.import_module("ecad_model.spice")

NETLIST = b"""servo_supply_001: 48 V servo-drive supply input -- fuse, precharge limiter with bypass, bulk capacitor, drive load
* Self-authored for the eCAD multi-domain validation pipeline (issue #27).
* No element is a real part: every value below is a design choice of this
* testbench, not a rating, measurement or datasheet value of any component.
* The 48 V supply and the 200 W load come from the eServo-200 product sheet
* (eRobotics_CAD_Design/robot_components/product_datasheet.md). I_LOAD is
* 200 W / 48 V written to six significant figures: a constant-current
* stand-in for the drive's input. R_F1 is a fuse's cold resistance only; it
* never opens. S_BYP is an ideal switch standing for the precharge bypass.
* S_FLT is a testbench fault injector: it shorts the bus through 100 mohm.
* Sequence: hot plug 0 -> 48 V in 100 us; bypass closes at 30 ms; the load
* steps on at 40 ms; the bus is shorted at 100 ms.
V_IN n_in 0 PWL(0 0 100u 48)
R_F1 n_in n_f 20m
R_PRE n_f n_bus 10
S_BYP n_f n_bus n_byp 0 SW_BYP
V_BYP n_byp 0 PWL(0 0 30m 0 30.001m 5)
C_BULK n_bus n_esr 470u
R_ESR n_esr 0 50m
I_LOAD n_bus 0 PWL(0 0 40m 0 40.1m 4.16667)
S_FLT n_bus 0 n_fc 0 SW_FLT
V_FLT n_fc 0 PWL(0 0 100m 0 100.001m 5)
.model SW_BYP SW(RON=10m ROFF=1g VT=2.5 VH=0)
.model SW_FLT SW(RON=100m ROFF=1g VT=2.5 VH=0)
.end
"""
NETLIST_SHA256 = "838cde196936a321bdca5e41eca4a91902b4ee0a8f1fe8dcc86401a7a3ef3344"

DECK = b"""* servo_supply_001: 48 V servo-drive supply input -- fuse, precharge limiter with bypass, bulk capacitor, drive load
* written by ecad_model.domains.electrical 1.0.0 from derived/engineering_model.json; regenerate with build, never edit
V_IN n_in 0 PWL(0.0 0.0 0.0001 48.0)
R_F1 n_in n_f 0.02
R_PRE n_f n_bus 10.0
S_BYP n_f n_bus n_byp 0 SW_BYP
V_BYP n_byp 0 PWL(0.0 0.0 0.03 0.0 0.030001 5.0)
C_BULK n_bus n_esr 0.00047
R_ESR n_esr 0 0.05
I_LOAD n_bus 0 PWL(0.0 0.0 0.04 0.0 0.0401 4.16667)
S_FLT n_bus 0 n_fc 0 SW_FLT
V_FLT n_fc 0 PWL(0.0 0.0 0.1 0.0 0.100001 5.0)
.model SW_BYP SW(RON=0.01 ROFF=1000000000.0 VT=2.5 VH=0.0)
.model SW_FLT SW(RON=0.1 ROFF=1000000000.0 VT=2.5 VH=0.0)
.options noacct
.tran 1e-06 0.11 0.0 1e-06
.meas tran inrush_peak_current_a MAX par('-i(V_IN)') FROM=0.0 TO=0.03
.meas tran inrush_i2t_a2s INTEG par('i(V_IN)*i(V_IN)') FROM=0.0 TO=0.03
.meas tran bus_charge_time_s WHEN v(n_bus)=43.2 RISE=1
.meas tran bus_voltage_at_bypass_v FIND v(n_bus) AT=0.03
.meas tran bus_peak_voltage_v MAX v(n_bus) FROM=0.0 TO=0.1
.meas tran steady_bus_voltage_v FIND v(n_bus) AT=0.1
.meas tran steady_input_current_a FIND par('-i(V_IN)') AT=0.1
.meas tran steady_fuse_power_w FIND par('(v(n_in)-v(n_f))*(-i(V_IN))') AT=0.1
.meas tran fault_input_current_a FIND par('-i(V_IN)') AT=0.11
.end
"""
DECK_SHA256 = "2840fc040b30a626891a347bb447a242f81ce97cd23aa415a6e32c7ef4451d30"
DECK_LINES = DECK.decode("ascii").split("\n")[:-1]

TITLE = ("servo_supply_001: 48 V servo-drive supply input -- fuse, precharge limiter with bypass, "
         "bulk capacitor, drive load")
SWITCH_VALUES = {"threshold_voltage": 2.5, "hysteresis_voltage": 0.0, "off_resistance": 1e9}
# (designator, element, terminals, values in SI, model, netlist line), read off NETLIST by hand:
# 100u = 1e-4 s, 20m = 0.02 ohm, 30.001m = 0.030001 s, 470u = 4.7e-4 F, 1g = 1e9 ohm.
EXPECTED = [
    ("V_IN", "voltage_source", {"p": "n_in", "n": "0"},
     {"waveform_time": [0.0, 0.0001], "waveform_voltage": [0.0, 48.0]}, None, 13),
    ("R_F1", "resistor", {"p": "n_in", "n": "n_f"}, {"resistance": 0.02}, None, 14),
    ("R_PRE", "resistor", {"p": "n_f", "n": "n_bus"}, {"resistance": 10.0}, None, 15),
    ("S_BYP", "voltage_controlled_switch", {"p": "n_f", "n": "n_bus", "cp": "n_byp", "cn": "0"},
     {"on_resistance": 0.01, **SWITCH_VALUES}, "SW_BYP", 16),
    ("V_BYP", "voltage_source", {"p": "n_byp", "n": "0"},
     {"waveform_time": [0.0, 0.03, 0.030001], "waveform_voltage": [0.0, 0.0, 5.0]}, None, 17),
    ("C_BULK", "capacitor", {"p": "n_bus", "n": "n_esr"}, {"capacitance": 0.00047}, None, 18),
    ("R_ESR", "resistor", {"p": "n_esr", "n": "0"}, {"resistance": 0.05}, None, 19),
    ("I_LOAD", "current_source", {"p": "n_bus", "n": "0"},
     {"waveform_time": [0.0, 0.04, 0.0401], "waveform_current": [0.0, 0.0, 4.16667]}, None, 20),
    ("S_FLT", "voltage_controlled_switch", {"p": "n_bus", "n": "0", "cp": "n_fc", "cn": "0"},
     {"on_resistance": 0.1, **SWITCH_VALUES}, "SW_FLT", 21),
    ("V_FLT", "voltage_source", {"p": "n_fc", "n": "0"},
     {"waveform_time": [0.0, 0.1, 0.100001], "waveform_voltage": [0.0, 0.0, 5.0]}, None, 22),
]
MODELS = {"SW_BYP": {"RON": 0.01, "ROFF": 1e9, "VT": 2.5, "VH": 0.0},
          "SW_FLT": {"RON": 0.1, "ROFF": 1e9, "VT": 2.5, "VH": 0.0}}

GOOD = ("V1 a 0 PWL(0 0 1m 5)", "R1 a b 1k", "R2 b 0 1k")
SW1 = ".model SW1 SW(RON=1 ROFF=1meg VT=2.5 VH=0.1)"
SWITCHED = ("V1 a 0 PWL(0 0 1m 5)", "R1 a b 1k", "S1 b 0 c 0 SW1", "V2 c 0 PWL(0 0 1m 5)", SW1)


def netlist(*cards: str, title: str = "divider", end: str = ".end") -> bytes:
    """A netlist of the given cards: the title is line 1, so the first card is line 2."""
    return ("\n".join((title, *cards, end)) + "\n").encode("ascii")


def deck(lines) -> bytes:
    return ("\n".join(lines) + "\n").encode("ascii")


def described(elements):
    return [(e.designator, e.element, e.terminals, e.values, e.model) for e in elements]


class TestNetlistGrammar(unittest.TestCase):
    def refused(self, data: bytes, expected: str, reader=None) -> None:
        with self.assertRaises(spice.NetlistRefused) as caught:
            (reader or spice.parse_netlist)(data, "x.cir")
        message = str(caught.exception)
        self.assertEqual(caught.exception.kind, "rejected")
        self.assertTrue(message.startswith(expected), f"{message!r} does not start with {expected!r}")

    def refused_value(self, token: str) -> None:
        with self.assertRaises(spice.NetlistRefused) as caught:
            spice.parse_value(token, "x.cir:9")
        self.assertTrue(str(caught.exception).startswith(f"x.cir:9: {token!r} is not a"), str(caught.exception))

    def test_the_committed_netlist_parses_to_its_hand_read_elements(self):
        self.assertEqual(hashlib.sha256(NETLIST).hexdigest(), NETLIST_SHA256)
        self.assertEqual(len(NETLIST), 1300)
        parsed = spice.parse_netlist(NETLIST, "servo_supply_001.cir")
        self.assertEqual(parsed.title, TITLE)
        self.assertEqual(len(parsed.elements), 10)
        self.assertEqual([(e.designator, e.element, e.terminals, e.values, e.model, e.line) for e in parsed.elements],
                         EXPECTED)
        self.assertEqual(parsed.models, MODELS)
        for element in parsed.elements:
            for value in element.values.values():
                for number in value if isinstance(value, list) else [value]:
                    self.assertIs(type(number), float, element.designator)

    def test_scale_suffixes_are_read_exactly(self):
        read = {"1t": 1e12, "1g": 1e9, "1meg": 1e6, "1k": 1e3, "1m": 1e-3, "1u": 1e-6, "1n": 1e-9, "1p": 1e-12,
                "1e3": 1000.0, "2.5E-3": 0.0025, "1e+2": 100.0, "-4.5e1": -45.0, ".5": 0.5, "5.": 5.0, "+5": 5.0,
                "10": 10.0, "20m": 0.02, "100u": 0.0001, "40.1m": 0.0401, "100.001m": 0.100001,
                "4.16667": 4.16667, "0": 0.0}
        for token, value in read.items():
            with self.subTest(token=token):
                self.assertEqual(spice.parse_value(token, "x.cir:9"), value)
        self.assertEqual(spice.parse_value("470u", "x.cir:9"), float("470e-6"))
        # One decimal conversion, not mantissa times a power of ten: the
        # product misses by one unit in the last place here.
        self.assertNotEqual(30.001 * 1e-3, float("30.001e-3"))
        self.assertEqual(spice.parse_value("30.001m", "x.cir:9"), float("30.001e-3"))
        self.assertEqual(math.copysign(1.0, spice.parse_value("-0", "x.cir:9")), 1.0)

    def test_values_spice_would_misread_are_refused(self):
        for token in ("1M", "1MEG", "1K", "1F", "1f", "10uF", "470uF", "2kohm", "1ms", "1mil", "1e3k", "nan", "inf",
                      "-inf", "Infinity", "1_0", "470µ", "", ".", "1e", "e3", "0x1f", "1.2.3", "1 k"):
            with self.subTest(token=token):
                self.refused_value(token)
        with self.assertRaises(spice.NetlistRefused) as caught:
            spice.parse_value("1e999", "x.cir:9")
        self.assertEqual(str(caught.exception), "x.cir:9: '1e999' is not a finite number")
        self.refused(netlist("V1 a 0 PWL(0 0 1m 5)", "R1 a b 1M", "R2 b 0 1k"), "x.cir:3: '1M' is not a number")
        self.refused(netlist("V1 a 0 PWL(0 0 1m 5)", "R1 a 0 1k", "C1 a 0 470uF"), "x.cir:4: '470uF' is not a number")

    def test_directives_that_read_files_run_commands_or_belong_to_the_adapter_are_refused(self):
        classes = {
            "reads another file": (".include", ".inc", ".lib", ".endl"),
            "runs commands, including shell": (".control", ".endc"),
            "expressions": (".param", ".func", ".csparam"),
            "subcircuits: PLANNED": (".subckt", ".ends"),
            "changes simulator state": (".options", ".option", ".temp", ".ic", ".nodeset", ".global"),
            "the analysis and measurements are written by the adapter": (
                ".tran", ".ac", ".dc", ".op", ".noise", ".tf", ".sens", ".pz", ".four", ".meas", ".measure",
                ".print", ".plot", ".save", ".probe"),
        }
        self.assertEqual(sum(len(directives) for directives in classes.values()), 32)
        spice.parse_netlist(netlist(*GOOD), "x.cir")
        for reason, directives in classes.items():
            for directive in directives:
                with self.subTest(directive=directive):
                    self.refused(netlist(*GOOD, f"{directive} x"), f"x.cir:5: {directive}: {reason}")
        self.refused(netlist(*GOOD, ".INCLUDE other.cir"), "x.cir:5: .include: reads another file")
        self.refused(netlist(*GOOD, ".Control"), "x.cir:5: .control: runs commands, including shell")
        self.refused(netlist(*GOOD, ".title x"), "x.cir:5: .title: an unknown directive")
        for line in ("*#shell touch x", "*# echo x", "   *#echo x", "\t*#echo x"):
            with self.subTest(line=line):
                self.refused(netlist(*GOOD, line), "x.cir:5: a *# comment, which ngspice runs as a command, including shell")
        spice.parse_netlist(netlist(*GOOD, "* # a comment with a space is inert", "*", "  * indented"), "x.cir")

    def test_continuations_and_characters_spice_would_reinterpret_are_refused(self):
        continued = "x.cir:4: a '+' continuation, which joins this line to the one before it"
        self.refused(netlist("V1 a 0 PWL(0 0 1m 5)", "R1 a b 1k", "+ 5", "R2 b 0 1k"), continued)
        self.refused(netlist("V1 a 0 PWL(0 0 1m 5)", "R1 a b 1k", "  +5", "R2 b 0 1k"), continued)
        for character in (";", "$", "'", '"', "{", "}", "`", "!", "\\"):
            with self.subTest(character=character):
                self.refused(netlist("V1 a 0 PWL(0 0 1m 5)", f"R1 a b 1k {character}x", "R2 b 0 1k"),
                             f"x.cir:3: character {character!r}: ngspice reads it as")
        self.refused(netlist(*GOOD, SW1.replace("VH=0.1", "VH={0.1}")), "x.cir:5: character '{'")
        # A comment may say anything: ngspice never reads it.
        spice.parse_netlist(netlist(*GOOD, "* the drive's input; $5 {not} `read` !"), "x.cir")

    def test_element_letters_outside_r_c_v_i_s_are_refused(self):
        reasons = {"L": "an inductor: PLANNED", "X": "a subcircuit instance: subcircuits are PLANNED"}
        reasons.update(dict.fromkeys("BEFGH", "a behavioural or controlled source, which evaluates expressions"))
        reasons.update(dict.fromkeys("AN", "a code model or OSDI device, which loads a library"))
        reasons.update(dict.fromkeys("DQMJKTUOWYZP", "a device this domain does not model"))
        self.assertEqual(sorted([*reasons, *"CIRSV"]), list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
        for letter, reason in reasons.items():
            with self.subTest(letter=letter):
                self.refused(netlist(*GOOD, f"{letter}1 a b 1k"), f"x.cir:5: {letter}1: {reason}")
        self.refused(netlist(*GOOD, "l1 a b 1u"), "x.cir:5: l1: an inductor: PLANNED")
        for card, designator in (("r1 a b 1k", "r1"), ("Rx a b 1k", "Rx"), ("R a b 1k", "R"),
                                 ("v1 a 0 PWL(0 0 1m 5)", "v1"), ("s1 b 0 c 0 SW1", "s1")):
            with self.subTest(card=card):
                self.refused(netlist(*GOOD, card), f"x.cir:5: {designator!r} is not a designator")
        self.refused(netlist(*GOOD, "1R a b 1k"), "x.cir:5: '1R' is not an element, a comment or a directive")
        self.refused(netlist(*GOOD, "R3 a b 1k tc1=0"), "x.cir:5: R3: a resistor is R<id> NODE NODE VALUE, exactly")
        self.refused(netlist(*GOOD, "C3 a 0 1u ic=0"), "x.cir:5: C3: a capacitor is C<id> NODE NODE VALUE, exactly")

    def test_sources_are_piecewise_linear_with_increasing_times(self):
        only_pwl = "source: only PWL(t0 v0 t1 v1 ...) sources are read; other source types are PLANNED"
        for spec, kind in (("DC 5", "DC"), ("5", "a bare (DC) value"), ("PULSE(0 5 0 1n 1n 1m 2m)", "PULSE"),
                           ("SIN(0 1 1k)", "SIN"), ("EXP(0 1 0 1m 2m 1m)", "EXP"), ("AC 1", "AC"),
                           ("PWL(0 0 1m 5) r=0", "PWL")):
            with self.subTest(spec=spec):
                self.refused(netlist(f"V1 a 0 {spec}", "R1 a b 1k", "R2 b 0 1k"), f"x.cir:2: V1: {kind} {only_pwl}")
        self.refused(netlist(*GOOD, "I1 b 0 DC 1"), f"x.cir:5: I1: DC {only_pwl}")
        for spec, reason in (("PWL(0 0 1m)", "a PWL is time-value pairs, at least two of them; found 3 numbers"),
                             ("PWL(0 0)", "a PWL is time-value pairs, at least two of them; found 2 numbers"),
                             ("PWL()", "a PWL is time-value pairs, at least two of them; found 0 numbers"),
                             ("PWL(1m 0 2m 5)", "a PWL starts at time 0, not 1m"),
                             ("PWL(0 0 1m 5 1m 6)", "PWL times must strictly increase"),
                             ("PWL(0 0 2m 5 1m 6)", "PWL times must strictly increase")):
            with self.subTest(spec=spec):
                self.refused(netlist(f"V1 a 0 {spec}", "R1 a b 1k", "R2 b 0 1k"), f"x.cir:2: V1: {reason}")
        parsed = spice.parse_netlist(netlist("V1 a 0 pwl (0 0 1m 5 2m 5)", "R1 a b 1k", "R2 b 0 1k",
                                             "I1 b 0 PWL(0 0 1u 2m)"), "x.cir")
        self.assertEqual(parsed.elements[0].values, {"waveform_time": [0.0, 0.001, 0.002],
                                                     "waveform_voltage": [0.0, 5.0, 5.0]})
        self.assertEqual(parsed.elements[3].values, {"waveform_time": [0.0, 1e-06], "waveform_current": [0.0, 0.002]})

    def test_switch_models_state_every_parameter_once(self):
        parsed = spice.parse_netlist(netlist(*SWITCHED), "x.cir")
        self.assertEqual(parsed.elements[2].values, {"on_resistance": 1.0, "off_resistance": 1e6,
                                                     "threshold_voltage": 2.5, "hysteresis_voltage": 0.1})
        self.assertEqual(parsed.elements[2].model, "SW1")
        any_case = spice.parse_netlist(netlist(*SWITCHED[:4], ".MODEL SW1 sw(vh=0.1 vt=2.5 roff=1meg ron=1)"), "x.cir")
        self.assertEqual(any_case.elements[2].values, parsed.elements[2].values)
        self.assertEqual(any_case.models, {"SW1": {"RON": 1.0, "ROFF": 1e6, "VT": 2.5, "VH": 0.1}})
        for model, reason in (
                (".model SW1 SW(RON=1 ROFF=1meg VT=2.5)", "model SW1: VH missing; no SPICE default fills a value nobody chose"),
                (".model SW1 SW(RON=1)", "model SW1: ROFF VT VH missing"),
                (".model SW1 SW(RON=1 ROFF=1meg VT=2.5 VH=0.1 TD=1)", "model SW1: 'TD=1' is not one of RON= ROFF= VT= VH="),
                (".model SW1 SW(RON=1 ROFF=1meg VT=2.5 VH)", "model SW1: 'VH' is not one of RON= ROFF= VT= VH="),
                (".model SW1 SW(RON=1 RON=2 ROFF=1meg VT=2.5 VH=0.1)", "model SW1: RON is given twice"),
                (".model SW1 CSW(IT=1 IH=0 RON=1 ROFF=1meg)", "model SW1: type CSW: only SW (voltage-controlled switch)"),
                (".model SW1 SW RON=1 ROFF=1meg VT=2.5 VH=0.1", "a .model card is .model NAME SW(RON=v ROFF=v VT=v VH=v)"),
                (".model SW1 SW(RON=1 ROFF=1M VT=2.5 VH=0.1)", "'1M' is not a number")):
            with self.subTest(model=model):
                self.refused(netlist(*SWITCHED[:4], model), f"x.cir:6: {reason}")
        self.refused(netlist(*SWITCHED[:2], "S1 b 0 c 0 SW2", *SWITCHED[3:]),
                     "x.cir:4: S1 names model SW2, which no .model card declares")
        self.refused(netlist(*SWITCHED[:4], "S2 b 0 c 0 SW1", SW1),
                     "x.cir:6: S2 names model SW1, which S1 already uses; each switch has its own .model")
        self.refused(netlist(*SWITCHED, SW1.replace("SW1", "SW9")), "x.cir:7: model SW9 is used by no switch")
        self.refused(netlist(*SWITCHED[:2], "S1 b 0 c 0 SW1 OFF", *SWITCHED[3:]),
                     "x.cir:4: S1: a switch is S<id> NODE NODE NODE NODE MODEL, exactly")
        self.refused(netlist(*SWITCHED[:2], "S1 b 0 c 0 sw1", *SWITCHED[3:]), "x.cir:4: S1: 'sw1' is not a model name")

    def test_names_are_canonical_unique_and_never_ground_aliases_or_par_nodes(self):
        self.refused(netlist(*GOOD, "R1 a 0 1k"), "x.cir:5: R1 is already declared on line 3")
        self.refused(netlist(*SWITCHED, SW1), "x.cir:7: model SW1 is already declared on line 6")
        for node, reason in (("A", "'A' is not a node name: 0, or a lower-case letter and up to 31 of a-z 0-9 _"),
                             ("gnd", "'gnd' is ground to ngspice; write 0"),
                             ("pa_0", "'pa_0' is a name ngspice's par() gives its own nodes"),
                             ("pa_12", "'pa_12' is a name ngspice's par() gives its own nodes"),
                             ("00", "'00' is not a node name"),
                             ("_a", "'_a' is not a node name"),
                             ("n" + "x" * 32, f"'n{'x' * 32}' is not a node name")):
            with self.subTest(node=node):
                self.refused(netlist("V1 a 0 PWL(0 0 1m 5)", "R1 a b 1k", f"R2 b {node} 1k"), f"x.cir:4: R2: {reason}")
        self.refused(netlist(*GOOD, f"R{'X' * 32} a b 1k"), f"x.cir:5: 'R{'X' * 32}' is not a designator")
        self.refused(netlist(*SWITCHED[:2], f"S1 b 0 c 0 S{'W' * 32}", *SWITCHED[3:]),
                     f"x.cir:4: S1: 'S{'W' * 32}' is not a model name")
        # The exclusions are exact: neighbouring names are ordinary nodes, and
        # 32 characters is the longest name.
        for node in ("pa_x", "pa_", "gnd1", "ground", "n" + "x" * 31):
            with self.subTest(accepted=node):
                parsed = spice.parse_netlist(netlist("V1 a 0 PWL(0 0 1m 5)", f"R1 a {node} 1k", f"R2 {node} 0 1k"), "x.cir")
                self.assertEqual(parsed.elements[2].terminals, {"p": node, "n": "0"})
        longest = "R" + "X" * 31
        self.assertEqual(spice.parse_netlist(netlist(*GOOD, f"{longest} a b 1k"), "x.cir").elements[3].designator, longest)

    def test_every_node_is_connected_twice_and_reaches_ground(self):
        self.refused(netlist(*GOOD, "R3 b c 1k"), "x.cir:5: node c has one terminal (R3.n): nothing else connects to it")
        singular = "has no DC path to ground: the operating point is singular"
        self.refused(netlist("V1 a 0 PWL(0 0 1m 5)", "R1 a 0 1k", "C1 a b 1u", "C2 b 0 1u"), f"x.cir:4: node b {singular}")
        self.refused(netlist("V1 a 0 PWL(0 0 1m 5)", "R1 a 0 1k", "I1 a b PWL(0 0 1m 1)", "C1 b 0 1u"),
                     f"x.cir:4: node b {singular}")
        self.refused(netlist("V1 a 0 PWL(0 0 1m 5)", "R1 a 0 1k", "S1 a 0 c d SW1", "C1 c d 1u", SW1),
                     f"x.cir:4: node c {singular}")
        self.refused(netlist("V1 a b PWL(0 0 1m 5)", "R1 a b 1k"), "x.cir: no element connects to ground, node 0")
        self.refused(netlist(*GOOD, "R3 b b 1k"), "x.cir:5: R3: both terminals are on node b")
        self.refused(netlist(*SWITCHED[:2], "S1 b b c 0 SW1", *SWITCHED[3:]), "x.cir:4: S1: both terminals are on node b")
        # A switch's p-n pair conducts (its off resistance is finite), and
        # ground needs only one terminal.
        spice.parse_netlist(netlist("V1 a 0 PWL(0 0 1m 5)", "R1 a 0 1k", "C1 a x 1u", "S1 x 0 a 0 SW1", SW1), "x.cir")
        spice.parse_netlist(netlist("V1 a 0 PWL(0 0 1m 5)", "R1 a b 1k", "R2 b a 1k"), "x.cir")

    def test_the_title_line_is_never_a_card(self):
        card = "x.cir:1: line 1 is the title, so SPICE never reads this element card"
        for title in ("R1 a 0 1k", "r1 A 0 1K", "C9 a 0 10uF", "V9 a 0 PWL(0 0 1m 5)", "v9 a 0 dc 5", "I9 a 0 1",
                      "V9 a 0 SIN(0 1 1k)", "S9 b 0 c 0 SW1", "s9 b 0 c 0 sw1 off"):
            with self.subTest(title=title):
                self.refused(netlist(*GOOD, title=title), card)
        self.refused(netlist(*GOOD, title=".include other.cir"),
                     "x.cir:1: line 1 is the title, so SPICE never reads this '.include' card")
        self.refused(netlist(*GOOD, title="+ 5"), "x.cir:1: line 1 is the title, so SPICE never reads this '+' card")
        for title in ("", "   \t"):
            with self.subTest(title=title):
                self.refused(netlist(*GOOD, title=title), "x.cir:1: line 1 is the title, and it is blank")
        for title in ("*ng_script", "*NG_SCRIPT_WITH_PARAMS x"):
            with self.subTest(title=title):
                self.refused(netlist(*GOOD, title=title),
                             "x.cir:1: line 1 is the title, and ngspice runs a file whose title starts with *ng_script")
        for title in (TITLE, "Inrush test of a 48 V bus", "RC filter", "Vin to the bus: 48 V", "* ng_script",
                      "* a comment in the title's place; still a title"):
            with self.subTest(accepted=title):
                self.assertEqual(spice.parse_netlist(netlist(*GOOD, title=title), "x.cir").title, title)

    def test_the_file_ends_at_dot_end(self):
        self.refused(netlist(*GOOD, end=""), "x.cir: no .end line; ngspice accepts a netlist without one")
        self.refused(netlist(*GOOD, end="* the end"), "x.cir: no .end line")
        after = "x.cir:6: text after .end, which ngspice still reads"
        for line in ("R3 b 0 1k", "* a comment", "*#echo x", ".end"):
            with self.subTest(line=line):
                self.refused(netlist(*GOOD, end=f".end\n{line}"), after)
        self.refused(netlist(*GOOD, end=".end now"), "x.cir:5: nothing follows .end on its line")
        for end in (".end\n\n   \n\t", ".END", ".End", "  .end  "):
            with self.subTest(end=end):
                self.assertEqual(len(spice.parse_netlist(netlist(*GOOD, end=end), "x.cir").elements), 3)
        self.assertEqual(len(spice.parse_netlist(netlist(*GOOD)[:-1], "x.cir").elements), 3)

    def test_input_bounds_and_encoding_are_exact(self):
        self.assertEqual((spice.MAX_NETLIST_BYTES, spice.MAX_LINE_CHARS, spice.MAX_ELEMENTS, spice.MAX_PWL_POINTS),
                         (1048576, 1024, 1000, 16))
        head, tail = ("divider\n" + "\n".join(GOOD) + "\n").encode("ascii"), b".end\n"
        room = 1048576 - len(head) - len(tail)
        filler = b"*" + b"x" * 998 + b"\n"
        rest = room % len(filler)
        at_limit = head + filler * (room // len(filler)) + (b"*" * (rest - 1) + b"\n" if rest else b"") + tail
        self.assertEqual(len(at_limit), 1048576)
        self.assertEqual(len(spice.parse_netlist(at_limit, "x.cir").elements), 3)
        self.refused(at_limit.replace(b"*x", b"*xx", 1), "x.cir: 1048577 bytes exceeds the 1048576-byte netlist limit")

        spice.parse_netlist(netlist(*GOOD, "*" + "x" * 1023), "x.cir")
        self.refused(netlist(*GOOD, "*" + "x" * 1024), "x.cir:5: 1025 characters exceeds the 1024-character line limit")

        resistors = [f"R{index} a 0 1k" for index in range(1, 1000)]
        self.assertEqual(len(spice.parse_netlist(netlist("V1 a 0 PWL(0 0 1m 5)", *resistors), "x.cir").elements), 1000)
        self.refused(netlist("V1 a 0 PWL(0 0 1m 5)", *resistors, "R1000 a 0 1k"), "x.cir:1002: more than 1000 elements")

        sixteen = " ".join(f"{time}m {time}" for time in range(16))
        parsed = spice.parse_netlist(netlist(f"V1 a 0 PWL({sixteen})", "R1 a 0 1k"), "x.cir")
        self.assertEqual(len(parsed.elements[0].values["waveform_time"]), 16)
        self.refused(netlist(f"V1 a 0 PWL({sixteen} 16m 16)", "R1 a 0 1k"), "x.cir:2: V1: more than 16 PWL points")

        self.refused(b"", "x.cir: is empty")
        self.refused(b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"0" * 64 + b"\nsize 1300\n",
                     "x.cir: is a Git LFS pointer, not a netlist")
        self.refused(netlist(*GOOD).replace(b"R1 a b 1k", b"R1 a b 1k\x00"), "x.cir:3: a NUL byte (0x00)")
        self.refused(netlist(*GOOD).replace(b"\n", b"\r\n"), "x.cir:1: a carriage return: lines end in LF only (0x0d)")
        self.refused(netlist(*GOOD).replace(b".end", "* 470 µF\n.end".encode("utf-8")),
                     "x.cir:5: a byte outside printable ASCII, tab and LF (0xc2)")
        for byte in (b"\x0b", b"\x0c", b"\x1b", b"\x7f", b"\xff"):
            with self.subTest(byte=byte):
                self.refused(netlist(*GOOD).replace(b"R2", byte + b"R2"), "x.cir:4: a byte outside printable ASCII")
        tabbed = spice.parse_netlist(netlist("V1\ta\t0\tPWL(0\t0 1m 5)", "R1\ta b\t1k", "R2 b 0 1k"), "x.cir")
        self.assertEqual(tabbed.elements[1].terminals, {"p": "a", "n": "b"})

    def test_the_deck_reader_accepts_only_the_adapters_own_lines(self):
        self.assertEqual(hashlib.sha256(DECK).hexdigest(), DECK_SHA256)
        circuit, section = spice.read_deck(DECK, "deck.cir")
        self.assertEqual(circuit.title, "* " + TITLE)
        self.assertEqual(described(circuit.elements), [entry[:5] for entry in EXPECTED])
        self.assertEqual([element.line for element in circuit.elements], list(range(3, 13)))
        self.assertEqual(circuit.models, MODELS)
        self.assertEqual(section, DECK_LINES[14:25])
        self.assertEqual(section[:2], [".options noacct", ".tran 1e-06 0.11 0.0 1e-06"])

        def insert(index, line):
            return deck(DECK_LINES[:index] + [line] + DECK_LINES[index:])

        def replace(index, line):
            return deck(DECK_LINES[:index] + [line] + DECK_LINES[index + 1:])

        read = spice.read_deck
        self.refused(insert(16, ".control"), "x.cir:17: not a .meas line the adapter writes, so not part of its section",
                     read)
        self.refused(insert(25, "shell touch x"), "x.cir:26: not a .meas line the adapter writes", read)
        self.refused(insert(14, ".control"), "x.cir:15: .control: runs commands, including shell", read)
        self.refused(insert(14, "*#shell touch x"), "x.cir:15: a *# comment, which ngspice runs as a command", read)
        self.refused(insert(14, ".meas tran extra FIND v(n_bus) AT=0.05"),
                     "x.cir:15: .meas: the analysis and measurements are written by the adapter", read)
        self.refused(insert(25, DECK_LINES[20]), "x.cir:26: measurement bus_peak_voltage_v is already declared on "
                                                 "line 21, and ngspice would print both", read)
        self.refused(insert(16, ".tran 1e-06 0.2 0.0 1e-06"), "x.cir:17: a second .tran; the deck runs one analysis", read)
        self.refused(insert(25, ".tran 1e-06 0.2 0.0 1e-06"), "x.cir:26: a second .tran", read)
        self.refused(replace(15, ".tran 1e-06 0.11 0.0"),
                     "x.cir:16: the line after .options noacct is the adapter's .tran TSTEP TSTOP TSTART TMAX", read)
        self.refused(replace(15, ".tran 1e-06 0.11 0.0 1M"), "x.cir:16: '1M' is not a number", read)
        self.refused(replace(19, ".meas tran bus_voltage_at_bypass_v FIND v(n_bus) AT=30M"),
                     "x.cir:20: '30M' is not a number", read)
        for line in (DECK_LINES[20] + " ; shell x", ".meas op bus_peak_voltage_v MAX v(n_bus)",
                     ".meas tran bus_peak_voltage_v MAX par('1';'2') FROM=0.0 TO=0.1",
                     ".meas tran bus_peak_voltage_v MAX v(n_bus) FROM=0.0"):
            with self.subTest(line=line):
                self.refused(replace(20, line), "x.cir:21: not a .meas line the adapter writes", read)
        self.refused(deck(DECK_LINES[:14] + DECK_LINES[15:]), "x.cir: no '.options noacct' line", read)
        self.refused(replace(14, ".options noacct "), "x.cir: no '.options noacct' line", read)
        self.refused(insert(14, ".end"), "x.cir: .end comes before the adapter's section", read)
        self.refused(insert(25, ".end"), "x.cir:26: .end is the deck's last line, and ngspice reads past an earlier one",
                     read)
        self.refused(DECK + b"\n", "x.cir:27: a deck ends with its .end line, and nothing follows it", read)
        self.refused(deck(DECK_LINES[:16] + [".end"]), "x.cir:17: the deck's section is .options noacct, one .tran, "
                                                        "at least one .meas, and .end", read)
        self.refused(deck(DECK_LINES[14:]), "x.cir:1: line 1 is the title, so SPICE never reads this '.options' card",
                     read)
        self.refused(replace(4, "R_PRE n_f n_bus 1M"), "x.cir:5: '1M' is not a number", read)
        self.refused(DECK.replace(b"\n", b"\r\n"), "x.cir:1: a carriage return", read)
        # A well-formed line the model does not call for is the caller's to
        # find: the reader returns it with the rest of the section.
        extra = ".meas tran extra_v FIND v(n_bus) AT=0.05"
        self.assertEqual(spice.read_deck(insert(25, extra), "x.cir")[1], DECK_LINES[14:25] + [extra])

    def test_the_writer_reproduces_the_committed_deck_from_si_values(self):
        element_lines = DECK_LINES[2:14]
        self.assertEqual(spice.write_elements(spice.parse_netlist(NETLIST, "servo_supply_001.cir")), element_lines)
        self.assertEqual(spice.write_elements(spice.read_deck(DECK, "deck.cir")[0]), element_lines)

        # A source line near the longest any accepted netlist can produce
        # still reads back: 32-character names and MAX_PWL_POINTS points of
        # numbers with 16 or 17 significant digits.
        designator, p, n = "V" + "X" * 31, "a" + "x" * 31, "b" + "x" * 31
        times = [0.0] + [float(f"{k}.2345678901234567e+200") for k in range(1, 10)] + [
            float(f"9.{k}345678901234567e+201") for k in range(1, 7)]
        levels = [-float(f"{k + 1}.2345678901234567e-300") for k in range(16)]
        source = spice.Element(designator, "voltage_source", {"p": p, "n": n},
                               {"waveform_time": times, "waveform_voltage": levels}, None, 0)
        written = spice.write_elements(spice.Netlist("", (source,), {}))
        self.assertGreater(len(written[0]), 800)
        worst = deck(["* worst case", *written, f"R1 {p} 0 1.0", f"R2 {n} 0 1.0", ".options noacct",
                      ".tran 1e-06 1e-05 0.0 1e-06", f".meas tran v_a FIND v({p}) AT=1e-06", ".end"])
        self.assertEqual(spice.read_deck(worst, "worst.cir")[0].elements[0].values,
                         {"waveform_time": times, "waveform_voltage": levels})

        def element(designator="R1", kind="resistor", terminals=None, values=None, model=None):
            return spice.Element(designator, kind, terminals or {"p": "a", "n": "0"},
                                 {"resistance": 1.0} if values is None else values, model, 0)

        for broken, reason in (
                (element(terminals={"p": "gnd", "n": "0"}), "'gnd' is ground"),
                (element(terminals={"p": "a;x", "n": "0"}), "is not a node name"),
                (element(terminals={"p": "a"}), "terminals ['p'], expected ['p', 'n']"),
                (element(designator="R1;x"), "'R1;x' as a resistor: not an element this module writes"),
                (element(designator="C1"), "'C1' as a resistor: not an element this module writes"),
                (element(kind="inductor", designator="L1"), "'L1' as a inductor: not an element this module writes"),
                (element(values={"resistance": float("nan")}), "nan is not a finite number"),
                (element(values={"resistance": float("inf")}), "inf is not a finite number"),
                (element(values={"resistance": True}), "True is not a finite number"),
                (element(values={"resistance": "1.0"}), "'1.0' is not a finite number"),
                (element(values={}), "R1: has no resistance"),
                (element("V1", "voltage_source", values={"waveform_time": [0.0, 1.0], "waveform_voltage": [0.0]}),
                 "V1: 2 PWL times but 1 values"),
                (element("S1", "voltage_controlled_switch", {"p": "a", "n": "0", "cp": "c", "cn": "0"},
                         {"on_resistance": 1.0}, "SW 1"), "S1: 'SW 1' is not a model name"),
                (element("S1", "voltage_controlled_switch", {"p": "a", "n": "0", "cp": "c", "cn": "0"},
                         {"on_resistance": 1.0}, "SW1"), "S1: has no off_resistance")):
            with self.subTest(reason=reason):
                with self.assertRaises(ValueError) as caught:
                    spice.write_elements(spice.Netlist("", (broken,), {}))
                self.assertIn(reason, str(caught.exception))


class TestDocumentationExamples(unittest.TestCase):
    """QUALITY.md: every public function's example must be one that was actually run."""

    def test_examples_in_the_spice_module(self):
        result = doctest.testmod(spice, optionflags=doctest.ELLIPSIS)
        self.assertGreater(result.attempted, 0)
        self.assertEqual(result.failed, 0)


if __name__ == "__main__":
    unittest.main()
