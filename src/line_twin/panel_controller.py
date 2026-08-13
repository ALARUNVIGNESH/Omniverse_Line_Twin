"""Pure logic behind the Kit viewport extension.

Every function here takes a `pxr.Usd.Stage` as an argument rather than owning
one - the real extension (exts/line_twin.viewport/) passes it
`omni.usd.get_context().get_stage()`, the actual stage open in the viewport,
so edits show up on screen immediately. Tests pass a stage opened with
`Usd.Stage.Open()` on a file instead. Same functions, same behaviour, no
Kit runtime required to test them.

No omni.ui / omni.ext / omni.usd imports here on purpose - that keeps the
untestable surface area limited to extension.py itself, which does nothing
but wire these functions to widgets.
"""

from __future__ import annotations

from pxr import Usd

LINE_PRIM_PATH = "/World/Line"
PAINT_VARIANT_SET = "paint"


def station_prims(stage: Usd.Stage) -> list[Usd.Prim]:
    """Every station prim under the line, discovered by carrying
    manufacturing:station - not a hardcoded list of prim paths, so a station
    added to the stage needs no change here."""
    if stage is None:
        return []
    line = stage.GetPrimAtPath(LINE_PRIM_PATH)
    if not line or not line.IsValid():
        return []
    return [
        prim
        for prim in line.GetChildren()
        if prim.GetAttribute("manufacturing:station").IsValid()
    ]


def available_paint_variants(stage: Usd.Stage) -> list[str]:
    """Read the paint options straight off the stage instead of hardcoding
    them - stays correct if build_stage.py's PAINT_VARIANTS ever changes."""
    for prim in station_prims(stage):
        vset = prim.GetVariantSet(PAINT_VARIANT_SET)
        if vset.IsValid():
            names = vset.GetVariantNames()
            if names:
                return names
    return []


def set_paint_variant(stage: Usd.Stage, variant_name: str) -> int:
    """Apply one paint variant to every station. Returns how many stations
    were actually changed, so a caller (or a test) can tell a no-op apart
    from a real switch."""
    changed = 0
    for prim in station_prims(stage):
        vset = prim.GetVariantSet(PAINT_VARIANT_SET)
        if vset.IsValid() and variant_name in vset.GetVariantNames():
            vset.SetVariantSelection(variant_name)
            changed += 1
    return changed
