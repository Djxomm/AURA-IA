"""Generador local de diagramas electrónicos KiCad 10 (.kicad_sch / .kicad_pro), esquemáticos SVG
y diagramas de arquitectura/bloques/flujo (SVG + Mermaid) 100 % offline para AURA."""

from __future__ import annotations

import html
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from .workspace import SafeWorkspace, WorkspaceError


_NS_UUID = uuid.UUID("a4b21008-7c1d-4d5e-9a21-001008a0b10c")


def _det_uuid(seed: str) -> str:
    return str(uuid.uuid5(_NS_UUID, seed))


def find_kicad_cli(runtime: Path | None = None) -> dict[str, str | None]:
    """Detecta kicad-cli.exe, eeschema.exe y pcbnew.exe en instalaciones estándar de KiCad en Windows."""
    roots: list[Path] = []
    if runtime is not None:
        roots.append(Path(runtime).resolve() / "herramientas" / "kicad" / "bin")
    for base in (
        Path(r"C:\Program Files\KiCad"),
        Path(r"C:\Program Files (x86)\KiCad"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "KiCad",
        Path(r"D:\KiCad"),
    ):
        if base.is_dir():
            for ver_dir in sorted(base.glob("*"), reverse=True):
                bin_dir = ver_dir / "bin"
                if bin_dir.is_dir():
                    roots.append(bin_dir)
            if (base / "bin").is_dir():
                roots.append(base / "bin")

    found: dict[str, str | None] = {"bin_dir": None, "kicad_cli": None, "eeschema": None, "pcbnew": None}
    ext = ".exe" if os.name == "nt" else ""
    for d in roots:
        cli = d / f"kicad-cli{ext}"
        if cli.is_file():
            found["bin_dir"] = str(d.resolve())
            found["kicad_cli"] = str(cli.resolve())
            if (d / f"eeschema{ext}").is_file():
                found["eeschema"] = str((d / f"eeschema{ext}").resolve())
            if (d / f"pcbnew{ext}").is_file():
                found["pcbnew"] = str((d / f"pcbnew{ext}").resolve())
            break
    if found["kicad_cli"] is None:
        cli_path = shutil.which("kicad-cli")
        if cli_path:
            found["kicad_cli"] = cli_path
            found["bin_dir"] = str(Path(cli_path).resolve().parent)
    return found


def _sexp_escape(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


def _lib_symbol_def(lib_id: str) -> str:
    """Genera una definición S-expression válida de símbolo embebido para abrir directamente en KiCad 9/10."""
    kind = lib_id.split(":")[-1].lower()
    if kind in ("r", "resistor"):
        body = (
            '      (rectangle (start -1.016 -2.54) (end 1.016 2.54) (stroke (width 0.254) (type default)) (fill (type none)))\n'
            '      (pin passive line (at 0 3.81 270) (length 1.27) (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))\n'
            '      (pin passive line (at 0 -3.81 90) (length 1.27) (name "~" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))'
        )
        prefix = "R"
    elif kind in ("c", "capacitor", "c_small"):
        body = (
            '      (polyline (pts (xy -2.032 -0.762) (xy 2.032 -0.762)) (stroke (width 0.508) (type default)) (fill (type none)))\n'
            '      (polyline (pts (xy -2.032 0.762) (xy 2.032 0.762)) (stroke (width 0.508) (type default)) (fill (type none)))\n'
            '      (pin passive line (at 0 3.81 270) (length 2.794) (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))\n'
            '      (pin passive line (at 0 -3.81 90) (length 2.794) (name "~" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))'
        )
        prefix = "C"
    elif kind in ("led", "d", "diode"):
        body = (
            '      (polyline (pts (xy -1.27 -1.27) (xy -1.27 1.27) (xy 1.27 0) (xy -1.27 -1.27)) (stroke (width 0.254) (type default)) (fill (type none)))\n'
            '      (polyline (pts (xy 1.27 -1.27) (xy 1.27 1.27)) (stroke (width 0.254) (type default)) (fill (type none)))\n'
            '      (pin passive line (at -3.81 0 0) (length 2.54) (name "A" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))\n'
            '      (pin passive line (at 3.81 0 180) (length 2.54) (name "K" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))'
        )
        prefix = "D"
    elif kind in ("gnd", "vcc", "+5v", "+3v3", "+12v"):
        is_gnd = kind == "gnd"
        if is_gnd:
            body = (
                '      (polyline (pts (xy 0 0) (xy 0 -1.27) (xy 1.27 -1.27) (xy 0 -2.54) (xy -1.27 -1.27) (xy 0 -1.27)) (stroke (width 0) (type default)) (fill (type none)))\n'
                '      (pin power_in line (at 0 0 270) (length 0) hide (name "GND" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))'
            )
        else:
            body = (
                '      (polyline (pts (xy -0.762 1.27) (xy 0 2.54) (xy 0.762 1.27)) (stroke (width 0) (type default)) (fill (type none)))\n'
                '      (polyline (pts (xy 0 0) (xy 0 2.54)) (stroke (width 0) (type default)) (fill (type none)))\n'
                f'      (pin power_in line (at 0 0 90) (length 0) hide (name "{_sexp_escape(kind.upper())}" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))'
            )
        prefix = "#PWR"
    else:
        body = (
            '      (rectangle (start -5.08 -5.08) (end 5.08 5.08) (stroke (width 0.254) (type default)) (fill (type background)))\n'
            '      (pin input line (at -7.62 2.54 0) (length 2.54) (name "IN1" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))\n'
            '      (pin input line (at -7.62 -2.54 0) (length 2.54) (name "IN2" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))\n'
            '      (pin output line (at 7.62 2.54 180) (length 2.54) (name "OUT1" (effects (font (size 1.27 1.27)))) (number "3" (effects (font (size 1.27 1.27)))))\n'
            '      (pin power_in line (at 7.62 -2.54 180) (length 2.54) (name "GND" (effects (font (size 1.27 1.27)))) (number "4" (effects (font (size 1.27 1.27)))))'
        )
        prefix = "U"

    return (
        f'    (symbol "{_sexp_escape(lib_id)}" (in_bom yes) (on_board yes)\n'
        f'      (property "Reference" "{prefix}" (at 2.032 0 90) (effects (font (size 1.27 1.27))))\n'
        f'      (property "Value" "{_sexp_escape(lib_id.split(":")[-1])}" (at 0 0 90) (effects (font (size 1.27 1.27))))\n'
        f'      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
        f'      (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
        f'      (symbol "{_sexp_escape(lib_id.split(":")[-1])}_1_1"\n'
        f'{body}\n'
        f'      )\n'
        f'    )'
    )


def build_kicad_schematic(
    title: str,
    components: list[dict[str, Any]],
    *,
    wires: list[dict[str, Any]] | None = None,
    labels: list[dict[str, Any]] | None = None,
    junctions: list[dict[str, Any]] | None = None,
    paper: str = "A4",
    rev: str = "1.0",
) -> str:
    """Construye un archivo esquemático `.kicad_sch` S-expression válido para KiCad 9/10."""
    if not components:
        raise WorkspaceError("El esquemático KiCad requiere al menos un componente en `components`.")

    root_uuid = _det_uuid(f"sch:{title}")
    lib_ids = list(dict.fromkeys(str(c.get("lib_id") or "Device:R") for c in components))
    lib_block = "\n".join(_lib_symbol_def(lid) for lid in lib_ids)

    sym_blocks: list[str] = []
    for idx, comp in enumerate(components, start=1):
        lib_id = str(comp.get("lib_id") or "Device:R")
        ref = str(comp.get("ref") or f"U{idx}")
        val = str(comp.get("value") or lib_id.split(":")[-1])
        fp = str(comp.get("footprint") or "")
        x = float(comp.get("x", 60.96 + (idx - 1) * 30.48))
        y = float(comp.get("y", 76.2))
        rot = int(comp.get("rotation", 0))
        uid = _det_uuid(f"sym:{title}:{ref}:{idx}")
        sym_blocks.append(
            f'  (symbol (lib_id "{_sexp_escape(lib_id)}") (at {x:.2f} {y:.2f} {rot}) (unit 1)\n'
            f'    (in_bom yes) (on_board yes) (dnp no)\n'
            f'    (uuid "{uid}")\n'
            f'    (property "Reference" "{_sexp_escape(ref)}" (at {x + 2.54:.2f} {y - 2.54:.2f} 0) (effects (font (size 1.27 1.27))))\n'
            f'    (property "Value" "{_sexp_escape(val)}" (at {x + 2.54:.2f} {y + 2.54:.2f} 0) (effects (font (size 1.27 1.27))))\n'
            f'    (property "Footprint" "{_sexp_escape(fp)}" (at {x:.2f} {y:.2f} 0) (effects (font (size 1.27 1.27)) hide))\n'
            f'    (property "Datasheet" "~" (at {x:.2f} {y:.2f} 0) (effects (font (size 1.27 1.27)) hide))\n'
            f'  )'
        )

    wire_blocks: list[str] = []
    for idx, w in enumerate(wires or [], start=1):
        x1, y1 = float(w["x1"]), float(w["y1"])
        x2, y2 = float(w["x2"]), float(w["y2"])
        uid = _det_uuid(f"wire:{title}:{idx}:{x1}:{y1}:{x2}:{y2}")
        wire_blocks.append(
            f'  (wire (pts (xy {x1:.2f} {y1:.2f}) (xy {x2:.2f} {y2:.2f}))\n'
            f'    (stroke (width 0) (type default))\n'
            f'    (uuid "{uid}")\n'
            f'  )'
        )

    junc_blocks: list[str] = []
    for idx, j in enumerate(junctions or [], start=1):
        jx, jy = float(j["x"]), float(j["y"])
        uid = _det_uuid(f"junc:{title}:{idx}:{jx}:{jy}")
        junc_blocks.append(f'  (junction (at {jx:.2f} {jy:.2f}) (diameter 0) (color 0 0 0 0) (uuid "{uid}"))')

    label_blocks: list[str] = []
    for idx, lb in enumerate(labels or [], start=1):
        name = str(lb.get("name") or f"NET_{idx}")
        lx, ly = float(lb["x"]), float(lb["y"])
        rot = int(lb.get("rotation", 0))
        uid = _det_uuid(f"lbl:{title}:{idx}:{name}")
        label_blocks.append(
            f'  (label "{_sexp_escape(name)}" (at {lx:.2f} {ly:.2f} {rot})\n'
            f'    (effects (font (size 1.27 1.27)) (justify left bottom))\n'
            f'    (uuid "{uid}")\n'
            f'  )'
        )

    sections = "\n".join(part for part in ("\n".join(sym_blocks), "\n".join(wire_blocks), "\n".join(junc_blocks), "\n".join(label_blocks)) if part)
    return (
        '(kicad_sch\n'
        '  (version 20250114)\n'
        '  (generator "aura-kicad-diagram-studio")\n'
        '  (generator_version "10.0")\n'
        f'  (uuid "{root_uuid}")\n'
        f'  (paper "{_sexp_escape(paper)}")\n'
        '  (title_block\n'
        f'    (title "{_sexp_escape(title)}")\n'
        f'    (rev "{_sexp_escape(rev)}")\n'
        '    (company "AURA IA · KiCad 10 Studio")\n'
        '  )\n'
        '  (lib_symbols\n'
        f'{lib_block}\n'
        '  )\n'
        f'{sections}\n'
        '  (sheet_instances\n'
        '    (path "/" (page "1"))\n'
        '  )\n'
        ')\n'
    )


def build_kicad_project(project_name: str) -> str:
    """Genera un archivo de proyecto `.kicad_pro` JSON mínimo compatible con KiCad 10."""
    payload = {
        "meta": {"filename": f"{project_name}.kicad_pro", "version": 1},
        "board": {"design_settings": {"defaults": {"board_outline_line_width": 0.1, "copper_line_width": 0.25}}},
        "schematic": {"drawing": {"default_line_thickness": 6.0, "default_text_size": 50.0}},
        "net_settings": {"classes": [{"name": "Default", "clearance": 0.2, "track_width": 0.25, "via_diameter": 0.6, "via_drill": 0.3}]},
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def render_schematic_svg(
    title: str,
    components: list[dict[str, Any]],
    *,
    wires: list[dict[str, Any]] | None = None,
    labels: list[dict[str, Any]] | None = None,
    junctions: list[dict[str, Any]] | None = None,
) -> str:
    """Renderiza un esquemático electrónico vectorial SVG limpio de alta legibilidad 100 % offline."""
    scale = 4.2
    pts_x = [float(c.get("x", 60.0)) for c in components]
    pts_y = [float(c.get("y", 60.0)) for c in components]
    for w in wires or []:
        pts_x.extend([float(w["x1"]), float(w["x2"])])
        pts_y.extend([float(w["y1"]), float(w["y2"])])
    min_x, max_x = min(pts_x) - 25.0, max(pts_x) + 35.0
    min_y, max_y = min(pts_y) - 22.0, max(pts_y) + 28.0
    width = max(720, int((max_x - min_x) * scale))
    height = max(440, int((max_y - min_y) * scale) + 64)

    def tx(x: float) -> float:
        return (x - min_x) * scale

    def ty(y: float) -> float:
        return (y - min_y) * scale + 48.0

    elems: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        '  <defs><pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M 24 0 L 0 0 0 24" fill="none" stroke="#182a42" stroke-width="1"/></pattern></defs>',
        f'  <rect width="{width}" height="{height}" fill="#081220"/>',
        f'  <rect width="{width}" height="{height}" fill="url(#grid)"/>',
        f'  <rect x="12" y="10" width="{width - 24}" height="34" rx="8" fill="#102138" stroke="#2c4e76"/>',
        f'  <text x="26" y="32" fill="#e6f2ff" font-family="Segoe UI, sans-serif" font-size="16" font-weight="700">{html.escape(title)} · Esquemático KiCad 10</text>',
    ]

    for w in wires or []:
        elems.append(
            f'  <line x1="{tx(float(w["x1"])):.1f}" y1="{ty(float(w["y1"])):.1f}" '
            f'x2="{tx(float(w["x2"])):.1f}" y2="{ty(float(w["y2"])):.1f}" '
            f'stroke="#22d3ee" stroke-width="2.4" stroke-linecap="round"/>'
        )

    for j in junctions or []:
        elems.append(f'  <circle cx="{tx(float(j["x"])):.1f}" cy="{ty(float(j["y"])):.1f}" r="4.2" fill="#38bdf8"/>')

    for comp in components:
        cx, cy = tx(float(comp.get("x", 60.0))), ty(float(comp.get("y", 60.0)))
        lib_id = str(comp.get("lib_id") or "Device:R").lower()
        ref = html.escape(str(comp.get("ref") or ""))
        val = html.escape(str(comp.get("value") or ""))
        kind = lib_id.split(":")[-1]
        if kind in ("r", "resistor"):
            elems.append(f'  <rect x="{cx - 10:.1f}" y="{cy - 18:.1f}" width="20" height="36" rx="3" fill="#11243b" stroke="#fbbf24" stroke-width="2.2"/>')
        elif kind in ("c", "capacitor", "c_small"):
            elems.append(f'  <line x1="{cx - 14:.1f}" y1="{cy - 5:.1f}" x2="{cx + 14:.1f}" y2="{cy - 5:.1f}" stroke="#fbbf24" stroke-width="3"/>')
            elems.append(f'  <line x1="{cx - 14:.1f}" y1="{cy + 5:.1f}" x2="{cx + 14:.1f}" y2="{cy + 5:.1f}" stroke="#fbbf24" stroke-width="3"/>')
        elif kind in ("led", "d", "diode"):
            elems.append(f'  <polygon points="{cx - 12:.1f},{cy - 10:.1f} {cx - 12:.1f},{cy + 10:.1f} {cx + 10:.1f},{cy:.1f}" fill="#f59e0b" stroke="#fde68a" stroke-width="1.8"/>')
            elems.append(f'  <line x1="{cx + 10:.1f}" y1="{cy - 10:.1f}" x2="{cx + 10:.1f}" y2="{cy + 10:.1f}" stroke="#fde68a" stroke-width="2.5"/>')
        elif kind == "gnd":
            elems.append(f'  <polygon points="{cx - 12:.1f},{cy:.1f} {cx + 12:.1f},{cy:.1f} {cx:.1f},{cy + 14:.1f}" fill="none" stroke="#94a3b8" stroke-width="2.2"/>')
        elif kind in ("vcc", "+5v", "+3v3", "+12v"):
            elems.append(f'  <polygon points="{cx - 10:.1f},{cy:.1f} {cx + 10:.1f},{cy:.1f} {cx:.1f},{cy - 13:.1f}" fill="#ef4444" stroke="#fca5a5" stroke-width="1.8"/>')
        else:
            elems.append(f'  <rect x="{cx - 28:.1f}" y="{cy - 22:.1f}" width="56" height="44" rx="6" fill="#172d4a" stroke="#60a5fa" stroke-width="2.2"/>')
        elems.append(f'  <text x="{cx + 18:.1f}" y="{cy - 6:.1f}" fill="#f8fafc" font-family="Consolas, monospace" font-size="13" font-weight="700">{ref}</text>')
        elems.append(f'  <text x="{cx + 18:.1f}" y="{cy + 12:.1f}" fill="#93c5fd" font-family="Consolas, monospace" font-size="12">{val}</text>')

    for lb in labels or []:
        lx, ly = tx(float(lb["x"])), ty(float(lb["y"]))
        name = html.escape(str(lb.get("name") or ""))
        elems.append(f'  <rect x="{lx - 2:.1f}" y="{ly - 15:.1f}" width="{max(44, len(name) * 8 + 12)}" height="18" rx="4" fill="#0f3d56" stroke="#38bdf8"/>')
        elems.append(f'  <text x="{lx + 4:.1f}" y="{ly - 2:.1f}" fill="#e0f2fe" font-family="Consolas, monospace" font-size="11" font-weight="700">{name}</text>')

    elems.append("</svg>\n")
    return "\n".join(elems)


def render_architecture_svg(
    title: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> tuple[str, str]:
    """Renderiza un diagrama de bloques/arquitectura/flujo como SVG vectorial + código Mermaid (.mmd)."""
    if not nodes:
        raise WorkspaceError("El diagrama requiere al menos un nodo en `nodes`.")

    cols = min(4, max(1, len(nodes)))
    card_w, card_h, gap_x, gap_y = 190, 74, 56, 56
    rows = (len(nodes) + cols - 1) // cols
    width = max(720, cols * card_w + (cols + 1) * gap_x)
    height = max(340, rows * card_h + (rows + 1) * gap_y + 64)

    palette = {
        "ui": ("#153254", "#38bdf8"),
        "api": ("#1e2948", "#818cf8"),
        "db": ("#143b36", "#34d399"),
        "hw": ("#3f2b14", "#fbbf24"),
        "default": ("#16263d", "#60a5fa"),
    }

    pos: dict[str, tuple[float, float]] = {}
    for idx, n in enumerate(nodes):
        nid = str(n["id"])
        r, c = divmod(idx, cols)
        x = gap_x + c * (card_w + gap_x)
        y = 66 + gap_y // 2 + r * (card_h + gap_y)
        pos[nid] = (x, y)

    elems = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        '  <defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L8,3 L0,6 Z" fill="#38bdf8"/></marker></defs>',
        f'  <rect width="{width}" height="{height}" fill="#081220"/>',
        f'  <text x="28" y="40" fill="#f1f5f9" font-family="Segoe UI, sans-serif" font-size="18" font-weight="700">{html.escape(title)}</text>',
    ]
    mmd_lines = ["flowchart LR"]

    for edge in edges:
        src, dst = str(edge["from"]), str(edge["to"])
        lbl = str(edge.get("label") or "").strip()
        mmd_lines.append(f'  {src} -->{("|" + lbl + "|") if lbl else ""} {dst}')
        if src in pos and dst in pos:
            x1, y1 = pos[src]
            x2, y2 = pos[dst]
            sx, sy = x1 + card_w / 2, y1 + card_h / 2
            ex, ey = x2 + card_w / 2, y2 + card_h / 2
            if abs(x2 - x1) >= abs(y2 - y1):
                sx = x1 + card_w if x2 >= x1 else x1
                ex = x2 if x2 >= x1 else x2 + card_w
            else:
                sy = y1 + card_h if y2 >= y1 else y1
                ey = y2 if y2 >= y1 else y2 + card_h
            elems.append(f'  <line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="#38bdf8" stroke-width="2.2" marker-end="url(#arrow)"/>')
            if lbl:
                mx, my = (sx + ex) / 2, (sy + ey) / 2 - 6
                elems.append(f'  <text x="{mx:.1f}" y="{my:.1f}" text-anchor="middle" fill="#bae6fd" font-family="Segoe UI, sans-serif" font-size="11">{html.escape(lbl)}</text>')

    for n in nodes:
        nid = str(n["id"])
        label = str(n.get("label") or nid)
        subtitle = str(n.get("subtitle") or "")
        fill, stroke = palette.get(str(n.get("kind") or "default").lower(), palette["default"])
        x, y = pos[nid]
        mmd_lines.append(f'  {nid}["{label}"]')
        elems.append(f'  <rect x="{x:.1f}" y="{y:.1f}" width="{card_w}" height="{card_h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
        elems.append(f'  <text x="{x + card_w/2:.1f}" y="{y + (34 if subtitle else 42):.1f}" text-anchor="middle" fill="#f8fafc" font-family="Segoe UI, sans-serif" font-size="14" font-weight="700">{html.escape(label[:26])}</text>')
        if subtitle:
            elems.append(f'  <text x="{x + card_w/2:.1f}" y="{y + 54:.1f}" text-anchor="middle" fill="#cbd5e1" font-family="Segoe UI, sans-serif" font-size="11">{html.escape(subtitle[:30])}</text>')

    elems.append("</svg>\n")
    return "\n".join(elems), "\n".join(mmd_lines) + "\n"


def create_kicad_diagram_bundle(
    workspace: SafeWorkspace,
    output_dir: str,
    project_name: str,
    title: str,
    components: list[dict[str, Any]],
    *,
    wires: list[dict[str, Any]] | None = None,
    labels: list[dict[str, Any]] | None = None,
    junctions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Crea un paquete completo `.kicad_pro` + `.kicad_sch` + vista previa `.svg` dentro del workspace."""
    safe_dir = workspace.resolve_safe_path(output_dir, allow_write=True)
    safe_dir.mkdir(parents=True, exist_ok=True)
    slug = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in project_name).strip("_") or "circuito"
    pro_path = safe_dir / f"{slug}.kicad_pro"
    sch_path = safe_dir / f"{slug}.kicad_sch"
    svg_path = safe_dir / f"{slug}.svg"

    pro_path.write_text(build_kicad_project(slug), encoding="utf-8")
    sch_path.write_text(
        build_kicad_schematic(title, components, wires=wires, labels=labels, junctions=junctions),
        encoding="utf-8",
    )
    svg_path.write_text(
        render_schematic_svg(title, components, wires=wires, labels=labels, junctions=junctions),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "project": workspace.to_rel_posix(pro_path),
        "schematic": workspace.to_rel_posix(sch_path),
        "svg_preview": workspace.to_rel_posix(svg_path),
        "kicad_cli": find_kicad_cli()["kicad_cli"],
    }
