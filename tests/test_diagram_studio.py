"""Pruebas del generador offline de diagramas KiCad 10 (.kicad_sch/.kicad_pro/.svg) y arquitectura SVG/Mermaid."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from agente_ia.diagram_studio import (
    build_kicad_project,
    build_kicad_schematic,
    create_kicad_diagram_bundle,
    render_architecture_svg,
    render_schematic_svg,
)
from agente_ia.skills import SkillStore
from agente_ia.slash_palette import build_slash_catalog, resolve_slash_command
from agente_ia.workspace import SafeWorkspace


def _parens_balanced(sexp: str) -> bool:
    depth = 0
    in_str = False
    esc = False
    for ch in sexp:
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and not in_str


def test_kicad_10_schematic_bundle_is_valid_sexp_json_and_svg(tmp_path: Path):
    ws = SafeWorkspace(str(tmp_path))
    components = [
        {"lib_id": "power:+5V", "ref": "#PWR01", "value": "+5V", "x": 60.96, "y": 50.8},
        {"lib_id": "Device:R", "ref": "R1", "value": "330R", "footprint": "Resistor_SMD:R_0805_2012Metric", "x": 60.96, "y": 66.04},
        {"lib_id": "Device:LED", "ref": "D1", "value": "LED_Rojo", "footprint": "LED_SMD:LED_0805_2012Metric", "x": 86.36, "y": 66.04},
        {"lib_id": "power:GND", "ref": "#PWR02", "value": "GND", "x": 106.68, "y": 81.28},
    ]
    wires = [
        {"x1": 60.96, "y1": 50.8, "x2": 60.96, "y2": 62.23},
        {"x1": 60.96, "y1": 69.85, "x2": 82.55, "y2": 66.04},
        {"x1": 90.17, "y1": 66.04, "x2": 106.68, "y2": 81.28},
    ]
    labels = [{"name": "LED_ANODO", "x": 71.12, "y": 66.04}]

    res = create_kicad_diagram_bundle(
        ws,
        "diagramas/led_5v",
        "led_5v",
        "Indicador LED 5V",
        components,
        wires=wires,
        labels=labels,
        junctions=[{"x": 60.96, "y": 66.04}],
    )
    assert res["ok"] is True

    sch_text = (tmp_path / res["schematic"]).read_text(encoding="utf-8")
    assert sch_text.startswith("(kicad_sch")
    assert "(lib_symbols" in sch_text
    assert 'Device:R' in sch_text and 'Device:LED' in sch_text
    assert 'LED_ANODO' in sch_text
    assert _parens_balanced(sch_text), "El S-expression .kicad_sch debe tener paréntesis balanceados"

    pro_data = json.loads((tmp_path / res["project"]).read_text(encoding="utf-8"))
    assert pro_data["meta"]["filename"] == "led_5v.kicad_pro"

    svg_text = (tmp_path / res["svg_preview"]).read_text(encoding="utf-8")
    root = ET.fromstring(svg_text)
    assert root.tag.endswith("svg")
    assert "R1" in svg_text and "330R" in svg_text and "LED_ANODO" in svg_text


def test_architecture_svg_and_mermaid_generation():
    svg, mmd = render_architecture_svg(
        "Sistema ESP32 + FastAPI",
        nodes=[
            {"id": "esp32", "label": "ESP32-S3", "subtitle": "Sensores", "kind": "hw"},
            {"id": "api", "label": "API FastAPI", "subtitle": "REST", "kind": "api"},
            {"id": "db", "label": "SQLite", "subtitle": "Histórico", "kind": "db"},
        ],
        edges=[
            {"from": "esp32", "to": "api", "label": "JSON"},
            {"from": "api", "to": "db", "label": "SQL"},
        ],
    )
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert "ESP32-S3" in svg and "API FastAPI" in svg
    assert "flowchart LR" in mmd and "esp32 -->|JSON| api" in mmd


def test_slash_kicad_and_diagrama_work_with_and_without_skill(tmp_path: Path):
    r_plain = resolve_slash_command("/kicad crea un regulador 5V a 3.3V con AMS1117", None)
    assert r_plain["type"] == "prompt" and r_plain.get("auto_autonomous") is True

    store = SkillStore(tmp_path / "skills")
    bundle = tmp_path / "bundle"
    (bundle / "kicad-diagramas").mkdir(parents=True)
    (bundle / "kicad-diagramas" / "SKILL.md").write_text(
        "---\nname: kicad-diagramas\ndescription: KiCad 10 y diagramas SVG/Mermaid\n---\n\n# KiCad\n",
        encoding="utf-8",
    )
    sid = store.install_bundled(bundle, "kicad-diagramas")
    cmds = {e.command for e in build_slash_catalog(store)}
    assert {"/kicad", "/kicad-diagramas"} <= cmds
    r_skill = resolve_slash_command("/diagrama arquitectura de microservicios", store)
    assert r_skill["type"] == "invoke_skill" and r_skill["skill_id"] == sid and r_skill.get("auto_autonomous") is True
