"""Measured before/after for USD native instancing on the line stage.

Builds the line twice into throwaway files - once without `instanceable`,
once with it, exactly as build_stage.py now authors it by default - and
prints the actual prim/prototype counts from each. This is what backs the
"applied USD native instancing, measured before/after" line: real numbers
from a real stage, not an estimate.

Run:  python -m line_twin.instancing_report
"""

from __future__ import annotations

import os
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom

from line_twin.build_stage import (
    BODY_PATH,
    STAGE_DIR,
    STATION_SPACING,
    STATIONS,
    build_body_asset,
)


def _build_line_variant(instanceable: bool, path: Path) -> Path:
    """Same authoring as build_stage.build_line_stage - the `instanceable`
    switch on the per-station reference is the only line that differs."""
    stage = Usd.Stage.CreateNew(str(path), load=Usd.Stage.LoadAll)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)

    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.Xform.Define(stage, "/World/Line")

    rel_body = os.path.relpath(BODY_PATH, STAGE_DIR).replace(os.sep, "/")

    for index, spec in enumerate(STATIONS):
        station = UsdGeom.Xform.Define(stage, f"/World/Line/{spec['name']}")
        UsdGeom.Xformable(station).AddTranslateOp().Set(
            Gf.Vec3d(index * STATION_SPACING, 0.0, 0.0)
        )
        prim = station.GetPrim()
        prim.GetReferences().AddReference(rel_body)
        prim.GetVariantSet("paint").SetVariantSelection(spec["paint"])
        prim.CreateAttribute(
            "manufacturing:station", Sdf.ValueTypeNames.String, custom=True
        ).Set(spec["name"])
        if instanceable:
            prim.SetInstanceable(True)

    stage.GetRootLayer().Save()
    return path


def instancing_stats(stage: Usd.Stage) -> dict:
    return {
        "prims_traversed_default": len(list(stage.Traverse())),
        "prims_traversed_with_instance_proxies": len(
            list(stage.Traverse(Usd.TraverseInstanceProxies()))
        ),
        "prototype_count": len(stage.GetPrototypes()),
        "prototype_paths": [str(p.GetPath()) for p in stage.GetPrototypes()],
    }


def main() -> None:
    STAGE_DIR.mkdir(parents=True, exist_ok=True)
    build_body_asset()

    before_path = STAGE_DIR / "_instancing_report_before.usda"
    after_path = STAGE_DIR / "_instancing_report_after.usda"
    for p in (before_path, after_path):
        if p.exists():
            p.unlink()

    before = Usd.Stage.Open(str(_build_line_variant(False, before_path)))
    after = Usd.Stage.Open(str(_build_line_variant(True, after_path)))

    before_stats = instancing_stats(before)
    after_stats = instancing_stats(after)

    print("BEFORE  instanceable = false")
    for key, value in before_stats.items():
        print(f"  {key}: {value}")

    print("\nAFTER   instanceable = true")
    for key, value in after_stats.items():
        print(f"  {key}: {value}")

    distinct_paints = len({s["paint"] for s in STATIONS})
    print(
        f"\n{len(STATIONS)} stations -> {after_stats['prototype_count']} shared "
        f"prototype(s) (one per distinct paint variant in use, {distinct_paints} "
        f"here), vs {before_stats['prototype_count']} prototypes / "
        f"{len(STATIONS)} fully independent copies without instancing."
    )

    before_path.unlink()
    after_path.unlink()


if __name__ == "__main__":
    main()
