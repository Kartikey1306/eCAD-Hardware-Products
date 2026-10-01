#!/usr/bin/env python3
"""Mechanical scenarios for a single revolute joint, simulated with MuJoCo.

Executed by the eCAD mujoco adapter in an isolated workspace holding only its
declared inputs: this script and the generated MJCF model. It prints one JSON
object of metrics as its last line, which the V3/V4 cases compare against
requirements. The script never decides pass or fail.

Scenarios (the --scenario JSON object's "name"):

    static_sweep  Torque the actuator must supply to hold the joint still,
                  by inverse dynamics at every pose across the joint range.
    rated_move    Peak torque, speed and acceleration of a minimum-jerk move.
    rom_sweep     Minimum clearance between the moving and fixed parts across
                  the joint range, using the model's collision proxies.
    free_swing    Period of small free oscillation about the stable
                  equilibrium, integrated forward in time.
    intent_tracking
                  Closed loop: a sequence of decoded intents (eNI's
                  move_left / move_right / select / ...) becomes joint
                  setpoints. Each move follows a minimum-jerk reference, and
                  computed torque (inverse dynamics of the reference) plus PD
                  on the tracking error drives the joint under forward
                  dynamics, saturated at the actuator limit. The run reports
                  whether each setpoint was reached and what that cost in
                  torque and speed. These are task metrics, not "the
                  simulation ran".

Every scenario except rom_sweep runs with contact disabled: the collision
proxies are conservative boxes for clearance checking, and must never push on
the dynamics. free_swing also disables the joint limits, because it measures
the pendulum's physics about its hanging equilibrium, which lies outside the
design's range of motion.

All scenarios are deterministic; ECAD_VALIDATION_SEED is accepted and unused.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Any, Dict, List, Set, Tuple

import mujoco
import numpy as np

SWEEP_SAMPLES = 721
MOVE_STEP_S = 1e-3
SWING_DURATION_S = 30.0
SWING_MIN_CROSSINGS = 6
CLEARANCE_SEARCH_M = 1.0


def load(path: str, scenario: Dict[str, Any]) -> mujoco.MjModel:
    model = mujoco.MjModel.from_xml_path(path)
    if "payload_mass_kg" in scenario:
        body = model.body(scenario["payload_component"]).id
        ratio = scenario["payload_mass_kg"] / model.body_mass[body]
        # Same shape at a different uniform density: the centre of mass stays
        # put and the inertia scales with the mass.
        model.body_mass[body] *= ratio
        model.body_inertia[body] *= ratio
    return model


def hinge(model: mujoco.MjModel) -> Tuple[int, int, float, float]:
    if model.njnt != 1 or model.jnt_type[0] != mujoco.mjtJoint.mjJNT_HINGE:
        raise ValueError("the model must have exactly one hinge joint")
    low, high = (float(value) for value in model.jnt_range[0])
    return int(model.jnt_qposadr[0]), int(model.jnt_bodyid[0]), low, high


def subtree(model: mujoco.MjModel, root: int) -> Set[int]:
    members = {root}
    for body in range(model.nbody):
        ancestor = body
        while ancestor > 0 and ancestor not in members:
            ancestor = int(model.body_parentid[ancestor])
        if ancestor in members:
            members.add(body)
    return members


def moving_mass(model: mujoco.MjModel, root: int) -> float:
    return float(sum(model.body_mass[body] for body in subtree(model, root)))


def holding_torque(model: mujoco.MjModel, data: mujoco.MjData, address: int, q: float) -> float:
    data.qpos[address] = q
    data.qvel[:] = 0.0
    data.qacc[:] = 0.0
    mujoco.mj_inverse(model, data)
    return float(data.qfrc_inverse[address])


def static_sweep(model: mujoco.MjModel, scenario: Dict[str, Any]) -> Dict[str, float]:
    model.opt.disableflags |= mujoco.mjtDisableBit.mjDSBL_CONTACT
    address, body, low, high = hinge(model)
    data = mujoco.MjData(model)
    torques = [abs(holding_torque(model, data, address, q)) for q in np.linspace(low, high, SWEEP_SAMPLES)]
    metrics = {
        "static_torque_max_abs_nm": max(torques),
        "moving_mass_kg": moving_mass(model, body),
    }
    if low <= 0.0 <= high:
        metrics["static_torque_at_zero_nm"] = abs(holding_torque(model, data, address, 0.0))
    return metrics


def rated_move(model: mujoco.MjModel, scenario: Dict[str, Any]) -> Dict[str, float]:
    model.opt.disableflags |= mujoco.mjtDisableBit.mjDSBL_CONTACT
    address, body, low, high = hinge(model)
    start, end, duration = scenario["start_rad"], scenario["end_rad"], scenario["duration_s"]
    for label, value in (("start", start), ("end", end)):
        if not low <= value <= high:
            raise ValueError(f"rated move {label} {value} rad is outside the joint range [{low}, {high}]")
    data = mujoco.MjData(model)
    delta = end - start
    peaks = {"torque": 0.0, "speed": 0.0, "accel": 0.0}
    for step in range(int(round(duration / MOVE_STEP_S)) + 1):
        s = min(1.0, step * MOVE_STEP_S / duration)
        # Minimum-jerk profile: q = start + delta * (10 s^3 - 15 s^4 + 6 s^5).
        data.qpos[address] = start + delta * (10 * s**3 - 15 * s**4 + 6 * s**5)
        data.qvel[address] = delta * (30 * s**2 - 60 * s**3 + 30 * s**4) / duration
        data.qacc[address] = delta * (60 * s - 180 * s**2 + 120 * s**3) / duration**2
        mujoco.mj_inverse(model, data)
        peaks["torque"] = max(peaks["torque"], abs(float(data.qfrc_inverse[address])))
        peaks["speed"] = max(peaks["speed"], abs(float(data.qvel[address])))
        peaks["accel"] = max(peaks["accel"], abs(float(data.qacc[address])))
    return {
        "move_peak_torque_abs_nm": peaks["torque"],
        "move_peak_speed_rad_s": peaks["speed"],
        "move_peak_accel_rad_s2": peaks["accel"],
        "moving_mass_kg": moving_mass(model, body),
    }


def checked_pairs(model: mujoco.MjModel, moving: Set[int]) -> List[Tuple[int, int]]:
    """Geom pairs between the moving and fixed sides that the model does not exclude."""
    excluded = set()
    for signature in model.exclude_signature:
        first, second = int(signature) >> 16, int(signature) & 0xFFFF
        excluded.add(frozenset((first, second)))
    pairs = []
    for g1 in range(model.ngeom):
        for g2 in range(model.ngeom):
            b1, b2 = int(model.geom_bodyid[g1]), int(model.geom_bodyid[g2])
            if b1 in moving and b2 not in moving and frozenset((b1, b2)) not in excluded:
                pairs.append((g1, g2))
    return pairs


def rom_sweep(model: mujoco.MjModel, scenario: Dict[str, Any]) -> Dict[str, float]:
    address, body, low, high = hinge(model)
    moving = subtree(model, body)
    parent = int(model.body_parentid[body])
    joint_pair = frozenset((parent, body))
    excluded = {frozenset((int(s) >> 16, int(s) & 0xFFFF)) for s in model.exclude_signature}
    if joint_pair in excluded:
        # The joint is realised by its own parent or child, so their box
        # proxies overlap by construction and the pair cannot be checked. No
        # clearance metric is reported: a requirement on it is INCONCLUSIVE.
        return {"rom_joint_pair_unchecked": 1.0}
    pairs = checked_pairs(model, moving)
    if not pairs:
        raise ValueError("no moving-versus-fixed geometry pair is checked; clearance would be vacuous")
    data = mujoco.MjData(model)
    minimum = math.inf
    colliding_poses = 0
    for q in np.linspace(low, high, SWEEP_SAMPLES):
        data.qpos[address] = q
        mujoco.mj_kinematics(model, data)
        pose_minimum = min(
            mujoco.mj_geomDistance(model, data, g1, g2, CLEARANCE_SEARCH_M, None) for g1, g2 in pairs
        )
        minimum = min(minimum, pose_minimum)
        colliding_poses += pose_minimum < 0.0
    return {
        "rom_min_clearance_m": float(minimum),
        "rom_colliding_poses": float(colliding_poses),
        "rom_checked_pairs": float(len(pairs)),
    }


def free_swing(model: mujoco.MjModel, scenario: Dict[str, Any]) -> Dict[str, float]:
    model.opt.disableflags |= mujoco.mjtDisableBit.mjDSBL_CONTACT | mujoco.mjtDisableBit.mjDSBL_LIMIT
    address, body, _low, _high = hinge(model)
    data = mujoco.MjData(model)

    def height(q: float) -> float:
        data.qpos[address] = q
        mujoco.mj_forward(model, data)
        return float(data.subtree_com[body][2])

    grid = np.linspace(-math.pi, math.pi, 3601)
    q_low = float(grid[int(np.argmin([height(q) for q in grid]))])
    step = grid[1] - grid[0]
    a, b = q_low - step, q_low + step
    ratio = (math.sqrt(5) - 1) / 2
    for _ in range(100):  # golden-section refinement of the potential minimum
        c, d = b - ratio * (b - a), a + ratio * (b - a)
        a, b = (a, d) if height(c) < height(d) else (c, b)
    equilibrium = (a + b) / 2

    mujoco.mj_resetData(model, data)
    data.qpos[address] = equilibrium + scenario["amplitude_rad"]
    crossings: List[float] = []
    previous = data.qpos[address] - equilibrium
    while data.time < SWING_DURATION_S and len(crossings) < SWING_MIN_CROSSINGS + 1:
        t0 = data.time
        mujoco.mj_step(model, data)
        current = data.qpos[address] - equilibrium
        if previous < 0.0 <= current:
            crossings.append(t0 + (data.time - t0) * (-previous) / (current - previous))
        previous = current
    if len(crossings) < SWING_MIN_CROSSINGS:
        raise ValueError(f"only {len(crossings)} oscillation crossings in {SWING_DURATION_S} s")
    return {
        "small_oscillation_period_s": (crossings[-1] - crossings[0]) / (len(crossings) - 1),
        "equilibrium_angle_rad": equilibrium,
    }


# Intent vocabulary of eNI's simulator provider, and the setpoint change each
# one commands, in units of step_rad. "select"/"activate" hold the current
# setpoint and "deactivate" returns to the as-modelled pose (0 rad). Anything
# else is an error, so a renamed intent cannot silently become "do nothing".
INTENT_STEPS = {
    "move_left": -1.0,
    "move_right": 1.0,
    "scroll_up": 0.5,
    "scroll_down": -0.5,
    "select": 0.0,
    "activate": 0.0,
}
TRACK_STEP_S = 5e-4
# Peaks of a minimum-jerk move over distance d in time T:
# speed 1.875 d / T, acceleration 10 / sqrt(3) d / T^2.
MIN_JERK_PEAK_SPEED = 1.875
MIN_JERK_PEAK_ACCEL = 10 / math.sqrt(3)


def intent_tracking(model: mujoco.MjModel, scenario: Dict[str, Any]) -> Dict[str, float]:
    model.opt.disableflags |= mujoco.mjtDisableBit.mjDSBL_CONTACT
    model.opt.timestep = TRACK_STEP_S
    address, _body, low, high = hinge(model)
    intents = scenario["intents"]
    if not intents:
        raise ValueError("intent_tracking needs at least one intent")
    step, dwell = scenario["step_rad"], scenario["dwell_s"]
    kp, kd = scenario["kp"], scenario["kd"]
    limit, tolerance = scenario["torque_limit_nm"], scenario["settle_tolerance_rad"]
    speed_cap = scenario["max_reference_speed_rad_s"]
    # Bounding speed alone is not enough. Short moves then finish so fast that
    # their acceleration, and so their torque, hits the actuator limit.
    accel_cap = scenario["max_reference_accel_rad_s2"]
    margin = scenario.get("range_margin_rad", 0.05)

    plant = mujoco.MjData(model)
    reference = mujoco.MjData(model)  # scratch state for inverse dynamics of the reference
    setpoint = 0.0
    plant.qpos[address] = setpoint
    mujoco.mj_forward(model, plant)
    peak_torque = peak_speed = worst_error = 0.0
    saturated = total = clamped = reached = range_violation = 0
    dwell_steps = int(round(dwell / TRACK_STEP_S))
    for intent in intents:
        if intent == "deactivate":
            commanded = 0.0
        elif intent in INTENT_STEPS:
            commanded = setpoint + INTENT_STEPS[intent] * step
        else:
            raise ValueError(f"unknown intent {intent!r}")
        goal = min(max(commanded, low + margin), high - margin)
        clamped += int(goal != commanded)
        start, delta = setpoint, goal - setpoint
        duration = max(MIN_JERK_PEAK_SPEED * abs(delta) / speed_cap,
                       math.sqrt(MIN_JERK_PEAK_ACCEL * abs(delta) / accel_cap),
                       TRACK_STEP_S)
        if duration > dwell:
            raise ValueError(f"a {abs(delta):.3f} rad move needs {duration:.3f} s within "
                             f"{speed_cap} rad/s and {accel_cap} rad/s^2, "
                             f"longer than dwell_s {dwell}")
        for k in range(dwell_steps):
            s_ = min(1.0, k * TRACK_STEP_S / duration)
            q_r = start + delta * (10 * s_**3 - 15 * s_**4 + 6 * s_**5)
            qd_r = delta * (30 * s_**2 - 60 * s_**3 + 30 * s_**4) / duration if s_ < 1 else 0.0
            qdd_r = delta * (60 * s_ - 180 * s_**2 + 120 * s_**3) / duration**2 if s_ < 1 else 0.0
            reference.qpos[address], reference.qvel[address], reference.qacc[address] = q_r, qd_r, qdd_r
            mujoco.mj_inverse(model, reference)
            q, qd = float(plant.qpos[address]), float(plant.qvel[address])
            tau = float(reference.qfrc_inverse[address]) + kp * (q_r - q) + kd * (qd_r - qd)
            if abs(tau) > limit:
                saturated += 1
                tau = math.copysign(limit, tau)
            plant.qfrc_applied[address] = tau
            mujoco.mj_step(model, plant)
            total += 1
            q, qd = float(plant.qpos[address]), float(plant.qvel[address])
            if not (math.isfinite(q) and math.isfinite(qd)):
                raise FloatingPointError("integration diverged")
            peak_torque = max(peak_torque, abs(tau))
            peak_speed = max(peak_speed, abs(qd))
            range_violation |= int(not low - 1e-6 <= q <= high + 1e-6)
        setpoint = goal
        error = abs(goal - float(plant.qpos[address]))
        worst_error = max(worst_error, error)
        reached += int(error <= tolerance)
    return {
        "intents_applied": float(len(intents)),
        "setpoints_reached_fraction": reached / len(intents),
        "settle_error_max_rad": worst_error,
        "track_peak_torque_abs_nm": peak_torque,
        "track_peak_speed_rad_s": peak_speed,
        "torque_saturated_fraction": saturated / total,
        "setpoints_clamped": float(clamped),
        "range_violation": float(range_violation),
        "final_angle_rad": float(plant.qpos[address]),
    }


SCENARIOS = {
    "static_sweep": static_sweep,
    "rated_move": rated_move,
    "rom_sweep": rom_sweep,
    "free_swing": free_swing,
    "intent_tracking": intent_tracking,
}


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True, help="MJCF model path")
    parser.add_argument("--scenario", required=True, help="scenario as a JSON object")
    args = parser.parse_args(argv)
    scenario = json.loads(args.scenario)
    if scenario.get("name") not in SCENARIOS:
        print(f"error: unknown scenario {scenario.get('name')!r}", file=sys.stderr)
        return 2
    metrics = SCENARIOS[scenario["name"]](load(args.model, scenario), scenario)
    print(json.dumps(metrics, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
