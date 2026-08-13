"""Unit tests for the pure logic behind the Kit viewport extension.

Every function in panel_controller.py takes a Usd.Stage as an argument rather
than owning one - the real extension gets its stage from
omni.usd.get_context().get_stage() (the live viewport stage), these tests get
theirs from Usd.Stage.Open() on a file. Same functions, same behaviour,
no Kit runtime required.

Builds its own composed stage in a module-scoped fixture rather than relying
on stage/line.usda already existing on disk - CI runs unit tests before the
explicit "author the stage from scratch" step.
"""

from __future__ import annotations

import pytest
from pxr import Usd

from line_twin.build_stage import (
    BODY_PATH,
    LINE_PATH,
    build_body_asset,
    build_line_stage,
)
from line_twin.panel_controller import (
    available_paint_variants,
    set_paint_variant,
    station_prims,
)


@pytest.fixture(scope="module", autouse=True)
def composed_stage_on_disk():
    for path in (BODY_PATH, LINE_PATH):
        if path.exists():
            path.unlink()
    build_body_asset()
    build_line_stage()
    yield


@pytest.fixture
def stage() -> Usd.Stage:
    # A fresh handle per test - mirrors how the extension re-fetches the live
    # stage from omni.usd on every call rather than caching a stale one.
    return Usd.Stage.Open(str(LINE_PATH))


def test_station_prims_finds_all_six_stations(stage):
    prims = station_prims(stage)
    assert len(prims) == 6
    assert all(p.GetAttribute("manufacturing:station").IsValid() for p in prims)


def test_station_prims_returns_empty_list_for_a_stage_with_no_line(stage):
    empty_stage = Usd.Stage.CreateInMemory()
    assert station_prims(empty_stage) == []


def test_station_prims_returns_empty_list_for_none():
    assert station_prims(None) == []


def test_available_paint_variants_reads_the_real_variant_names(stage):
    variants = available_paint_variants(stage)
    assert set(variants) == {"gloss_white", "racing_blue", "matte_black"}


def test_set_paint_variant_repaints_every_station_and_reports_the_count(stage):
    changed = set_paint_variant(stage, "matte_black")

    assert changed == 6
    assert all(
        p.GetVariantSet("paint").GetVariantSelection() == "matte_black"
        for p in station_prims(stage)
    )

    set_paint_variant(stage, "gloss_white")  # restore for other tests in this module


def test_set_paint_variant_is_a_no_op_for_an_unknown_variant_name(stage):
    before = [p.GetVariantSet("paint").GetVariantSelection() for p in station_prims(stage)]

    changed = set_paint_variant(stage, "hot_pink")

    after = [p.GetVariantSet("paint").GetVariantSelection() for p in station_prims(stage)]
    assert changed == 0
    assert before == after


def test_stations_are_instanceable_and_share_a_prototype_per_paint_variant(stage):
    # 6 stations, 3 distinct paint variants (2 stations each) -> 3 shared
    # prototypes, not 6 independent copies. See instancing_report.py for the
    # full before/after this pins.
    assert all(p.IsInstanceable() for p in station_prims(stage))
    assert len(stage.GetPrototypes()) == 3
