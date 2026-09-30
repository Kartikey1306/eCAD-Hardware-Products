"""Regression tests for the repository CI workflow and test entry point."""

import io
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest import mock

import run_all_tests


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"


def _job(workflow: str, name: str) -> Dict[str, Any]:
    """One job of the workflow, read strictly in the layout ci.yml uses.

    No YAML parser is installed, so this reads the two-space layout itself:
    job keys at four spaces, env entries at six, steps at six ("- ") with
    their keys at eight, and anything deeper (a block scalar's lines, the
    entries of with: or env:) appended to the key above it. A line in any
    other place fails the test rather than being skipped.

    Returns:
        {"keys": job keys and their values, "env": the job's env entries,
        "steps": each step's keys and values, "text": the job's lines}.
    """
    lines = workflow.split("\n")
    start = lines.index(f"  {name}:")
    body = []
    for line in lines[start + 1:]:
        if line.strip() and not line.startswith("    "):
            break
        body.append(line)
    keys: Dict[str, str] = {}
    env: Dict[str, str] = {}
    steps: list = []
    section, current = "", ""
    for line in body:
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 4:
            section, _, value = text.partition(":")
            keys[section] = value.strip()
        elif section == "env" and indent == 6:
            key, _, value = text.partition(":")
            env[key] = value.strip()
        elif section == "steps" and indent == 6 and text.startswith("- "):
            current, _, value = text[2:].partition(":")
            steps.append({current: value.strip()})
        elif section == "steps" and indent == 8 and steps:
            current, _, value = text.partition(":")
            steps[-1][current] = value.strip()
        elif section == "steps" and indent >= 10 and steps:
            steps[-1][current] = f"{steps[-1][current]}\n{text}"
        else:
            raise AssertionError(f"job {name}: a line this reader does not place: {line!r}")
    return {"keys": keys, "env": env, "steps": steps, "text": "\n".join(body)}


class TestCIWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    def test_targets_repository_default_branch(self):
        self.assertIn("branches: [master, develop]", self.workflow)
        self.assertIn("branches: [master]", self.workflow)
        self.assertNotIn("branches: [main", self.workflow)

    def test_installs_checked_in_requirements(self):
        self.assertIn("cache-dependency-path: tools/requirements.txt", self.workflow)
        self.assertIn(
            "python -m pip install -r tools/requirements.txt",
            self.workflow,
        )

    def test_runs_complete_suite_through_repository_runner(self):
        self.assertIn("run: python run_all_tests.py --tb=short", self.workflow)
        for incomplete_path in (
            "tests/unit/",
            "tests/functional/",
            "tests/performance/",
            "tests/simulation/",
        ):
            self.assertNotIn(incomplete_path, self.workflow)

    def test_executes_and_verifies_complete_inventory_evidence(self):
        self.assertIn("validation-evidence:", self.workflow)
        self.assertIn("validate --all", self.workflow)
        self.assertIn("--mode evidence", self.workflow)
        self.assertIn("verify-bundle", self.workflow)
        self.assertIn("uses: actions/upload-artifact@v4", self.workflow)
        self.assertIn("needs: [test, validation-evidence]", self.workflow)

    def test_does_not_attempt_to_build_absent_python_package(self):
        self.assertNotIn("python -m build", self.workflow)
        self.assertNotIn("dist/*.whl", self.workflow)

    def assert_the_suite_runs_whole_and_required(self, name: str, variable: str) -> None:
        """The job runs, unconditionally, the whole suite with the variable set to 1.

        Each of these read as green with the simulation tests skipped, and
        the substring checks of the tests below let every one through: an
        `if:` on the job, `|| true` after the suite, `--ignore`, `--deselect`
        or `-k` on it, and the variable set to 0 in a step's own env.
        """
        job = _job(self.workflow, name)
        self.assertEqual(set(job["keys"]), {"name", "runs-on", "env", "steps"}, "no if:, continue-on-error or matrix")
        self.assertEqual(job["env"], {variable: '"1"'})
        self.assertEqual(job["text"].count(variable), 1, "set once, for the whole job, and never overridden")
        suite = [step for step in job["steps"] if "run_all_tests.py" in step.get("run", "")]
        self.assertEqual(len(suite), 1)
        self.assertEqual(set(suite[0]), {"name", "run"}, "the suite step has no if:, env or continue-on-error")
        self.assertEqual(suite[0]["run"], "python run_all_tests.py --tb=short")
        for step in job["steps"]:
            self.assertNotIn("continue-on-error", step)
            self.assertNotIn(variable, step.get("env", ""))
            for flag in ("||", "--ignore", "--deselect", " -k ", " -k="):
                self.assertNotIn(flag, step.get("run", ""))

    def test_the_job_reader_refuses_a_line_it_cannot_place(self):
        with self.assertRaisesRegex(AssertionError, "a line this reader does not place"):
            _job("jobs:\n  spice:\n    steps:\n     - run: x\n", "spice")
        job = _job("jobs:\n  spice:\n    if: false\n    env:\n      A: \"1\"\n    steps:\n      - name: s\n"
                   "        run: |\n          a\n          b\n  next:\n", "spice")
        self.assertEqual((job["keys"]["if"], job["env"], job["steps"]), ("false", {"A": '"1"'}, [{"name": "s", "run": "|\na\nb"}]))

    def test_cad_dataset_job_cannot_skip_silently(self):
        """The dataset tests skip without the CAD kernel. The one job that installs
        it must turn a skip into a failure, or a broken install reads as green."""
        self.assert_the_suite_runs_whole_and_required("cad-dataset", "ECAD_REQUIRE_CAD_TOOLS")
        start = self.workflow.index("\n  cad-dataset:\n")
        following = self.workflow.find("\n  release:\n", start)
        job = self.workflow[start:following]
        self.assertIn('ECAD_REQUIRE_CAD_TOOLS: "1"', job)
        self.assertIn("-r tools/requirements-cad.txt", job)
        # Every transitive CAD dependency is pinned (SECURITY-STANDARDS.md).
        self.assertIn("-c tools/constraints-cad.txt", job)
        self.assertIn("apt-get install -y libgl1", job)  # the CAD kernel links libGL
        self.assertIn("run: python run_all_tests.py --tb=short", job)  # the whole suite, not a subset
        self.assertIn("python tools/cad_dataset.py check datasets/cad/robotic_joint_001", job)
        self.assertNotIn("continue-on-error", job)

    def test_spice_job_cannot_skip_silently(self):
        """The electrical simulation tests skip without ngspice. The one job that
        installs it must turn a skip into a failure, or a missing simulator reads as green."""
        self.assert_the_suite_runs_whole_and_required("spice", "ECAD_REQUIRE_SPICE_TOOLS")
        start = self.workflow.index("\n  spice:\n")
        # Before cad-dataset, so the slice of the test above still ends at release.
        self.assertLess(self.workflow.index("\n  validation-evidence:\n"), start)
        following = self.workflow.index("\n  cad-dataset:\n", start)
        job = self.workflow[start:following]
        self.assertIn('ECAD_REQUIRE_SPICE_TOOLS: "1"', job)
        self.assertIn("sudo apt-get install -y ngspice", job)  # a system package, not on PyPI
        self.assertIn("ngspice --version", job)  # the version every receipt records, in the job's log
        self.assertIn("python -m pip install -r tools/requirements.txt pytest", job)
        self.assertIn("run: python run_all_tests.py --tb=short", job)  # the whole suite, not a subset
        self.assertIn("python tools/cad_dataset.py check datasets/cad/servo_supply_001", job)
        self.assertIn("python tools/cad_dataset.py validate datasets/cad/servo_supply_001", job)
        self.assertIn("--output electrical-validation", job)
        self.assertIn("uses: actions/upload-artifact@v4", job)
        self.assertIn("path: electrical-validation/", job)
        self.assertIn("if-no-files-found: error", job)
        self.assertNotIn("continue-on-error", job)


class TestTestRunner(unittest.TestCase):
    @mock.patch("run_all_tests.subprocess.run")
    def test_runs_entire_tests_tree_with_current_python(self, run):
        run.return_value = subprocess.CompletedProcess(args=[], returncode=7)
        stdout = io.StringIO()

        with mock.patch("sys.stdout", stdout):
            returncode = run_all_tests.main(["--tb=short"])

        run.assert_called_once_with(
            [sys.executable, "-m", "pytest", "tests", "-v", "--tb=short"],
            check=False,
        )
        self.assertEqual(returncode, 7)
        self.assertIn("complete test suite", stdout.getvalue())
        self.assertNotIn("production-ready", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
