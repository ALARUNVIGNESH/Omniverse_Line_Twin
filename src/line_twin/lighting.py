"""Lighting and a framed camera for the line stage.

Before this, the stage had zero lights - correct geometry and materials on
an unlit stage still render flat and gray. This authors a real UsdLux
lighting setup: a dome light for overall fill, a few rect lights over the
line for practical factory-floor illumination, and a camera framed on the
whole line, so the first thing anyone sees on opening this stage - in Kit,
in Unreal, in usdview - is a lit, framed shot rather than an empty gray box
they have to light and frame themselves before it means anything.

This authors the lighting *setup* - UsdLux prims with real position,
intensity, and color values, verified with tests. It does not, and cannot in
this environment, verify the actual RTX-rendered image; that needs Kit's
renderer running, the same honesty caveat as the physics simulation and the
Kit extension UI.
"""

from __future__ import annotations

from pxr import Gf, Usd, UsdGeom, UsdLux

from line_twin.build_stage import LINE_PATH, STATIONS, STATION_SPACING

DOME_LIGHT_PATH = "/World/Lights/Dome"
KEY_LIGHT_PATH = "/World/Lights/KeyLight"
FILL_LIGHT_PATH = "/World/Lights/FillLight"
CAMERA_PATH = "/World/Cameras/LineOverview"


def add_lighting(stage: Usd.Stage) -> None:
    """A simple three-point-ish setup: a dome for ambient fill, one rect
    key light with warm-neutral color over the middle of the line, and a
    softer, cooler rect fill light from the opposite side to keep shadows
    from going fully black."""
    line_center_x = (len(STATIONS) - 1) * STATION_SPACING / 2.0

    dome = UsdLux.DomeLight.Define(stage, DOME_LIGHT_PATH)
    dome.CreateIntensityAttr(400.0)
    dome.CreateColorAttr(Gf.Vec3f(0.9, 0.92, 1.0))

    key = UsdLux.RectLight.Define(stage, KEY_LIGHT_PATH)
    key.CreateWidthAttr(6.0)
    key.CreateHeightAttr(4.0)
    key.CreateIntensityAttr(6000.0)
    key.CreateColorAttr(Gf.Vec3f(1.0, 0.96, 0.9))
    UsdGeom.Xformable(key).AddTranslateOp().Set(Gf.Vec3d(line_center_x, 6.0, 6.0))
    UsdGeom.Xformable(key).AddRotateXOp().Set(-45.0)

    fill = UsdLux.RectLight.Define(stage, FILL_LIGHT_PATH)
    fill.CreateWidthAttr(6.0)
    fill.CreateHeightAttr(4.0)
    fill.CreateIntensityAttr(2000.0)
    fill.CreateColorAttr(Gf.Vec3f(0.85, 0.9, 1.0))
    UsdGeom.Xformable(fill).AddTranslateOp().Set(Gf.Vec3d(line_center_x, 6.0, -6.0))
    UsdGeom.Xformable(fill).AddRotateXOp().Set(-135.0)


def add_camera(stage: Usd.Stage) -> None:
    """Framed on the whole line from a three-quarter angle, not straight
    down its axis - the layout actually reads as a line rather than one
    station occluding the next."""
    line_center_x = (len(STATIONS) - 1) * STATION_SPACING / 2.0
    line_length = (len(STATIONS) - 1) * STATION_SPACING

    camera = UsdGeom.Camera.Define(stage, CAMERA_PATH)
    camera.CreateFocalLengthAttr(24.0)  # wide enough to fit the whole line
    xformable = UsdGeom.Xformable(camera)
    xformable.AddTranslateOp().Set(Gf.Vec3d(line_center_x, line_length * 0.5, line_length * 0.9))
    xformable.AddRotateXOp().Set(-35.0)


if __name__ == "__main__":
    stage = Usd.Stage.Open(str(LINE_PATH))
    add_lighting(stage)
    add_camera(stage)
    stage.GetRootLayer().Save()
    print(f"lighting + camera added: {DOME_LIGHT_PATH}, {KEY_LIGHT_PATH}, {FILL_LIGHT_PATH}, {CAMERA_PATH}")
