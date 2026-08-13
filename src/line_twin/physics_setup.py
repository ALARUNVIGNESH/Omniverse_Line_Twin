"""Physics scene and a kinematic inspection-gate mechanism on the line.

Authors real UsdPhysics schema - a PhysicsScene, rigid bodies, collision
shapes, and a revolute joint constraining a swing gate at the final
inspection station - the same schema a PhysX-enabled runtime (Kit, Unreal)
consumes to actually simulate the mechanism.

Deliberately one small mechanism, not a physics showcase: an inspection gate
that swings from -10 deg (rest) to 80 deg (open, scanning the part) is a
believable thing to find at a real final-inspection station, and it's enough
to demonstrate rigid bodies, collision, and a constrained joint without
overreaching into a bigger simulation than this project needs.

Honesty note: this module authors and verifies the *schema* only - joint
type, axis, limits, and body relationships are all checked with pxr's
UsdPhysics API in the test suite. It does not, and cannot in this
environment, run an actual physics step. Seeing the gate swing needs a
PhysX-enabled runtime (Kit or Unreal), neither of which is available here -
that verification is genuinely outstanding, the same as the Kit extension UI
and the Unreal client itself.

Run:  python -m line_twin.physics_setup
"""

from __future__ import annotations

from pxr import Gf, Usd, UsdGeom, UsdPhysics

from line_twin.build_stage import LINE_PATH, STATION_SPACING

GATE_STATION_PATH = "/World/Line/ST060_FinalInspect"
# A sibling of the station, not a child of it: ST060_FinalInspect is
# instanceable (see build_stage.py), and USD does not allow authoring new
# prims underneath an instanceable prim's own subtree - its children are
# instance proxies onto a shared prototype, not directly editable. Keeping
# the gate as its own top-level prim under /World/Line, named after the
# station it belongs to, sidesteps that without weakening the instancing
# story for the station itself.
GATE_ROOT_PATH = "/World/Line/ST060_InspectionGate"
GATE_BASE_PATH = f"{GATE_ROOT_PATH}/Base"
GATE_ARM_PATH = f"{GATE_ROOT_PATH}/Arm"
GATE_JOINT_PATH = f"{GATE_ROOT_PATH}/HingeJoint"

# Degrees. Rest position to a swung-open scanning position - not a full
# rotation, matching how an actual inspection gate/arm would move.
GATE_LOWER_LIMIT_DEG = -10.0
GATE_UPPER_LIMIT_DEG = 80.0


def add_physics_scene(stage: Usd.Stage) -> UsdPhysics.Scene:
    scene = UsdPhysics.Scene.Define(stage, "/PhysicsScene")
    scene.CreateGravityDirectionAttr(Gf.Vec3f(0.0, -1.0, 0.0))
    scene.CreateGravityMagnitudeAttr(9.81)
    return scene


def add_inspection_gate(stage: Usd.Stage) -> str:
    """A two-link swing gate: a kinematic base and a dynamic arm connected
    by a revolute joint. Positioned at ST060_FinalInspect's location.
    Returns the joint's prim path."""
    # ST060_FinalInspect is STATIONS[5], at x = 5 * STATION_SPACING.
    root = UsdGeom.Xform.Define(stage, GATE_ROOT_PATH)
    UsdGeom.Xformable(root).AddTranslateOp().Set(Gf.Vec3d(5 * STATION_SPACING, 0.0, 1.0))

    base_xform = UsdGeom.Xform.Define(stage, GATE_BASE_PATH)
    base_cube = UsdGeom.Cube.Define(stage, f"{GATE_BASE_PATH}/Geo")
    base_cube.CreateSizeAttr(0.2)
    UsdPhysics.CollisionAPI.Apply(base_cube.GetPrim())
    # Kinematic, not dynamic: the base doesn't move under simulation - the
    # arm swings relative to it, driven by the joint.
    UsdPhysics.RigidBodyAPI.Apply(base_xform.GetPrim()).CreateKinematicEnabledAttr(True)

    arm_xform = UsdGeom.Xform.Define(stage, GATE_ARM_PATH)
    UsdGeom.Xformable(arm_xform).AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.5))
    arm_cube = UsdGeom.Cube.Define(stage, f"{GATE_ARM_PATH}/Geo")
    arm_cube.CreateSizeAttr(0.1)
    UsdGeom.Xformable(arm_cube).AddScaleOp().Set(Gf.Vec3f(1.0, 1.0, 6.0))
    UsdPhysics.CollisionAPI.Apply(arm_cube.GetPrim())
    UsdPhysics.RigidBodyAPI.Apply(arm_xform.GetPrim())
    UsdPhysics.MassAPI.Apply(arm_xform.GetPrim()).CreateMassAttr(4.0)

    joint = UsdPhysics.RevoluteJoint.Define(stage, GATE_JOINT_PATH)
    joint.CreateBody0Rel().SetTargets([GATE_BASE_PATH])
    joint.CreateBody1Rel().SetTargets([GATE_ARM_PATH])
    joint.CreateAxisAttr("X")
    joint.CreateLowerLimitAttr(GATE_LOWER_LIMIT_DEG)
    joint.CreateUpperLimitAttr(GATE_UPPER_LIMIT_DEG)

    return GATE_JOINT_PATH


def main() -> None:
    stage = Usd.Stage.Open(str(LINE_PATH))
    add_physics_scene(stage)
    add_inspection_gate(stage)
    stage.GetRootLayer().Save()
    print(f"physics scene + inspection gate joint added at {GATE_JOINT_PATH}")


if __name__ == "__main__":
    main()
