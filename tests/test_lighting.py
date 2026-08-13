"""Unit tests for the lighting and camera setup.

These verify the UsdLux/Camera schema is authored correctly - real prim
types, sane intensity/color/position values. They cannot and do not verify
the actual rendered image; that needs Kit's RTX renderer running, which is
not available in this environment - the same honesty caveat as the physics
simulation and the Kit extension UI.
"""

from __future__ import annotations

import pytest
from pxr import Usd, UsdGeom, UsdLux

from line_twin.build_stage import BODY_PATH, LINE_PATH, build_body_asset, build_line_stage
from line_twin.lighting import CAMERA_PATH, DOME_LIGHT_PATH, FILL_LIGHT_PATH, KEY_LIGHT_PATH


@pytest.fixture(scope="module", autouse=True)
def composed_stage():
    for path in (BODY_PATH, LINE_PATH):
        if path.exists():
            path.unlink()
    build_body_asset()
    build_line_stage()  # now authors lighting + camera as part of the normal build
    yield


@pytest.fixture
def stage() -> Usd.Stage:
    return Usd.Stage.Open(str(LINE_PATH))


def test_dome_light_exists_with_positive_intensity(stage):
    dome = UsdLux.DomeLight(stage.GetPrimAtPath(DOME_LIGHT_PATH))
    assert dome.GetPrim().IsValid()
    assert dome.GetIntensityAttr().Get() > 0


def test_key_and_fill_lights_exist_and_key_is_brighter_than_fill(stage):
    key = UsdLux.RectLight(stage.GetPrimAtPath(KEY_LIGHT_PATH))
    fill = UsdLux.RectLight(stage.GetPrimAtPath(FILL_LIGHT_PATH))
    assert key.GetPrim().IsValid()
    assert fill.GetPrim().IsValid()
    # A key/fill setup where fill is brighter than key isn't a key/fill
    # setup - this is the one thing worth pinning about the relationship
    # between them, not just that both exist.
    assert key.GetIntensityAttr().Get() > fill.GetIntensityAttr().Get()


def test_key_and_fill_lights_are_on_opposite_sides_of_the_line():
    stage = Usd.Stage.Open(str(LINE_PATH))
    key_xform = UsdGeom.Xformable(stage.GetPrimAtPath(KEY_LIGHT_PATH))
    fill_xform = UsdGeom.Xformable(stage.GetPrimAtPath(FILL_LIGHT_PATH))
    key_matrix = key_xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    fill_matrix = fill_xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    key_z = key_matrix.ExtractTranslation()[2]
    fill_z = fill_matrix.ExtractTranslation()[2]
    assert (key_z > 0) != (fill_z > 0)


def test_camera_exists_and_is_framed_with_a_reasonable_focal_length(stage):
    camera = UsdGeom.Camera(stage.GetPrimAtPath(CAMERA_PATH))
    assert camera.GetPrim().IsValid()
    focal_length = camera.GetFocalLengthAttr().Get()
    assert 10.0 < focal_length < 100.0  # a believable real-world lens, not a placeholder
