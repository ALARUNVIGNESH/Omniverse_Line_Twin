"""Unit tests for the per-station bill of materials."""

from __future__ import annotations

import pytest

from line_twin.bom import STATION_BOM, full_bom_report, read_bom
from line_twin.build_stage import BODY_PATH, LINE_PATH, build_body_asset, build_line_stage


@pytest.fixture(scope="module", autouse=True)
def composed_stage():
    for path in (BODY_PATH, LINE_PATH):
        if path.exists():
            path.unlink()
    build_body_asset()
    build_line_stage()  # now authors BOM as part of the normal build
    yield


def test_every_station_in_stations_has_a_bom_defined():
    from line_twin.build_stage import STATIONS

    names = {s["name"] for s in STATIONS}
    assert names == set(STATION_BOM)


def test_read_bom_matches_the_authored_data_for_one_station():
    components = read_bom("/World/Line/ST010_BodyDrop")
    expected = STATION_BOM["ST010_BodyDrop"]

    assert len(components) == len(expected)
    assert components[0] == {"part": "FRM-1001", "description": "Chassis frame rail", "qty": 2}


def test_bom_order_is_preserved_not_alphabetized_or_reordered():
    components = read_bom("/World/Line/ST050_Trim")
    assert [c["part"] for c in components] == ["TRM-5001", "TRM-5002", "TRM-5003"]


def test_full_bom_report_covers_every_station_on_the_real_line():
    report = full_bom_report()
    assert set(report) == {
        "ST010_BodyDrop", "ST020_Weld", "ST030_PaintPrep",
        "ST040_PaintBooth", "ST050_Trim", "ST060_FinalInspect",
    }
    assert all(len(components) > 0 for components in report.values())


def test_read_bom_raises_for_an_unknown_station_path():
    with pytest.raises(ValueError):
        read_bom("/World/Line/NotAStation")
