"""Unit tests for the MQTT telemetry layer.

`_handle_message` and `_synthesize_one` are exercised directly with a fake message
object - the maths and the aggregation logic are what's worth pinning per commit,
not the broker round-trip, which is a wire-format detail already covered by
`--publish` / `--subscribe` manual runs against a live Mosquitto instance.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass

from line_twin.kpi import StationSample
from line_twin.telemetry import TelemetryAggregator, _synthesize_one


@dataclass
class _FakeMsg:
    payload: bytes


def _sample_payload(station: str = "ST010_BodyDrop", good_units: int = 58) -> bytes:
    return json.dumps(
        {
            "station": station,
            "ideal_cycle_time": 52.0,
            "planned_time": 3600.0,
            "downtime": 120.0,
            "total_units": 60,
            "good_units": good_units,
        }
    ).encode("utf-8")


def test_handle_message_stores_latest_sample_by_station():
    agg = TelemetryAggregator()
    agg._handle_message(None, None, _FakeMsg(payload=_sample_payload()))

    assert "ST010_BodyDrop" in agg._latest
    sample = agg._latest["ST010_BodyDrop"]
    assert isinstance(sample, StationSample)
    assert sample.good_units == 58


def test_handle_message_fires_on_update_callback_with_station_name():
    seen: list[str] = []
    agg = TelemetryAggregator(on_update=seen.append)
    agg._handle_message(None, None, _FakeMsg(payload=_sample_payload("ST020_Weld")))

    assert seen == ["ST020_Weld"]


def test_a_later_message_replaces_the_station_sample_not_appends():
    agg = TelemetryAggregator()
    agg._handle_message(None, None, _FakeMsg(payload=_sample_payload(good_units=58)))
    agg._handle_message(None, None, _FakeMsg(payload=_sample_payload(good_units=50)))

    assert len(agg._latest) == 1
    assert agg._latest["ST010_BodyDrop"].good_units == 50


def test_samples_are_returned_in_line_order_not_arrival_order():
    # station_order injected directly so this test does not depend on a
    # composed USD stage existing on disk - CI runs unit tests before
    # `build_stage`, so a call to read_stations() here would fail.
    agg = TelemetryAggregator(station_order={"ST010_BodyDrop": 0, "ST060_FinalInspect": 5})
    # Heard from a late station before an early one.
    agg._handle_message(None, None, _FakeMsg(payload=_sample_payload("ST060_FinalInspect")))
    agg._handle_message(None, None, _FakeMsg(payload=_sample_payload("ST010_BodyDrop")))

    stations = [s.station for s in agg.samples()]
    assert stations == ["ST010_BodyDrop", "ST060_FinalInspect"]


def test_synthesize_one_matches_the_stationsample_shape():
    station = {"station": "ST030_PaintPrep", "cycle_time": 47.0}
    payload = _synthesize_one(station, random.Random(1))

    sample = StationSample(**payload)  # raises if the shape is wrong
    assert sample.station == "ST030_PaintPrep"
    assert 0.0 <= sample.downtime <= 3600.0
    assert sample.good_units <= sample.total_units
