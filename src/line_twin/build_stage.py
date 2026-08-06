"""Author the two-layer USD composition for the production line digital twin.

Layer 1 (assets/body.usda)  - the vehicle body asset, carrying a `paint` variant set.
Layer 2 (stage/line.usda)   - the production line: six stations, each referencing the
                              body asset and carrying custom `manufacturing:*` metadata.

Run:  python -m line_twin.build_stage
"""

from __future__ import annotations

import os
from pathlib import Path

from pxr import Usd, UsdGeom, Sdf, Gf, Vt

REPO_ROOT = Path(__file__).resolve().parents[2]
ASSET_DIR = REPO_ROOT / "assets"
STAGE_DIR = REPO_ROOT / "stage"

BODY_PATH = ASSET_DIR / "body.usda"
LINE_PATH = STAGE_DIR / "line.usda"

# Paint options exposed as a USD variant set on the body asset.
PAINT_VARIANTS = {
    "gloss_white": (0.90, 0.90, 0.90),
    "racing_blue": (0.05, 0.20, 0.65),
    "matte_black": (0.06, 0.06, 0.07),
}

# The production line. cycle_time is seconds per unit at that station.
STATIONS = [
    {"name": "ST010_BodyDrop",    "part": "BDY-1001", "cycle_time": 52.0, "paint": "gloss_white"},
    {"name": "ST020_Weld",        "part": "WLD-2004", "cycle_time": 61.5, "paint": "gloss_white"},
    {"name": "ST030_PaintPrep",   "part": "PNP-3011", "cycle_time": 47.0, "paint": "racing_blue"},
    {"name": "ST040_PaintBooth",  "part": "PNB-3020", "cycle_time": 78.0, "paint": "racing_blue"},
    {"name": "ST050_Trim",        "part": "TRM-4008", "cycle_time": 55.5, "paint": "matte_black"},
    {"name": "ST060_FinalInspect","part": "FNI-5002", "cycle_time": 43.0, "paint": "matte_black"},
]

STATION_SPACING = 8.0  # metres between station origins along +X


def build_body_asset() -> Path:
    """Author the body asset layer with a `paint` variant set."""
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    stage = Usd.Stage.CreateNew(str(BODY_PATH), load=Usd.Stage.LoadAll)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)

    body = UsdGeom.Xform.Define(stage, "/Body")
    stage.SetDefaultPrim(body.GetPrim())

    # Stand-in geometry. Swap for the real CAD-derived mesh without touching the
    # variant set or anything downstream - the line layer only references /Body.
    shell = UsdGeom.Cube.Define(stage, "/Body/Shell")
    shell.CreateSizeAttr(1.0)
    UsdGeom.Xformable(shell).AddScaleOp().Set(Gf.Vec3f(4.2, 1.3, 1.8))

    vset = body.GetPrim().GetVariantSets().AddVariantSet("paint")
    for variant_name, rgb in PAINT_VARIANTS.items():
        vset.AddVariant(variant_name)
        vset.SetVariantSelection(variant_name)
        with vset.GetVariantEditContext():
            UsdGeom.Gprim(shell).CreateDisplayColorAttr(
                Vt.Vec3fArray([Gf.Vec3f(*rgb)])
            )
    vset.SetVariantSelection("gloss_white")

    stage.GetRootLayer().Save()
    return BODY_PATH


def build_line_stage() -> Path:
    """Author the line layer: six stations referencing the body asset."""
    STAGE_DIR.mkdir(parents=True, exist_ok=True)
    stage = Usd.Stage.CreateNew(str(LINE_PATH), load=Usd.Stage.LoadAll)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)

    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    line = UsdGeom.Xform.Define(stage, "/World/Line")

    rel_body = os.path.relpath(BODY_PATH, STAGE_DIR).replace(os.sep, "/")

    for index, spec in enumerate(STATIONS):
        station = UsdGeom.Xform.Define(stage, f"/World/Line/{spec['name']}")
        UsdGeom.Xformable(station).AddTranslateOp().Set(
            Gf.Vec3d(index * STATION_SPACING, 0.0, 0.0)
        )

        prim = station.GetPrim()
        prim.GetReferences().AddReference(rel_body)
        prim.GetVariantSet("paint").SetVariantSelection(spec["paint"])

        # Custom manufacturing metadata. Namespaced so a Kit extension (or any
        # USD client) can discover every station by attribute prefix alone.
        prim.CreateAttribute(
            "manufacturing:partNumber", Sdf.ValueTypeNames.String, custom=True
        ).Set(spec["part"])
        prim.CreateAttribute(
            "manufacturing:station", Sdf.ValueTypeNames.String, custom=True
        ).Set(spec["name"])
        prim.CreateAttribute(
            "manufacturing:cycleTime", Sdf.ValueTypeNames.Float, custom=True
        ).Set(float(spec["cycle_time"]))
        prim.CreateAttribute(
            "manufacturing:sequence", Sdf.ValueTypeNames.Int, custom=True
        ).Set(index)

    stage.GetRootLayer().Save()
    return LINE_PATH


def read_stations(stage_path: Path | str = LINE_PATH) -> list[dict]:
    """Read every station back off the composed stage by metadata prefix."""
    stage = Usd.Stage.Open(str(stage_path))
    stations: list[dict] = []
    for prim in stage.Traverse():
        attr = prim.GetAttribute("manufacturing:station")
        if not attr or not attr.HasValue():
            continue
        stations.append(
            {
                "path": str(prim.GetPath()),
                "station": attr.Get(),
                "part": prim.GetAttribute("manufacturing:partNumber").Get(),
                "cycle_time": float(prim.GetAttribute("manufacturing:cycleTime").Get()),
                "sequence": int(prim.GetAttribute("manufacturing:sequence").Get()),
                "paint": prim.GetVariantSet("paint").GetVariantSelection(),
            }
        )
    return sorted(stations, key=lambda s: s["sequence"])


def main() -> None:
    for path in (BODY_PATH, LINE_PATH):
        if path.exists():
            path.unlink()

    body = build_body_asset()
    line = build_line_stage()
    print(f"body asset : {body.relative_to(REPO_ROOT)}")
    print(f"line stage : {line.relative_to(REPO_ROOT)}")

    print("\ncomposed stations:")
    for s in read_stations(line):
        print(
            f"  {s['sequence']}  {s['station']:<18} {s['part']:<10}"
            f" cycle={s['cycle_time']:>5.1f}s  paint={s['paint']}"
        )


if __name__ == "__main__":
    main()
