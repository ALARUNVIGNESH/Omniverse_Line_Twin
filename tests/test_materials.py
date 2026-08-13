"""Unit tests for the UsdShade/UsdPreviewSurface paint materials.

Verifies materials resolve correctly at two levels: on the body asset in
isolation, and through the full station -> reference -> variant-override
chain in the composed line stage - the second is what actually matters,
since that's the path any real client (Kit, Unreal) reads through.
"""

from __future__ import annotations

import pytest
from pxr import Usd, UsdShade

from line_twin.build_stage import (
    BODY_PATH,
    LINE_PATH,
    PAINT_VARIANTS,
    build_body_asset,
    build_line_stage,
    read_stations,
)
from line_twin.materials import PAINT_MATERIAL_PARAMS


@pytest.fixture(scope="module", autouse=True)
def composed_stage():
    for path in (BODY_PATH, LINE_PATH):
        if path.exists():
            path.unlink()
    build_body_asset()  # now authors materials as part of the normal build
    build_line_stage()
    yield


def test_all_three_paint_materials_exist_on_the_body_asset():
    stage = Usd.Stage.Open(str(BODY_PATH))
    for variant_name in PAINT_VARIANTS:
        material_prim = stage.GetPrimAtPath(f"/Body/Materials/{variant_name}")
        assert material_prim.IsValid()
        assert UsdShade.Material(material_prim)


def test_each_variant_binds_its_own_material_with_correct_diffuse_color():
    stage = Usd.Stage.Open(str(BODY_PATH))
    body = stage.GetPrimAtPath("/Body")
    shell = stage.GetPrimAtPath("/Body/Shell")
    vset = body.GetVariantSets().GetVariantSet("paint")

    for variant_name, rgb in PAINT_VARIANTS.items():
        vset.SetVariantSelection(variant_name)
        material, _ = UsdShade.MaterialBindingAPI(shell).ComputeBoundMaterial()

        assert material.GetPath() == f"/Body/Materials/{variant_name}"

        shader = UsdShade.Shader(stage.GetPrimAtPath(f"{material.GetPath()}/PreviewSurface"))
        assert tuple(shader.GetInput("diffuseColor").Get()) == pytest.approx(rgb)


def test_gloss_and_matte_are_different_materials_not_just_different_colors():
    # The point of real materials over displayColor: finish differs too.
    gloss = PAINT_MATERIAL_PARAMS["gloss_white"]
    matte = PAINT_MATERIAL_PARAMS["matte_black"]
    assert gloss["roughness"] < matte["roughness"]
    assert gloss["clearcoat"] > matte["clearcoat"]


def test_every_station_resolves_to_the_material_matching_its_own_paint():
    # End-to-end through station -> reference -> variant override, which is
    # the path Kit and Unreal actually read through - not just the body
    # asset in isolation.
    stage = Usd.Stage.Open(str(LINE_PATH))
    for station in read_stations():
        shell = stage.GetPrimAtPath(f"{station['path']}/Shell")
        material, _ = UsdShade.MaterialBindingAPI(shell).ComputeBoundMaterial()
        assert material.GetPath().name == station["paint"]
