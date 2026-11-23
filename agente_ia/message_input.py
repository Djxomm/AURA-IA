"""Compact native message input: Enter submits, Shift+Enter adds a line."""
import math
from PySide6.QtCore import Qt,Signal,QTimer
from PySide6.QtWidgets import QPlainTextEdit
from PySide6.QtGui import QPalette,QColor

class MessageInput(QPlainTextEdit):
    submit_requested=Signal()
    def __init__(self,parent=None):
        super().__init__(parent);self.composing=False;self.popup=None;self.setMinimumHeight(26);self.setMaximumHeight(96);self.setFixedHeight(26);self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.textChanged.connect(self.fit_text);self.document().documentLayout().documentSizeChanged.connect(lambda size:self.fit_text())
        palette=self.palette();palette.setColor(QPalette.ColorRole.PlaceholderText,QColor('#8fa6bf'));self.setPalette(palette)
        self.setToolTip('Enter: enviar · Shift + Enter: nueva línea · / acciones y habilidades · @ archivos')
    def fit_text(self):
        line_count=max(1,math.ceil(self.document().documentLayout().documentSize().height()))
        height=min(96,max(26,line_count*self.fontMetrics().lineSpacing()+8))
        self.setFixedHeight(height);self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded if height>=96 else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    def resizeEvent(self,event):super().resizeEvent(event);QTimer.singleShot(0,self.fit_text)
    def inputMethodEvent(self,event):self.composing=bool(event.preeditString());super().inputMethodEvent(event)
    def keyPressEvent(self,event):
        if self.popup is not None and self.popup.isVisible():
            if event.key()==Qt.Key.Key_Down:self.popup.move_selection(1);event.accept();return
            if event.key()==Qt.Key.Key_Up:self.popup.move_selection(-1);event.accept();return
            if event.key()==Qt.Key.Key_Escape:self.popup.hide();event.accept();return
            if event.key() in (Qt.Key.Key_Tab,Qt.Key.Key_Return,Qt.Key.Key_Enter) and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                if self.popup.accept_current():event.accept();return
        modifiers=event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and modifiers==Qt.KeyboardModifier.NoModifier and not self.composing:
            if not event.isAutoRepeat() and self.toPlainText().strip():self.submit_requested.emit()
            event.accept();return
        super().keyPressEvent(event)
