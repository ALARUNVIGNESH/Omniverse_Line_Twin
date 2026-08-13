"""Run from the repo root: python check_status.py

Checks every file delivered across today's sprint against what's actually
on disk, grouped by the batch it was delivered in. Doesn't touch git or
run tests - just tells you what's copied in and what isn't yet.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent

BATCHES = {
    "Day 1 - MQTT telemetry": [
        "src/line_twin/telemetry.py",
        "tests/test_telemetry.py",
    ],
    "Day 1-2 - Kit extension": [
        "src/line_twin/panel_controller.py",
        "tests/test_panel_controller.py",
        "exts/line_twin.viewport/config/extension.toml",
        "exts/line_twin.viewport/line_twin_viewport/__init__.py",
        "exts/line_twin.viewport/line_twin_viewport/extension.py",
    ],
    "Day 3 - CAD + instancing": [
        "src/line_twin/instancing_report.py",
        "src/line_twin/cad_integration.py",
        "tests/test_cad_integration.py",
    ],
    "Day 4 - Unreal client": [
        "unreal/line_twin_stage_client.py",
    ],
    "Materials + physics": [
        "src/line_twin/materials.py",
        "src/line_twin/physics_setup.py",
        "tests/test_materials.py",
        "tests/test_physics_setup.py",
    ],
    "BOM + routing + lighting": [
        "src/line_twin/bom.py",
        "src/line_twin/routing.py",
        "src/line_twin/lighting.py",
        "tests/test_bom.py",
        "tests/test_routing.py",
        "tests/test_lighting.py",
    ],
}

total = 0
present = 0

for batch, files in BATCHES.items():
    print(f"\n{batch}")
    for rel_path in files:
        total += 1
        ok = (ROOT / rel_path).exists()
        present += ok
        mark = "OK  " if ok else "MISSING"
        print(f"  [{mark}] {rel_path}")

print(f"\n{present}/{total} files present.")
print("\nNext: run `python -m pytest -q` - if anything above is missing,")
print("pytest will fail on import and name the exact missing module.")
