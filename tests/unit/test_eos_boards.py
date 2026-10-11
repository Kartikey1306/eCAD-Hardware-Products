"""tools/eos_boards: the board generator's pure-Python parts, and the exactness of the copper
reused from Raspberry Pi's RP2350A minimal design on the built EoS Learn RP2350.

None of this needs KiCad: symbols come from a small library written here, and the built board
is read as text. The exactness check compares in integer nanometres (KiCad's own unit), so a
1 nm move of any reused footprint, track end, via or zone corner fails it.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from eos_boards import build, design, schematic  # noqa: E402
from eos_boards.design import NC, Board, Part  # noqa: E402
from eos_boards.kicad_lib import Library  # noqa: E402
from eos_boards.reference import extract_rpi_minimal as extract  # noqa: E402
from eos_boards.sexpr import Sym, dumps, find, find_all, loads  # noqa: E402

BOARD_DIR = REPO_ROOT / "boards" / "eos" / "eos-learn-rp2350"
PCB = BOARD_DIR / "hardware" / "eos-learn-rp2350.kicad_pcb"
CORE = REPO_ROOT / "tools" / "eos_boards" / "reference" / "rp2350a_minimal_r4_core.json"
MCU = (26.3, 30.3)

SYMBOLS = """(kicad_symbol_lib (version 20231120) (generator "test")
  (symbol "R" (pin_names (offset 0)) (in_bom yes) (on_board yes)
    (property "Reference" "R" (at 0 0 0) (effects (font (size 1.27 1.27))))
    (property "Value" "R" (at 0 0 0) (effects (font (size 1.27 1.27))))
    (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27))))
    (symbol "R_1_1"
      (pin passive line (at 0 3.81 270) (length 1.27) (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
      (pin passive line (at 0 -3.81 90) (length 1.27) (name "~" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))))
  (symbol "U" (in_bom yes) (on_board yes)
    (property "Reference" "U" (at 0 0 0) (effects (font (size 1.27 1.27))))
    (property "Value" "U" (at 0 0 0) (effects (font (size 1.27 1.27))))
    (symbol "U_1_1"
      (pin power_in line (at -7.62 2.54 0) (length 2.54) (name "VDD" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
      (pin power_in line (at -7.62 0 0) (length 2.54) (name "VDD" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))
      (pin bidirectional line (at 7.62 0 180) (length 2.54) (name "IO" (effects (font (size 1.27 1.27)))) (number "3" (effects (font (size 1.27 1.27))))))))
"""


def nm(value) -> int:
    return round(float(value) * 1_000_000)


class _Lib(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        Path(self.tmp.name, "T.kicad_sym").write_text(SYMBOLS)
        self.lib = Library(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def board(self, parts, **kw):
        return Board(name="t", title="T", revision="A", date="2026-10-11", company="Kartikeydheer Srivastava",
                     licence="MIT", width=10, height=10, parts=parts, power_nets={}, flagged_nets=[], **kw)


class SexprTest(unittest.TestCase):
    def test_round_trip_keeps_order_and_quoted_brackets(self):
        text = '(a "x ( y" (b 1 2.5) (c "q\\"r") d)'
        node = loads(text)
        self.assertEqual(str(node[0]), "a")
        self.assertEqual(node[1], "x ( y")                 # a quoted bracket is text, not structure
        self.assertEqual([str(x[0]) for x in node[2:4]], ["b", "c"])
        self.assertEqual(loads(dumps(node)), node)

    def test_find_and_find_all(self):
        node = loads("(r (p 1) (q 2) (p 3))")
        self.assertEqual(find(node, "q")[1], 2)
        self.assertEqual([p[1] for p in find_all(node, "p")], [1, 3])
        self.assertIsNone(find(node, "z"))


class ResolveTest(_Lib):
    def test_pins_by_number_and_by_shared_name(self):
        part = Part("U1", "T:U", "U", "fp", (0, 0), {"VDD": "+3V3", "3": "SIG"})
        out = design.resolve(part, self.lib)
        self.assertEqual({k: v[1] for k, v in out.items()}, {"1": "+3V3", "2": "+3V3", "3": "SIG"})

    def test_missing_pin_is_refused(self):
        with self.assertRaisesRegex(ValueError, "pins without a net"):
            design.resolve(Part("U1", "T:U", "U", "fp", (0, 0), {"VDD": "+3V3"}), self.lib)

    def test_unknown_pin_is_refused(self):
        with self.assertRaisesRegex(KeyError, "no pin named or numbered"):
            design.resolve(Part("R1", "T:R", "1k", "fp", (0, 0), {"1": "A", "2": "B", "9": "C"}), self.lib)

    def test_two_nets_on_one_pin_is_refused(self):
        with self.assertRaisesRegex(ValueError, "given two nets"):
            design.resolve(Part("U1", "T:U", "U", "fp", (0, 0), {"VDD": "+3V3", "1": "GND", "3": NC}), self.lib)


class SchematicTest(_Lib):
    def test_rebuild_is_identical_and_carries_copyright_and_credits(self):
        parts = [Part("R1", "T:R", "1k", "fp", (50, 50), {"1": "A", "2": NC})]
        board = self.board(parts, credits=["Core layout (c) 2026 Raspberry Pi Ltd, MIT"])
        first = schematic.write(board, self.lib)
        self.assertEqual(first, schematic.write(board, self.lib))          # stable UUIDs
        self.assertIn('"Copyright (c) 2026 Kartikeydheer Srivastava. Licence: MIT"', first)
        self.assertIn('"Core layout (c) 2026 Raspberry Pi Ltd, MIT"', first)
        self.assertIn("(no_connect", first)


class LicenceTest(_Lib):
    def test_mit_with_owner_and_third_party_notice(self):
        board = self.board([], credits=["Core layout: Copyright (c) 2026 Raspberry Pi Ltd, MIT licence"])
        text = build.licence_text(board)
        self.assertTrue(text.startswith("MIT License\n\nCopyright (c) 2026 Kartikeydheer Srivastava\n"))
        self.assertIn("Permission is hereby granted", text)
        self.assertIn("- Core layout: Copyright (c) 2026 Raspberry Pi Ltd, MIT licence", text)

    def closed(self, **kw):
        board = self.board([], **kw)
        board.licence = design.ALL_RIGHTS_RESERVED
        return board

    def test_all_rights_reserved_names_board_owner_contact_and_embeddedos(self):
        board = self.closed(credits=["Core layout: Copyright (c) 2026 Raspberry Pi Ltd, MIT licence"],
                            contact="someone@example.org", licence_terms="boards/licence_terms.txt")
        text = build.licence_text(board, "t")
        self.assertTrue(text.startswith('All Rights Reserved Board Licence\n\nT, revision A\n'
                                        'Copyright (c) 2026 Kartikeydheer Srivastava ("the copyright holder").\n'
                                        'All rights reserved.\n'))
        self.assertIn("- everything in boards/eos/t/:", text)                    # names the board's own files
        self.assertIn("tools/eos_boards/boards/t.py", text)
        self.assertIn("To ask,\n   write to someone@example.org.", text)
        self.assertIn("EmbeddedOS may not sell boards made from the Design", text)
        self.assertIn("It ends thirty days after that notice.", text)            # what withdrawal means
        self.assertNotIn("Permission is hereby granted", text)                   # not the MIT grant
        self.assertNotIn("{", text)                                               # every field filled in
        self.assertIn("- Core layout: Copyright (c) 2026 Raspberry Pi Ltd, MIT licence", text)
        self.assertIn("- " + build.KICAD_LIBRARIES, text)

    def test_all_rights_reserved_needs_a_contact_and_terms(self):
        terms = "boards/licence_terms.txt"
        for kw, module in (({"contact": "  ", "licence_terms": terms}, "t"), ({"contact": "a@example.org"}, "t"),
                           ({"contact": "a@example.org", "licence_terms": terms}, "")):
            with self.subTest(module=module, **kw), self.assertRaisesRegex(SystemExit, "needs a contact, its licence terms"):
                build.licence_text(self.closed(**kw), module)

    def test_other_licences_are_not_guessed(self):
        board = self.board([])
        board.licence = "CERN-OHL-S-2.0"
        with self.assertRaisesRegex(SystemExit, "no licence text"):
            build.licence_text(board)


class CheckReferenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ref = Path(self.tmp.name, "ref.json")
        self.ref.write_text(json.dumps({"footprints": {"C1": {"footprint": "L:cap", "x": 0, "y": 0, "rot": 0,
                                                              "pads": {"1": "+3V3", "2": "GND"}}},
                                        "tracks": [], "vias": [], "zones": []}))
        self.board = Board(name="t", title="T", revision="A", date="2026-10-11", company="X", licence="MIT",
                           width=1, height=1, parts=[], power_nets={}, flagged_nets=[],
                           reference_copper={"file": str(self.ref), "origin": (0, 0)})

    def tearDown(self):
        self.tmp.cleanup()

    def test_matching_part_passes(self):
        build.check_reference(self.board, None, [{"ref": "C1", "footprint": "L:cap", "pads": {"1": "+3V3", "2": "GND"}}])

    def test_pad_on_another_net_is_refused(self):
        with self.assertRaisesRegex(SystemExit, "other nets than the reference copper expects"):
            build.check_reference(self.board, None, [{"ref": "C1", "footprint": "L:cap", "pads": {"1": "+1V1", "2": "GND"}}])

    def test_other_footprint_is_refused(self):
        with self.assertRaisesRegex(SystemExit, "drawn for"):
            build.check_reference(self.board, None, [{"ref": "C1", "footprint": "L:other", "pads": {"1": "+3V3", "2": "GND"}}])

    def test_missing_part_is_refused(self):
        with self.assertRaisesRegex(SystemExit, "is not on"):
            build.check_reference(self.board, None, [])


class ExtractorTest(unittest.TestCase):
    def test_footprint_keeps_four_fields_and_unrotates(self):
        fp = loads('(footprint "Lib:part" (layer "F.Cu") (uuid "u") (at 10 20 90)'
                   ' (property "Reference" "C5" (at 0 -1 90)) (property "Value" "4.7u" (at 0 1 90))'
                   ' (property "lcsc_pn" "C123" (at 0 0 90)) (path "/x")'
                   ' (pad "1" smd rect (at -0.5 0 90) (size 0.5 0.5) (layers "F.Cu") (net "+3V3") (uuid "p")))')
        name, text = extract.footprint(fp, {})
        node = loads(text)
        self.assertEqual(name, "part")
        self.assertEqual({str(p[1]): p[2] for p in find_all(node, "property")},
                         {"Reference": "REF**", "Value": "part"})
        self.assertNotIn("lcsc_pn", text)
        self.assertNotIn("uuid", text)
        self.assertNotIn("(net", text)
        self.assertEqual(find(find(node, "pad"), "at")[1:], [-0.5, 0])   # the footprint's 90 degrees taken out

    def test_reference_file_records_its_source(self):
        data = json.loads(CORE.read_text())
        self.assertEqual(set(data["footprints"]), set(extract.PARTS.values()))
        self.assertRegex(data["source_sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("MIT", data["source"])

    @unittest.skipUnless(os.environ.get("RPI_MINIMAL_PCB"),
                         "set RPI_MINIMAL_PCB to Raspberry Pi's RPI-RP2350A-MINIMAL_R4-S1.kicad_pcb to re-extract")
    def test_reference_file_is_what_raspberry_pis_design_gives(self):
        # Re-extract from Raspberry Pi's own file and compare with the committed reference, so the
        # nanometre checks below rest on Raspberry Pi's design, not only on our copy of it.
        source = Path(os.environ["RPI_MINIMAL_PCB"])
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, "-I", str(REPO_ROOT / "tools/eos_boards/reference/extract_rpi_minimal.py"),
                            str(source), "--footprints", str(Path(tmp) / "fp.pretty"), "--out", str(Path(tmp) / "core.json")],
                           check=True, capture_output=True)
            self.assertEqual(json.loads(Path(tmp, "core.json").read_text()), json.loads(CORE.read_text()))


class ReferenceExactnessTest(unittest.TestCase):
    """Raspberry Pi's copper on the built board, nanometre for nanometre. The board is committed,
    so a missing file is a failure, not a skip."""

    @classmethod
    def setUpClass(cls):
        assert PCB.is_file(), f"built board missing: {PCB}"
        cls.pcb = loads(PCB.read_text())
        cls.ref = json.loads(CORE.read_text())
        cls.ox, cls.oy = MCU

    def _at(self, x, y):
        return nm(self.ox + x), nm(self.oy + y)

    def test_footprints_where_the_reference_puts_them(self):
        placed = {}
        for fp in find_all(self.pcb, "footprint"):
            ref = next(str(p[2]) for p in find_all(fp, "property") if str(p[1]) == "Reference")
            placed[ref] = fp
        for name, f in self.ref["footprints"].items():
            fp = placed[name]
            at = find(fp, "at")
            self.assertEqual(str(fp[1]), f["footprint"], name)
            self.assertEqual((nm(at[1]), nm(at[2])), self._at(f["x"], f["y"]), name)
            self.assertEqual(round(float(at[3]) if len(at) > 3 else 0.0) % 360, round(f["rot"]) % 360, name)
            nets = {str(p[1]): str(find(p, "net")[-1]) for p in find_all(fp, "pad") if find(p, "net")}
            for pad, net in f["pads"].items():
                self.assertEqual(nets[pad], net, f"{name} pad {pad}")

    def test_every_track_exact_and_locked(self):
        segs = set()
        for s in find_all(self.pcb, "segment"):
            a = (nm(find(s, "start")[1]), nm(find(s, "start")[2]))
            b = (nm(find(s, "end")[1]), nm(find(s, "end")[2]))
            locked = find(s, "locked") is not None and str(find(s, "locked")[1]) == "yes"
            segs.add((str(find(s, "net")[-1]), str(find(s, "layer")[1]), nm(find(s, "width")[1]),
                      frozenset((a, b)), locked))
        for t in self.ref["tracks"]:
            key = (t["net"], t["layer"], nm(t["w"]), frozenset((self._at(*t["a"]), self._at(*t["b"]))), True)
            self.assertIn(key, segs, t)

    def test_every_via_exact(self):
        vias = {(str(find(v, "net")[-1]), nm(find(v, "at")[1]), nm(find(v, "at")[2]), nm(find(v, "size")[1]),
                 nm(find(v, "drill")[1])) for v in find_all(self.pcb, "via")}
        for d in self.ref["vias"]:
            self.assertIn((d["net"], *self._at(d["x"], d["y"]), nm(d["d"]), nm(d["drill"])), vias, d)

    def test_every_zone_outline_exact(self):
        zones = []
        for z in find_all(self.pcb, "zone"):
            if find(z, "name") is None or find(z, "name")[1] != "eos-reference":
                continue
            pts = tuple((nm(p[1]), nm(p[2])) for p in find_all(find(find(z, "polygon"), "pts"), "xy"))
            zones.append((str(find(z, "net_name")[1]) if find(z, "net_name") else str(find(z, "net")[-1]),
                          str(find(z, "layer")[1]), int(find(z, "priority")[1]), pts))
        self.assertEqual(len(zones), len(self.ref["zones"]))
        for zd in self.ref["zones"]:
            key = (zd["net"], zd["layer"], zd["priority"] + 10, tuple(self._at(x, y) for x, y in zd["outline"]))
            self.assertIn(key, zones, zd["net"])



CAPE_PCB = REPO_ROOT / "boards" / "eos" / "eos-sense-cape" / "hardware" / "eos-sense-cape.kicad_pcb"
PB_HEADERS = REPO_ROOT / "tools" / "eos_boards" / "reference" / "pocketbeagle_headers.json"


def _pad_positions(pcb, refs):
    """{(ref, pad number): (x, y) in nm} for the given footprints, rotation applied as KiCad does."""
    import math
    out = {}
    for fp in find_all(pcb, "footprint"):
        ref = next(str(p[2]) for p in find_all(fp, "property") if str(p[1]) == "Reference")
        if ref not in refs:
            continue
        at = find(fp, "at")
        x0, y0, rot = float(at[1]), float(at[2]), math.radians(float(at[3]) if len(at) > 3 else 0.0)
        for pad in find_all(fp, "pad"):
            px, py = float(find(pad, "at")[1]), float(find(pad, "at")[2])
            out[(ref, str(pad[1]))] = (nm(x0 + px * math.cos(rot) + py * math.sin(rot)),
                                       nm(y0 - px * math.sin(rot) + py * math.cos(rot)))
    return out


class CapeFitTest(unittest.TestCase):
    """The cape's sockets meet PocketBeagle's header pins, pin for pin, to the nanometre."""

    def test_every_socket_pad_on_its_pocketbeagle_pin(self):
        self.assertTrue(CAPE_PCB.is_file(), f"built board missing: {CAPE_PCB}")
        pins = json.loads(PB_HEADERS.read_text())["pins"]
        pads = _pad_positions(loads(CAPE_PCB.read_text()), {"J1", "J2"})
        self.assertEqual(len(pins), 72)
        for name, (x, y) in pins.items():
            header, number = name.split(".")
            ref = {"P1": "J1", "P2": "J2"}[header]
            self.assertEqual(pads[(ref, number)], (x, y), name)



CM5_PCB = REPO_ROOT / "boards" / "eos" / "eos-cm5-base" / "hardware" / "eos-cm5-base.kicad_pcb"
CM5_REF = REPO_ROOT / "tools" / "eos_boards" / "reference" / "cm5_carrier.json"


class CM5FitTest(unittest.TestCase):
    """The carrier's two connectors and four mounting holes sit where the CM5's own are, to the nanometre."""

    @classmethod
    def setUpClass(cls):
        assert CM5_PCB.is_file(), f"built board missing: {CM5_PCB}"
        from eos_boards.boards import eos_cm5_base as board
        cls.board = board
        cls.ref = json.loads(CM5_REF.read_text())
        cls.pcb = loads(CM5_PCB.read_text())

    def _on_board(self, fx_nm, fy_nm):
        x, y = self.board.from_cm5(fx_nm / 1e6, fy_nm / 1e6)
        return nm(x), nm(y)

    def test_every_connector_pad_on_its_cm5_pin(self):
        pads = _pad_positions(self.pcb, {"J1", "J2"})
        self.assertEqual(len(self.ref["pads"]), 200)
        for pin, (fx, fy) in self.ref["pads"].items():
            ref, number = ("J1", pin) if int(pin) <= 100 else ("J2", str(int(pin) - 100))
            self.assertEqual(pads[(ref, number)], self._on_board(fx, fy), f"CM5 pin {pin}")

    def test_mounting_holes(self):
        holes = set()
        for fp in find_all(self.pcb, "footprint"):
            ref = next(str(p[2]) for p in find_all(fp, "property") if str(p[1]) == "Reference")
            if ref.startswith("H"):
                at = find(fp, "at")
                holes.add((nm(at[1]), nm(at[2])))
        self.assertEqual(holes, {self._on_board(h[0], h[1]) for h in self.ref["holes"]})

    def test_connector_nets_follow_the_datasheet(self):
        nets = {}
        for fp in find_all(self.pcb, "footprint"):
            ref = next(str(p[2]) for p in find_all(fp, "property") if str(p[1]) == "Reference")
            if ref in ("J1", "J2"):
                for pad in find_all(fp, "pad"):
                    n = find(pad, "net")
                    nets[int(str(pad[1])) + (100 if ref == "J2" else 0)] = str(n[-1]) if n else None
        names = self.ref["pins"]
        for pin, name in names.items():
            got = nets[int(pin)]
            if name == "GND":
                self.assertEqual(got, "GND", f"pin {pin}")
            elif name == "5V":
                self.assertEqual(got, "+5V", f"pin {pin}")
            elif name in ("CM5_3.3V", "GPIO_VREF"):
                self.assertEqual(got, "+3V3", f"pin {pin}")
            elif name.startswith("GPIO") and name[4:].isdigit():
                self.assertEqual(got, f"/{name}", f"pin {pin}")
        self.assertEqual(nets[94], "/CC1")
        self.assertEqual(nets[96], "/CC2")



def _parts(pcb):
    """{reference: (value, {pad number: net})} from a built board."""
    out = {}
    for fp in find_all(pcb, "footprint"):
        props = {str(p[1]): str(p[2]) for p in find_all(fp, "property")}
        pads = {}
        for pad in find_all(fp, "pad"):
            n = find(pad, "net")
            pads.setdefault(str(pad[1]), str(n[-1]) if n else None)
        out[props["Reference"]] = (props.get("Value"), pads)
    return out


class BoardIntentTest(unittest.TestCase):
    """What each board's documentation promises, read back from the built boards' own pads."""

    @classmethod
    def setUpClass(cls):
        cls.boards = {}
        for name in ("eos-learn-rp2350", "eos-sense-cape", "eos-probe-s3", "eos-cm5-base"):
            path = REPO_ROOT / "boards" / "eos" / name / "hardware" / f"{name}.kicad_pcb"
            assert path.is_file(), f"built board missing: {path}"
            cls.boards[name] = _parts(loads(path.read_text()))

    def test_rp2350_power_path_and_usb(self):
        b = self.boards["eos-learn-rp2350"]
        self.assertEqual(b["U3"][0], "AP7361C-33")                       # stable with ceramic capacitors
        self.assertEqual(b["U3"][1], {"1": "+5V", "2": "GND", "3": "+3V3"})
        self.assertEqual(b["D1"][1], {"1": "+5V", "2": "/VBUS_F"})       # cathode +5V: header 5 V cannot reach VBUS
        self.assertEqual(b["F1"][1], {"1": "VBUS", "2": "/VBUS_F"})                 # VBUS is a power net: no "/"
        self.assertEqual((b["R3"][0], b["R4"][0]), ("27", "27"))          # USB series resistors
        self.assertEqual(set(b["R3"][1].values()), {"/USB_D+", "/RP_USB_DP"})
        self.assertEqual(b["R8"][0], "1k")                                 # BOOTSEL resistor on QSPI_SS
        self.assertEqual(set(b["R8"][1].values()), {"/QSPI_SS", "/BOOTSEL"})

    def test_cape_straps_pullups_and_analog(self):
        b = self.boards["eos-sense-cape"]
        self.assertEqual(b["U1"][1]["2"], "+3V3")                          # BME280 CSB to VDDIO: I2C
        self.assertEqual(b["U1"][1]["5"], "/BME_SDO")
        self.assertEqual(b["JP2"][1], {"1": "GND", "2": "/BME_SDO", "3": "+3V3"})   # bridged 1-2: 0x76
        self.assertEqual(b["U2"][1]["8"], "+3V3")                          # LIS3DH CS high: I2C
        self.assertEqual(b["U2"][1]["10"], "GND")                          # RES to GND
        self.assertEqual(b["JP3"][1], {"1": "GND", "2": "/ACC_SA0", "3": "+3V3"})
        self.assertEqual([b["U4"][1][p] for p in "123"], ["+3V3"] * 3)     # 24LC256 at 0x57
        self.assertEqual(b["JP1"][1], {"1": "GND", "2": "/EE_WP", "3": "+3V3"})
        for ref, net in (("R1", "/I2C1_SDA"), ("R2", "/I2C1_SCL"), ("R4", "/I2C2_SDA"), ("R5", "/I2C2_SCL")):
            self.assertEqual((b[ref][0], set(b[ref][1].values())), ("4.7k", {net, "+3V3"}), ref)
        self.assertEqual(b["J1"][1]["2"], "/AIN6")                         # 3.3 V-tolerant inputs only
        self.assertEqual(b["J2"][1]["35"], "/AIN5")
        for pin in ("19", "21", "23", "25", "27"):                          # AIN0-4: 1.8 V only, untouched
            self.assertTrue(b["J1"][1][pin].startswith("unconnected-"), pin)
        self.assertTrue(b["J2"][1]["36"].startswith("unconnected-"))       # AIN7

    def test_probe_translators(self):
        b = self.boards["eos-probe-s3"]
        direction = {"U4": "+3V3", "U5": "/SWDIO_DIR", "U6": "GND", "U7": "+3V3", "U8": "+3V3", "U9": "GND"}
        for ref, d in direction.items():
            pads = b[ref][1]
            self.assertEqual((pads["1"], pads["6"], pads["5"]), ("+3V3", "/VTREF", d), ref)   # VCCA, VCCB, DIR
        self.assertEqual(set(b["R10"][1].values()), {"/SWDIO_DIR", "GND"})                  # reads at power-up
        self.assertEqual(set(b["R17"][1].values()), {"/NRESET_G", "GND"})                   # nRESET switch off
        for pin in ("15", "16", "26"):                                                       # IO3, IO46, IO45 untouched
            self.assertTrue(b["U3"][1][pin].startswith("unconnected-"), pin)

    def test_cm5_usb_c_and_host_port(self):
        b = self.boards["eos-cm5-base"]
        cc = {b["J3"][1][p] for p in ("A5", "B5")}
        self.assertEqual(cc, {"/CC1", "/CC2"})
        self.assertFalse(any(set(pads.values()) & {"/CC1", "/CC2"} for ref, (_, pads) in b.items()
                             if ref not in ("J1", "J3")), "the CM5 negotiates USB-C power itself: no CC resistors")
        self.assertEqual(b["U2"][1], {"1": "/USBH_VBUS", "2": "GND", "3": b["U2"][1]["3"], "4": "/VBUS_EN", "5": "+5V"})


EOS_BOARDS = {"eos-learn-rp2350": "eos_learn_rp2350", "eos-sense-cape": "eos_sense_cape",
              "eos-probe-s3": "eos_probe_s3", "eos-cm5-base": "eos_cm5_base"}


class OwnershipTest(unittest.TestCase):
    """The four boards are Kartikeydheer Srivastava's, all rights reserved. Everywhere a reader or a
    fab sees the licence says so, and nothing still gives the boards themselves the MIT licence."""

    def test_each_board_carries_the_all_rights_reserved_licence(self):
        for name, module in EOS_BOARDS.items():
            with self.subTest(board=name):
                board = importlib.import_module(f"eos_boards.boards.{module}").BOARD
                self.assertEqual((board.company, board.licence, board.contact),
                                 ("Kartikeydheer Srivastava", design.ALL_RIGHTS_RESERVED, "kartikeydheer@gmail.com"))
                folder = REPO_ROOT / "boards" / "eos" / name
                licence = (folder / "LICENSE.txt").read_text()
                self.assertEqual(licence, build.licence_text(board, module))     # what the build writes
                self.assertEqual("tools/eos_boards/footprints/EoS_Connectors.pretty" in licence, name == "eos-cm5-base")
                self.assertIn("To ask,\n   write to kartikeydheer@gmail.com.", licence)
                self.assertIn(f"tools/eos_boards/boards/{module}.py", licence)
                sch = (folder / "hardware" / f"{name}.kicad_sch").read_text()
                self.assertIn('(comment 1 "Copyright (c) 2026 Kartikeydheer Srivastava. Licence: All rights reserved")', sch)
                pcb = loads((folder / "hardware" / f"{name}.kicad_pcb").read_text())
                silk = [str(t[1]) for t in find_all(pcb, "gr_text") if str(find(t, "layer")[1]) == "B.SilkS"]
                self.assertIn("(c) 2026 Kartikeydheer Srivastava", silk)
                self.assertIn("All rights reserved", silk)
                self.assertFalse([s for s in silk if "Srivastava" in s and "MIT" in s], silk)
                readme = (folder / "README.md").read_text()
                self.assertIn("All rights reserved: not open source", readme)
                self.assertNotIn("MIT licence (see", readme)

    def test_generic_symbols_copied_into_a_board_stay_mit(self):
        licence = (REPO_ROOT / "boards" / "eos" / "eos-cm5-base" / "LICENSE.txt").read_text()
        self.assertIn("Schematic symbols in hardware/symbols (EoS_Connectors.kicad_sym, EoS_Parts.kicad_sym): "
                      "written by this repository's generator, tools/eos_boards/symbols, MIT licence", licence)

    def test_repository_docs_state_the_exception(self):
        contributing = (REPO_ROOT / "CONTRIBUTING.md").read_text()
        self.assertIn("### Exception: the EmbeddedOS original boards", contributing)
        self.assertIn("may use and relicense the change on any terms", contributing)
        self.assertIn("all rights reserved, and are not under the MIT licence", (REPO_ROOT / "README.md").read_text())
        notice = REPO_ROOT / "tools" / "eos_boards" / "footprints" / "EoS_Connectors.NOTICE.txt"
        self.assertIn("All rights reserved", notice.read_text())
        self.assertFalse((notice.parent / "EoS_Connectors.LICENSE.txt").exists())   # would be listed as third-party

if __name__ == "__main__":
    unittest.main()
