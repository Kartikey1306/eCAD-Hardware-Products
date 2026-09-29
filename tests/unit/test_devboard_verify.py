"""Issue #28: the verifier decides availability from content, and never from a status code.

Every test here is offline. Payloads are synthesised in memory, so the suite is
deterministic and CI never depends on a vendor's CDN being up or willing to serve a bot.
The behaviours pinned below are the ones that were observed to matter against real vendor
infrastructure:

* ``datasheets.raspberrypi.com`` answers HEAD for a real 266 kB ZIP with
  ``content-type: text/html`` and ``content-length: 0``, so headers cannot be trusted and
  only a GET of the body settles anything.
* ``raspberrypi.com`` answers an automated client with a Cloudflare interstitial at
  status 200, so a 200 whose body is HTML must never satisfy a CAD claim.
* A guessed URL that 404s says the guess was wrong, not that the vendor publishes nothing.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from devboard_cad import harvest_github as harvest  # noqa: E402
from devboard_cad.verify import (  # noqa: E402
    FetchResult,
    Fetcher,
    classify,
    derive_status,
    detect_format,
    is_binary_stl,
    parse_step_header,
    revision_corroborated,
)
from jsonschema import Draft7Validator  # noqa: E402

STEP_BODY = (
    b"ISO-10303-21;\n"
    b"HEADER;\n"
    b"FILE_DESCRIPTION (( 'STEP AP203' ),\n    '1' );\n"
    b"FILE_NAME ('PICO.STEP',\n    '2021-01-22T14:05:44',\n    ( '' ),\n    ( '' ),\n"
    b"    'SwSTEP 2.0',\n    'SolidWorks 2021',\n    '' );\n"
    b"FILE_SCHEMA (( 'CONFIG_CONTROL_DESIGN' ));\n"
    b"ENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"
)
CLOUDFLARE = (
    b"<!DOCTYPE html><html lang=\"en-US\"><head><title>Just a moment...</title>"
    b"<meta http-equiv=\"Content-Type\" content=\"text/html; charset=UTF-8\">"
)


def _zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _result(payload: bytes | None, status: int | None = 200,
            media_type: str | None = None, error: str | None = None) -> FetchResult:
    return FetchResult("https://vendor.invalid/file", status, payload, media_type,
                       "https://vendor.invalid/file", error)


class TestContentSniffing(unittest.TestCase):
    def test_recognises_the_formats_vendors_actually_ship(self) -> None:
        cases = {
            b"%PDF-1.4\n1 0 obj": "pdf",
            b"PK\x03\x04\x14\x00": "zip",
            STEP_BODY: "step",
            CLOUDFLARE: "html",
            b"EESchema Schematic File Version 4": "kicad",
            b"(kicad_pcb (version 20221018)": "kicad",
            b"<?xml version=\"1.0\"?>\n<eagle version=\"9.6\">": "eagle",
            b"solid boardOutline\n facet normal": "stl",
            b"  0\r\nSECTION\r\n  2\r\nHEADER": "dxf",
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1": "ole",
        }
        for payload, expected in cases.items():
            self.assertEqual(detect_format(payload), expected, payload[:24])

    def test_a_zip_is_recognised_despite_a_lying_content_type(self) -> None:
        """The Pico case: HEAD said text/html and length 0 for a genuine ZIP."""
        result = _result(_zip({"Pico-R3.step": STEP_BODY}), media_type="text/html")
        self.assertEqual(classify("step", result).available, True)

    def test_recognises_pcb_fabrication_output(self) -> None:
        """Gerber and Excellon are what 'gerbers' and 'nc_drill' actually resolve to."""
        cases = {
            b"G04 EAGLE Gerber RS-274X export*\nG75*\n%MOMM*%\n": "gerber",
            b"G04 #@! TF.GenerationSoftware,KiCad,Pcbnew*\n": "gerber",
            b"%FSLAX34Y34*%\n%MOMM*%\n": "gerber",
            b"M48\nINCH\nT01C.006\n": "excellon",
        }
        for payload, expected in cases.items():
            self.assertEqual(detect_format(payload), expected, payload[:24])
        self.assertIs(classify("gerbers", _result(b"G04 EAGLE Gerber*\n")).available, True)
        self.assertIs(classify("nc_drill", _result(b"M48\nINCH\n")).available, True)

    def test_delimited_text_is_a_last_resort_and_stays_conservative(self) -> None:
        table = b"Designator,Manufacturer/MPN,Qty,Description\r\n,\"PLACON\",1,\"x\"\r\n"
        self.assertEqual(detect_format(table), "csv")
        self.assertIs(classify("bom", _result(table)).available, True)
        # Prose and binary must not be promoted into a satisfied claim.
        self.assertIsNone(detect_format(b"Just a sentence with no delimiters.\nAnother.\n"))
        self.assertIsNone(detect_format(b"\x00\x01\x02binary,garbage,here\n"))
        self.assertIsNone(classify("bom", _result(b"Just prose.\nMore prose.\n")).available)

    def test_binary_stl_is_detected_by_its_triangle_count(self) -> None:
        payload = b"\x00" * 80 + (2).to_bytes(4, "little") + b"\x00" * 100
        self.assertTrue(is_binary_stl(payload))
        self.assertFalse(is_binary_stl(payload + b"\x00"))


class TestStepHeader(unittest.TestCase):
    def test_reads_schema_tool_and_internal_name(self) -> None:
        header = parse_step_header(STEP_BODY)
        self.assertEqual(header["step_schema"], "CONFIG_CONTROL_DESIGN")
        self.assertEqual(header["internal_name"], "PICO.STEP")
        self.assertEqual(header["timestamp"], "2021-01-22T14:05:44")
        self.assertIn("SolidWorks 2021", header["authoring_tool"] or "")

    def test_a_file_that_names_the_revision_corroborates_it(self) -> None:
        self.assertTrue(revision_corroborated(STEP_BODY, "Pico-R3.step", "Pico-R3"))
        self.assertFalse(revision_corroborated(STEP_BODY, "Pico-R3.step", "Pico-R4"))
        self.assertFalse(revision_corroborated(STEP_BODY, None, "unverified"))


class TestClassification(unittest.TestCase):
    def test_a_guessed_url_that_404s_is_unknown_not_absent(self) -> None:
        verdict = classify("step", _result(None, status=404, error="HTTP 404"))
        self.assertIsNone(verdict.available)
        self.assertIsNone(verdict.evidence)

    def test_an_indexed_url_that_404s_may_be_recorded_absent(self) -> None:
        verdict = classify("step", _result(None, status=404, error="HTTP 404"),
                           absent_on_404=True)
        self.assertIs(verdict.available, False)
        self.assertEqual(verdict.evidence["verification_method"], "http_get_absent")
        self.assertEqual(verdict.evidence["http_status"], 404)

    def test_a_200_serving_html_never_satisfies_a_cad_claim(self) -> None:
        verdict = classify("step", _result(CLOUDFLARE, media_type="text/html"))
        self.assertIsNone(verdict.available)
        self.assertIn("HTML", verdict.reason)

    def test_a_timeout_is_unknown(self) -> None:
        verdict = classify("step", _result(None, status=None, error="timeout"))
        self.assertIsNone(verdict.available)
        self.assertEqual(verdict.reason, "timeout")

    def test_an_archive_must_contain_a_member_that_satisfies_the_claim(self) -> None:
        good = classify("step", _result(_zip({"Pico-R3.step": STEP_BODY})))
        self.assertIs(good.available, True)
        self.assertEqual(good.evidence["contained_member"], "Pico-R3.step")
        self.assertEqual(good.evidence["verification_method"], "http_get_step_header")
        self.assertEqual(good.evidence["detected_format"], "step:CONFIG_CONTROL_DESIGN")

        bad = classify("step", _result(_zip({"readme.txt": b"nothing here"})))
        self.assertIsNone(bad.available)

    def test_macos_resource_forks_do_not_satisfy_a_claim(self) -> None:
        payload = _zip({"__MACOSX/._Pico-R3.step": b"junk", "readme.txt": b"x"})
        self.assertIsNone(classify("step", payload and _result(payload)).available)

    def test_content_must_match_the_declared_format(self) -> None:
        self.assertIsNone(classify("step", _result(b"%PDF-1.4 not a model")).available)
        self.assertIs(classify("schematic", _result(b"%PDF-1.4\n1 0 obj")).available, True)

    def test_a_native_eagle_schematic_satisfies_a_schematic_claim(self) -> None:
        """Issue #28 section 8 counts native schematics, not only schematic PDFs."""
        payload = b"<?xml version=\"1.0\"?>\n<eagle version=\"9.6\"><drawing/></eagle>"
        self.assertIs(classify("schematic", _result(payload)).available, True)

    def test_evidence_produced_by_the_tool_satisfies_the_schema(self) -> None:
        schema = json.loads(
            (REPO_ROOT / "schemas" / "devboard-cad" / "v1" /
             "board-record.schema.json").read_text(encoding="utf-8")
        )
        record = json.loads(
            (REPO_ROOT / "tools" / "devboard_cad" / "records" /
             "raspberry-pi__pico.json").read_text(encoding="utf-8")
        )
        verdict = classify("step", _result(_zip({"Pico-R3.step": STEP_BODY})))
        record["files"]["step"] = {
            "available": verdict.available,
            "url": "https://vendor.invalid/file",
            "verified_revision": None,
            "evidence": verdict.evidence,
        }
        record["record_status"] = derive_status(record)
        errors = list(Draft7Validator(schema).iter_errors(record))
        self.assertEqual(errors, [], errors[:1])


