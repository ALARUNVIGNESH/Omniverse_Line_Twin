"""Unit tests for the CAD-derived station integration path.

Uses build_stub_cad_asset() as the "converted CAD file" - a real STEP file
run through usd-convert-cad is what belongs there in production; the stub
only proves the referencing/metadata/read-back path works, independent of
whether a real CAD converter is available in this environment.

add_cad_station() saves the stage it's given, so tests operate on an
isolated tmp_path copy of the real line stage rather than the repo's
checked-in stage/line.usda - a unit test should not have the side effect of
permanently adding a station to a tracked file.
"""

from __future__ import annotations

import shutil

import pytest
from pxr import Usd

from line_twin.build_stage import (
    BODY_PATH,
    LINE_PATH,
    build_body_asset,
    build_line_stage,
    read_stations,
)
from line_twin.cad_integration import add_cad_station, build_stub_cad_asset


@pytest.fixture(scope="module", autouse=True)
def composed_stage_on_disk():
    for path in (BODY_PATH, LINE_PATH):
        if path.exists():
            path.unlink()
    build_body_asset()
    build_line_stage()
    yield


@pytest.fixture
def line_copy_and_stub(tmp_path):
    """An isolated copy of the real line stage, plus a stub CAD asset placed
    next to it, so add_cad_station's relative reference resolves correctly
    and nothing here touches the repo's tracked stage/line.usda."""
    line_copy = tmp_path / "line.usda"
    shutil.copy(LINE_PATH, line_copy)
    cad_stub = build_stub_cad_asset(tmp_path / "cad_fixture_stub.usda")
    return line_copy, cad_stub


def test_add_cad_station_appears_in_read_stations(line_copy_and_stub):
    line_copy, cad_stub = line_copy_and_stub

    path = add_cad_station(
        cad_asset_path=cad_stub,
        name="ST070_WeldFixture",
        part_number="FIX-9001",
        cycle_time=35.0,
        sequence=6,
        line_stage_path=line_copy,
        x_position=48.0,
    )

    stations = {s["station"]: s for s in read_stations(line_copy)}
    assert "ST070_WeldFixture" in stations
    assert stations["ST070_WeldFixture"]["part"] == "FIX-9001"
    assert stations["ST070_WeldFixture"]["cycle_time"] == 35.0
    assert path == "/World/Line/ST070_WeldFixture"


def test_cad_station_does_not_disturb_the_existing_six_stations(line_copy_and_stub):
    line_copy, cad_stub = line_copy_and_stub
    add_cad_station(
        cad_asset_path=cad_stub,
        name="ST070_WeldFixture",
        part_number="FIX-9001",
        cycle_time=35.0,
        sequence=6,
        line_stage_path=line_copy,
    )

    original_names = {
        "ST010_BodyDrop", "ST020_Weld", "ST030_PaintPrep",
        "ST040_PaintBooth", "ST050_Trim", "ST060_FinalInspect",
    }
    present = {s["station"] for s in read_stations(line_copy)}
    assert original_names.issubset(present)
    assert len(present) == 7


def test_cad_station_is_instanceable(line_copy_and_stub):
    line_copy, cad_stub = line_copy_and_stub
    add_cad_station(
        cad_asset_path=cad_stub,
        name="ST070_WeldFixture",
        part_number="FIX-9001",
        cycle_time=35.0,
        sequence=6,
        line_stage_path=line_copy,
    )

    stage = Usd.Stage.Open(str(line_copy))
    prim = stage.GetPrimAtPath("/World/Line/ST070_WeldFixture")
    assert prim.IsValid()
    assert prim.IsInstanceable()


def test_repo_stage_line_usda_is_untouched_by_these_tests():
    # The real committed file should still have exactly the original 6 -
    # everything above operated on a tmp_path copy, never on LINE_PATH.
    assert len(read_stations(LINE_PATH)) == 6
