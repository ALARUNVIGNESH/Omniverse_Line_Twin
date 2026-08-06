"""Read the composed USD stage and report line KPIs.

This is the headless equivalent of the KPI panel the Kit extension draws:
same stage, same maths, no Omniverse required - which keeps the KPI logic
testable in CI and identical across the Kit and Unreal clients.

Run:  python -m line_twin.report
"""

from __future__ import annotations

import random

from line_twin.build_stage import read_stations
from line_twin.kpi import StationSample, line_summary

WINDOW_SECONDS = 3600.0  # one-hour measurement window


def synthesize_samples(seed: int = 7) -> list[StationSample]:
    """Stand in for the live telemetry feed with a deterministic shift.

    Replace this with the real station feed - `line_summary` does not care
    where the samples came from.
    """
    rng = random.Random(seed)
    samples: list[StationSample] = []

    for station in read_stations():
        ideal = station["cycle_time"]
        downtime = round(rng.uniform(0.0, 0.12) * WINDOW_SECONDS, 1)
        running = WINDOW_SECONDS - downtime
        # Stations rarely hit their ideal rate exactly.
        achieved_cycle = ideal * rng.uniform(1.0, 1.18)
        total = int(running // achieved_cycle)
        good = total - int(total * rng.uniform(0.0, 0.05))

        samples.append(
            StationSample(
                station=station["station"],
                ideal_cycle_time=ideal,
                planned_time=WINDOW_SECONDS,
                downtime=downtime,
                total_units=total,
                good_units=good,
            )
        )
    return samples


def main() -> None:
    summary = line_summary(synthesize_samples())

    header = f"{'STATION':<20}{'AVAIL':>8}{'PERF':>8}{'QUAL':>8}{'OEE':>8}{'UNITS/HR':>11}"
    print(header)
    print("-" * len(header))
    for row in summary["stations"]:
        print(
            f"{row['station']:<20}"
            f"{row['availability']:>7.1%}"
            f"{row['performance']:>8.1%}"
            f"{row['quality']:>8.1%}"
            f"{row['oee']:>8.1%}"
            f"{row['throughput_per_hour']:>11.1f}"
        )
    print("-" * len(header))
    print(f"bottleneck      : {summary['bottleneck']}")
    print(f"line throughput : {summary['line_throughput_per_hour']:.1f} good units/hour")


if __name__ == "__main__":
    main()
