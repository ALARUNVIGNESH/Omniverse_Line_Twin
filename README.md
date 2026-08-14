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
| Omniverse Kit extension with in-viewport KPI panel | working — verified live in Kit (panel, variant dropdown, MQTT KPIs) |
| USD native instancing on the referenced body asset | working, unit tested, measured before/after |
| CAD-derived station integration | working, unit tested (stub asset - swap in real `usd-convert-cad` output) |
| PBR materials (UsdShade/UsdPreviewSurface) per paint variant | working — unit tested, and verified rendering in Unreal |
| Physics scene + kinematic inspection-gate joint | schema authored and unit tested; runtime simulation unverified (needs Kit/Unreal PhysX) |
| Bill of materials per station | working, unit tested |
| Routing graph with a validator that catches cycles/gaps | working, unit tested against deliberately broken input |
| Lighting (dome + key/fill) and a framed camera | schema authored and unit tested; RTX-rendered result unverified |
| Unreal Engine 5 `UsdStageActor` client | working — stage renders in UE5 with correct per-station materials |

Everything marked *working* runs from a clean checkout with the commands below.

## Verified end to end

Run in Omniverse Kit (Kit Base Editor built from `kit-app-template`) and in Unreal
Engine 5, not just in tests:

- The Kit extension loads, reads the six stations off the composed stage, and its
  KPI panel updates live from MQTT — stations heard, per-station OEE and
  throughput, and the bottleneck correctly identified as the slowest station.
- Switching the paint variant from the panel re-binds the material on every
  station (`set_paint_variant` returns 6; each station's `ComputeBoundMaterial`
  follows the new variant).
- Unreal renders the same `stage/line.usda` through a `UsdStageActor` with no
  import step, showing the three paint variants correctly across the six stations.

Two things are deliberately not claimed. The physics gate is authored and
schema-tested but has not been stepped under PhysX, and the lighting has not been
seen under an RTX render — both need hardware this was not built on. The CAD
integration path is tested against a generated stub rather than a real STEP file.

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

## Materials

The original body asset only set `displayColor` per paint variant - a flat
viewport preview color, not an actual shaded material. `src/line_twin/materials.py`
replaces that with real `UsdShade`/`UsdPreviewSurface` materials: diffuse
color, roughness, metallic, and clearcoat, tuned differently per finish (gloss
white and racing blue lean into a strong clearcoat like real automotive paint;
matte black has none). Materials are authored once under `/Body/Materials`
and bound inside each variant's own edit context, so selecting a paint
variant switches the bound *material*, not just a display color - verified
end-to-end through the full station reference chain, not just on the
isolated body asset. UsdPreviewSurface is render-delegate-agnostic, so the
same binding resolves consistently in Kit, in the Unreal client, and in
usdview with no per-engine re-authoring.

## Bill of materials and routing

Before this, each station only carried the one part it *produces*
(`manufacturing:partNumber`) - nothing about what goes into it, and its
position in the line was implicit in a Python list index rather than an
authored graph. `src/line_twin/bom.py` and `src/line_twin/routing.py` close
both:

