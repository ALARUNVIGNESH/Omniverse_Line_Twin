"""Unit tests for the routing graph and its validator.

The validator tests deliberately construct broken graphs (cycle, gap,
multiple entry points, a dangling reference) - a validator that only ever
sees valid input and never fails proves nothing. These prove it actually
rejects what it should.
"""

from __future__ import annotations

import pytest

from line_twin.build_stage import BODY_PATH, LINE_PATH, build_body_asset, build_line_stage
from line_twin.routing import RoutingError, read_routing, validate_routing


@pytest.fixture(scope="module", autouse=True)
def composed_stage():
    for path in (BODY_PATH, LINE_PATH):
        if path.exists():
            path.unlink()
    build_body_asset()
    build_line_stage()  # now authors routing as part of the normal build
    yield


def test_the_real_line_routing_is_valid_and_in_the_right_order():
    order = validate_routing(read_routing())
    assert order == [
        "ST010_BodyDrop", "ST020_Weld", "ST030_PaintPrep",
        "ST040_PaintBooth", "ST050_Trim", "ST060_FinalInspect",
    ]


def test_rejects_a_cycle():
    routing = {
        "A": {"predecessor": "", "successor": "B"},
        "B": {"predecessor": "A", "successor": "C"},
        "C": {"predecessor": "B", "successor": "A"},  # cycles back to A
    }
    with pytest.raises(RoutingError, match="cycle"):
        validate_routing(routing)


def test_rejects_a_gap_leaving_a_station_unreachable():
    routing = {
        "A": {"predecessor": "", "successor": "B"},
        "B": {"predecessor": "A", "successor": ""},   # chain ends here...
        "C": {"predecessor": "B", "successor": ""},   # ...but C claims B as predecessor
        # anyway - B's successor never actually points at C, so C is unreachable
        # by walking the chain even though it isn't a second entry point.
    }
    with pytest.raises(RoutingError, match="unreachable"):
        validate_routing(routing)


def test_rejects_more_than_one_entry_point():
    routing = {
        "A": {"predecessor": "", "successor": "B"},
        "B": {"predecessor": "A", "successor": ""},
        "C": {"predecessor": "", "successor": "B"},  # a second station with no predecessor
    }
    with pytest.raises(RoutingError, match="more than one entry point"):
        validate_routing(routing)


def test_rejects_a_dangling_successor_reference():
    routing = {
        "A": {"predecessor": "", "successor": "DoesNotExist"},
    }
    with pytest.raises(RoutingError, match="unknown station"):
        validate_routing(routing)


def test_rejects_empty_routing():
    with pytest.raises(RoutingError, match="no stations"):
        validate_routing({})
