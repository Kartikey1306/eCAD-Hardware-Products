"""KiCad file-format regression test (eCAD-Hardware-Products#50).

The KiCad file format is an s-expression with no comment syntax, but
tools/cad_render.py used to emit `;` comment lines into generated
`.kicad_pcb` files (and three `.kicad_sch` files carried `;;` banner
lines). Viewers like KiCanvas refuse such files outright
("Unexpected character ... : ;").

This test strictly scans every committed `.kicad_pcb` and `.kicad_sch`
and fails on any `;` outside a string literal, so a regenerated file
can never reintroduce them. Parenthesis balance is checked as well —
cheap insurance against truncated generation.
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def scan_kicad(text: str) -> list[str]:
    """Return a list of problems found in KiCad s-expression text."""
    problems = []
    in_string = False
    escaped = False
    depth = 0
    for lineno, line in enumerate(text.splitlines(), 1):
        for ch in line:
            if escaped:
                escaped = False
                continue
            if ch == "\\" and in_string:
                escaped = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == ";":
                problems.append(f"line {lineno}: ';' outside string literal: {line.strip()[:80]}")
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    problems.append(f"line {lineno}: unbalanced ')'")
                    depth = 0
    if in_string:
        problems.append("unterminated string literal at end of file")
    if depth != 0:
        problems.append(f"unbalanced parentheses at end of file (depth {depth})")
    return problems


class TestKicadNoCommentLines(unittest.TestCase):
    def test_no_comment_lines_in_committed_kicad_files(self):
        files = sorted(REPO_ROOT.rglob("*.kicad_pcb")) + sorted(REPO_ROOT.rglob("*.kicad_sch"))
        self.assertGreater(len(files), 0, "no KiCad files found under the repo root")
        failures = {}
        for path in files:
            problems = scan_kicad(path.read_text(encoding="utf-8", errors="replace"))
            if problems:
                failures[path.relative_to(REPO_ROOT).as_posix()] = problems
        if failures:
            detail = "\n".join(
                f"  {name}:\n" + "\n".join(f"    - {p}" for p in probs[:5])
                for name, probs in sorted(failures.items())
            )
            self.fail(
                f"{len(failures)} KiCad file(s) contain ';' comments or "
                f"malformed s-expressions:\n{detail}"
            )


if __name__ == "__main__":
    unittest.main()
