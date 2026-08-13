"""Explicit routing graph for the line, and a validator that actually
detects a broken routing - not just data that happens to look fine.

Before this, "routing" was implicit: a station's position in the line was
just its index in the STATIONS list. That's fine for authoring, but it's not
a routing model - nothing prevents a mistake (a duplicated sequence number, a
gap, a station pointing at itself) from silently landing on the stage.

Each station now carries explicit predecessor/successor attributes -
`manufacturing:routing:predecessor` / `...successor`, empty string at the
ends of the line - and validate_routing() walks the graph itself rather than
trusting the sequence numbers, so a routing mistake fails loudly instead of
composing correctly and reporting wrong KPIs downstream.
"""

from __future__ import annotations

from pxr import Sdf, Usd

from line_twin.build_stage import LINE_PATH, STATIONS, read_stations

ROUTING_PREDECESSOR_ATTR = "manufacturing:routing:predecessor"
ROUTING_SUCCESSOR_ATTR = "manufacturing:routing:successor"


def routing_pairs() -> list[tuple[str, str, str]]:
    """(station, predecessor, successor) for every station in STATIONS,
    derived from list order - authored once at build time, then treated as
    the source of truth by validate_routing() rather than re-derived."""
    names = [s["name"] for s in STATIONS]
    pairs = []
    for i, name in enumerate(names):
        predecessor = names[i - 1] if i > 0 else ""
        successor = names[i + 1] if i < len(names) - 1 else ""
        pairs.append((name, predecessor, successor))
    return pairs


def author_routing(stage: Usd.Stage) -> None:
    """Write predecessor/successor attributes onto each already-authored
    station prim. Called from build_line_stage() after stations exist."""
    for name, predecessor, successor in routing_pairs():
        prim = stage.GetPrimAtPath(f"/World/Line/{name}")
        prim.CreateAttribute(
            ROUTING_PREDECESSOR_ATTR, Sdf.ValueTypeNames.String, custom=True
        ).Set(predecessor)
        prim.CreateAttribute(
            ROUTING_SUCCESSOR_ATTR, Sdf.ValueTypeNames.String, custom=True
        ).Set(successor)


def read_routing(line_stage_path=LINE_PATH) -> dict[str, dict[str, str]]:
    """{station: {"predecessor": ..., "successor": ...}} read back off the
    stage - not from STATIONS - so validation exercises what's actually on
    disk, not the Python list that authored it."""
    stage = Usd.Stage.Open(str(line_stage_path))
    routing = {}
    for station in read_stations(line_stage_path):
        prim = stage.GetPrimAtPath(station["path"])
        routing[station["station"]] = {
            "predecessor": prim.GetAttribute(ROUTING_PREDECESSOR_ATTR).Get() or "",
            "successor": prim.GetAttribute(ROUTING_SUCCESSOR_ATTR).Get() or "",
        }
    return routing


class RoutingError(ValueError):
    """The routing graph doesn't form a single unbroken chain."""


def validate_routing(routing: dict[str, dict[str, str]]) -> list[str]:
    """Walk the graph from its entry point and return station names in
    visited order. Raises RoutingError on anything that isn't a single
    unbroken chain through every station exactly once: no entry point, more
    than one entry point, a cycle, a gap, or a dangling reference to a
    station that doesn't exist.
    """
    if not routing:
        raise RoutingError("no stations to route")

    entries = [name for name, r in routing.items() if r["predecessor"] == ""]
    if len(entries) == 0:
        raise RoutingError("no entry point: every station has a predecessor (cycle?)")
    if len(entries) > 1:
        raise RoutingError(f"more than one entry point: {entries}")

    visited: list[str] = []
    current = entries[0]
    seen = set()
    while current:
        if current not in routing:
            raise RoutingError(f"routing points at an unknown station: {current!r}")
        if current in seen:
            raise RoutingError(f"cycle detected back to {current!r}")
        seen.add(current)
        visited.append(current)
        current = routing[current]["successor"]

    missing = set(routing) - seen
    if missing:
        raise RoutingError(f"unreachable from the entry point: {missing}")

    return visited


if __name__ == "__main__":
    order = validate_routing(read_routing())
    print("routing OK, entry -> exit order:")
    for name in order:
        print(f"  {name}")
