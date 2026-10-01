"""robotic_joint_001's intent_tracking scenario: closed-loop task metrics.

The scenario exists so that "the simulation ran" is never mistaken for "the
joint did its job". These tests check that its metrics catch the failures they
claim to catch, not only that the committed trace passes.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import unittest
from importlib import util
from pathlib import Path

ITEM = Path(__file__).resolve().parents[2] / "datasets" / "cad" / "robotic_joint_001"


def require(*modules: str) -> None:
    """Skip without the CAD toolchain, unless CI says it must be there (as test_cad_dataset does)."""
    missing = [name for name in modules if importlib.util.find_spec(name) is None]
    if not missing:
        return
    message = f"needs {', '.join(missing)} (pip install -r tools/requirements-cad.txt)"
    if os.environ.get("ECAD_REQUIRE_CAD_TOOLS") == "1":
        raise AssertionError(f"ECAD_REQUIRE_CAD_TOOLS=1 but this environment {message}")
    raise unittest.SkipTest(message)


MODEL = ITEM / "derived" / "mechanical" / "robotic_joint_001.mjcf.xml"


def _requirement_scenario():
    requirements = json.loads((ITEM / "requirements" / "requirements.json").read_text(encoding="utf-8"))
    entry = next(r for r in requirements["requirements"] if r["requirement_id"] == "REQ-MECH-006")
    return entry["scenario"]


class TestIntentTracking(unittest.TestCase):
    def setUp(self) -> None:
        require("mujoco")
        spec = util.spec_from_file_location("joint_dynamics", ITEM / "simulation" / "joint_dynamics.py")
        self.script = util.module_from_spec(spec)
        spec.loader.exec_module(self.script)

    def run_scenario(self, scenario):
        return self.script.intent_tracking(self.script.load(str(MODEL), scenario), scenario)

    def test_committed_trace_meets_every_tracking_requirement(self):
        metrics = self.run_scenario(_requirement_scenario())
        self.assertEqual(metrics["intents_applied"], 13.0)
        self.assertEqual(metrics["setpoints_reached_fraction"], 1.0)
        self.assertEqual(metrics["range_violation"], 0.0)
        self.assertEqual(metrics["torque_saturated_fraction"], 0.0)
        self.assertLessEqual(metrics["track_peak_torque_abs_nm"], 3.0)
        self.assertLessEqual(metrics["track_peak_speed_rad_s"], 5.0)
        # Eleven move_left steps of 0.25 rad would pass the -2.094 rad stop;
        # the margin clamps exactly one setpoint, and the run says so.
        self.assertEqual(metrics["setpoints_clamped"], 1.0)
        self.assertAlmostEqual(metrics["final_angle_rad"], 0.0, places=6)

    def test_an_aggressive_reference_is_reported_as_saturating(self):
        scenario = copy.deepcopy(_requirement_scenario())
        scenario["max_reference_accel_rad_s2"] = 200.0
        scenario["max_reference_speed_rad_s"] = 20.0
        metrics = self.run_scenario(scenario)
        self.assertGreater(metrics["torque_saturated_fraction"], 0.0)
        self.assertEqual(metrics["track_peak_torque_abs_nm"], scenario["torque_limit_nm"])

    def test_a_weak_actuator_misses_setpoints(self):
        scenario = copy.deepcopy(_requirement_scenario())
        scenario["torque_limit_nm"] = 1.0  # below the ~1.68 N*m it takes to hold the arm level
        metrics = self.run_scenario(scenario)
        self.assertLess(metrics["setpoints_reached_fraction"], 1.0)
        self.assertGreater(metrics["settle_error_max_rad"], scenario["settle_tolerance_rad"])

    def test_unknown_intent_is_an_error_not_a_no_op(self):
        scenario = copy.deepcopy(_requirement_scenario())
        scenario["intents"] = ["move_left", "jump"]
        with self.assertRaisesRegex(ValueError, "unknown intent 'jump'"):
            self.run_scenario(scenario)

    def test_a_move_that_cannot_finish_within_the_dwell_is_refused(self):
        scenario = copy.deepcopy(_requirement_scenario())
        scenario["dwell_s"] = 0.2
        with self.assertRaisesRegex(ValueError, "longer than dwell_s"):
            self.run_scenario(scenario)


if __name__ == "__main__":
    unittest.main()
