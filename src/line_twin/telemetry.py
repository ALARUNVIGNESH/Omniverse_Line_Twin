"""Live telemetry over MQTT, replacing the synthetic `report.synthesize_samples`
stand-in with a real pub/sub transport.

Two roles talking through a broker (a local Mosquitto instance for dev/demo, a
plant's existing broker in production):

  - `TelemetryPublisher`  : stands in for the plant's sensors. Publishes one JSON
                            sample per station, on an interval, to `line/<station>/telemetry`.
  - `TelemetryAggregator` : the subscriber side. The Kit extension and the Unreal
                            client each run one; it holds the latest sample per
                            station and turns them into the same `StationSample`
                            objects `kpi.line_summary` already knows how to consume.

Swapping this in for `synthesize_samples` is a transport change only - the
`StationSample` shape and every downstream KPI call are unchanged. Pointing this at
a real plant means swapping the publisher for a bridge that reads the plant's actual
protocol (often OPC-UA on the factory floor) and republishes onto the same topics;
`TelemetryAggregator` does not need to change.

Run a live demo (two terminals, a local broker running on 1883):
    python -m line_twin.telemetry --publish
    python -m line_twin.telemetry --subscribe
"""

from __future__ import annotations

import argparse
import json
import random
import time
from typing import Callable, Optional

import paho.mqtt.client as mqtt

from line_twin.build_stage import read_stations
from line_twin.kpi import StationSample, line_summary

BROKER_HOST = "localhost"
BROKER_PORT = 1883
TOPIC_PREFIX = "line"
WINDOW_SECONDS = 3600.0  # one-hour measurement window, matches report.py


def _topic(station: str) -> str:
    return f"{TOPIC_PREFIX}/{station}/telemetry"


def _synthesize_one(station: dict, rng: random.Random) -> dict:
    """Same sample maths as report.synthesize_samples, one station at a time.

    Kept here rather than imported so the publisher has no dependency on report.py -
    it is standing in for a sensor, not for the reporting tool.
    """
    ideal = station["cycle_time"]
    downtime = round(rng.uniform(0.0, 0.12) * WINDOW_SECONDS, 1)
    running = WINDOW_SECONDS - downtime
    achieved_cycle = ideal * rng.uniform(1.0, 1.18)
    total = int(running // achieved_cycle)
    good = total - int(total * rng.uniform(0.0, 0.05))

    return {
        "station": station["station"],
        "ideal_cycle_time": ideal,
        "planned_time": WINDOW_SECONDS,
        "downtime": downtime,
        "total_units": total,
        "good_units": good,
    }


class TelemetryPublisher:
    """Stands in for the plant's sensors until a real feed is wired in."""

    def __init__(self, host: str = BROKER_HOST, port: int = BROKER_PORT, seed: int = 7):
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._host, self._port = host, port
        self._rng = random.Random(seed)

    def connect(self) -> None:
        self._client.connect(self._host, self._port)
        self._client.loop_start()

    def disconnect(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def publish_once(self) -> None:
        """One fresh sample per station, published to its own topic."""
        for station in read_stations():
            sample = _synthesize_one(station, self._rng)
            self._client.publish(_topic(sample["station"]), json.dumps(sample), qos=1)

    def run_forever(self, interval_seconds: float = 5.0) -> None:
        self.connect()
        try:
            while True:
                self.publish_once()
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            pass
        finally:
            self.disconnect()


class TelemetryAggregator:
    """Subscriber side: holds the latest sample per station.

    The Kit extension and the Unreal client each own one of these. `on_update`
    fires with the station name on every message, so a UI panel can refresh only
    when data actually changes rather than polling on a timer.
    """

    def __init__(
        self,
        host: str = BROKER_HOST,
        port: int = BROKER_PORT,
        on_update: Optional[Callable[[str], None]] = None,
        station_order: Optional[dict[str, int]] = None,
    ):
        self._latest: dict[str, StationSample] = {}
        self._on_update = on_update
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_message = self._handle_message
        self._host, self._port = host, port
        # Injectable so tests can pin ordering without a composed USD stage on
        # disk; real callers (Kit extension, Unreal client) always have one and
        # can leave this as None.
        self._station_order = station_order

    def _handle_message(self, _client, _userdata, msg) -> None:
        payload = json.loads(msg.payload.decode("utf-8"))
        sample = StationSample(
            station=payload["station"],
            ideal_cycle_time=payload["ideal_cycle_time"],
            planned_time=payload["planned_time"],
            downtime=payload["downtime"],
            total_units=payload["total_units"],
            good_units=payload["good_units"],
        )
        self._latest[sample.station] = sample
        if self._on_update:
            self._on_update(sample.station)

    def connect(self) -> None:
        self._client.connect(self._host, self._port)
        self._client.subscribe(f"{TOPIC_PREFIX}/+/telemetry", qos=1)
        self._client.loop_start()

    def disconnect(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def samples(self) -> list[StationSample]:
        """Every station heard from so far, in line order."""
        order = self._station_order
        if order is None:
            order = {s["station"]: s["sequence"] for s in read_stations()}
        return sorted(self._latest.values(), key=lambda s: order.get(s.station, 0))

    def summary(self) -> dict:
        """Same shape report.py prints - the Kit panel and Unreal client both bind to this."""
        return line_summary(self.samples())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--publish", action="store_true", help="run the simulated sensor feed")
    group.add_argument("--subscribe", action="store_true", help="run a demo subscriber")
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between publishes")
    args = parser.parse_args()

    if args.publish:
        print(f"publishing station telemetry to {BROKER_HOST}:{BROKER_PORT} every {args.interval}s")
        TelemetryPublisher().run_forever(args.interval)
        return

    def on_update(station: str) -> None:
        print(f"[{station}] updated")

    agg = TelemetryAggregator(on_update=on_update)
    agg.connect()
    print(f"subscribed at {BROKER_HOST}:{BROKER_PORT}, ctrl-C to stop")
    try:
        while True:
            time.sleep(10)
            summary = agg.summary()
            if summary["station_count"]:
                print(
                    f"  stations heard: {summary['station_count']}  "
                    f"bottleneck: {summary['bottleneck']}  "
                    f"line throughput: {summary['line_throughput_per_hour']:.1f}/hr"
                )
    except KeyboardInterrupt:
        pass
    finally:
        agg.disconnect()


if __name__ == "__main__":
    main()
