"""Add a CAD-derived station to the line, sourced from an external USD file
produced by NVIDIA's usd-convert-cad (or any CAD-to-USD converter) from a
real STEP/IGES file.

This module only knows how to *reference* an already-converted USD asset and
tag it with the same manufacturing:* metadata every other station carries -
running the actual CAD conversion needs the usd-convert-cad tool itself,
which is part of Omniverse and not something this repo runs standalone. See
README "CAD integration" for the conversion step.

`build_stub_cad_asset()` produces a placeholder USD file purely so the
integration path (adding the station, tagging metadata, reading it back) can
be exercised and unit tested before a real converted asset exists. Point
`add_cad_station` at your real usd-convert-cad output instead and nothing
else in this module changes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pxr import Gf, Sdf, Usd, UsdGeom

from line_twin.build_stage import ASSET_DIR, LINE_PATH

STUB_CAD_ASSET_PATH = ASSET_DIR / "cad_fixture_stub.usda"


def build_stub_cad_asset(path: Path = STUB_CAD_ASSET_PATH) -> Path:
    """A placeholder standing in for real usd-convert-cad output, so the
    integration path below is testable before a real STEP file is converted.
    Point add_cad_station at a real converted asset once you have one -
    this function is only ever needed for the stub."""
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = Usd.Stage.CreateNew(str(path), load=Usd.Stage.LoadAll)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    fixture = UsdGeom.Xform.Define(stage, "/Fixture")
    stage.SetDefaultPrim(fixture.GetPrim())
    cone = UsdGeom.Cone.Define(stage, "/Fixture/Body")
    cone.CreateHeightAttr(0.6)
    cone.CreateRadiusAttr(0.25)
    stage.GetRootLayer().Save()
    return path


def add_cad_station(
    cad_asset_path: Path,
    name: str,
    part_number: str,
    cycle_time: float,
    sequence: int,
    line_stage_path: Path = LINE_PATH,
    x_position: Optional[float] = None,
) -> str:
    """Add one station to the line, geometry sourced from an external
    CAD-derived USD file rather than the synthetic body asset. Returns the
    new station's prim path.

    The reference is authored relative to line_stage_path's own directory
    (not a hardcoded repo path), so this works whether it's writing the real
    stage/line.usda or an isolated copy under a test's tmp_path.
    """
    line_stage_path = Path(line_stage_path)
    stage = Usd.Stage.Open(str(line_stage_path))
    rel_cad = os.path.relpath(cad_asset_path, line_stage_path.parent).replace(os.sep, "/")

    station = UsdGeom.Xform.Define(stage, f"/World/Line/{name}")
    if x_position is not None:
        UsdGeom.Xformable(station).AddTranslateOp().Set(Gf.Vec3d(x_position, 0.0, 0.0))

    prim = station.GetPrim()
    prim.GetReferences().AddReference(rel_cad)
    # Same reasoning as the synthetic stations: shares one composed copy if
    # more than one station ever references the same converted CAD asset.
    prim.SetInstanceable(True)

    prim.CreateAttribute(
        "manufacturing:partNumber", Sdf.ValueTypeNames.String, custom=True
    ).Set(part_number)
    prim.CreateAttribute(
        "manufacturing:station", Sdf.ValueTypeNames.String, custom=True
    ).Set(name)
    prim.CreateAttribute(
        "manufacturing:cycleTime", Sdf.ValueTypeNames.Float, custom=True
    ).Set(float(cycle_time))
    prim.CreateAttribute(
        "manufacturing:sequence", Sdf.ValueTypeNames.Int, custom=True
    ).Set(sequence)

    stage.GetRootLayer().Save()
    return str(prim.GetPath())