class TestFetchCache(unittest.TestCase):
    """A cached failure is not a result; replaying one would freeze a record at unknown."""

    UNREACHABLE = "http://127.0.0.1:1/never-served"

    def _fetcher(self, directory: str, **kwargs) -> Fetcher:
        return Fetcher(cache_dir=Path(directory), min_interval=0.0, timeout=1.0, **kwargs)

    def test_a_cached_transport_error_is_retried_rather_than_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fetcher = self._fetcher(directory)
            first = fetcher.get(self.UNREACHABLE)
            self.assertIsNone(first.payload)
            self.assertFalse(first.from_cache)
            second = fetcher.get(self.UNREACHABLE)
            self.assertFalse(
                second.from_cache,
                "a transient failure was replayed from cache instead of retried",
            )

    def test_offline_mode_does_replay_what_was_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self._fetcher(directory).get(self.UNREACHABLE)
            offline = self._fetcher(directory, offline=True).get(self.UNREACHABLE)
            self.assertTrue(offline.from_cache)

    def test_a_404_is_definitive_and_may_be_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fetcher = self._fetcher(directory)
            blob, meta = fetcher._paths("https://vendor.invalid/gone")
            Path(directory).mkdir(parents=True, exist_ok=True)
            meta.write_text(json.dumps({"url": "https://vendor.invalid/gone", "status": 404,
                                        "media_type": None, "final_url": None,
                                        "error": "HTTP 404"}), encoding="utf-8")
            replayed = fetcher.get("https://vendor.invalid/gone")
            self.assertTrue(replayed.from_cache)
            self.assertEqual(replayed.status, 404)


