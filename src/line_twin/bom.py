"""Bill-of-materials per station, authored directly onto USD.

Before this, each station only carried one partNumber string - the finished
part it produces, not what goes into it. This adds the actual BOM: the
sub-components and quantities assembled at each station.

Authored as parallel array attributes on the station prim itself rather than
child BOM-line prims, because every station is instanceable (see
build_stage.py) and USD does not allow authoring new prims underneath an
instanceable prim's subtree - the same constraint physics_setup.py hit with
the inspection gate. Parallel arrays are less elegant than a real prim per
line item, but they're a legitimate, well-established USD pattern for
compact tabular data, and they don't fight the instancing this project
already relies on for its optimization story.
"""

from __future__ import annotations

from pxr import Sdf, Usd

from line_twin.build_stage import LINE_PATH, read_stations

BOM_PART_NUMBERS_ATTR = "manufacturing:bom:partNumbers"
BOM_DESCRIPTIONS_ATTR = "manufacturing:bom:descriptions"
BOM_QUANTITIES_ATTR = "manufacturing:bom:quantities"

# Sub-components consumed at each station - not the part the station
# produces (that's already manufacturing:partNumber), but what goes into it.
STATION_BOM: dict[str, list[dict]] = {
    "ST010_BodyDrop": [
        {"part": "FRM-1001", "description": "Chassis frame rail", "qty": 2},
        {"part": "XMB-1002", "description": "Cross-member bracket", "qty": 4},
        {"part": "FLR-1003", "description": "Floor pan", "qty": 1},
    ],
    "ST020_Weld": [
        {"part": "WLD-2001", "description": "Weld nut, M8", "qty": 24},
        {"part": "WLD-2002", "description": "Structural gusset", "qty": 6},
    ],
    "ST030_PaintPrep": [
        {"part": "PNP-3001", "description": "Surface cleaner, per unit", "qty": 1},
        {"part": "PNP-3002", "description": "Masking kit", "qty": 1},
    ],
    "ST040_PaintBooth": [
        {"part": "PNB-4001", "description": "Base coat, racing blue", "qty": 1},
        {"part": "PNB-4002", "description": "Clear coat", "qty": 1},
    ],
    "ST050_Trim": [
        {"part": "TRM-5001", "description": "Door seal kit", "qty": 4},
        {"part": "TRM-5002", "description": "Interior trim panel", "qty": 6},
        {"part": "TRM-5003", "description": "Badge, rear", "qty": 1},
    ],
    "ST060_FinalInspect": [
        {"part": "FNI-6001", "description": "Inspection checklist tag", "qty": 1},
    ],
}


def author_bom(stage: Usd.Stage) -> None:
    """Write BOM arrays onto each already-authored station prim. Called
    from build_line_stage() after stations exist."""
    for station_name, components in STATION_BOM.items():
        prim = stage.GetPrimAtPath(f"/World/Line/{station_name}")
        if not prim.IsValid():
            continue
        prim.CreateAttribute(
            BOM_PART_NUMBERS_ATTR, Sdf.ValueTypeNames.StringArray, custom=True
        ).Set([c["part"] for c in components])
        prim.CreateAttribute(
            BOM_DESCRIPTIONS_ATTR, Sdf.ValueTypeNames.StringArray, custom=True
        ).Set([c["description"] for c in components])
        prim.CreateAttribute(
            BOM_QUANTITIES_ATTR, Sdf.ValueTypeNames.IntArray, custom=True
        ).Set([c["qty"] for c in components])


def read_bom(station_path: str, line_stage_path=LINE_PATH) -> list[dict]:
    """[{"part": ..., "description": ..., "qty": ...}, ...] read back off
    the stage for one station, in authored order."""
    stage = Usd.Stage.Open(str(line_stage_path))
    prim = stage.GetPrimAtPath(station_path)
    if not prim.IsValid():
        raise ValueError(f"no prim at {station_path!r}")

    parts = prim.GetAttribute(BOM_PART_NUMBERS_ATTR).Get() or []
    descriptions = prim.GetAttribute(BOM_DESCRIPTIONS_ATTR).Get() or []
    quantities = prim.GetAttribute(BOM_QUANTITIES_ATTR).Get() or []

    return [
        {"part": p, "description": d, "qty": q}
        for p, d, q in zip(parts, descriptions, quantities)
    ]


def full_bom_report(line_stage_path=LINE_PATH) -> dict[str, list[dict]]:
    """Every station's BOM, keyed by station name - what a real "export the
    BOM for this line" tool would return."""
    return {
        s["station"]: read_bom(s["path"], line_stage_path)
        for s in read_stations(line_stage_path)
    }


if __name__ == "__main__":
    for station_name, components in full_bom_report().items():
        print(station_name)
        for c in components:
            print(f"  {c['qty']:>3}x  {c['part']:<10} {c['description']}")
