"""Issue #28: dev-board records validate, and every claim in them is accountable.

These are invariants over the *database*, not over its current emptiness. The seed records
carry no availability yet, but the suite must stay meaningful as records are populated, so
nothing here asserts that a query matches zero rows. What it asserts instead is that a row
only ever appears in a positive result when the evidence behind it would survive an audit.
"""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from devboard_cad.query import (  # noqa: E402
    FILE_FORMATS,
    cmd_commercial,
    cmd_mechanical,
    cmd_with,
    load_records,
)
from devboard_cad.verify import derive_status  # noqa: E402
from jsonschema import Draft7Validator  # noqa: E402

RECORDS_DIR = REPO_ROOT / "tools" / "devboard_cad" / "records"


def _schema() -> dict:
    return json.loads(
        (
            REPO_ROOT / "schemas" / "devboard-cad" / "v1" / "board-record.schema.json"
        ).read_text(encoding="utf-8")
    )


class FakeArgs:
    def __init__(self, root: Path, formats: list[str] | None = None) -> None:
        self.root = str(root)
        self.formats = formats or []


def _run(command, args) -> str:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        command(args)
    return buffer.getvalue()


class TestDevboardDatabase(unittest.TestCase):
    def test_every_record_conforms_to_schema(self) -> None:
        schema = _schema()
        Draft7Validator.check_schema(schema)
        records = load_records(REPO_ROOT)
        self.assertGreaterEqual(len(records), 5)
        for record in records:
            errors = list(Draft7Validator(schema).iter_errors(record))
            self.assertEqual(errors, [], f"{record.get('board_id')}: {errors[:2]}")

    def test_record_status_matches_the_data(self) -> None:
        """record_status is derived, so a hand-edited record cannot misreport itself."""
        for record in load_records(REPO_ROOT):
            self.assertEqual(
                record["record_status"],
                derive_status(record),
                f"{record['board_id']}: record_status disagrees with its own files",
            )

    def test_positive_claims_carry_retrievable_evidence(self) -> None:
        """available=true means somebody fetched bytes and kept the digest."""
        for record in load_records(REPO_ROOT):
            for name, entry in record["files"].items():
                if entry.get("available") is not True:
                    continue
                evidence = entry.get("evidence")
                self.assertIsInstance(
                    evidence, dict, f"{record['board_id']}.{name}: no evidence"
                )
                self.assertRegex(
                    evidence.get("sha256") or "",
                    r"^[0-9a-f]{64}$",
                    f"{record['board_id']}.{name}: evidence has no digest",
                )
                self.assertTrue(
                    entry.get("url"), f"{record['board_id']}.{name}: no URL"
                )

    def test_absence_claims_cite_a_definitive_source(self) -> None:
        """available=false is a claim too: it needs a 404 or an exhaustive official index."""
        for record in load_records(REPO_ROOT):
            for name, entry in record["files"].items():
                if entry.get("available") is not False:
                    continue
                evidence = entry.get("evidence") or {}
                method = evidence.get("verification_method")
                self.assertIn(
                    method,
                    ("http_get_absent", "official_index_absent"),
                    f"{record['board_id']}.{name}: absence asserted via '{method}'",
                )
                if method == "official_index_absent":
                    self.assertTrue(
                        evidence.get("index_ref"),
                        f"{record['board_id']}.{name}: no index cited",
                    )
                else:
                    self.assertIn(
                        evidence.get("http_status"),
                        (404, 410),
                        f"{record['board_id']}.{name}: absence without a 404/410",
                    )

    def test_unknown_never_carries_evidence(self) -> None:
        """This is what keeps 'we have not looked' distinct from 'we looked and it is not there'."""
        for record in load_records(REPO_ROOT):
            for name, entry in record["files"].items():
                if entry.get("available") is None:
                    self.assertIsNone(
                        entry.get("evidence"),
                        f"{record['board_id']}.{name}: unknown must not carry evidence",
                    )

    def test_board_id_is_unique_and_matches_its_filename(self) -> None:
        seen: dict[str, str] = {}
        for path in sorted(RECORDS_DIR.glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            board_id = record["board_id"]
            self.assertNotIn(
                board_id, seen, f"{board_id} duplicated in {seen.get(board_id)} and {path.name}"
            )
            seen[board_id] = path.name
            self.assertEqual(
                path.stem,
                board_id.replace(":", "__"),
                f"{path.name} does not match board_id {board_id}",
            )

    def test_commercial_reuse_claims_cite_a_licence(self) -> None:
        """The field with real downstream consequences may not be asserted bare."""
        for record in load_records(REPO_ROOT):
            licenses = record["licenses"]
            for field in ("commercial_use_allowed", "modification_allowed",
                          "redistribution_allowed"):
                if licenses.get(field) is not None:
                    self.assertTrue(
                        licenses.get("license_url"),
                        f"{record['board_id']}: {field} decided with no license_url",
                    )
                    self.assertNotEqual(
                        licenses.get("hardware_license"),
                        "UNVERIFIED",
                        f"{record['board_id']}: {field} decided with no named licence",
                    )

    def test_community_sources_are_justified(self) -> None:
        """Issue #28 section 10 makes a community source a last resort, not a default."""
        for record in load_records(REPO_ROOT):
            if record["sources"]["source_tier"] == "community":
                self.assertTrue(
                    (record.get("notes") or "").strip(),
                    f"{record['board_id']}: community tier with no justification",
                )

    def test_every_schema_format_is_queryable(self) -> None:
        """A format the schema can express but the CLI cannot filter on is invisible."""
        declared = set(_schema()["properties"]["files"]["properties"])
        self.assertEqual(
            declared - set(FILE_FORMATS),
            set(),
            "schema declares formats that query.py cannot filter on",
        )

    def test_positive_queries_round_trip(self) -> None:
        """A verified row must be findable, and an unverified one must stay invisible."""
        records = load_records(REPO_ROOT)
        verified_step = {
            r["board_id"] for r in records
            if r["files"].get("step", {}).get("available") is True
        }
        output = _run(cmd_mechanical, FakeArgs(REPO_ROOT))
        for board_id in verified_step:
            self.assertIn(board_id, output, f"{board_id} has STEP but 'mechanical' missed it")

        not_available = {
            r["board_id"] for r in records
            if r["files"].get("step", {}).get("available") is not True
            and r["files"].get("mechanical", {}).get("available") is not True
        }
        for board_id in not_available:
            self.assertNotIn(
                board_id, output, f"{board_id} has no verified mechanical CAD but matched"
            )

    def test_unknown_is_never_counted_as_a_yes(self) -> None:
        records = load_records(REPO_ROOT)
        expected = sum(
            1 for r in records
            if r["files"].get("step", {}).get("available") is True
        )
        output = _run(cmd_with, FakeArgs(REPO_ROOT, ["step"]))
        self.assertIn(f"matched={expected}", output)

    def test_commercial_query_requires_both_permissions(self) -> None:
        records = load_records(REPO_ROOT)
        expected = sum(
            1 for r in records
            if r["licenses"].get("modification_allowed") is True
            and r["licenses"].get("commercial_use_allowed") is True
        )
        output = _run(cmd_commercial, FakeArgs(REPO_ROOT))
        self.assertIn(f"matched={expected}", output)


if __name__ == "__main__":
    unittest.main()