class TestDerivedStatus(unittest.TestCase):
    def _record(self, files: dict, **identity) -> dict:
        base = {"part_number": "X", "mcu_soc": "Y", "revision": "R1"}
        base.update(identity)
        base["files"] = files
        return base

    def test_all_unknown_is_incomplete(self) -> None:
        self.assertEqual(derive_status(self._record({"a": {"available": None}})), "incomplete")

    def test_some_known_is_partial(self) -> None:
        record = self._record({"a": {"available": True}, "b": {"available": None}})
        self.assertEqual(derive_status(record), "partial")

    def test_all_known_with_confirmed_identity_is_verified(self) -> None:
        record = self._record({"a": {"available": True}, "b": {"available": False}})
        self.assertEqual(derive_status(record), "verified")

    def test_unverified_identity_holds_a_record_at_partial(self) -> None:
        """Issue #28 section 9: a record must bind an exact part number, not a family."""
        record = self._record({"a": {"available": True}}, part_number="UNVERIFIED")
        self.assertEqual(derive_status(record), "partial")


class TestGithubHarvester(unittest.TestCase):
    PATHS = [
        "Adafruit Feather RP2040.brd",
        "Adafruit Feather RP2040.sch",
        "Adafruit Feather RP2040 Original.brd",
        "Adafruit Feather RP2040 rev B.brd",
        "Adafruit Feather RP2040 pinout.pdf",
        "feather_test/feather_test.c",
        ".DS_Store",
    ]

    def test_one_file_can_answer_several_format_questions(self) -> None:
        found = harvest.classify_paths(self.PATHS)
        self.assertIn("Adafruit Feather RP2040.brd", found["pcb_source"])
        self.assertIn("Adafruit Feather RP2040.brd", found["eagle"])
        self.assertIn("Adafruit Feather RP2040.sch", found["schematic"])
        self.assertIn("Adafruit Feather RP2040 pinout.pdf", found["pinout"])
        self.assertNotIn("step", found)

    def test_dotfiles_are_not_design_files(self) -> None:
        self.assertEqual(harvest.classify_paths([".DS_Store", "__MACOSX/._a.brd"]), {})

    def test_the_current_revision_is_preferred_over_superseded_ones(self) -> None:
        chosen = harvest._pick([
            "Adafruit Feather RP2040 Original.brd",
            "Adafruit Feather RP2040 rev B.brd",
            "Adafruit Feather RP2040.brd",
        ])
        self.assertEqual(chosen, "Adafruit Feather RP2040.brd")

    def test_a_neutral_slot_prefers_the_format_most_people_can_open(self) -> None:
        """'Does this board have PCB source?' should answer with the interoperable file."""
        both = ["EAGLE/PocketBeagle.brd", "KiCAD/PocketBeagle.kicad_pcb"]
        self.assertEqual(harvest._pick(both, "pcb_source"), "KiCAD/PocketBeagle.kicad_pcb")
        # The vendor-specific slot still answers with its own format, so nothing is hidden.
        self.assertEqual(harvest._pick(["EAGLE/PocketBeagle.brd"], "eagle"),
                         "EAGLE/PocketBeagle.brd")
        # Currency still outranks format: a superseded KiCad file loses to the current one.
        self.assertEqual(
            harvest._pick(["old/Board.kicad_pcb", "Board.kicad_pcb"], "pcb_source"),
            "Board.kicad_pcb")

    def test_absence_is_claimed_only_against_a_pinned_index(self) -> None:
        files = harvest.build_files("adafruit/X", "a" * 40, harvest.classify_paths(self.PATHS))
        self.assertIs(files["step"]["available"], False)
        self.assertEqual(files["step"]["evidence"]["verification_method"],
                         "official_index_absent")
        self.assertEqual(files["step"]["evidence"]["index_ref"], "adafruit/X@" + "a" * 40)
        # A repository is not evidence about documents that live on product pages.
        self.assertNotIn("user_manual", files)

    def test_the_index_only_proposes_presence(self) -> None:
        """Presence is decided by verify.py from bytes, never by a filename in a tree."""
        files = harvest.build_files("adafruit/X", "b" * 40, harvest.classify_paths(self.PATHS))
        self.assertIsNone(files["pcb_source"]["available"])
        self.assertTrue(files["pcb_source"]["url"].startswith(
            "https://raw.githubusercontent.com/adafruit/X/" + "b" * 40))
        self.assertIn("%20", files["pcb_source"]["url"])


if __name__ == "__main__":
    unittest.main()
