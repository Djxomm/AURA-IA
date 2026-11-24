"""Motor ligero de avatares 3D detallados, transparentes y animados por modelo para AURA IA,
más animación de inicio transparente sobre el escritorio (sin fondo negro).

Personajes dinámicos según el modelo activo:
- lumen  -> Linterna 3D con jaula metálica fina, núcleo incandescente, ojos y manos flotantes.
- angel  -> Angelito 3D con aureola con destellos, alas de plumas en capas, ojos y manos.
- mateo  -> Avatar 3D de un niño coder con audífonos LED/micrófono, cabello con brillo, ojos y manos.
- zamara -> Avatar 3D de una niña futurista multimodal con lazo cristalino, ojos violeta y manos.
- aura   -> Núcleo 3D cristalino genérico (fallback para modelos base).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QRegion,
)
from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget


@dataclass(frozen=True)
class PersonaMeta:
    id: str
    title: str
    subtitle: str
    accent: str
    accent_soft: str
    glow: str


PERSONAS: dict[str, PersonaMeta] = {
    "lumen": PersonaMeta(
        id="lumen",
        title="LUMEN",
        subtitle="Linterna 3D · Código ágil",
        accent="#f59e0b",
        accent_soft="#fde68a",
        glow="#fbbf24",
    ),
    "angel": PersonaMeta(
        id="angel",
        title="ANGEL",
        subtitle="Ángel 3D · Precisión 5.6",
        accent="#38bdf8",
        accent_soft="#bae6fd",
        glow="#67e8f9",
    ),
    "mateo": PersonaMeta(
        id="mateo",
        title="MATEO",
        subtitle="Agente 3D · Razonamiento Pro",
        accent="#22d3ee",
        accent_soft="#a5f3fc",
        glow="#3b82f6",
    ),
    "zamara": PersonaMeta(
        id="zamara",
        title="ZAMARA V8.2",
        subtitle="Multimodal 3D · Voz · Visión",
        accent="#e879f9",
        accent_soft="#f5d0fe",
        glow="#f472b6",
    ),
    "aura": PersonaMeta(
        id="aura",
        title="AURA",
        subtitle="Núcleo 3D · Espacio Local",
        accent="#38bdf8",
        accent_soft="#cbd5e1",
        glow="#0ea5e9",
    ),
}

STATE_LABELS: dict[str, str] = {
    "idle": "En línea · listo",
    "thinking": "Pensando paso a paso…",
    "working": "Ejecutando herramientas…",
    "speaking": "Hablando…",
    "listening": "Escuchando tu voz…",
    "error": "Requiere revisión",
}


def resolve_avatar_persona(model_ref: str | Path | None) -> str:
    """Identifica el avatar 3D correspondiente al nombre o ruta del modelo activo."""
    raw = str(model_ref or "").lower()
    if "zamara" in raw or "gemma-4" in raw or "gemma4" in raw:
        return "zamara"
    if "mateo" in raw:
        return "mateo"
    if "angel" in raw:
        return "angel"
    if "lumen" in raw:
        return "lumen"
    return "aura"


def persona_meta(persona_id: str) -> PersonaMeta:
    return PERSONAS.get(persona_id, PERSONAS["aura"])


def _rgba(hex_color: str, alpha: int) -> QColor:
    c = QColor(hex_color)
    c.setAlpha(max(0, min(255, int(alpha))))
    return c


def _draw_3d_sphere(
    p: QPainter,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    highlight: str,
    mid: str,
    shadow: str,
    rim: str | None = None,
) -> None:
    grad = QRadialGradient(cx - rx * 0.30, cy - ry * 0.36, max(rx, ry) * 1.42)
    grad.setColorAt(0.0, QColor(highlight))
    grad.setColorAt(0.50, QColor(mid))
    grad.setColorAt(1.0, QColor(shadow))
    p.setBrush(QBrush(grad))
    p.setPen(QPen(_rgba(rim, 125), 0.95) if rim else Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(cx - rx, cy - ry, rx * 2.0, ry * 2.0))


def _draw_eyes(
    p: QPainter,
    cx: float,
    cy: float,
    spacing: float,
    rx: float,
    ry: float,
    iris_color: str,
    look_x: float,
    look_y: float,
    blink_ratio: float,
    *,
    lashes: bool = False,
    glow_mode: bool = False,
) -> None:
    open_h = max(1.1, ry * (1.0 - blink_ratio * 0.92))
    for side in (-1.0, 1.0):
        ex = cx + side * spacing
        if blink_ratio > 0.78:
            pen = QPen(QColor("#1e293b" if not glow_mode else iris_color), 1.85, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            arc = QPainterPath()
            arc.moveTo(ex - rx * 0.85, cy)
            arc.quadTo(ex, cy + ry * 0.42, ex + rx * 0.85, cy)
            p.drawPath(arc)
            continue

        if glow_mode:
            halo = QRadialGradient(ex, cy, rx * 1.95)
            halo.setColorAt(0.0, _rgba(iris_color, 215))
            halo.setColorAt(0.55, _rgba(iris_color, 65))
            halo.setColorAt(1.0, _rgba(iris_color, 0))
            p.setBrush(QBrush(halo))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(ex - rx * 1.75, cy - open_h * 1.55, rx * 3.5, open_h * 3.1))

            p.setBrush(QColor("#fffbeb"))
            p.drawEllipse(QRectF(ex - rx * 0.84 + look_x * 0.45, cy - open_h * 0.84 + look_y * 0.45, rx * 1.68, open_h * 1.68))
            p.setBrush(QColor("#78350f"))
            p.drawEllipse(QRectF(ex - rx * 0.34 + look_x, cy - open_h * 0.40 + look_y, rx * 0.68, open_h * 0.80))
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(QRectF(ex - rx * 0.48 + look_x * 0.65, cy - open_h * 0.54 + look_y * 0.65, rx * 0.34, open_h * 0.34))
            continue

        # Esclerótica con sombreado superior sutil
        sclera = QLinearGradient(ex, cy - open_h, ex, cy + open_h)
        sclera.setColorAt(0.0, QColor("#cbd5e1"))
        sclera.setColorAt(0.24, QColor("#ffffff"))
        sclera.setColorAt(1.0, QColor("#e2e8f0"))
        p.setBrush(QBrush(sclera))
        p.setPen(QPen(_rgba("#1e293b", 170), 0.75))
        p.drawEllipse(QRectF(ex - rx, cy - open_h, rx * 2.0, open_h * 2.0))

        # Iris 3D con anillo exterior + brillo inferior
        ix = ex + look_x
        iy = cy + look_y
        ir = min(rx * 0.68, open_h * 0.84)
        igrad = QRadialGradient(ix, iy + ir * 0.30, ir * 1.15)
        igrad.setColorAt(0.0, QColor(iris_color).lighter(155))
        igrad.setColorAt(0.58, QColor(iris_color))
        igrad.setColorAt(1.0, QColor("#0f172a"))
        p.setBrush(QBrush(igrad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(ix - ir, iy - ir, ir * 2.0, ir * 2.0))

        # Pupila + doble destello especular
        pr = ir * 0.46
        p.setBrush(QColor("#070a12"))
        p.drawEllipse(QRectF(ix - pr, iy - pr, pr * 2.0, pr * 2.0))
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(ix - ir * 0.44, iy - ir * 0.50, ir * 0.38, ir * 0.38))
        p.setBrush(_rgba("#ffffff", 185))
        p.drawEllipse(QRectF(ix + ir * 0.16, iy + ir * 0.18, ir * 0.19, ir * 0.19))

        # Párpado superior fino
        lid_pen = QPen(QColor("#1e1b2e" if lashes else "#2c221e"), 1.35 if lashes else 1.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(lid_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        lid = QPainterPath()
        lid.moveTo(ex - rx * 0.90, cy - open_h * 0.42)
        lid.quadTo(ex, cy - open_h * 1.16, ex + rx * (1.12 if lashes else 0.90) * side, cy - open_h * (0.58 if lashes else 0.42))
        p.drawPath(lid)


def _draw_mouth(p: QPainter, cx: float, cy: float, width: float, state: str, t: float, color: str = "#7c2d12") -> None:
    p.save()
    if state == "speaking":
        open_amt = 1.8 + 2.2 * (0.5 + 0.5 * math.sin(t * 12.5))
        p.setBrush(QColor("#521b2c"))
        p.setPen(QPen(QColor(color), 0.95))
        p.drawRoundedRect(QRectF(cx - width * 0.36, cy - open_amt * 0.42, width * 0.72, open_amt), open_amt * 0.48, open_amt * 0.48)
    elif state == "thinking":
        p.setPen(QPen(QColor(color), 1.35, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(cx - width * 0.28, cy + 0.4)
        path.quadTo(cx + width * 0.06, cy - 0.8, cx + width * 0.32, cy + 0.2)
        p.drawPath(path)
    elif state == "error":
        p.setPen(QPen(QColor("#f97316"), 1.45, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(cx - width * 0.34, cy + 2.0)
        path.quadTo(cx, cy - 1.2, cx + width * 0.34, cy + 2.0)
        p.drawPath(path)
    else:
        p.setPen(QPen(QColor(color), 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(cx - width * 0.40, cy - 0.4)
        path.quadTo(cx, cy + 2.5, cx + width * 0.40, cy - 0.4)
        p.drawPath(path)
    p.restore()


def _draw_floating_hands(
    p: QPainter,
    cx: float,
    cy: float,
    span: float,
    t: float,
    state: str,
    hi: str,
    mid: str,
    sh: str,
    accent: str,
) -> None:
    if state == "thinking":
        lx, ly = cx - span * 0.74, cy + 5.5 + math.sin(t * 2.2) * 2.0
        rx, ry = cx + span * 0.40, cy - 5.5 + math.cos(t * 2.4) * 2.3
    elif state == "working":
        lx, ly = cx - span * 0.64, cy + 1.5 + math.sin(t * 8.0) * 3.8
        rx, ry = cx + span * 0.64, cy + 1.5 + math.cos(t * 8.0) * 3.8
    elif state == "speaking":
        lx, ly = cx - span * 0.90, cy - 1.0 + math.sin(t * 5.0) * 4.5
        rx, ry = cx + span * 0.90, cy - 1.0 - math.sin(t * 5.0) * 4.5
    elif state == "listening":
        lx, ly = cx - span * 0.85, cy - 3.5 + math.sin(t * 2.6) * 2.0
        rx, ry = cx + span * 0.85, cy - 3.5 + math.sin(t * 2.6 + 0.8) * 2.0
    else:
        lx, ly = cx - span * 0.86, cy + 3.5 + math.sin(t * 1.9) * 2.8
        rx, ry = cx + span * 0.86, cy + 3.5 + math.sin(t * 1.9 + 1.1) * 2.8

    for hx, hy, side in ((lx, ly, -1.0), (rx, ry, 1.0)):
        aura = QRadialGradient(hx, hy, 10.5)
        aura.setColorAt(0.0, _rgba(accent, 90))
        aura.setColorAt(1.0, _rgba(accent, 0))
        p.setBrush(QBrush(aura))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(hx - 10.5, hy - 10.5, 21.0, 21.0))

        # Aro fino de energía en la muñeca
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(_rgba(accent, 155), 1.1))
        p.drawEllipse(QRectF(hx - 6.8, hy - 6.0, 13.6, 12.0))

        _draw_3d_sphere(p, hx, hy, 6.2, 5.6, hi, mid, sh, rim=accent)
        _draw_3d_sphere(p, hx - side * 4.5, hy - 2.1, 2.5, 2.3, hi, mid, sh)


def _draw_thought_orbs(p: QPainter, cx: float, top_y: float, t: float, accent: str, state: str) -> None:
    if state not in ("thinking", "working", "listening"):
        return
    for i in range(3):
        ang = t * (3.1 if state == "working" else 1.7) + i * (2.0 * math.pi / 3.0)
        ox = cx + math.cos(ang) * 31.0
        oy = top_y + math.sin(ang * 1.4) * 6.5
        rad = 3.0 + 1.0 * math.sin(t * 4.0 + i)
        glow = QRadialGradient(ox, oy, rad * 2.5)
        glow.setColorAt(0.0, _rgba(accent, 230))
        glow.setColorAt(0.6, _rgba(accent, 70))
        glow.setColorAt(1.0, _rgba(accent, 0))
        p.setBrush(QBrush(glow))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(ox - rad * 2.3, oy - rad * 2.3, rad * 4.6, rad * 4.6))
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(ox - rad * 0.52, oy - rad * 0.52, rad * 1.04, rad * 1.04))


def _compute_kinematics(t: float, state: str) -> tuple[float, float, float, float]:
    breath_y = math.sin(t * 2.1) * (3.2 if state != "idle" else 2.3)
    if state == "thinking":
        look_x = math.sin(t * 1.4) * 2.5
        look_y = -2.1 + math.cos(t * 1.1) * 0.65
    elif state == "working":
        look_x = math.sin(t * 4.8) * 2.3
        look_y = 1.4
    elif state == "listening":
        look_x = 0.0
        look_y = -0.35
    else:
        look_x = math.sin(t * 0.85) * 1.7
        look_y = math.sin(t * 0.55) * 0.75

    cycle = t % 4.2
    blink = 0.0
    if 3.92 <= cycle <= 4.12:
        blink = math.sin(((cycle - 3.92) / 0.20) * math.pi)
    return breath_y, look_x, look_y, blink


def _paint_lumen(p: QPainter, cx: float, cy: float, t: float, state: str) -> None:
    """LUMEN: Linterna 3D detallada con jaula metálica, núcleo incandescente, ojos y manos."""
    breath, lx, ly, blink = _compute_kinematics(t, state)
    y = cy + breath
    pulse = 0.5 + 0.5 * math.sin(t * (6.0 if state in ("thinking", "speaking", "working") else 2.3))

    # Halo volumétrico cálido
    glow = QRadialGradient(cx, y - 2.0, 56.0 + pulse * 7.0)
    glow.setColorAt(0.0, _rgba("#fde047", int(115 + 45 * pulse)))
    glow.setColorAt(0.55, _rgba("#f59e0b", 42))
    glow.setColorAt(1.0, _rgba("#f59e0b", 0))
    p.setBrush(QBrush(glow))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(cx - 56.0, y - 56.0, 112.0, 112.0))

    # Asa metálica superior 3D con brillo
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor("#94a3b8"), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    handle = QPainterPath()
    handle.moveTo(cx - 13.0, y - 34.0)
    handle.cubicTo(cx - 14.0, y - 51.0, cx + 14.0, y - 51.0, cx + 13.0, y - 34.0)
    p.drawPath(handle)
    p.setPen(QPen(QColor("#f8fafc"), 1.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawPath(handle)

    # Cristal cilíndrico 3D + llama/filamento interior
    glass = QLinearGradient(cx - 24.0, y - 25.0, cx + 26.0, y + 25.0)
    glass.setColorAt(0.0, QColor("#fef9c3"))
    glass.setColorAt(0.42, QColor("#f59e0b"))
    glass.setColorAt(0.82, QColor("#b45309"))
    glass.setColorAt(1.0, QColor("#451a03"))
    p.setBrush(QBrush(glass))
    p.setPen(QPen(_rgba("#fde68a", 215), 1.3))
    p.drawRoundedRect(QRectF(cx - 23.0, y - 26.0, 46.0, 52.0), 14.0, 14.0)

    # Llama cálida interna suave
    core = QRadialGradient(cx, y - 4.0, 18.0 + pulse * 3.0)
    core.setColorAt(0.0, _rgba("#ffffff", 165))
    core.setColorAt(0.55, _rgba("#fde047", 90))
    core.setColorAt(1.0, _rgba("#f59e0b", 0))
    p.setBrush(QBrush(core))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(cx - 18.0, y - 21.0, 36.0, 36.0))

    # Reflejo especular curvo + costillas finas de jaula metálica
    spec = QLinearGradient(cx - 19.0, y - 22.0, cx - 10.0, y + 18.0)
    spec.setColorAt(0.0, _rgba("#ffffff", 170))
    spec.setColorAt(1.0, _rgba("#ffffff", 12))
    p.setBrush(QBrush(spec))
    p.drawRoundedRect(QRectF(cx - 18.5, y - 21.0, 7.0, 38.0), 3.5, 3.5)

    p.setPen(QPen(_rgba("#1e293b", 155), 1.6))
    for rx in (-21.0, 21.0):
        p.drawLine(QPointF(cx + rx, y - 24.0), QPointF(cx + rx, y + 23.0))

    # Cúpula superior y base metálicas 3D con ribete dorado
    cap_grad = QLinearGradient(cx - 26.0, y - 35.0, cx + 26.0, y - 23.0)
    cap_grad.setColorAt(0.0, QColor("#64748b"))
    cap_grad.setColorAt(0.45, QColor("#1e293b"))
    cap_grad.setColorAt(1.0, QColor("#070a10"))
    p.setBrush(QBrush(cap_grad))
    p.setPen(QPen(QColor("#fbbf24"), 1.15))
    p.drawRoundedRect(QRectF(cx - 26.0, y - 35.0, 52.0, 11.5), 5.5, 5.5)
    p.drawRoundedRect(QRectF(cx - 24.0, y + 22.5, 48.0, 11.5), 5.5, 5.5)
    # Remate superior pequeño
    p.drawRoundedRect(QRectF(cx - 11.0, y - 39.0, 22.0, 5.0), 2.5, 2.5)

    # Ojos luminosos expresivos + boca
    _draw_eyes(p, cx, y - 3.0, 9.2, 5.0, 6.0, "#fef08a", lx, ly, blink, glow_mode=True)
    _draw_mouth(p, cx, y + 12.0, 12.5, state, t, color="#451a03")

    _draw_floating_hands(p, cx, y + 10.0, 39.0, t, state, "#fef08a", "#f59e0b", "#78350f", "#fbbf24")
    _draw_thought_orbs(p, cx, y - 48.0, t, "#fde047", state)


def _paint_angel(p: QPainter, cx: float, cy: float, t: float, state: str) -> None:
    """ANGEL: Angelito 3D detallado con alas en capas de plumas, aureola con destellos, ojos y manos."""
    breath, lx, ly, blink = _compute_kinematics(t, state)
    y = cy + breath
    flap = math.sin(t * (7.2 if state in ("working", "thinking") else 3.0)) * 7.2

    aura = QRadialGradient(cx, y - 4.0, 56.0)
    aura.setColorAt(0.0, _rgba("#67e8f9", 82))
    aura.setColorAt(0.65, _rgba("#38bdf8", 26))
    aura.setColorAt(1.0, _rgba("#38bdf8", 0))
    p.setBrush(QBrush(aura))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(cx - 56.0, y - 56.0, 112.0, 112.0))

    # Alas 3D en doble capa de plumas
    for side in (-1.0, 1.0):
        p.save()
        p.translate(cx + side * 13.0, y + 10.0)
        p.rotate(side * (-13.0 + flap))
        for layer, scale_w, alpha in ((0, 1.0, 255), (1, 0.72, 225)):
            wgrad = QLinearGradient(0.0, -20.0, side * 38.0 * scale_w, 16.0)
            wgrad.setColorAt(0.0, _rgba("#ffffff", alpha))
            wgrad.setColorAt(0.55, _rgba("#bae6fd", alpha))
            wgrad.setColorAt(1.0, _rgba("#38bdf8", alpha))
            p.setBrush(QBrush(wgrad))
            p.setPen(QPen(_rgba("#e0f2fe", 190), 0.95))
            wing = QPainterPath()
            wing.moveTo(0.0, layer * 3.0)
            wing.cubicTo(side * 16.0 * scale_w, -24.0 * scale_w, side * 38.0 * scale_w, -18.0 * scale_w, side * 36.0 * scale_w, 2.0 * scale_w)
            wing.cubicTo(side * 28.0 * scale_w, 12.0 * scale_w, side * 14.0 * scale_w, 14.0 * scale_w, 0.0, 8.0 + layer * 2.0)
            wing.closeSubpath()
            p.drawPath(wing)
        p.restore()

    # Túnica 3D perlada con cuello luminoso
    robe = QLinearGradient(cx - 18.0, y + 8.0, cx + 18.0, y + 42.0)
    robe.setColorAt(0.0, QColor("#ffffff"))
    robe.setColorAt(0.52, QColor("#cbd5e1"))
    robe.setColorAt(1.0, QColor("#475569"))
    p.setBrush(QBrush(robe))
    p.setPen(QPen(QColor("#38bdf8"), 1.15))
    body = QPainterPath()
    body.moveTo(cx - 13.0, y + 10.0)
    body.quadTo(cx - 21.0, y + 36.0, cx - 15.0, y + 40.0)
    body.lineTo(cx + 15.0, y + 40.0)
    body.quadTo(cx + 21.0, y + 36.0, cx + 13.0, y + 10.0)
    body.closeSubpath()
    p.drawPath(body)
    # Cuello fino dorado-celeste
    p.setPen(QPen(QColor("#bae6fd"), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    collar = QPainterPath()
    collar.moveTo(cx - 9.0, y + 12.0)
    collar.quadTo(cx, y + 18.0, cx + 9.0, y + 12.0)
    p.drawPath(collar)

    # Cabeza 3D + flequillo celeste con brillo sedoso
    _draw_3d_sphere(p, cx, y - 10.0, 21.8, 20.8, "#fff7ed", "#fde0c6", "#d29d7d", rim="#bae6fd")

    hair = QLinearGradient(cx - 22.0, y - 34.0, cx + 22.0, y - 10.0)
    hair.setColorAt(0.0, QColor("#f8fafc"))
    hair.setColorAt(0.50, QColor("#93c5fd"))
    hair.setColorAt(1.0, QColor("#1d4ed8"))
    p.setBrush(QBrush(hair))
    p.setPen(Qt.PenStyle.NoPen)
    bangs = QPainterPath()
    bangs.moveTo(cx - 22.5, y - 11.0)
    bangs.cubicTo(cx - 22.0, y - 36.0, cx + 22.0, y - 36.0, cx + 22.5, y - 11.0)
    bangs.quadTo(cx + 11.0, y - 22.0, cx + 1.5, y - 16.0)
    bangs.quadTo(cx - 10.0, y - 22.0, cx - 22.5, y - 11.0)
    p.drawPath(bangs)
    # Brillo del cabello
    p.setPen(QPen(_rgba("#ffffff", 150), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    shine = QPainterPath()
    shine.moveTo(cx - 11.0, y - 27.0)
    shine.quadTo(cx, y - 31.0, cx + 10.0, y - 27.0)
    p.drawPath(shine)

    # Aureola 3D flotante con chispa
    halo_y = y - 39.0 + math.sin(t * 3.0) * 2.1
    p.setPen(QPen(_rgba("#fde047", 85), 5.0))
    p.drawEllipse(QRectF(cx - 16.0, halo_y - 4.6, 32.0, 9.2))
    p.setPen(QPen(QColor("#fef08a"), 2.1))
    p.drawEllipse(QRectF(cx - 16.0, halo_y - 4.6, 32.0, 9.2))
    sx = cx + math.cos(t * 2.4) * 16.0
    sy = halo_y + math.sin(t * 2.4) * 4.5
    p.setBrush(QColor("#ffffff"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(sx - 2.0, sy - 2.0, 4.0, 4.0))

    _draw_eyes(p, cx, y - 8.4, 8.1, 4.8, 5.5, "#38bdf8", lx, ly, blink)
    _draw_mouth(p, cx, y + 3.0, 11.5, state, t, color="#9a5b4a")

    _draw_floating_hands(p, cx, y + 20.0, 36.0, t, state, "#fff7ed", "#fde0c6", "#c49172", "#67e8f9")
    _draw_thought_orbs(p, cx, y - 48.0, t, "#67e8f9", state)


def _paint_mateo(p: QPainter, cx: float, cy: float, t: float, state: str) -> None:
    """MATEO: Avatar 3D detallado de un niño coder futurista con audífonos LED/micrófono, ojos y manos."""
    breath, lx, ly, blink = _compute_kinematics(t, state)
    y = cy + breath

    aura = QRadialGradient(cx, y, 56.0)
    aura.setColorAt(0.0, _rgba("#22d3ee", 74))
    aura.setColorAt(0.6, _rgba("#2563eb", 26))
    aura.setColorAt(1.0, _rgba("#2563eb", 0))
    p.setBrush(QBrush(aura))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(cx - 56.0, y - 56.0, 112.0, 112.0))

    # Sudadera tech 3D con cierre y emblema cian
    jacket = QLinearGradient(cx - 22.0, y + 10.0, cx + 22.0, y + 42.0)
    jacket.setColorAt(0.0, QColor("#1e293b"))
    jacket.setColorAt(0.55, QColor("#0f172a"))
    jacket.setColorAt(1.0, QColor("#020617"))
    p.setBrush(QBrush(jacket))
    p.setPen(QPen(QColor("#22d3ee"), 1.25))
    torso = QPainterPath()
    torso.moveTo(cx - 17.0, y + 12.0)
    torso.quadTo(cx - 24.0, y + 36.0, cx - 18.0, y + 41.0)
    torso.lineTo(cx + 18.0, y + 41.0)
    torso.quadTo(cx + 24.0, y + 36.0, cx + 17.0, y + 12.0)
    torso.closeSubpath()
    p.drawPath(torso)
    # Línea central fina y emblema < >
    p.setPen(QPen(_rgba("#38bdf8", 130), 1.0))
    p.drawLine(QPointF(cx, y + 14.0), QPointF(cx, y + 40.0))
    p.setPen(QPen(QColor("#38bdf8"), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(cx - 7.5, y + 21.0), QPointF(cx, y + 28.0))
    p.drawLine(QPointF(cx, y + 28.0), QPointF(cx + 7.5, y + 21.0))

    # Diadema + audífonos tech con anillo LED cian y brazo de micrófono
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor("#334155"), 4.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    band = QPainterPath()
    band.moveTo(cx - 24.0, y - 10.0)
    band.cubicTo(cx - 25.0, y - 40.0, cx + 25.0, y - 40.0, cx + 24.0, y - 10.0)
    p.drawPath(band)
    for side in (-1.0, 1.0):
        _draw_3d_sphere(p, cx + side * 24.0, y - 9.0, 5.4, 8.2, "#64748b", "#1e293b", "#090d16", rim="#22d3ee")
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("#22d3ee"), 1.15))
        p.drawEllipse(QRectF(cx + side * 24.0 - 2.6, y - 13.0, 5.2, 8.0))
    # Micrófono sutil al costado
    p.setPen(QPen(QColor("#475569"), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    mic = QPainterPath()
    mic.moveTo(cx + 22.0, y - 3.0)
    mic.quadTo(cx + 19.0, y + 5.0, cx + 10.0, y + 4.5)
    p.drawPath(mic)
    p.setBrush(QColor("#22d3ee"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(cx + 8.5, y + 3.0, 3.0, 3.0))

    # Cabeza 3D del niño
    _draw_3d_sphere(p, cx, y - 10.0, 22.0, 21.5, "#ffedd5", "#fed7aa", "#c2885c", rim="#38bdf8")

    # Cabello juvenil esculpido con brillo
    hair = QLinearGradient(cx - 22.0, y - 36.0, cx + 22.0, y - 10.0)
    hair.setColorAt(0.0, QColor("#4e382b"))
    hair.setColorAt(0.55, QColor("#1f1612"))
    hair.setColorAt(1.0, QColor("#0d0a09"))
    p.setBrush(QBrush(hair))
    p.setPen(Qt.PenStyle.NoPen)
    spiky = QPainterPath()
    spiky.moveTo(cx - 22.0, y - 12.0)
    spiky.cubicTo(cx - 24.0, y - 36.0, cx + 24.0, y - 36.0, cx + 22.0, y - 12.0)
    spiky.lineTo(cx + 14.0, y - 21.0)
    spiky.lineTo(cx + 6.0, y - 15.0)
    spiky.lineTo(cx - 2.0, y - 23.0)
    spiky.lineTo(cx - 11.0, y - 15.0)
    spiky.closeSubpath()
    p.drawPath(spiky)
    p.setPen(QPen(_rgba("#9a7b67", 120), 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    hshine = QPainterPath()
    hshine.moveTo(cx - 10.0, y - 27.5)
    hshine.quadTo(cx, y - 31.0, cx + 10.0, y - 27.5)
    p.drawPath(hshine)

    # Cejas expresivas + ojos + boca
    brow_pen = QPen(QColor("#2b1e17"), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(brow_pen)
    brow_lift = -1.6 if state == "thinking" else 0.0
    p.drawLine(QPointF(cx - 13.0, y - 16.0 + brow_lift), QPointF(cx - 4.5, y - 16.5))
    p.drawLine(QPointF(cx + 4.5, y - 16.5), QPointF(cx + 13.0, y - 16.0 + brow_lift))

    _draw_eyes(p, cx, y - 8.5, 8.4, 5.0, 5.6, "#0284c7", lx, ly, blink)
    _draw_mouth(p, cx, y + 3.2, 13.0, state, t, color="#7c2d12")

    _draw_floating_hands(p, cx, y + 21.0, 38.0, t, state, "#ffedd5", "#fed7aa", "#b77e54", "#22d3ee")
    _draw_thought_orbs(p, cx, y - 47.0, t, "#22d3ee", state)


def _paint_zamara(p: QPainter, cx: float, cy: float, t: float, state: str) -> None:
    """ZAMARA V8.2: Avatar 3D detallado de una niña futurista multimodal con lazo cristalino, ojos y manos."""
    breath, lx, ly, blink = _compute_kinematics(t, state)
    y = cy + breath

    aura = QRadialGradient(cx, y - 2.0, 58.0)
    aura.setColorAt(0.0, _rgba("#e879f9", 80))
    aura.setColorAt(0.55, _rgba("#ec4899", 30))
    aura.setColorAt(1.0, _rgba("#ec4899", 0))
    p.setBrush(QBrush(aura))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(cx - 58.0, y - 58.0, 116.0, 116.0))

    # Coletas sedosas con movimiento sutil
    back_hair = QLinearGradient(cx - 28.0, y - 26.0, cx + 28.0, y + 28.0)
    back_hair.setColorAt(0.0, QColor("#4c1d95"))
    back_hair.setColorAt(0.52, QColor("#1e1033"))
    back_hair.setColorAt(1.0, QColor("#0d0717"))
    p.setBrush(QBrush(back_hair))
    p.setPen(QPen(_rgba("#e879f9", 115), 0.9))
    for side in (-1.0, 1.0):
        sway = math.sin(t * 2.2 + side) * 2.0
        p.drawEllipse(QRectF(cx + side * 20.5 - 11.0 + sway, y - 14.0, 22.0, 35.0))

    # Vestuario fino obsidiana-violeta + prisma multimodal en el pecho
    dress = QLinearGradient(cx - 20.0, y + 10.0, cx + 20.0, y + 42.0)
    dress.setColorAt(0.0, QColor("#2e1649"))
    dress.setColorAt(0.6, QColor("#150b24"))
    dress.setColorAt(1.0, QColor("#090512"))
    p.setBrush(QBrush(dress))
    p.setPen(QPen(QColor("#f472b6"), 1.2))
    torso = QPainterPath()
    torso.moveTo(cx - 14.0, y + 11.0)
    torso.quadTo(cx - 24.0, y + 36.0, cx - 18.0, y + 41.0)
    torso.lineTo(cx + 18.0, y + 41.0)
    torso.quadTo(cx + 24.0, y + 36.0, cx + 14.0, y + 11.0)
    torso.closeSubpath()
    p.drawPath(torso)
    # Cuello fino + rombo cristalino multimodal
    p.setPen(QPen(QColor("#f5d0fe"), 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    col = QPainterPath()
    col.moveTo(cx - 8.5, y + 12.0)
    col.quadTo(cx, y + 17.5, cx + 8.5, y + 12.0)
    p.drawPath(col)
    gem = QPainterPath()
    gem.moveTo(cx, y + 18.5)
    gem.lineTo(cx + 5.0, y + 24.0)
    gem.lineTo(cx, y + 29.5)
    gem.lineTo(cx - 5.0, y + 24.0)
    gem.closeSubpath()
    p.setBrush(QColor("#e879f9"))
    p.setPen(QPen(QColor("#fdf4ff"), 0.9))
    p.drawPath(gem)

    # Cabeza 3D + rubor sutil
    _draw_3d_sphere(p, cx, y - 10.0, 21.5, 21.0, "#fff5f5", "#fde2d8", "#cf9d91", rim="#f472b6")
    for side in (-1.0, 1.0):
        blush = QRadialGradient(cx + side * 12.0, y - 2.0, 5.5)
        blush.setColorAt(0.0, _rgba("#f472b6", 72))
        blush.setColorAt(1.0, _rgba("#f472b6", 0))
        p.setBrush(QBrush(blush))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx + side * 12.0 - 5.5, y - 7.5, 11.0, 11.0))

    # Flequillo sedoso 3D con brillo
    p.setBrush(QBrush(back_hair))
    p.setPen(Qt.PenStyle.NoPen)
    front = QPainterPath()
    front.moveTo(cx - 22.5, y - 10.0)
    front.cubicTo(cx - 22.0, y - 36.0, cx + 22.0, y - 36.0, cx + 22.5, y - 10.0)
    front.quadTo(cx + 11.0, y - 23.0, cx + 2.0, y - 16.0)
    front.quadTo(cx - 10.0, y - 23.0, cx - 22.5, y - 10.0)
    p.drawPath(front)
    p.setPen(QPen(_rgba("#f5d0fe", 140), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    zshine = QPainterPath()
    zshine.moveTo(cx - 10.0, y - 26.5)
    zshine.quadTo(cx, y - 30.0, cx + 10.0, y - 26.5)
    p.drawPath(zshine)

    # Lazo cristalino facetado
    bow_y = y - 32.0 + math.sin(t * 2.5) * 1.2
    bow_grad = QLinearGradient(cx - 13.0, bow_y - 6.0, cx + 13.0, bow_y + 5.0)
    bow_grad.setColorAt(0.0, QColor("#f9a8d4"))
    bow_grad.setColorAt(0.5, QColor("#e879f9"))
    bow_grad.setColorAt(1.0, QColor("#a21caf"))
    p.setBrush(QBrush(bow_grad))
    p.setPen(QPen(QColor("#fdf4ff"), 0.95))
    for side in (-1.0, 1.0):
        wing = QPainterPath()
        wing.moveTo(cx, bow_y)
        wing.lineTo(cx + side * 13.5, bow_y - 6.5)
        wing.lineTo(cx + side * 11.5, bow_y + 4.0)
        wing.closeSubpath()
        p.drawPath(wing)
    _draw_3d_sphere(p, cx, bow_y, 3.6, 3.6, "#ffffff", "#e879f9", "#a21caf")

    _draw_eyes(p, cx, y - 8.2, 8.2, 5.2, 5.9, "#a855f7", lx, ly, blink, lashes=True)
    _draw_mouth(p, cx, y + 3.0, 11.2, state, t, color="#9d174d")

    _draw_floating_hands(p, cx, y + 21.0, 37.0, t, state, "#fff5f5", "#fde2d8", "#c59086", "#e879f9")
    _draw_thought_orbs(p, cx, y - 47.0, t, "#f472b6", state)


def _paint_aura_core(p: QPainter, cx: float, cy: float, t: float, state: str) -> None:
    """Fallback AURA: Esfera holográfica 3D con visor expresivo, ojos y manos flotantes."""
    breath, lx, ly, blink = _compute_kinematics(t, state)
    y = cy + breath

    aura = QRadialGradient(cx, y, 54.0)
    aura.setColorAt(0.0, _rgba("#38bdf8", 80))
    aura.setColorAt(1.0, _rgba("#38bdf8", 0))
    p.setBrush(QBrush(aura))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(cx - 54.0, y - 54.0, 108.0, 108.0))

    _draw_3d_sphere(p, cx, y - 4.0, 26.0, 26.0, "#475569", "#0f172a", "#020617", rim="#38bdf8")
    p.setBrush(QColor("#07111f"))
    p.setPen(QPen(QColor("#38bdf8"), 1.2))
    p.drawRoundedRect(QRectF(cx - 18.0, y - 14.0, 36.0, 19.0), 9.0, 9.0)
    _draw_eyes(p, cx, y - 4.5, 7.5, 4.2, 5.0, "#38bdf8", lx, ly, blink, glow_mode=True)
    _draw_mouth(p, cx, y + 11.0, 12.0, state, t, color="#38bdf8")
    _draw_floating_hands(p, cx, y + 16.0, 38.0, t, state, "#bae6fd", "#38bdf8", "#0c4a6e", "#38bdf8")
    _draw_thought_orbs(p, cx, y - 44.0, t, "#38bdf8", state)


def paint_avatar_3d(
    painter: QPainter,
    rect: QRectF,
    persona: str,
    state: str = "idle",
    t: float = 0.0,
) -> None:
    """Dibuja el avatar 3D puro (sin recuadro ni fondo opaco) dentro de `rect`."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    side = min(rect.width(), rect.height())
    scale = side / 128.0
    cx = rect.center().x()
    cy = rect.center().y() + 4.0 * scale

    painter.save()
    painter.translate(cx, cy)
    painter.scale(scale, scale)

    # Sombra de piso suave únicamente debajo del personaje (sin caja)
    shadow_w = 32.0 - math.sin(t * 2.1) * 2.0
    floor = QRadialGradient(0.0, 48.0, shadow_w)
    floor.setColorAt(0.0, _rgba("#000000", 105))
    floor.setColorAt(1.0, _rgba("#000000", 0))
    painter.setBrush(QBrush(floor))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QRectF(-shadow_w, 42.0, shadow_w * 2.0, 11.0))

    pid = persona if persona in PERSONAS else "aura"
    if pid == "lumen":
        _paint_lumen(painter, 0.0, 0.0, t, state)
    elif pid == "angel":
        _paint_angel(painter, 0.0, 0.0, t, state)
    elif pid == "mateo":
        _paint_mateo(painter, 0.0, 0.0, t, state)
    elif pid == "zamara":
        _paint_zamara(painter, 0.0, 0.0, t, state)
    else:
        _paint_aura_core(painter, 0.0, 0.0, t, state)

    painter.restore()
    painter.restore()


