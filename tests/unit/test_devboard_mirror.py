"""Issue #48: the mirror holds exactly the verified, openly licensed design files.

Every test is offline. Payloads are synthesised in memory and served by a fake fetcher,
except the last class, which checks the committed mirror against the committed records.
The check also accepts Git LFS pointer files, so it keeps working if the mirror moves
to LFS.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from devboard_cad import mirror  # noqa: E402
from devboard_cad.verify import FetchResult  # noqa: E402

EAGLE_BRD = b'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE eagle SYSTEM "eagle.dtd">\n<eagle version="9.6.2"><drawing/></eagle>\n'
KICAD_PCB = b'(kicad_pcb (version 20240108) (generator "pcbnew"))\n'
GERBER = b"G04 Layer: BottomLayer*\n%FSLAX24Y24*%\n%MOIN*%\nM02*\n"
PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
HTML = b"<!doctype html><html><head><title>Sign in</title></head><body></body></html>"
JSON = b'{"error": "not found"}'


def _zip(members: Dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _entry(url: str, payload: bytes, available: Optional[bool] = True,
           detected: Optional[str] = None) -> dict:
    return {
        "available": available,
        "url": url if available else None,
        "evidence": {"sha256": _sha(payload) if available else None, "size_bytes": len(payload),
                     "captured_at": "2026-09-29T07:22:11Z",
                     "detected_format": detected or (mirror.identify(payload) if available else None)},
    }


def _record(board_id: str, files: dict, redistribution: Optional[bool] = True) -> dict:
    return {
        "board_id": board_id,
        "manufacturer": "Example Corp",
        "board": f"Example {board_id}",
        "part_number": "EX-1",
        "files": files,
        "licenses": {"cad_license": "CC BY-SA 4.0", "hardware_license": "CC BY-SA 4.0",
                     "redistribution_allowed": redistribution,
                     "license_url": "https://creativecommons.org/licenses/by-sa/4.0/"},
    }


class FakeFetcher:
    def __init__(self, payloads: Dict[str, bytes]) -> None:
        self.payloads = payloads

    def get(self, url: str) -> FetchResult:
        payload = self.payloads.get(url)
        return FetchResult(url, 200 if payload is not None else 404, payload, None, url,
                           None if payload is not None else "HTTP 404")


class SelectionTests(unittest.TestCase):
    def test_only_redistributable_boards_are_selected(self) -> None:
        records = [
            _record("open:a", {"eagle": _entry("https://x/a.brd", EAGLE_BRD)}),
            _record("closed:b", {"eagle": _entry("https://x/b.brd", EAGLE_BRD)}, redistribution=None),
            _record("denied:c", {"eagle": _entry("https://x/c.brd", EAGLE_BRD)}, redistribution=False),
        ]
        self.assertEqual([s.board_id for s in mirror.select(records)], ["open:a"])

    def test_unavailable_and_unknown_files_are_not_selected(self) -> None:
        record = _record("open:a", {
            "eagle": _entry("https://x/a.brd", EAGLE_BRD),
            "step": _entry("https://x/a.step", b"", available=None),
            "bom": _entry("https://x/a.csv", b"", available=False),
        })
        self.assertEqual([s.url for s in mirror.select([record])], ["https://x/a.brd"])

    def test_documents_are_not_selected(self) -> None:
        record = _record("open:a", {
            "eagle": _entry("https://x/a.brd", EAGLE_BRD),
            "schematic": _entry("https://x/a.pdf", PDF),
            "bom": _entry("https://x/bom.csv", b"Ref,Value,Footprint\nR1,10k,0402\n"),
        })
        self.assertEqual([s.url for s in mirror.select([record])], ["https://x/a.brd"])

    def test_step_recorded_with_its_schema_is_cad(self) -> None:
        step = b"ISO-10303-21;\nHEADER;\n"
        record = _record("open:a", {
            "step": _entry("https://x/a.stp", step, detected="step:AUTOMOTIVE_DESIGN { 1 0 10303 214 3 1 1 }"),
        })
        self.assertEqual([s.url for s in mirror.select([record])], ["https://x/a.stp"])

    def test_altium_is_cad_and_a_spreadsheet_is_not(self) -> None:
        ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 64
        record = _record("open:a", {
            "altium": _entry("https://x/board.PcbDoc", ole, detected="ole"),
            "bom": _entry("https://x/bom.xls", ole, detected="ole"),
        })
        self.assertEqual([s.url for s in mirror.select([record])], ["https://x/board.PcbDoc"])

    def test_one_url_serving_several_formats_is_one_file(self) -> None:
        record = _record("open:a", {
            "eagle": _entry("https://x/a.brd", EAGLE_BRD),
            "pcb_source": _entry("https://x/a.brd", EAGLE_BRD),
        })
        sources = mirror.select([record])
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].formats, ["eagle", "pcb_source"])


class ClassificationTests(unittest.TestCase):
    def test_design_sources_and_fabrication_files_are_cad(self) -> None:
        for payload, name in ((EAGLE_BRD, "a.brd"), (KICAD_PCB, "a.kicad_pcb"), (GERBER, "a.gbl"),
                              (b"ISO-10303-21;\nHEADER;\n", "a.step"), (b"M48\nINCH\nT01C0.02\n", "a.drl")):
            with self.subTest(name=name):
                self.assertEqual(mirror.category(payload, name)[0], "cad")

    def test_binary_stl_is_cad(self) -> None:
        stl = b"\0" * 80 + (1).to_bytes(4, "little") + b"\0" * 50
        self.assertEqual(mirror.category(stl, "case.stl"), ("cad", "stl"))

    def test_pdf_and_bom_are_documents(self) -> None:
        self.assertEqual(mirror.category(PDF, "schematic.pdf"), ("docs", "pdf"))
        self.assertEqual(mirror.category(b"Ref,Value,Footprint\nR1,10k,0402\n", "bom.csv"), ("docs", "csv"))

    def test_web_pages_json_and_unknown_bytes_are_refused(self) -> None:
        for payload in (HTML, JSON, b"\x00\x01\x02 not a format"):
            with self.subTest(payload=payload[:12]):
                self.assertIsNone(mirror.category(payload, "a.brd")[0])

    def test_legacy_ole_is_decided_by_extension(self) -> None:
        ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 64
        self.assertEqual(mirror.category(ole, "board.PcbDoc"), ("cad", "altium"))
        self.assertEqual(mirror.category(ole, "bom.xls"), ("docs", "office"))
        self.assertIsNone(mirror.category(ole, "mystery.bin")[0])

    def test_an_archive_is_cad_only_when_it_holds_design_files(self) -> None:
        self.assertEqual(mirror.category(_zip({"gerbers/top.gtl": GERBER}), "fab.zip"), ("cad", "zip"))
        self.assertEqual(mirror.category(_zip({"manual.pdf": PDF}), "docs.zip"), ("docs", "zip"))
        self.assertEqual(mirror.category(_zip({"__MACOSX/._top.gtl": b"x", "a.pdf": PDF}), "z.zip"),
                         ("docs", "zip"))


class PathTests(unittest.TestCase):
    def test_board_directory_is_vendor_then_board(self) -> None:
        self.assertEqual(mirror.board_dir("sparkfun:qwiic-pocket").as_posix(),
                         "boards/cad/sparkfun/qwiic-pocket")

    def test_names_cannot_escape_the_board_directory(self) -> None:
        name = mirror.file_name("https://x/a/..%2F..%2Fetc%2Fpasswd", None)
        self.assertNotIn("/", name)
        self.assertNotIn("..", name)
        directory = mirror.board_dir("../../evil:../x")
        self.assertTrue(directory.as_posix().startswith("boards/cad/"))
        self.assertNotIn("..", directory.parts)

    def test_extension_is_added_from_content_when_the_url_has_none(self) -> None:
        self.assertEqual(mirror.file_name("https://www.ti.com/lit/zip/SPRM860", "zip"), "SPRM860.zip")
        self.assertEqual(mirror.file_name("https://x/Board%20v2.brd", "eagle"), "Board-v2.brd")

    def test_colliding_names_get_a_digest_prefix(self) -> None:
        record = _record("open:a", {
            "eagle": _entry("https://x/rev1/board.brd", EAGLE_BRD),
            "pcb_source": _entry("https://x/rev2/board.brd", EAGLE_BRD + b"<!-- rev2 -->"),
        })
        with tempfile.TemporaryDirectory() as tmp:
            fetcher = FakeFetcher({"https://x/rev1/board.brd": EAGLE_BRD,
                                   "https://x/rev2/board.brd": EAGLE_BRD + b"<!-- rev2 -->"})
            mirror.build(Path(tmp), [record], fetcher)
            names = sorted(p.name for p in (Path(tmp) / "boards/cad/open/a/cad").iterdir())
        self.assertEqual(len(names), 2)
        self.assertIn("board.brd", names)


class BuildTests(unittest.TestCase):
    def _build(self, records, payloads, vendors=()):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        return root, mirror.build(root, records, FakeFetcher(payloads), vendors)

    def test_only_cad_files_are_written_with_attribution_and_manifest(self) -> None:
        record = _record("open:a", {"eagle": _entry("https://x/a.brd", EAGLE_BRD),
                                    "schematic": _entry("https://x/a.pdf", PDF)})
        root, report = self._build([record], {"https://x/a.brd": EAGLE_BRD, "https://x/a.pdf": PDF})
        self.assertTrue(report.ok)
        self.assertEqual((root / "boards/cad/open/a/cad/a.brd").read_bytes(), EAGLE_BRD)
        self.assertFalse((root / "boards/cad/open/a/docs").exists())
        attribution = (root / "boards/cad/open/a/ATTRIBUTION.md").read_text(encoding="utf-8")
        self.assertIn("CC BY-SA 4.0", attribution)
        self.assertIn("https://x/a.brd", attribution)
        self.assertNotIn("https://x/a.pdf", attribution)
        self.assertIn("Changes: none", attribution)
        manifest = json.loads((root / mirror.MANIFEST_PATH).read_text(encoding="utf-8"))
        self.assertEqual({e["category"] for e in manifest["entries"]}, {"cad"})
        self.assertFalse(any(p.suffix == ".json" for p in (root / "boards/cad").rglob("*")))
        self.assertEqual(mirror.check(root, [record]), [])

    def test_bytes_that_differ_from_the_record_are_refused(self) -> None:
        record = _record("open:a", {"eagle": _entry("https://x/a.brd", EAGLE_BRD)})
        root, report = self._build([record], {"https://x/a.brd": EAGLE_BRD + b"tampered"})
        self.assertFalse(report.ok)
        self.assertIn("sha256", report.refused[0])
        self.assertFalse((root / "boards/cad/open/a/cad/a.brd").exists())

    def test_a_web_page_is_refused_even_when_its_digest_matches(self) -> None:
        record = _record("open:a", {"eagle": _entry("https://x/a.brd", HTML, detected="eagle")})
        root, report = self._build([record], {"https://x/a.brd": HTML})
        self.assertFalse(report.ok)
        self.assertIn("not a CAD file", report.refused[0])

    def test_a_rebuild_removes_documents_and_boards_left_without_cad(self) -> None:
        cad_board = _record("open:a", {"eagle": _entry("https://x/a.brd", EAGLE_BRD)})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mirror.build(root, [cad_board], FakeFetcher({"https://x/a.brd": EAGLE_BRD}))
            stale_doc = root / "boards/cad/open/a/docs/a.pdf"
            stale_doc.parent.mkdir(parents=True)
            stale_doc.write_bytes(PDF)
            empty_board = root / "boards/cad/open/docs-only"
            (empty_board / "docs").mkdir(parents=True)
            (empty_board / "docs" / "manual.pdf").write_bytes(PDF)
            (empty_board / "ATTRIBUTION.md").write_text("# old\n", encoding="utf-8")
            self.assertTrue(mirror.check(root, [cad_board]))
            report = mirror.build(root, [cad_board], FakeFetcher({}))
            self.assertIn("boards/cad/open/a/docs/a.pdf", report.removed)
            self.assertFalse(stale_doc.exists())
            self.assertFalse(empty_board.exists())
            self.assertEqual(mirror.check(root, [cad_board]), [])

    def test_an_unreachable_file_is_refused_not_skipped(self) -> None:
        record = _record("open:a", {"eagle": _entry("https://x/a.brd", EAGLE_BRD)})
        root, report = self._build([record], {})
        self.assertFalse(report.ok)
        self.assertEqual(mirror.check(root, [record]), ["missing: open:a https://x/a.brd"])

    def test_vendor_batches_accumulate_in_one_manifest(self) -> None:
        records = [_record("one:a", {"eagle": _entry("https://x/a.brd", EAGLE_BRD)}),
                   _record("two:b", {"eagle": _entry("https://x/b.brd", KICAD_PCB)})]
        payloads = {"https://x/a.brd": EAGLE_BRD, "https://x/b.brd": KICAD_PCB}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mirror.build(root, records, FakeFetcher(payloads), ["one"])
            self.assertEqual(len(mirror.check(root, records)), 1)
            mirror.build(root, records, FakeFetcher(payloads), ["two"])
            self.assertEqual(mirror.check(root, records), [])


    def test_a_rebuild_reuses_mirrored_files_without_fetching(self) -> None:
        record = _record("open:a", {"eagle": _entry("https://x/a.brd", EAGLE_BRD)})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mirror.build(root, [record], FakeFetcher({"https://x/a.brd": EAGLE_BRD}))
            report = mirror.build(root, [record], FakeFetcher({}))
            self.assertTrue(report.ok)
            self.assertEqual(report.unchanged, ["boards/cad/open/a/cad/a.brd"])
            self.assertEqual(mirror.check(root, [record]), [])

    def test_a_mirrored_file_that_no_longer_matches_is_fetched_again(self) -> None:
        record = _record("open:a", {"eagle": _entry("https://x/a.brd", EAGLE_BRD)})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mirror.build(root, [record], FakeFetcher({"https://x/a.brd": EAGLE_BRD}))
            (root / "boards/cad/open/a/cad/a.brd").write_bytes(b"corrupted")
            report = mirror.build(root, [record], FakeFetcher({"https://x/a.brd": EAGLE_BRD}))
            self.assertEqual(report.written, ["boards/cad/open/a/cad/a.brd"])
            self.assertEqual((root / "boards/cad/open/a/cad/a.brd").read_bytes(), EAGLE_BRD)

class CheckTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.record = _record("open:a", {"eagle": _entry("https://x/a.brd", EAGLE_BRD)})
        mirror.build(self.root, [self.record], FakeFetcher({"https://x/a.brd": EAGLE_BRD}))
        self.file = self.root / "boards/cad/open/a/cad/a.brd"

    def _pointer(self, data: bytes) -> bytes:
        return (b"version https://git-lfs.github.com/spec/v1\noid sha256:"
                + _sha(data).encode() + b"\nsize " + str(len(data)).encode() + b"\n")

    def test_an_lfs_pointer_with_the_right_oid_passes(self) -> None:
        self.file.write_bytes(self._pointer(EAGLE_BRD))
        self.assertEqual(mirror.check(self.root, [self.record]), [])

    def test_an_lfs_pointer_with_the_wrong_oid_fails(self) -> None:
        self.file.write_bytes(self._pointer(EAGLE_BRD + b"x"))
        self.assertTrue(any("digest mismatch" in p for p in mirror.check(self.root, [self.record])))

    def test_a_deleted_file_fails(self) -> None:
        self.file.unlink()
        self.assertTrue(any("file absent" in p for p in mirror.check(self.root, [self.record])))

    def test_a_board_that_lost_its_licence_fails(self) -> None:
        withdrawn = dict(self.record, licenses=dict(self.record["licenses"], redistribution_allowed=None))
        problems = mirror.check(self.root, [withdrawn])
        self.assertTrue(any("not redistributable" in p for p in problems))

    def test_a_loose_file_in_the_mirror_root_fails(self) -> None:
        (self.root / "boards/cad/notes.json").write_text("{}", encoding="utf-8")
        self.assertTrue(any("stray file" in p for p in mirror.check(self.root, [self.record])))

    def test_a_stray_file_in_the_store_fails(self) -> None:
        (self.file.parent / "extra.brd").write_bytes(EAGLE_BRD)
        self.assertTrue(any("untracked file" in p for p in mirror.check(self.root, [self.record])))


class CommittedMirrorTests(unittest.TestCase):
    """The mirror in this repository is complete and every file is the verified one."""

    def test_committed_mirror_is_complete_and_intact(self) -> None:
        records = mirror.load_records(REPO_ROOT)
        self.assertTrue((REPO_ROOT / mirror.MANIFEST_PATH).is_file())
        self.assertEqual(mirror.check(REPO_ROOT, records), [])


if __name__ == "__main__":
    unittest.main()
