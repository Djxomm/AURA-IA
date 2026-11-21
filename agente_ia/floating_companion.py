"""Small transparent AURAX companion, with animation only while active."""
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QPoint
from PySide6.QtGui import QPixmap,QPainter,QColor,QRegion
from PySide6.QtWidgets import QWidget,QApplication,QMenu

class FloatingCompanion(QWidget):
    def __init__(self,owner):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.owner=owner;self.drag=None;self.moved=False;self.active=False;self.phase=0;self.attention=''
        self.setWindowTitle('AURAX · Asistente');self.setAccessibleName('Asistente flotante AURAX');self.setFixedSize(140,166);self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground);self.setCursor(Qt.CursorShape.PointingHandCursor)
        source=QPixmap(str(Path(__file__).parent/'static/assets/aurax-companion.png'))
        if source.isNull():source=QPixmap(str(Path(__file__).parent/'static/assets/aura-icono-transparente.png'))
        if not source.isNull():
            bounds=QRegion(source.mask()).boundingRect()
            if not bounds.isEmpty():source=source.copy(bounds)
        self.sprite=source.scaled(120,140,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
        self.timer=QTimer(self);self.timer.setInterval(350);self.timer.timeout.connect(self.animate)
        self.update_state(False,'Listo. Clic para abrir AURAX; arrastra para mover.')
        area=QApplication.primaryScreen().availableGeometry();position=owner.prefs.get('floating_position')
        if isinstance(position,list) and len(position)==2 and all(isinstance(v,int) for v in position):self.move(position[0],position[1])
        else:self.move(area.right()-self.width()-24,area.bottom()-self.height()-24)
        self.clamp_position()

    def clamp_position(self):
        screen=QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen();area=screen.availableGeometry()
        self.move(max(area.left(),min(self.x(),area.right()-self.width()+1)),max(area.top(),min(self.y(),area.bottom()-self.height()+1)))

    def animate(self):self.phase=(self.phase+1)%6;self.update()

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bob=2 if self.active and self.phase%2 else 0
        painter.drawPixmap((self.width()-self.sprite.width())//2,8+bob,self.sprite)
        if self.attention:
            painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#ffc46b'));painter.drawEllipse(110,8,20,20);painter.setPen(QColor('#10213b'));painter.drawText(110,8,20,20,Qt.AlignmentFlag.AlignCenter,'!')
        elif self.active:
            painter.setPen(Qt.PenStyle.NoPen)
            for index in range(3):painter.setBrush(QColor('#63e4ef' if self.phase%3==index else '#315474'));painter.drawEllipse(52+index*12,154,6,6)
        painter.end()

    def update_state(self,active,text):
        changed=self.active!=bool(active);self.active=bool(active)
        self.setToolTip('AURAX · '+(self.attention or text)+'\nClic: abrir AURAX · Clic derecho: opciones')
        if self.active and self.isVisible() and self.owner.prefs.get('animations',True):
            if not self.timer.isActive():self.timer.start()
        elif self.timer.isActive():self.timer.stop();self.phase=0
        if changed:self.update()

    def set_attention(self,text):self.attention=text;self.setToolTip('AURAX · '+text if text else 'AURAX · Clic para abrir');self.update()
    def open(self):self.owner.showNormal();self.owner.raise_();self.owner.activateWindow();self.owner.open_aurax();self.owner.input.setFocus()
    def dictate(self):self.open();self.owner.toggle_dictation()
    def hide_safe(self):self.hide();self.owner.save_pref('floating',False)
    def contextMenuEvent(self,event):
        menu=QMenu(self);menu.setStyleSheet('QMenu{background:#102035;color:#e7f4ff;border:1px solid #315776;}QMenu::item{padding:9px 17px;}QMenu::item:selected{background:#21557e;}')
        for label,callback in [('Abrir AURAX',self.open),('Dictar',self.dictate),('Leer última respuesta',self.owner.speak),('Ocultar asistente',self.hide_safe)]:menu.addAction(label,callback)
        menu.exec(event.globalPos())
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.drag=event.globalPosition().toPoint()-self.frameGeometry().topLeft();self.moved=False;event.accept()
    def mouseMoveEvent(self,event):
        if self.drag is not None and event.buttons()&Qt.MouseButton.LeftButton:
            target=event.globalPosition().toPoint()-self.drag
            if (target-self.pos()).manhattanLength()>3:self.moved=True
            self.move(target);self.clamp_position();event.accept()
    def mouseReleaseEvent(self,event):
        if self.drag is None:return
        self.drag=None
        if self.moved:self.owner.save_pref('floating_position',[self.x(),self.y()])
        else:self.open()
    def mouseDoubleClickEvent(self,event):self.open()
    def hideEvent(self,event):self.timer.stop();super().hideEvent(event)
    def showEvent(self,event):
        super().showEvent(event)
        if self.active and self.owner.prefs.get('animations',True):self.timer.start()
    def closeEvent(self,event):self.timer.stop();super().closeEvent(event)