def render_avatar_pixmap(
    persona: str,
    state: str = "idle",
    t: float = 0.0,
    width: int = 128,
    height: int = 140,
) -> QPixmap:
    """Genera un QPixmap 100 % transparente (sin recuadro) del avatar 3D."""
    pix = QPixmap(max(32, int(width)), max(32, int(height)))
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    paint_avatar_3d(painter, QRectF(0, 0, pix.width(), pix.height()), persona, state, t)
    painter.end()
    return pix


class AvatarStageWidget(QWidget):
    """Avatar 3D animado con fondo 100 % transparente y SIN recuadro alrededor para el sidebar."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None, *, compact: bool = False):
        super().__init__(parent)
        self.persona = "aura"
        self.state = "idle"
        self.model_caption = "AURA"
        self.status_caption = STATE_LABELS["idle"]
        self.animations_enabled = True
        self._t = 0.0
        self._compact = compact
        self.setObjectName("avatarStage")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background:transparent;border:none;")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(88 if compact else 118)
        self.setAccessibleName("Avatar 3D transparente animado del modelo activo")

        self._timer = QTimer(self)
        self._timer.setInterval(55)
        self._timer.timeout.connect(self._tick)

    def set_model(self, model_ref: str | Path | None, label: str = "") -> None:
        self.persona = resolve_avatar_persona(model_ref)
        meta = persona_meta(self.persona)
        self.model_caption = label or meta.title
        self.setToolTip(f"{self.model_caption} · {meta.subtitle}\nClic para mostrar el asistente 3D flotante")
        self.update()

    def set_state(self, state: str, caption: str = "") -> None:
        self.state = state if state in STATE_LABELS else "idle"
        self.status_caption = caption or STATE_LABELS[self.state]
        self._sync_timer()
        self.update()

    def set_animations_enabled(self, enabled: bool) -> None:
        self.animations_enabled = bool(enabled)
        self._sync_timer()
        self.update()

    def _sync_timer(self) -> None:
        if self.animations_enabled and self.isVisible():
            if not self._timer.isActive():
                self._timer.start()
        elif self._timer.isActive():
            self._timer.stop()

    def _tick(self) -> None:
        step = 0.075 if self.state in ("thinking", "working", "speaking") else 0.05
        self._t += step
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        meta = persona_meta(self.persona)
        w, h = float(self.width()), float(self.height())

        # Sin recuadro ni fondo opaco: solo el avatar 3D puro flotando + etiqueta limpia
        av_size = h - 4.0
        paint_avatar_3d(painter, QRectF(0.0, 2.0, av_size, av_size), self.persona, self.state, self._t)

        tx = av_size + 6.0
        tw = max(40.0, w - tx - 4.0)
        font = painter.font()
        font.setFamily("Segoe UI")
        font.setPointSize(9 if self._compact else 10)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#f8fafc"))
        painter.drawText(QRectF(tx, 14.0 if self._compact else 22.0, tw, 20.0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.model_caption)

        font.setPointSize(8)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(meta.accent_soft))
        painter.drawText(QRectF(tx, 34.0 if self._compact else 44.0, tw, 18.0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, meta.subtitle)

        dot_y = 56.0 if self._compact else 72.0
        dot_color = "#f97316" if self.state == "error" else meta.accent
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(dot_color))
        painter.drawEllipse(QRectF(tx, dot_y + 4.0, 6.5, 6.5))
        painter.setPen(QColor("#94a3b8"))
        painter.drawText(QRectF(tx + 11.0, dot_y, tw - 11.0, 16.0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.status_caption)
        painter.end()


class TransparentStartupSplash(QWidget):
    """Animación de inicio 100 % transparente (sin fondo negro) que flota directo sobre el escritorio."""

    def __init__(self, owner, assets_dir: Path, model_ref: str | Path | None = None):
        super().__init__(
            None,
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.owner = owner
        self.persona = resolve_avatar_persona(model_ref)
        self._t = 0.0
        self.setWindowTitle("Iniciando AURA IA")
        ico_path = Path(assets_dir) / "aura.ico"
        if ico_path.is_file():
            self.setWindowIcon(QIcon(str(ico_path)))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.resize(440, 400)

        logo = QPixmap(str(Path(assets_dir) / "aura-logo-transparente.png"))
        if logo.isNull():
            logo = QPixmap(str(Path(assets_dir) / "aura-icono-transparente.png"))
        if not logo.isNull():
            bounds = QRegion(logo.mask()).boundingRect()
            if not bounds.isEmpty():
                logo = logo.copy(bounds)
            self.logo = logo.scaled(168, 168, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        else:
            self.logo = QPixmap()

        screen = QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(area.center() - self.rect().center())

        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 FPS suaves sobre el escritorio
        self._timer.timeout.connect(self._tick)

    def begin(self) -> None:
        self.show()
        self.raise_()
        self._timer.start()

    def release(self) -> None:
        self._timer.stop()
        self.hide()
        self.deleteLater()

    def _tick(self) -> None:
        self._t += 0.08
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        meta = persona_meta(self.persona)
        cx, cy = self.width() / 2.0, self.height() / 2.0 - 16.0
        ease = min(1.0, self._t / 1.4)
        scale_in = 0.78 + 0.22 * (1.0 - (1.0 - ease) ** 3)

        # Anillos holográficos flotantes transparentes (sin fondo negro)
        for idx, base_r in enumerate((104.0, 128.0, 152.0)):
            r = (base_r + math.sin(self._t * 2.0 + idx) * 6.0) * scale_in
            alpha = int((125 - idx * 32) * ease)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(_rgba(meta.accent if idx % 2 == 0 else meta.glow, alpha), 1.8 - idx * 0.35))
            start_deg = int((self._t * (38 + idx * 18) * (1 if idx % 2 == 0 else -1)) % 360) * 16
            p.drawArc(QRectF(cx - r, cy - r, r * 2.0, r * 2.0), start_deg, 115 * 16)
            p.drawArc(QRectF(cx - r, cy - r, r * 2.0, r * 2.0), start_deg + 180 * 16, 85 * 16)

        # Resplandor alfa suave en el centro (sin caja ni bordes negros)
        glow = QRadialGradient(cx, cy, 130.0 * scale_in)
        glow.setColorAt(0.0, _rgba(meta.accent, int(92 * ease)))
        glow.setColorAt(0.6, _rgba(meta.glow, int(28 * ease)))
        glow.setColorAt(1.0, _rgba(meta.glow, 0))
        p.setBrush(QBrush(glow))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - 130.0, cy - 130.0, 260.0, 260.0))

        # Logo transparente AURA IA flotando + avatar 3D vivo en primer plano
        bob = math.sin(self._t * 2.4) * 5.0
        if not self.logo.isNull():
            lw = self.logo.width() * scale_in
            lh = self.logo.height() * scale_in
            p.setOpacity(0.95 * ease)
            p.drawPixmap(QRectF(cx - lw / 2.0, cy - lh / 2.0 - 18.0 + bob * 0.5, lw, lh), self.logo, QRectF(self.logo.rect()))
            p.setOpacity(1.0)

        paint_avatar_3d(p, QRectF(cx + 34.0, cy + 12.0 + bob, 118.0 * scale_in, 118.0 * scale_in), self.persona, "thinking", self._t)

        # Pastilla flotante limpia de estado debajo (semitransparente, sin bloque negro)
        pill = QRectF(cx - 120.0, self.height() - 62.0, 240.0, 34.0)
        p.setBrush(_rgba("#090d16", int(185 * ease)))
        p.setPen(QPen(_rgba(meta.accent, int(170 * ease)), 1.15))
        p.drawRoundedRect(pill, 17.0, 17.0)
        p.setPen(QColor("#f8fafc"))
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.drawText(pill, Qt.AlignmentFlag.AlignCenter, f"AURA IA · {meta.title} iniciando…")
        p.end()