- **BOM** - sub-components and quantities per station, authored as parallel
  array attributes on the station prim (not child prims - stations are
  instanceable, and USD doesn't allow authoring new prims under an
  instanceable prim's subtree, the same constraint the inspection gate hit).
- **Routing** - explicit `predecessor`/`successor` attributes per station,
  plus a validator that walks the graph itself rather than trusting sequence
  numbers. `build_line_stage()` calls it on every build and raises loudly if
  the routing is ever broken - the test suite proves this by feeding it
  deliberately broken graphs (a cycle, a gap, two entry points, a dangling
  reference) and confirming each one is rejected, not just that the happy
  path passes.

## Lighting

`src/line_twin/lighting.py` adds a `UsdLux` dome light plus a key/fill rect
light pair, and a camera framed on the whole line - the stage had zero
lights before this, which would render flat and gray regardless of how
correct the geometry and materials underneath it are. Schema-verified
(intensities, relative brightness, camera focal length); the actual
RTX-rendered result is unverified, same caveat as the physics simulation.

## Physics and kinematics

`src/line_twin/physics_setup.py` authors a `PhysicsScene` and a small,
honest kinematic mechanism: a two-link inspection gate at the final
inspection station (a kinematic base + a dynamic arm connected by a
`UsdPhysics.RevoluteJoint`, swinging from rest to a scanning position). This
is real `UsdPhysics` schema, verified with tests that check joint type, axis,
limits, and body relationships - the same schema a PhysX-enabled runtime
would consume to actually simulate it. **It has not been runtime-simulated**
- that needs Kit's or Unreal's PhysX, neither of which is available in the
environment this was built in. The gate lives as a sibling of
`ST060_FinalInspect` rather than a child of it, because that station is
instanceable and USD does not allow authoring new prims under an
instanceable prim's own subtree.

## Kit viewport extension

`exts/line_twin.viewport/` is a Kit extension: a paint-variant dropdown that
applies to every station at once, plus a live KPI panel reading
`TelemetryAggregator`. The stage-manipulation logic (`src/line_twin/panel_controller.py`
- finding station prims, reading available paint variants, applying a variant)
takes a `Usd.Stage` as an argument rather than owning one, so it's unit tested
against a plain `Usd.Stage.Open()` handle exactly like the rest of the suite.
The extension itself passes it `omni.usd.get_context().get_stage()` - the
actual stage open in the viewport - so `extension.py` does nothing but wire
that tested logic to widgets. It is the one file in this repo that can't be
exercised outside Kit, and is kept as thin as possible for that reason.

To load it: add this repo's `exts` folder to Kit's extension search paths,
enable **Line Twin Viewport** in the Extension Manager, open `stage/line.usda`
in the viewport, then (with a local broker running) `python -m line_twin.telemetry
--publish` in a separate terminal to see the panel update live.

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

## USD instancing

All six stations reference the same body asset, so each one is marked
`instanceable = true` (in `build_stage.py`). USD shares one composed copy of
the geometry across every station whose full composed opinion - the
reference plus the paint variant selection - matches, instead of expanding
six fully independent copies. Because the three paint variants aren't all
the same, this yields one shared prototype per distinct variant in use (3
here, from 6 stations), not one for the whole line.

`python -m line_twin.instancing_report` builds the line both ways and prints
the real difference:

```
BEFORE  instanceable = false        AFTER   instanceable = true
  prims_traversed_default: 14         prims_traversed_default: 8
  prototype_count: 0                  prototype_count: 3
```

## CAD integration

`src/line_twin/cad_integration.py` adds a station whose geometry comes from
an externally converted CAD file rather than the synthetic body asset -
`add_cad_station()` references it in and tags it with the same
`manufacturing:*` metadata every other station carries, so it shows up in
`read_stations()`, the KPI panel, and the Unreal client with no special
casing anywhere downstream.

Running the actual conversion needs NVIDIA's `usd-convert-cad` (or any
CAD-to-USD tool) on a real STEP/IGES file - not something this repo runs
standalone. `build_stub_cad_asset()` exists only so the integration path
itself (add, tag, read back) is unit tested before a real converted asset
exists:

```python
from line_twin.cad_integration import add_cad_station

add_cad_station(
    cad_asset_path="assets/my_converted_part.usda",  # usd-convert-cad output
    name="ST070_WeldFixture",
    part_number="FIX-9001",
    cycle_time=35.0,
    sequence=6,
    x_position=48.0,
)
```

## Unreal client

`unreal/line_twin_stage_client.py` runs inside Unreal Editor's Python
console (not runnable outside UE5 - see the file's own header for setup).
It points a `UsdStageActor` at `stage/line.usda` and drives an on-screen KPI
readout from the same `TelemetryAggregator` the Kit extension uses, so Kit
and Unreal are both watching the same live feed rather than two separate
copies of the truth.

## Layout

```
assets/body.usda            generated - body asset with paint variant set
stage/line.usda             generated - six-station production line
src/line_twin/build_stage.py  USD authoring and stage read-back
src/line_twin/kpi.py          OEE and throughput maths
src/line_twin/report.py       headless KPI report off the composed stage (synthetic samples)
src/line_twin/telemetry.py    MQTT publisher + aggregator - the live equivalent of report.py
src/line_twin/panel_controller.py  stage logic behind the Kit extension - unit tested
src/line_twin/instancing_report.py  measured before/after for USD instancing
src/line_twin/cad_integration.py  reference a CAD-derived asset in as a station
src/line_twin/materials.py    real UsdShade/UsdPreviewSurface materials per paint variant
src/line_twin/physics_setup.py  physics scene + kinematic inspection-gate joint (schema only)
src/line_twin/bom.py          bill of materials per station
src/line_twin/routing.py      routing graph + validator (catches cycles/gaps)
src/line_twin/lighting.py     dome/key/fill lighting + framed camera
unreal/line_twin_stage_client.py  UE5 client - needs Unreal itself to run
exts/line_twin.viewport/      Kit extension - thin omni.ui/omni.ext wrapper over panel_controller.py
tests/test_kpi.py             unit tests
tests/test_telemetry.py       unit tests
tests/test_panel_controller.py  unit tests, incl. the instancing/prototype assertion
tests/test_cad_integration.py  unit tests, isolated from the tracked stage file
tests/test_materials.py       unit tests, incl. end-to-end resolution through station composition
tests/test_physics_setup.py   unit tests for the physics/joint schema
tests/test_bom.py             unit tests
tests/test_routing.py         unit tests, incl. deliberately broken routing graphs
tests/test_lighting.py        unit tests
```

## Next

- Run a real STEP file through `usd-convert-cad` and swap it in for the stub
  in `cad_integration.build_stub_cad_asset`.
- Step the inspection-gate joint under PhysX, and render the lighting under RTX,
  on RT-capable hardware.
- Subscribe the Unreal client to the same MQTT topics as the Kit panel
  (`unreal/line_twin_stage_client.py`, not yet run in UE5).
- Sync the Kit panel's paint dropdown to the stage's current variant selection on
  build — it currently always starts at the first option.
