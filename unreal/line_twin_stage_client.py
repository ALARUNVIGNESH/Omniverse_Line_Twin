"""Run inside Unreal Editor's Python console (Window > Developer Tools > Output
Log has a Python tab; or Edit > Project Settings > Python to run this as a
startup script) - NOT runnable outside UE5. Everything in this repo's
`line_twin` package (telemetry, KPI maths) is real and already unit tested;
this file is the one piece that genuinely needs Unreal itself to verify,
since there is no UE5 runtime available to test it against here.

What it does:
  1. Finds or spawns a UsdStageActor and points its root layer at
     stage/line.usda - Unreal's USD plugin renders it directly, no import
     step, and re-reads it live when the stage changes on disk.
  2. Connects a TelemetryAggregator to the same MQTT broker the Kit
     extension subscribes to, and drives a TextRenderActor with the live
     KPI summary - so Kit and Unreal are both watching the same feed, not
     two separate copies of the truth.

Before running:
  - Enable the "Universal Scene Description (USD)" plugin (Edit > Plugins).
  - pip install paho-mqtt into UE5's embedded Python (Project Settings >
    Python > Additional Paths, or `<UE5>/Engine/Binaries/ThirdParty/Python3/
    <platform>/python -m pip install paho-mqtt`).
  - Edit REPO_ROOT and LINE_STAGE_PATH below to match your machine
    (D:\\omniverse-line-twin per this project's local path).
"""

import sys
from pathlib import Path

import unreal

REPO_ROOT = Path(r"D:\omniverse-line-twin")
LINE_STAGE_PATH = REPO_ROOT / "stage" / "line.usda"

_src = str(REPO_ROOT / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from line_twin.telemetry import TelemetryAggregator  # noqa: E402  (path setup above)

_STAGE_ACTOR_LABEL = "LineTwinStage"
_KPI_TEXT_ACTOR_LABEL = "LineTwinKPIReadout"


def _find_or_spawn_stage_actor() -> "unreal.Actor":
    world = unreal.EditorLevelLibrary.get_editor_world()
    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        if actor.get_actor_label() == _STAGE_ACTOR_LABEL:
            return actor

    stage_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.UsdStageActor, unreal.Vector(0, 0, 0)
    )
    stage_actor.set_actor_label(_STAGE_ACTOR_LABEL)
    return stage_actor


def _find_or_spawn_kpi_text_actor() -> "unreal.TextRenderActor":
    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        if actor.get_actor_label() == _KPI_TEXT_ACTOR_LABEL:
            return actor

    text_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.TextRenderActor, unreal.Vector(0, 0, 300)
    )
    text_actor.set_actor_label(_KPI_TEXT_ACTOR_LABEL)
    text_actor.text_render.set_editor_property("text_render_color", unreal.LinearColor(1, 1, 1, 1))
    text_actor.text_render.set_world_size(24.0)
    return text_actor


def _set_kpi_text(text_actor, summary: dict) -> None:
    lines = [
        f"bottleneck: {summary['bottleneck'] or '-'}",
        f"line throughput: {summary['line_throughput_per_hour']:.1f} good units/hour",
    ]
    for row in summary["stations"]:
        lines.append(f"{row['station']:<20} oee={row['oee']:.1%}  {row['throughput_per_hour']:.1f}/hr")
    text_actor.text_render.set_text(unreal.Text("\n".join(lines)))


def setup() -> TelemetryAggregator:
    stage_actor = _find_or_spawn_stage_actor()
    stage_actor.set_editor_property("root_layer", unreal.FilePath(path=str(LINE_STAGE_PATH)))

    text_actor = _find_or_spawn_kpi_text_actor()

    def on_update(_station: str) -> None:
        # This callback fires on paho-mqtt's own thread. Unlike Kit,
        # Unreal's Python/Slate calls used here are generally safe from a
        # background thread for simple property sets, but if you see
        # crashes or hitches, marshal this through unreal.register_slate_
        # post_tick_callback the same way the Kit extension marshals to its
        # per-frame update event.
        aggregator = _AGGREGATOR
        if aggregator is not None:
            _set_kpi_text(text_actor, aggregator.summary())

    aggregator = TelemetryAggregator(on_update=on_update)
    aggregator.connect()
    return aggregator


_AGGREGATOR = setup()

unreal.log("line_twin: UsdStageActor pointed at %s, KPI readout live." % LINE_STAGE_PATH)
