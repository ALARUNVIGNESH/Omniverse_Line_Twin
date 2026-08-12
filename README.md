# Omniverse Production-Line Digital Twin

An OpenUSD digital twin of a six-station vehicle production line, built to be driven
from NVIDIA Omniverse Kit and consumed by other real-time clients from the same
composed stage.

The idea is that the stage is the single source of truth. Geometry, the paint variant
set and the per-station manufacturing metadata all live in USD, so a Kit extension, an
Unreal `UsdStageActor`, and a headless Python report can all read the same line without
any of them owning a private copy of the data.

## Status

| Part | State |
|---|---|
| Two-layer USD composition (body asset + line layer) | working |
| `paint` variant set on the body asset | working |
| `manufacturing:*` metadata on all six stations | working |
| KPI module (OEE, bottleneck-gated line throughput) | working, unit tested |
| Headless KPI report off the composed stage | working |
| Live MQTT telemetry service (publisher + aggregator) | working, unit tested |
| Omniverse Kit extension with in-viewport KPI panel | in progress |
| Unreal Engine 5 `UsdStageActor` client | planned |

Everything marked *working* runs from a clean checkout with the commands below.

## Quick start

```bash
pip install -r requirements.txt

# author assets/body.usda and stage/line.usda
PYTHONPATH=src python -m line_twin.build_stage

# read the composed stage back and report line KPIs
PYTHONPATH=src python -m line_twin.report

# unit tests for the KPI maths and the telemetry layer
python -m pytest -q

# live demo against a local broker (needs mosquitto running on :1883):
#   terminal 1
PYTHONPATH=src python -m line_twin.telemetry --publish
#   terminal 2
PYTHONPATH=src python -m line_twin.telemetry --subscribe
```

`stage/line.usda` opens directly in USD Composer, usdview, or any USD-capable DCC.

## How the stage is composed

```
assets/body.usda          # vehicle body, owns the `paint` variant set
        ▲
        │ references (one per station)
        │
stage/line.usda           # /World/Line
                          #   ST010_BodyDrop     → paint: gloss_white
                          #   ST020_Weld         → paint: gloss_white
                          #   ST030_PaintPrep    → paint: racing_blue
                          #   ST040_PaintBooth   → paint: racing_blue
                          #   ST050_Trim         → paint: matte_black
                          #   ST060_FinalInspect → paint: matte_black
```

The body asset is referenced once per station rather than duplicated, so each station
carries its own variant selection and transform while sharing a single source asset.
Replacing the stand-in geometry with a real CAD-derived mesh is a change to
`assets/body.usda` alone — the line layer, the metadata and every client are untouched.

### Manufacturing metadata

Each station prim carries custom namespaced attributes:

| Attribute | Type | Purpose |
|---|---|---|
| `manufacturing:partNumber` | `string` | part produced at the station |
| `manufacturing:station` | `string` | station identifier |
| `manufacturing:cycleTime` | `float` | ideal seconds per unit |
| `manufacturing:sequence` | `int` | position in the line |

Namespacing means a client discovers every station by attribute prefix alone — no
hardcoded prim paths, and adding a station to the stage requires no client changes.

## KPI model

`src/line_twin/kpi.py` is pure stdlib and side-effect free, so the same maths is used by
the Kit panel and by CI.

- **OEE** = availability × performance × quality, on the standard definitions.
- **Performance is capped at 1.0.** A station cannot beat its own ideal cycle time; an
  uncapped value quietly hides a wrong cycle-time constant behind a healthy-looking OEE.
- **Line throughput is gated by the bottleneck, not averaged.** A serial line runs no
  faster than its slowest station — averaging station throughputs is the usual way this
  metric gets reported wrong, and it flatters the line badly. The test suite pins this.

## Live telemetry

`src/line_twin/telemetry.py` replaces the synthetic samples in `report.py` with a
real pub/sub transport (MQTT, e.g. a local Mosquitto broker for dev, or a plant's
existing broker in production):

- `TelemetryPublisher` stands in for the plant's sensors - one JSON sample per
  station, published to `line/<station>/telemetry`.
- `TelemetryAggregator` is the subscriber side the Kit extension and the Unreal
  client each run - it holds the latest sample per station and turns them into the
  same `StationSample` objects `kpi.line_summary` already consumes.

Pointing this at a real plant is a publisher swap, not an architecture change: a
bridge reads the plant's actual protocol (often OPC-UA on the factory floor) and
republishes onto the same topics. `TelemetryAggregator`, the Kit panel and the KPI
maths do not need to change.

## Layout

```
assets/body.usda            generated - body asset with paint variant set
stage/line.usda             generated - six-station production line
src/line_twin/build_stage.py  USD authoring and stage read-back
src/line_twin/kpi.py          OEE and throughput maths
src/line_twin/report.py       headless KPI report off the composed stage (synthetic samples)
src/line_twin/telemetry.py    MQTT publisher + aggregator - the live equivalent of report.py
tests/test_kpi.py             unit tests
tests/test_telemetry.py       unit tests
```

## Next

- Kit extension: variant switcher plus a live KPI panel reading `TelemetryAggregator`.
- A real CAD-derived body mesh in place of the stand-in cube, via `usd-convert-cad`.
- `instanceable = true` on the referenced body asset, with a measured before/after.
- Unreal client consuming `stage/line.usda` through `UsdStageActor`, subscribed to
  the same MQTT topics as the Kit panel.
