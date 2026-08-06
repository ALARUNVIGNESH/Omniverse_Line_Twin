"""Line KPI maths, shared by the Kit extension and any other USD client.

Pure stdlib and side-effect free so it can be unit tested without USD or Omniverse.
"""

from __future__ import annotations

from dataclasses import dataclass

SECONDS_PER_HOUR = 3600.0


@dataclass(frozen=True)
class StationSample:
    """One station's state over a measurement window."""

    station: str
    ideal_cycle_time: float   # seconds per unit at 100% rate
    planned_time: float       # seconds the station was scheduled to run
    downtime: float           # seconds lost to unplanned stops
    total_units: int          # units produced, good and bad
    good_units: int           # units that passed inspection

    def __post_init__(self) -> None:
        if self.ideal_cycle_time <= 0:
            raise ValueError("ideal_cycle_time must be positive")
        if self.planned_time <= 0:
            raise ValueError("planned_time must be positive")
        if self.downtime < 0 or self.downtime > self.planned_time:
            raise ValueError("downtime must be between 0 and planned_time")
        if self.total_units < 0 or self.good_units < 0:
            raise ValueError("unit counts cannot be negative")
        if self.good_units > self.total_units:
            raise ValueError("good_units cannot exceed total_units")


def run_time(sample: StationSample) -> float:
    return sample.planned_time - sample.downtime


def availability(sample: StationSample) -> float:
    """Share of planned time the station was actually running."""
    return run_time(sample) / sample.planned_time


def performance(sample: StationSample) -> float:
    """Actual rate against ideal rate. Capped at 1.0 - a station cannot beat
    its own ideal cycle time, and an uncapped value hides a bad cycle-time
    constant behind an OEE that looks healthy."""
    running = run_time(sample)
    if running <= 0:
        return 0.0
    return min(1.0, (sample.ideal_cycle_time * sample.total_units) / running)


def quality(sample: StationSample) -> float:
    if sample.total_units == 0:
        return 0.0
    return sample.good_units / sample.total_units


def oee(sample: StationSample) -> float:
    """Overall Equipment Effectiveness = availability x performance x quality."""
    return availability(sample) * performance(sample) * quality(sample)


def station_throughput(sample: StationSample) -> float:
    """Good units per hour this station is actually achieving."""
    running = run_time(sample)
    if running <= 0:
        return 0.0
    return sample.good_units * (SECONDS_PER_HOUR / running)


def bottleneck(samples: list[StationSample]) -> StationSample | None:
    """The station holding the line back - lowest achieved throughput."""
    if not samples:
        return None
    return min(samples, key=station_throughput)


def line_throughput(samples: list[StationSample]) -> float:
    """A serial line runs no faster than its slowest station, so line
    throughput is gated by the bottleneck rather than averaged."""
    slowest = bottleneck(samples)
    return 0.0 if slowest is None else station_throughput(slowest)


def line_summary(samples: list[StationSample]) -> dict:
    """Everything the KPI panel needs, in one call."""
    slowest = bottleneck(samples)
    return {
        "station_count": len(samples),
        "line_throughput_per_hour": line_throughput(samples),
        "bottleneck": None if slowest is None else slowest.station,
        "stations": [
            {
                "station": s.station,
                "availability": availability(s),
                "performance": performance(s),
                "quality": quality(s),
                "oee": oee(s),
                "throughput_per_hour": station_throughput(s),
            }
            for s in samples
        ],
    }
