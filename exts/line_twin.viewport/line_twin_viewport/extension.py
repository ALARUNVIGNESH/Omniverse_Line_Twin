"""Kit extension: paint-variant switcher and live KPI panel for the line twin.

Deliberately thin. The KPI maths and telemetry aggregation are not reimplemented
here - this extension imports the same `line_twin` package that `tests/` and
`report.py` already exercise, so the panel and the CI-tested code are one thing,
not two. The repo's `src` directory is added to `sys.path` at import time so
`import line_twin` resolves correctly no matter where Kit was launched from.

Load this by adding this repo's `exts` folder to Kit's extension search paths,
then enabling "Line Twin Viewport" in the Extension Manager, with
`stage/line.usda` open in the viewport.

Threading note: paho-mqtt's network loop runs on a background thread, but Kit's
UI must only be touched from the main thread. The telemetry callback below does
nothing but set a flag; the actual label refresh happens in `_on_update_frame`,
which runs on Kit's main-thread per-frame update event.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Optional

import omni.ext
import omni.kit.app
import omni.ui as ui
import omni.usd

_REPO_SRC = Path(__file__).resolve().parents[3] / "src"
if str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

from line_twin.panel_controller import (  # noqa: E402  (path setup above)
    available_paint_variants,
    set_paint_variant,
    station_prims,
)
from line_twin.telemetry import TelemetryAggregator  # noqa: E402


class LineTwinViewportExtension(omni.ext.IExt):
    """Registered via extension.toml's [[python.module]] entry."""

    def on_startup(self, ext_id: str) -> None:
        self._aggregator: Optional[TelemetryAggregator] = None
        self._dirty = threading.Event()
        self._status_label: Optional[ui.Label] = None
        self._line_label: Optional[ui.Label] = None
        self._station_labels: dict[str, ui.Label] = {}

        self._window = ui.Window("Line Twin", width=340, height=440)
        self._window.frame.set_build_fn(self._build_ui)

        self._update_sub = (
            omni.kit.app.get_app()
            .get_update_event_stream()
            .create_subscription_to_pop(self._on_update_frame, name="line_twin.viewport.update")
        )

        self._connect_telemetry()

    def on_shutdown(self) -> None:
        if self._update_sub is not None:
            self._update_sub.unsubscribe()
            self._update_sub = None
        if self._aggregator is not None:
            self._aggregator.disconnect()
            self._aggregator = None
        self._window = None

    # -- UI ------------------------------------------------------------

    def _build_ui(self) -> None:
        stage = omni.usd.get_context().get_stage()
        stations = station_prims(stage)
        variants = available_paint_variants(stage)
        self._station_labels = {}

        with ui.VStack(spacing=6, height=0):
            ui.Label("Paint variant (applies to every station)", height=20)
            if variants:
                combo = ui.ComboBox(0, *variants)

                def on_variant_changed(item_model, _item):
                    index = item_model.get_item_value_model().as_int
                    self._set_paint_variant(variants[index])

                combo.model.add_item_changed_fn(on_variant_changed)
            else:
                ui.Label("(open stage/line.usda, then Refresh)", height=20)

            ui.Button("Refresh from stage", height=24, clicked_fn=self._window.frame.rebuild)

            ui.Separator(height=10)
            ui.Label("Live KPIs (MQTT)", height=20)
            self._status_label = ui.Label("waiting for telemetry...", height=20)
            self._line_label = ui.Label("", height=20)

            ui.Separator(height=10)
            with ui.ScrollingFrame(height=180):
                with ui.VStack(spacing=2):
                    if stations:
                        for prim in stations:
                            name = prim.GetAttribute("manufacturing:station").Get()
                            self._station_labels[name] = ui.Label(f"{name}: --")
                    else:
                        ui.Label("no stations found on the open stage")

        # A rebuild (e.g. from the Refresh button) drops the old labels - if
        # telemetry has already arrived, repaint immediately instead of waiting
        # for the next MQTT message.
        if self._aggregator is not None:
            self._refresh_kpi_labels()

    # -- Variant switching ------------------------------------------------

    def _set_paint_variant(self, variant_name: str) -> None:
        stage = omni.usd.get_context().get_stage()
        set_paint_variant(stage, variant_name)

    # -- Telemetry ----------------------------------------------------------

    def _connect_telemetry(self) -> None:
        def on_update(_station: str) -> None:
            # Fires on paho-mqtt's network thread - only flag, never touch ui.* here.
            self._dirty.set()

        self._aggregator = TelemetryAggregator(on_update=on_update)
        try:
            self._aggregator.connect()
        except Exception as exc:  # broker not reachable, etc. - don't crash the extension
            if self._status_label is not None:
                self._status_label.text = f"telemetry offline: {exc}"

    def _on_update_frame(self, _event) -> None:
        if self._dirty.is_set():
            self._dirty.clear()
            self._refresh_kpi_labels()

    def _refresh_kpi_labels(self) -> None:
        if self._aggregator is None:
            return
        summary = self._aggregator.summary()

        if self._status_label is not None:
            self._status_label.text = (
                f"stations heard: {summary['station_count']}   "
                f"bottleneck: {summary['bottleneck']}"
            )
        if self._line_label is not None:
            self._line_label.text = (
                f"line throughput: {summary['line_throughput_per_hour']:.1f} good units/hr"
            )
        for row in summary["stations"]:
            label = self._station_labels.get(row["station"])
            if label is not None:
                label.text = (
                    f"{row['station']}: OEE {row['oee']:.0%}  |  "
                    f"{row['throughput_per_hour']:.1f}/hr"
                )
