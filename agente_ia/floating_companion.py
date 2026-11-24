"""Small transparent AURAX companion with clickable instruction speech bubble ('Globo AURAX')."""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QPoint, QRect, QRectF
from PySide6.QtGui import QPixmap, QPainter, QColor, QRegion, QFont, QPen, QKeySequence, QShortcut
from .avatar_3d import paint_avatar_3d, persona_meta, render_avatar_pixmap, resolve_avatar_persona
from PySide6.QtWidgets import (
    QWidget,
    QApplication,
    QMenu,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QCheckBox,
    QPushButton,
    QFrame,
)


class AuraxInstructionBubble(QWidget):
    """Globo flotante de instrucciones directas de AURAX: envía exactamente las palabras del usuario al chat."""

    def __init__(self, companion: "FloatingCompanion"):
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.companion = companion
        self.owner = companion.owner
        self.setWindowTitle("AURAX · Globo de instrucciones")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(360)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        card = QFrame()
        card.setObjectName("auraxBubbleCard")
        card.setStyleSheet(
            "QFrame#auraxBubbleCard{background:#090d16;border:1px solid #38bdf8;border-radius:14px;}"
            "QLabel{color:#f8fafc;background:transparent;}"
            "QPlainTextEdit{background:#0f1626;color:#f8fafc;border:1px solid #26354d;border-radius:10px;padding:8px;font-size:13px;}"
            "QCheckBox{color:#cbd5e1;background:transparent;font-size:11px;}"
            "QPushButton{background:#0284c7;color:#ffffff;border:1px solid #38bdf8;border-radius:8px;padding:7px 14px;font-weight:600;}"
            "QPushButton:hover{background:#0ea5e9;}"
            "QPushButton#secondaryBtn{background:#121926;color:#e2e8f0;border:1px solid #243247;}"
            "QPushButton#secondaryBtn:hover{background:#1b2638;border-color:#38bdf8;}"
        )
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("💬 Globo AURAX → Chat")
        title.setStyleSheet("font-size:14px;font-weight:700;color:#7dd3fc;")
        close_btn = QPushButton("✕")
        close_btn.setObjectName("secondaryBtn")
        close_btn.setFixedSize(26, 26)
        close_btn.clicked.connect(self.hide)
        head.addWidget(title, 1)
        head.addWidget(close_btn)
        layout.addLayout(head)

        hint = QLabel("Escribe solo tu instrucción clara; se enviará tal cual al chat con el contexto de AuraX.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#94a3b8;font-size:11px;")
        layout.addWidget(hint)

        self.context_badge = QLabel("")
        self.context_badge.setWordWrap(True)
        self.context_badge.setStyleSheet("color:#38bdf8;font-size:11px;font-family:Consolas;")
        layout.addWidget(self.context_badge)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Ej.: compila el proyecto y corrige el error del botón guardar…")
        self.editor.setFixedHeight(86)
        layout.addWidget(self.editor)

        opts = QHBoxLayout()
        self.chk_file = QCheckBox("Archivo AuraX")
        self.chk_file.setChecked(True)
        self.chk_err = QCheckBox("Error consola")
        self.chk_err.setChecked(True)
        self.chk_auto = QCheckBox("Autónomo")
        self.chk_auto.setChecked(True)
        opts.addWidget(self.chk_file)
        opts.addWidget(self.chk_err)
        opts.addWidget(self.chk_auto)
        layout.addLayout(opts)

        actions = QHBoxLayout()
        send_btn = QPushButton("Enviar al chat (Ctrl+Enter)")
        send_btn.clicked.connect(self.submit)
        voice_btn = QPushButton("🎙️")
        voice_btn.setObjectName("secondaryBtn")
        voice_btn.setToolTip("Iniciar o detener conversación de voz en vivo con MATEO / AURAX")
        voice_btn.clicked.connect(self.start_live_voice)
        apps_btn = QPushButton("Apps CLI")
        apps_btn.setObjectName("secondaryBtn")
        apps_btn.setToolTip("Abrir Claude Code, Codex CLI, OpenCode, Qwen Code u Ollama en el proyecto")
        apps_btn.clicked.connect(self.open_apps)
        actions.addWidget(send_btn, 1)
        actions.addWidget(voice_btn)
        actions.addWidget(apps_btn)
        layout.addLayout(actions)

        QShortcut(QKeySequence("Ctrl+Return"), self, self.submit)
        QShortcut(QKeySequence("Ctrl+Enter"), self, self.submit)
        QShortcut(QKeySequence("Escape"), self, self.hide)

    def refresh_context_preview(self) -> None:
        aurax = getattr(self.owner, "aurax", None)
        bits: list[str] = []
        if aurax is not None:
            bits.append(f"Proyecto: {aurax.workspace.root.name}")
            ed = aurax.tabs.currentWidget()
            if ed is not None:
                bits.append(f"Archivo: {ed.path}")
            if getattr(aurax, "last_exit_code", 0) not in (0, None):
                bits.append(f"Último error: salida {aurax.last_exit_code}")
        elif hasattr(self.owner, "store"):
            try:
                ws = Path(self.owner.store.get_settings().workspace_path).name
                bits.append(f"Proyecto: {ws}")
            except Exception:
                pass
        self.context_badge.setText(" · ".join(bits) if bits else "Chat listo · modo directo")

    def open_near_companion(self) -> None:
        self.refresh_context_preview()
        self.adjustSize()
        screen = QApplication.screenAt(self.companion.frameGeometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        x = self.companion.x() - self.width() + self.companion.width()
        y = self.companion.y() - self.height() - 8
        if y < area.top():
            y = self.companion.y() + self.companion.height() + 8
        x = max(area.left() + 8, min(x, area.right() - self.width() - 8))
        y = max(area.top() + 8, min(y, area.bottom() - self.height() - 8))
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.editor.setFocus()

    def open_apps(self) -> None:
        self.hide()
        if hasattr(self.owner, "open_external_agents"):
            self.owner.open_external_agents(self.editor.toPlainText().strip())

    def start_live_voice(self) -> None:
        self.hide()
        if hasattr(self.owner, "toggle_live_conversation"):
            self.owner.toggle_live_conversation()
        else:
            self.companion.dictate()

    def submit(self) -> None:
        text = self.editor.toPlainText().strip()
        if not text:
            self.editor.setFocus()
            return
        self.editor.clear()
        self.hide()
        if hasattr(self.owner, "send_from_aurax_bubble"):
            self.owner.send_from_aurax_bubble(
                text,
                include_file=self.chk_file.isChecked(),
                include_error=self.chk_err.isChecked(),
                autonomous=self.chk_auto.isChecked(),
            )
        else:
            self.companion.open()
            if hasattr(self.owner, "input"):
                self.owner.input.setPlainText(text)
            if hasattr(self.owner, "send"):
                self.owner.send()


class FloatingCompanion(QWidget):
    def __init__(self, owner):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.owner = owner
        self.drag = None
        self.moved = False
        self.active = False
        self.phase = 0
        self._anim_t = 0.0
        self.avatar_state = "idle"
        self.persona = resolve_avatar_persona(getattr(getattr(owner, "client", None), "model", None))
        self.attention = ""
        self.bubble_rect = QRect(4, 4, 42, 32)
        self.bubble = AuraxInstructionBubble(self)
        self.setWindowTitle("AURA · Asistente 3D")
        self.setAccessibleName("Asistente flotante 3D AURA")
        self.setFixedSize(152, 174)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sprite = render_avatar_pixmap(self.persona, "idle", 0.0, 128, 140)
        self.timer = QTimer(self)
        self.timer.setInterval(85)
        self.timer.timeout.connect(self.animate)
        self.update_state(False, "Listo. Clic en 💬 para escribir en el globo; clic en el avatar para abrir.")
        area = QApplication.primaryScreen().availableGeometry()
        position = owner.prefs.get("floating_position")
        if isinstance(position, list) and len(position) == 2 and all(isinstance(v, int) for v in position):
            self.move(position[0], position[1])
        else:
            self.move(area.right() - self.width() - 24, area.bottom() - self.height() - 24)
        self.clamp_position()

    def set_model_persona(self, model_ref) -> None:
        new_persona = resolve_avatar_persona(model_ref)
        if new_persona != self.persona:
            self.persona = new_persona
            self.sprite = render_avatar_pixmap(self.persona, self.avatar_state, self._anim_t, 128, 140)
            self.update()

    def set_avatar_state(self, state: str) -> None:
        self.avatar_state = state or "idle"
        self.update()

    def clamp_position(self):
        screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(
            max(area.left(), min(self.x(), area.right() - self.width() + 1)),
            max(area.top(), min(self.y(), area.bottom() - self.height() + 1)),
        )

    def animate(self):
        self.phase = (self.phase + 1) % 60
        self._anim_t += 0.14
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        meta = persona_meta(self.persona)
        state = self.avatar_state if self.active else "idle"
        paint_avatar_3d(painter, QRectF(8, 12, self.width() - 16, self.height() - 28), self.persona, state, self._anim_t)

        # Globo clickeable de instrucciones directas al chat (arriba a la izquierda)
        r = self.bubble_rect
        painter.setPen(QPen(QColor(meta.accent), 1.6))
        painter.setBrush(QColor("#0a0f1a"))
        painter.drawRoundedRect(r, 11, 11)
        painter.setPen(QColor("#f8fafc"))
        painter.setFont(QFont("Segoe UI Emoji", 11, QFont.Weight.Bold))
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, "💬")

        if self.attention:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#f59e0b"))
            painter.drawEllipse(122, 8, 20, 20)
            painter.setPen(QColor("#090d16"))
            painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            painter.drawText(122, 8, 20, 20, Qt.AlignmentFlag.AlignCenter, "!")
        elif self.active:
            painter.setPen(Qt.PenStyle.NoPen)
            for index in range(3):
                painter.setBrush(QColor(meta.accent if (self.phase // 3) % 3 == index else "#243247"))
                painter.drawEllipse(58 + index * 12, 160, 6, 6)
        painter.end()

    def update_state(self, active, text, *, avatar_state: str = ""):
        changed = self.active != bool(active)
        self.active = bool(active)
        if avatar_state:
            self.avatar_state = avatar_state
        elif not self.active:
            self.avatar_state = "idle"
        elif self.avatar_state == "idle":
            self.avatar_state = "thinking"
        meta = persona_meta(self.persona)
        self.setToolTip(
            f"AURA · {meta.title} · " + (self.attention or text) + "\nClic en 💬: globo al chat · Clic en el avatar: abrir · Clic derecho: opciones"
        )
        if self.active and self.isVisible() and self.owner.prefs.get("animations", True):
            if not self.timer.isActive():
                self.timer.start()
        elif self.timer.isActive():
            self.timer.stop()
            self.phase = 0
        if changed:
            self.update()

    def set_attention(self, text):
        self.attention = text
        self.setToolTip("AURAX · " + text if text else "AURAX · Clic en 💬 para globo o en AURAX para abrir")
        self.update()

    def open_bubble(self):
        if self.bubble.isVisible():
            self.bubble.hide()
        else:
            self.bubble.open_near_companion()

    def open(self):
        self.bubble.hide()
        self.owner.showNormal()
        self.owner.raise_()
        self.owner.activateWindow()
        self.owner.open_aurax()
        self.owner.input.setFocus()

    def dictate(self):
        self.open()
        self.owner.toggle_dictation()

    def hide_safe(self):
        self.bubble.hide()
        self.hide()
        self.owner.save_pref("floating", False)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu{background:#102035;color:#e7f4ff;border:1px solid #315776;}"
            "QMenu::item{padding:9px 17px;}QMenu::item:selected{background:#21557e;}"
        )
        actions = [
            ("💬 Abrir globo de instrucciones", self.open_bubble),
            ("🎙️ Conversar en vivo (voz con MATEO/AURAX)", lambda: self.owner.toggle_live_conversation() if hasattr(self.owner, "toggle_live_conversation") else self.dictate()),
            ("Abrir AURAX", self.open),
            ("Apps CLI (Codex / Claude / OpenCode…)", lambda: self.owner.open_external_agents() if hasattr(self.owner, "open_external_agents") else None),
            ("Dictar", self.dictate),
            ("Leer última respuesta", self.owner.speak),
            ("Ocultar asistente", self.hide_safe),
        ]
        for label, callback in actions:
            menu.addAction(label, callback)
        menu.exec(event.globalPos())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.moved = False
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            target = event.globalPosition().toPoint() - self.drag
            if (target - self.pos()).manhattanLength() > 3:
                self.moved = True
                if self.bubble.isVisible():
                    self.bubble.hide()
            self.move(target)
            self.clamp_position()
            event.accept()

    def mouseReleaseEvent(self, event):
        if self.drag is None:
            return
        self.drag = None
        if self.moved:
            self.owner.save_pref("floating_position", [self.x(), self.y()])
        elif self.bubble_rect.contains(event.position().toPoint()):
            self.open_bubble()
        else:
            self.open()

    def mouseDoubleClickEvent(self, event):
        self.open()

    def hideEvent(self, event):
        self.timer.stop()
        self.bubble.hide()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self.active and self.owner.prefs.get("animations", True):
            self.timer.start()

    def closeEvent(self, event):
        self.timer.stop()
        self.bubble.close()
        super().closeEvent(event)
