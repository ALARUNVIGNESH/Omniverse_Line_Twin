"""Unit tests for the KPI maths. Run: python -m pytest -q"""

import pytest

from line_twin.kpi import (
    StationSample, availability, performance, quality, oee,
    station_throughput, bottleneck, line_throughput, line_summary,
)


def sample(**kw):
    base = dict(
        station="ST010", ideal_cycle_time=50.0, planned_time=3600.0,
        downtime=0.0, total_units=72, good_units=72,
    )
    base.update(kw)
    return StationSample(**base)


def test_perfect_station_scores_one():
    s = sample()
    assert availability(s) == 1.0
    assert performance(s) == pytest.approx(1.0)
    assert quality(s) == 1.0
    assert oee(s) == pytest.approx(1.0)


def test_downtime_reduces_availability():
    s = sample(downtime=900.0, total_units=54, good_units=54)
    assert availability(s) == pytest.approx(0.75)
    assert performance(s) == pytest.approx(1.0)
    assert oee(s) == pytest.approx(0.75)


def test_scrap_reduces_quality():
    s = sample(good_units=68)
    assert quality(s) == pytest.approx(68 / 72)


def test_performance_is_capped_at_one():
    s = sample(total_units=100, good_units=100)
    assert performance(s) == 1.0


def test_full_downtime_scores_zero_not_divide_by_zero():
    s = sample(downtime=3600.0, total_units=0, good_units=0)
    assert performance(s) == 0.0
    assert station_throughput(s) == 0.0
    assert oee(s) == 0.0


def test_line_throughput_is_gated_by_the_slowest_station():
    fast = sample(station="ST010", ideal_cycle_time=40.0, total_units=90, good_units=90)
    slow = sample(station="ST040", ideal_cycle_time=80.0, total_units=45, good_units=45)
    samples = [fast, slow]

    assert bottleneck(samples).station == "ST040"
    assert line_throughput(samples) == pytest.approx(45.0)
    assert line_throughput(samples) != pytest.approx(67.5)


def test_line_summary_shape():
    out = line_summary([sample()])
    assert out["station_count"] == 1
    assert out["bottleneck"] == "ST010"
    assert set(out["stations"][0]) == {
        "station", "availability", "performance", "quality", "oee", "throughput_per_hour",
    }


def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError):
        sample(good_units=999)
    with pytest.raises(ValueError):
        sample(ideal_cycle_time=0.0)
    with pytest.raises(ValueError):
        sample(downtime=-1.0)
