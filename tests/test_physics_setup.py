"""Unit tests for the physics scene and inspection-gate kinematic mechanism.

These pin the *schema*: joint type, axis, limits, body relationships, rigid
body and collision APIs. They cannot and do not test that the gate actually
swings under simulation - that needs a PhysX-enabled runtime (Kit or
Unreal), neither of which is available in this environment. See
physics_setup.py's module docstring for the same caveat.
"""

from __future__ import annotations

import pytest
from pxr import Usd, UsdPhysics

from line_twin.build_stage import BODY_PATH, LINE_PATH, build_body_asset, build_line_stage
from line_twin.physics_setup import (
    GATE_ARM_PATH,
    GATE_BASE_PATH,
    GATE_JOINT_PATH,
    GATE_LOWER_LIMIT_DEG,
    GATE_ROOT_PATH,
    GATE_UPPER_LIMIT_DEG,
)


@pytest.fixture(scope="module", autouse=True)
def composed_stage():
    for path in (BODY_PATH, LINE_PATH):
        if path.exists():
            path.unlink()
    build_body_asset()
    build_line_stage()  # now authors the physics scene + gate as part of the normal build
    yield


@pytest.fixture
def stage() -> Usd.Stage:
    return Usd.Stage.Open(str(LINE_PATH))


def test_physics_scene_exists_with_gravity(stage):
    scene = UsdPhysics.Scene(stage.GetPrimAtPath("/PhysicsScene"))
    assert scene.GetPrim().IsValid()
    assert scene.GetGravityMagnitudeAttr().Get() == pytest.approx(9.81)


def test_gate_root_is_not_an_instance_proxy(stage):
    # The gate deliberately lives as a sibling of ST060_FinalInspect, not a
    # child of it, because that station is instanceable and USD does not
    # allow authoring new prims under an instanceable prim's subtree.
    root = stage.GetPrimAtPath(GATE_ROOT_PATH)
    assert root.IsValid()
    assert not root.IsInstanceProxy()


def test_gate_base_is_a_kinematic_rigid_body_with_collision(stage):
    base = stage.GetPrimAtPath(GATE_BASE_PATH + "/Geo")
    xform = stage.GetPrimAtPath(GATE_BASE_PATH)
    assert xform.HasAPI(UsdPhysics.RigidBodyAPI)
    assert UsdPhysics.RigidBodyAPI(xform).GetKinematicEnabledAttr().Get() is True
    assert base.HasAPI(UsdPhysics.CollisionAPI)


def test_gate_arm_is_a_dynamic_rigid_body_with_mass_and_collision(stage):
    arm = stage.GetPrimAtPath(GATE_ARM_PATH)
    geo = stage.GetPrimAtPath(GATE_ARM_PATH + "/Geo")
    assert arm.HasAPI(UsdPhysics.RigidBodyAPI)
    assert UsdPhysics.RigidBodyAPI(arm).GetKinematicEnabledAttr().Get() in (False, None)
    assert UsdPhysics.MassAPI(arm).GetMassAttr().Get() == pytest.approx(4.0)
    assert geo.HasAPI(UsdPhysics.CollisionAPI)


def test_hinge_joint_connects_base_to_arm_with_the_expected_swing_range(stage):
    joint = UsdPhysics.RevoluteJoint(stage.GetPrimAtPath(GATE_JOINT_PATH))
    assert joint.GetPrim().IsValid()
    assert joint.GetAxisAttr().Get() == "X"
    assert joint.GetBody0Rel().GetTargets() == [GATE_BASE_PATH]
    assert joint.GetBody1Rel().GetTargets() == [GATE_ARM_PATH]
    assert joint.GetLowerLimitAttr().Get() == pytest.approx(GATE_LOWER_LIMIT_DEG)
    assert joint.GetUpperLimitAttr().Get() == pytest.approx(GATE_UPPER_LIMIT_DEG)
    # A believable inspection-gate sweep, not a full free rotation.
    assert 0 < (GATE_UPPER_LIMIT_DEG - GATE_LOWER_LIMIT_DEG) < 180
