"""Motor ligero de avatares 3D estilizados y animados por modelo para AURA IA.

Personajes dinámicos según el modelo activo:
- lumen  -> Linterna 3D viva con núcleo cálido, ojos luminosos y manos flotantes.
- angel  -> Angelito 3D fino con aureola flotante, alas animadas, ojos y manos.
- mateo  -> Avatar 3D de un niño futurista/coder con diadema LED, ojos y manos.
- zamara -> Avatar 3D de una niña futurista multimodal con lazo cristalino, ojos y manos.
- aura   -> Núcleo 3D cristalino genérico (fallback para modelos base).

Renderizado 100 % nativo en PySide6 (QPainter con sombreado volumétrico 3D, brillos
especulares, sombras proyectadas, respiración, parpadeo, mirada, manos y orbes de
pensamiento), diseñado para consumir < 1 % de CPU y < 15 MB de RAM.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QSizePolicy, QWidget


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
    grad = QRadialGradient(cx - rx * 0.30, cy - ry * 0.34, max(rx, ry) * 1.38)
    grad.setColorAt(0.0, QColor(highlight))
    grad.setColorAt(0.52, QColor(mid))
    grad.setColorAt(1.0, QColor(shadow))
    p.setBrush(QBrush(grad))
    p.setPen(QPen(_rgba(rim, 130), 1.1) if rim else Qt.PenStyle.NoPen)
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
            pen = QPen(QColor("#0f172a" if not glow_mode else iris_color), 1.9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            arc = QPainterPath()
            arc.moveTo(ex - rx * 0.85, cy)
            arc.quadTo(ex, cy + ry * 0.45, ex + rx * 0.85, cy)
            p.drawPath(arc)
            continue

        if glow_mode:
            # Ojos luminosos (Lumen / núcleo)
            halo = QRadialGradient(ex, cy, rx * 1.9)
            halo.setColorAt(0.0, _rgba(iris_color, 210))
            halo.setColorAt(0.55, _rgba(iris_color, 70))
            halo.setColorAt(1.0, _rgba(iris_color, 0))
            p.setBrush(QBrush(halo))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(ex - rx * 1.7, cy - open_h * 1.5, rx * 3.4, open_h * 3.0))

            p.setBrush(QColor("#fffbeb"))
            p.drawEllipse(QRectF(ex - rx * 0.85 + look_x * 0.5, cy - open_h * 0.85 + look_y * 0.5, rx * 1.7, open_h * 1.7))
            p.setBrush(QColor("#78350f"))
            p.drawEllipse(QRectF(ex - rx * 0.32 + look_x, cy - open_h * 0.38 + look_y, rx * 0.64, open_h * 0.76))
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(QRectF(ex - rx * 0.46 + look_x * 0.7, cy - open_h * 0.52 + look_y * 0.7, rx * 0.34, open_h * 0.34))
            continue

        # Esclerótica con sombra superior suave
        sclera = QLinearGradient(ex, cy - open_h, ex, cy + open_h)
        sclera.setColorAt(0.0, QColor("#cbd5e1"))
        sclera.setColorAt(0.28, QColor("#ffffff"))
        sclera.setColorAt(1.0, QColor("#e2e8f0"))
        p.setBrush(QBrush(sclera))
        p.setPen(QPen(QColor("#1e293b"), 0.85))
        p.drawEllipse(QRectF(ex - rx, cy - open_h, rx * 2.0, open_h * 2.0))

        # Iris 3D degradado
        ix = ex + look_x
        iy = cy + look_y
        ir = min(rx * 0.66, open_h * 0.82)
        igrad = QRadialGradient(ix, iy + ir * 0.25, ir * 1.15)
        igrad.setColorAt(0.0, QColor(iris_color).lighter(145))
        igrad.setColorAt(0.65, QColor(iris_color))
        igrad.setColorAt(1.0, QColor("#0f172a"))
        p.setBrush(QBrush(igrad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(ix - ir, iy - ir, ir * 2.0, ir * 2.0))

        # Pupila + doble brillo especular
        pr = ir * 0.48
        p.setBrush(QColor("#090d16"))
        p.drawEllipse(QRectF(ix - pr, iy - pr, pr * 2.0, pr * 2.0))
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(ix - ir * 0.42, iy - ir * 0.48, ir * 0.36, ir * 0.36))
        p.setBrush(_rgba("#ffffff", 180))
        p.drawEllipse(QRectF(ix + ir * 0.16, iy + ir * 0.16, ir * 0.18, ir * 0.18))

        if lashes:
            lpen = QPen(QColor("#1e1b2e"), 1.35, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            p.setPen(lpen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            lash = QPainterPath()
            lash.moveTo(ex - rx * 0.92, cy - open_h * 0.45)
            lash.quadTo(ex, cy - open_h * 1.18, ex + rx * 1.05 * side, cy - open_h * 0.55)
            p.drawPath(lash)


def _draw_mouth(p: QPainter, cx: float, cy: float, width: float, state: str, t: float, color: str = "#7c2d12") -> None:
    p.save()
    if state == "speaking":
        open_amt = 2.0 + 3.2 * (0.5 + 0.5 * math.sin(t * 14.0))
        p.setBrush(QColor("#3b1525"))
        p.setPen(QPen(QColor(color), 1.1))
        p.drawRoundedRect(QRectF(cx - width * 0.42, cy - open_amt * 0.45, width * 0.84, open_amt), open_amt * 0.45, open_amt * 0.45)
    elif state == "thinking":
        p.setPen(QPen(QColor(color), 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(cx - width * 0.32, cy + 0.5)
        path.quadTo(cx + width * 0.05, cy - 0.8, cx + width * 0.36, cy + 0.2)
        p.drawPath(path)
    elif state == "error":
        p.setPen(QPen(QColor("#f97316"), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(cx - width * 0.36, cy + 2.2)
        path.quadTo(cx, cy - 1.5, cx + width * 0.36, cy + 2.2)
        p.drawPath(path)
    else:
        p.setPen(QPen(QColor(color), 1.45, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(cx - width * 0.42, cy - 0.4)
        path.quadTo(cx, cy + 2.6, cx + width * 0.42, cy - 0.4)
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
        lx, ly = cx - span * 0.72, cy + 6.0 + math.sin(t * 2.2) * 2.0
        rx, ry = cx + span * 0.42, cy - 6.0 + math.cos(t * 2.4) * 2.4
    elif state == "working":
        lx, ly = cx - span * 0.62, cy + 2.0 + math.sin(t * 8.5) * 4.0
        rx, ry = cx + span * 0.62, cy + 2.0 + math.cos(t * 8.5) * 4.0
    elif state == "speaking":
        lx, ly = cx - span * 0.92, cy - 1.0 + math.sin(t * 5.2) * 5.0
        rx, ry = cx + span * 0.92, cy - 1.0 - math.sin(t * 5.2) * 5.0
    elif state == "listening":
        lx, ly = cx - span * 0.86, cy - 4.0 + math.sin(t * 2.6) * 2.2
        rx, ry = cx + span * 0.86, cy - 4.0 + math.sin(t * 2.6 + 0.8) * 2.2
    else:
        lx, ly = cx - span * 0.88, cy + 4.0 + math.sin(t * 1.9) * 3.0
        rx, ry = cx + span * 0.88, cy + 4.0 + math.sin(t * 1.9 + 1.1) * 3.0

    for hx, hy, side in ((lx, ly, -1.0), (rx, ry, 1.0)):
        # Pequeña muñeca / aura energética
        aura = QRadialGradient(hx, hy, 11.0)
        aura.setColorAt(0.0, _rgba(accent, 95))
        aura.setColorAt(1.0, _rgba(accent, 0))
        p.setBrush(QBrush(aura))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(hx - 11.0, hy - 11.0, 22.0, 22.0))

        # Palma 3D redondeada + pulgar estilizado
        _draw_3d_sphere(p, hx, hy, 6.4, 5.8, hi, mid, sh, rim=accent)
        _draw_3d_sphere(p, hx - side * 4.8, hy - 2.2, 2.7, 2.5, hi, mid, sh)


def _draw_thought_orbs(p: QPainter, cx: float, top_y: float, t: float, accent: str, state: str) -> None:
    if state not in ("thinking", "working", "listening"):
        return
    count = 3
    for i in range(count):
        ang = t * (3.2 if state == "working" else 1.8) + i * (2.0 * math.pi / count)
        ox = cx + math.cos(ang) * 32.0
        oy = top_y + math.sin(ang * 1.4) * 7.0
        rad = 3.2 + 1.1 * math.sin(t * 4.0 + i)
        glow = QRadialGradient(ox, oy, rad * 2.6)
        glow.setColorAt(0.0, _rgba(accent, 230))
        glow.setColorAt(0.6, _rgba(accent, 75))
        glow.setColorAt(1.0, _rgba(accent, 0))
        p.setBrush(QBrush(glow))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(ox - rad * 2.4, oy - rad * 2.4, rad * 4.8, rad * 4.8))
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(ox - rad * 0.55, oy - rad * 0.55, rad * 1.1, rad * 1.1))


def _compute_kinematics(t: float, state: str) -> tuple[float, float, float, float]:
    """Devuelve (breath_y, look_x, look_y, blink_ratio)."""
    breath_y = math.sin(t * 2.1) * (3.4 if state != "idle" else 2.4)
    if state == "thinking":
        look_x = math.sin(t * 1.4) * 2.6
        look_y = -2.2 + math.cos(t * 1.1) * 0.7
    elif state == "working":
        look_x = math.sin(t * 5.0) * 2.4
        look_y = 1.6
    elif state == "listening":
        look_x = 0.0
        look_y = -0.4
    else:
        look_x = math.sin(t * 0.85) * 1.8
        look_y = math.sin(t * 0.55) * 0.8

    # Parpadeo orgánico cada ~4.2 s
    cycle = t % 4.2
    blink = 0.0
    if 3.92 <= cycle <= 4.12:
        phase = (cycle - 3.92) / 0.20
        blink = math.sin(phase * math.pi)
    return breath_y, look_x, look_y, blink


def _paint_lumen(p: QPainter, cx: float, cy: float, t: float, state: str) -> None:
    """LUMEN: Linterna 3D estilizada con núcleo de luz cálida, ojos brillantes y manos flotantes."""
    breath, lx, ly, blink = _compute_kinematics(t, state)
    y = cy + breath
    pulse = 0.5 + 0.5 * math.sin(t * (6.0 if state in ("thinking", "speaking", "working") else 2.3))

    # Haz volumétrico y aura cálida
    glow = QRadialGradient(cx, y - 2.0, 56.0 + pulse * 8.0)
    glow.setColorAt(0.0, _rgba("#fde047", int(115 + 45 * pulse)))
    glow.setColorAt(0.55, _rgba("#f59e0b", 48))
    glow.setColorAt(1.0, _rgba("#f59e0b", 0))
    p.setBrush(QBrush(glow))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(cx - 58.0, y - 58.0, 116.0, 116.0))

    # Asa metálica superior 3D
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor("#cbd5e1"), 2.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    handle = QPainterPath()
    handle.moveTo(cx - 13.0, y - 34.0)
    handle.cubicTo(cx - 14.0, y - 50.0, cx + 14.0, y - 50.0, cx + 13.0, y - 34.0)
    p.drawPath(handle)

    # Cuerpo de cristal 3D de la linterna
    glass = QLinearGradient(cx - 24.0, y - 24.0, cx + 26.0, y + 24.0)
    glass.setColorAt(0.0, QColor("#fef3c7"))
    glass.setColorAt(0.45, QColor("#f59e0b"))
    glass.setColorAt(0.82, QColor("#b45309"))
    glass.setColorAt(1.0, QColor("#451a03"))
    p.setBrush(QBrush(glass))
    p.setPen(QPen(_rgba("#fde68a", 210), 1.4))
    p.drawRoundedRect(QRectF(cx - 23.0, y - 26.0, 46.0, 52.0), 15.0, 15.0)

    # Reflejo especular de vidrio curvo
    spec = QLinearGradient(cx - 18.0, y - 22.0, cx - 8.0, y + 18.0)
    spec.setColorAt(0.0, _rgba("#ffffff", 165))
    spec.setColorAt(1.0, _rgba("#ffffff", 10))
    p.setBrush(QBrush(spec))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(cx - 18.5, y - 21.0, 8.0, 38.0), 4.0, 4.0)

    # Tapa y base metálicas 3D (grafito-titanio con aro dorado)
    cap_grad = QLinearGradient(cx - 26.0, y - 34.0, cx + 26.0, y - 24.0)
    cap_grad.setColorAt(0.0, QColor("#475569"))
    cap_grad.setColorAt(0.45, QColor("#1e293b"))
    cap_grad.setColorAt(1.0, QColor("#090d16"))
    p.setBrush(QBrush(cap_grad))
    p.setPen(QPen(QColor("#fbbf24"), 1.2))
    p.drawRoundedRect(QRectF(cx - 26.0, y - 35.0, 52.0, 12.0), 6.0, 6.0)
    p.drawRoundedRect(QRectF(cx - 24.0, y + 22.0, 48.0, 12.0), 6.0, 6.0)

    # Ojos luminosos expresivos + boca sutil dentro del cristal
    _draw_eyes(p, cx, y - 3.0, 9.5, 5.2, 6.2, "#fef08a", lx, ly, blink, glow_mode=True)
    _draw_mouth(p, cx, y + 12.0, 13.0, state, t, color="#451a03")

    # Manos flotantes doradas-titanio
    _draw_floating_hands(p, cx, y + 10.0, 39.0, t, state, "#fef08a", "#f59e0b", "#78350f", "#fbbf24")
    _draw_thought_orbs(p, cx, y - 48.0, t, "#fde047", state)


def _paint_angel(p: QPainter, cx: float, cy: float, t: float, state: str) -> None:
    """ANGEL: Angelito 3D fino con aureola flotante, alas animadas, ojos y manos."""
    breath, lx, ly, blink = _compute_kinematics(t, state)
    y = cy + breath
    flap = math.sin(t * (7.5 if state in ("working", "thinking") else 3.1)) * 7.5

    # Aura celeste perlada
    aura = QRadialGradient(cx, y - 4.0, 56.0)
    aura.setColorAt(0.0, _rgba("#67e8f9", 85))
    aura.setColorAt(0.65, _rgba("#38bdf8", 30))
    aura.setColorAt(1.0, _rgba("#38bdf8", 0))
    p.setBrush(QBrush(aura))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(cx - 56.0, y - 56.0, 112.0, 112.0))

    # Alitas 3D detrás del cuerpo (dos capas de plumas estilizadas)
    for side in (-1.0, 1.0):
        p.save()
        p.translate(cx + side * 14.0, y + 10.0)
        p.rotate(side * (-14.0 + flap))
        wgrad = QLinearGradient(0.0, -20.0, side * 38.0, 16.0)
        wgrad.setColorAt(0.0, QColor("#f8fafc"))
        wgrad.setColorAt(0.55, QColor("#bae6fd"))
        wgrad.setColorAt(1.0, QColor("#38bdf8"))
        p.setBrush(QBrush(wgrad))
        p.setPen(QPen(_rgba("#e0f2fe", 190), 1.1))
        wing = QPainterPath()
        wing.moveTo(0.0, 0.0)
        wing.cubicTo(side * 16.0, -24.0, side * 38.0, -18.0, side * 36.0, 2.0)
        wing.cubicTo(side * 28.0, 12.0, side * 14.0, 14.0, 0.0, 8.0)
        wing.closeSubpath()
        p.drawPath(wing)
        p.restore()

    # Túnica / cuerpo 3D perlado con ribete cian metálico
    robe = QLinearGradient(cx - 18.0, y + 8.0, cx + 18.0, y + 42.0)
    robe.setColorAt(0.0, QColor("#f8fafc"))
    robe.setColorAt(0.55, QColor("#cbd5e1"))
    robe.setColorAt(1.0, QColor("#475569"))
    p.setBrush(QBrush(robe))
    p.setPen(QPen(QColor("#38bdf8"), 1.2))
    body = QPainterPath()
    body.moveTo(cx - 13.0, y + 10.0)
    body.quadTo(cx - 21.0, y + 36.0, cx - 15.0, y + 40.0)
    body.lineTo(cx + 15.0, y + 40.0)
    body.quadTo(cx + 21.0, y + 36.0, cx + 13.0, y + 10.0)
    body.closeSubpath()
    p.drawPath(body)

    # Cabeza 3D fina (porcelana cálida) + flequillo celeste perlado
    _draw_3d_sphere(p, cx, y - 10.0, 22.0, 21.0, "#fff7ed", "#fde0c6", "#d6a485", rim="#bae6fd")

    hair = QLinearGradient(cx - 22.0, y - 34.0, cx + 22.0, y - 10.0)
    hair.setColorAt(0.0, QColor("#f8fafc"))
    hair.setColorAt(0.55, QColor("#93c5fd"))
    hair.setColorAt(1.0, QColor("#1d4ed8"))
    p.setBrush(QBrush(hair))
    p.setPen(Qt.PenStyle.NoPen)
    bangs = QPainterPath()
    bangs.moveTo(cx - 22.5, y - 12.0)
    bangs.cubicTo(cx - 22.0, y - 36.0, cx + 22.0, y - 36.0, cx + 22.5, y - 12.0)
    bangs.quadTo(cx + 10.0, y - 22.0, cx, y - 16.0)
    bangs.quadTo(cx - 10.0, y - 22.0, cx - 22.5, y - 12.0)
    p.drawPath(bangs)

    # Aureola 3D flotante dorada-celeste
    halo_y = y - 39.0 + math.sin(t * 3.0) * 2.2
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(_rgba("#fde047", 90), 5.0))
    p.drawEllipse(QRectF(cx - 16.0, halo_y - 4.8, 32.0, 9.6))
    p.setPen(QPen(QColor("#fef08a"), 2.1))
    p.drawEllipse(QRectF(cx - 16.0, halo_y - 4.8, 32.0, 9.6))

    # Ojos luminosos y sonrisa serena
    _draw_eyes(p, cx, y - 8.5, 8.2, 4.9, 5.6, "#38bdf8", lx, ly, blink)
    _draw_mouth(p, cx, y + 3.0, 12.0, state, t, color="#9a5b4a")

    # Manos flotantes delicadas
    _draw_floating_hands(p, cx, y + 20.0, 36.0, t, state, "#fff7ed", "#fde0c6", "#c49172", "#67e8f9")
    _draw_thought_orbs(p, cx, y - 48.0, t, "#67e8f9", state)


def _paint_mateo(p: QPainter, cx: float, cy: float, t: float, state: str) -> None:
    """MATEO: Avatar 3D de un niño coder futurista con audífonos LED, ojos expresivos y manos."""
    breath, lx, ly, blink = _compute_kinematics(t, state)
    y = cy + breath

    # Halo tecnológico azul-eléctrico
    aura = QRadialGradient(cx, y, 56.0)
    aura.setColorAt(0.0, _rgba("#22d3ee", 78))
    aura.setColorAt(0.6, _rgba("#2563eb", 30))
    aura.setColorAt(1.0, _rgba("#2563eb", 0))
    p.setBrush(QBrush(aura))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(cx - 56.0, y - 56.0, 112.0, 112.0))

    # Chaqueta / hoodie futurista 3D del niño (obsidiana + línea cian)
    jacket = QLinearGradient(cx - 22.0, y + 10.0, cx + 22.0, y + 42.0)
    jacket.setColorAt(0.0, QColor("#1e293b"))
    jacket.setColorAt(0.55, QColor("#0f172a"))
    jacket.setColorAt(1.0, QColor("#020617"))
    p.setBrush(QBrush(jacket))
    p.setPen(QPen(QColor("#22d3ee"), 1.3))
    torso = QPainterPath()
    torso.moveTo(cx - 17.0, y + 12.0)
    torso.quadTo(cx - 24.0, y + 36.0, cx - 18.0, y + 41.0)
    torso.lineTo(cx + 18.0, y + 41.0)
    torso.quadTo(cx + 24.0, y + 36.0, cx + 17.0, y + 12.0)
    torso.closeSubpath()
    p.drawPath(torso)
    # Emblema V energético en el pecho
    p.setPen(QPen(QColor("#38bdf8"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(cx - 7.0, y + 20.0), QPointF(cx, y + 28.0))
    p.drawLine(QPointF(cx, y + 28.0), QPointF(cx + 7.0, y + 20.0))

    # Diadema de audífonos tech
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor("#334155"), 4.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    band = QPainterPath()
    band.moveTo(cx - 24.0, y - 10.0)
    band.cubicTo(cx - 25.0, y - 40.0, cx + 25.0, y - 40.0, cx + 24.0, y - 10.0)
    p.drawPath(band)
    for side in (-1.0, 1.0):
        _draw_3d_sphere(p, cx + side * 24.0, y - 9.0, 5.4, 8.2, "#475569", "#1e293b", "#090d16", rim="#22d3ee")

    # Cabeza 3D del niño
    _draw_3d_sphere(p, cx, y - 10.0, 22.0, 21.5, "#ffedd5", "#fed7aa", "#c2885c", rim="#38bdf8")

    # Cabello corto juvenil 3D con mechones estilizados
    hair = QLinearGradient(cx - 22.0, y - 36.0, cx + 22.0, y - 10.0)
    hair.setColorAt(0.0, QColor("#3f2e24"))
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

    # Cejas expresivas + ojos vivos + boca
    brow_pen = QPen(QColor("#2b1e17"), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(brow_pen)
    brow_lift = -1.6 if state == "thinking" else 0.0
    p.drawLine(QPointF(cx - 13.0, y - 16.0 + brow_lift), QPointF(cx - 4.5, y - 16.5))
    p.drawLine(QPointF(cx + 4.5, y - 16.5), QPointF(cx + 13.0, y - 16.0 + brow_lift))

    _draw_eyes(p, cx, y - 8.5, 8.4, 5.0, 5.6, "#0284c7", lx, ly, blink)
    _draw_mouth(p, cx, y + 3.2, 13.5, state, t, color="#7c2d12")

    # Manos animadas del niño
    _draw_floating_hands(p, cx, y + 21.0, 38.0, t, state, "#ffedd5", "#fed7aa", "#b77e54", "#22d3ee")
    _draw_thought_orbs(p, cx, y - 47.0, t, "#22d3ee", state)


def _paint_zamara(p: QPainter, cx: float, cy: float, t: float, state: str) -> None:
    """ZAMARA V8.2: Avatar 3D de una niña futurista multimodal con corona cristalina, ojos y manos."""
    breath, lx, ly, blink = _compute_kinematics(t, state)
    y = cy + breath

    # Halo multimodal violeta-magenta-oro rosa
    aura = QRadialGradient(cx, y - 2.0, 58.0)
    aura.setColorAt(0.0, _rgba("#e879f9", 84))
    aura.setColorAt(0.55, _rgba("#ec4899", 34))
    aura.setColorAt(1.0, _rgba("#ec4899", 0))
    p.setBrush(QBrush(aura))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(cx - 58.0, y - 58.0, 116.0, 116.0))

    # Melena / coletas estilizadas detrás de la cabeza
    back_hair = QLinearGradient(cx - 28.0, y - 26.0, cx + 28.0, y + 28.0)
    back_hair.setColorAt(0.0, QColor("#3b0764"))
    back_hair.setColorAt(0.55, QColor("#1e1033"))
    back_hair.setColorAt(1.0, QColor("#0d0717"))
    p.setBrush(QBrush(back_hair))
    p.setPen(QPen(_rgba("#e879f9", 110), 0.9))
    for side in (-1.0, 1.0):
        sway = math.sin(t * 2.2 + side) * 2.0
        p.drawEllipse(QRectF(cx + side * 20.0 - 11.0 + sway, y - 14.0, 22.0, 34.0))

    # Vestuario futurista fino (obsidiana perlada + ribete magenta/oro rosa)
    dress = QLinearGradient(cx - 20.0, y + 10.0, cx + 20.0, y + 42.0)
    dress.setColorAt(0.0, QColor("#2a1642"))
    dress.setColorAt(0.6, QColor("#150b24"))
    dress.setColorAt(1.0, QColor("#090512"))
    p.setBrush(QBrush(dress))
    p.setPen(QPen(QColor("#f472b6"), 1.25))
    torso = QPainterPath()
    torso.moveTo(cx - 14.0, y + 11.0)
    torso.quadTo(cx - 24.0, y + 36.0, cx - 18.0, y + 41.0)
    torso.lineTo(cx + 18.0, y + 41.0)
    torso.quadTo(cx + 24.0, y + 36.0, cx + 14.0, y + 11.0)
    torso.closeSubpath()
    p.drawPath(torso)
    # Cristal multimodal en el pecho
    _draw_3d_sphere(p, cx, y + 23.0, 4.4, 4.4, "#fdf4ff", "#e879f9", "#86198f")

    # Cabeza 3D de la niña con rubor sutil
    _draw_3d_sphere(p, cx, y - 10.0, 21.5, 21.0, "#fff5f5", "#fde2d8", "#cf9d91", rim="#f472b6")
    for side in (-1.0, 1.0):
        blush = QRadialGradient(cx + side * 12.0, y - 2.0, 5.5)
        blush.setColorAt(0.0, _rgba("#f472b6", 75))
        blush.setColorAt(1.0, _rgba("#f472b6", 0))
        p.setBrush(QBrush(blush))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx + side * 12.0 - 5.5, y - 7.5, 11.0, 11.0))

    # Flequillo sedoso 3D
    p.setBrush(QBrush(back_hair))
    p.setPen(Qt.PenStyle.NoPen)
    front = QPainterPath()
    front.moveTo(cx - 22.5, y - 10.0)
    front.cubicTo(cx - 22.0, y - 36.0, cx + 22.0, y - 36.0, cx + 22.5, y - 10.0)
    front.quadTo(cx + 11.0, y - 23.0, cx + 2.0, y - 16.0)
    front.quadTo(cx - 10.0, y - 23.0, cx - 22.5, y - 10.0)
    p.drawPath(front)

    # Lazo / diadema cristalina luminosa en la parte superior
    bow_y = y - 32.0 + math.sin(t * 2.5) * 1.2
    p.setBrush(QColor("#f472b6"))
    p.setPen(QPen(QColor("#fdf4ff"), 1.0))
    for side in (-1.0, 1.0):
        wing = QPainterPath()
        wing.moveTo(cx, bow_y)
        wing.lineTo(cx + side * 13.0, bow_y - 6.0)
        wing.lineTo(cx + side * 11.0, bow_y + 4.0)
        wing.closeSubpath()
        p.drawPath(wing)
    _draw_3d_sphere(p, cx, bow_y, 3.6, 3.6, "#ffffff", "#e879f9", "#a21caf")

    # Ojos grandes expresivos con pestañas finas y boca
    _draw_eyes(p, cx, y - 8.2, 8.2, 5.2, 6.0, "#a855f7", lx, ly, blink, lashes=True)
    _draw_mouth(p, cx, y + 3.0, 11.5, state, t, color="#9d174d")

    # Manos delicadas animadas
    _draw_floating_hands(p, cx, y + 21.0, 37.0, t, state, "#fff5f5", "#fde2d8", "#c59086", "#e879f9")
    _draw_thought_orbs(p, cx, y - 47.0, t, "#f472b6", state)


def _paint_aura_core(p: QPainter, cx: float, cy: float, t: float, state: str) -> None:
    """Fallback AURA: Esfera holográfica 3D con visor expresivo, ojos y manos flotantes."""
    breath, lx, ly, blink = _compute_kinematics(t, state)
    y = cy + breath

    aura = QRadialGradient(cx, y, 54.0)
    aura.setColorAt(0.0, _rgba("#38bdf8", 85))
    aura.setColorAt(1.0, _rgba("#38bdf8", 0))
    p.setBrush(QBrush(aura))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(cx - 54.0, y - 54.0, 108.0, 108.0))

    _draw_3d_sphere(p, cx, y - 4.0, 26.0, 26.0, "#334155", "#0f172a", "#020617", rim="#38bdf8")
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
    """Dibuja el avatar 3D del modelo dentro de `rect` manteniendo proporción y suavizado."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    side = min(rect.width(), rect.height())
    scale = side / 128.0
    cx = rect.center().x()
    cy = rect.center().y() + 4.0 * scale

    # Sombra de piso suave para dar volumen 3D
    painter.save()
    painter.translate(cx, cy)
    painter.scale(scale, scale)

    shadow_w = 34.0 - math.sin(t * 2.1) * 2.2
    floor = QRadialGradient(0.0, 48.0, shadow_w)
    floor.setColorAt(0.0, _rgba("#000000", 125))
    floor.setColorAt(1.0, _rgba("#000000", 0))
    painter.setBrush(QBrush(floor))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QRectF(-shadow_w, 42.0, shadow_w * 2.0, 12.0))

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
    """Genera un QPixmap transparente con canal alfa del avatar 3D (útil para sprites y pruebas)."""
    pix = QPixmap(max(32, int(width)), max(32, int(height)))
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    paint_avatar_3d(painter, QRectF(0, 0, pix.width(), pix.height()), persona, state, t)
    painter.end()
    return pix


class AvatarStageWidget(QWidget):
    """Escenario compacto 3D animado en vivo para la barra lateral / cabecera de AURA IA."""

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
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(86 if compact else 118)
        self.setAccessibleName("Avatar 3D animado del modelo activo")

        self._timer = QTimer(self)
        self._timer.setInterval(55)  # ~18 FPS ultrasuaves y < 1 % CPU
        self._timer.timeout.connect(self._tick)

    def set_model(self, model_ref: str | Path | None, label: str = "") -> None:
        self.persona = resolve_avatar_persona(model_ref)
        meta = persona_meta(self.persona)
        self.model_caption = label or meta.title
        self.setToolTip(f"{self.model_caption} · {meta.subtitle}\nClic para abrir el asistente o cambiar de modelo")
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

        # Tarjeta fina estilo obsidiana metálica con borde sutil del modelo activo
        bg = QLinearGradient(0.0, 0.0, w, h)
        bg.setColorAt(0.0, QColor("#0d1320"))
        bg.setColorAt(1.0, QColor("#080c15"))
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(_rgba(meta.accent, 115 if self.state != "idle" else 70), 1.15))
        painter.drawRoundedRect(QRectF(1.0, 1.0, w - 2.0, h - 2.0), 12.0, 12.0)

        # Escenario del avatar a la izquierda
        av_size = h - 8.0
        av_rect = QRectF(4.0, 4.0, av_size, av_size)
        paint_avatar_3d(painter, av_rect, self.persona, self.state, self._t)

        # Texto fino de identidad y estado a la derecha
        tx = av_size + 10.0
        tw = max(40.0, w - tx - 10.0)
        font = painter.font()
        font.setFamily("Segoe UI")
        font.setPointSize(9 if self._compact else 10)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#f8fafc"))
        painter.drawText(QRectF(tx, 14.0 if self._compact else 20.0, tw, 20.0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.model_caption)

        font.setPointSize(8)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(meta.accent_soft))
        painter.drawText(QRectF(tx, 34.0 if self._compact else 43.0, tw, 18.0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, meta.subtitle)

        # Indicador de estado vivo
        dot_y = 58.0 if self._compact else 74.0
        dot_color = "#f97316" if self.state == "error" else meta.accent
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(dot_color))
        painter.drawEllipse(QRectF(tx, dot_y + 4.0, 7.0, 7.0))
        painter.setPen(QColor("#94a3b8"))
        painter.drawText(QRectF(tx + 12.0, dot_y, tw - 12.0, 16.0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.status_caption)
        painter.end()
