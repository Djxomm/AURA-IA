"""Optional image-region marker; selections are evidence, never automatic edit approval."""
from PySide6.QtCore import Qt,QRect,QPoint
from PySide6.QtGui import QPixmap,QImageReader
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QDialogButtonBox,QRubberBand
from .image_evidence import prepare_image

class RegionLabel(QLabel):
    def __init__(self,pixmap,parent=None):
        super().__init__(parent);self.setPixmap(pixmap);self.setFixedSize(pixmap.size());self.origin=QPoint();self.band=QRubberBand(QRubberBand.Shape.Rectangle,self)
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.origin=event.position().toPoint();self.band.setGeometry(QRect(self.origin,self.origin));self.band.show()
    def mouseMoveEvent(self,event):
        if event.buttons() & Qt.MouseButton.LeftButton:self.band.setGeometry(QRect(self.origin,event.position().toPoint()).normalized().intersected(self.rect()))

class ImageRegionDialog(QDialog):
    def __init__(self,path,parent=None):
        super().__init__(parent);self.setWindowTitle('Imagen de referencia · Marca una zona si lo necesitas');self.region=None
        reader=QImageReader(str(path));size=reader.size()
        if not size.isValid() or size.width()*size.height()>20_000_000:raise ValueError('Imagen no válida o demasiado grande.')
        pixmap=QPixmap(str(path));self.original=pixmap.size()
        if pixmap.isNull() or pixmap.width()*pixmap.height()>20_000_000:raise ValueError('Imagen no válida o demasiado grande.')
        display=pixmap.scaled(700,410,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
        layout=QVBoxLayout(self);layout.addWidget(QLabel('Arrastra sobre la zona donde quieres el cambio, o utiliza la imagen completa.'))
        self.image=RegionLabel(display);layout.addWidget(self.image)
        buttons=QDialogButtonBox();whole=buttons.addButton('Imagen completa',QDialogButtonBox.ButtonRole.AcceptRole);marked=buttons.addButton('Usar zona marcada',QDialogButtonBox.ButtonRole.ActionRole);buttons.addButton(QDialogButtonBox.StandardButton.Cancel);whole.clicked.connect(self.accept);marked.clicked.connect(self.choose_region);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def choose_region(self):
        rectangle=self.image.band.geometry()
        if not self.image.band.isVisible() or rectangle.width()<8 or rectangle.height()<8:return
        sx=self.original.width()/self.image.width();sy=self.original.height()/self.image.height()
        x,y=round(rectangle.x()*sx),round(rectangle.y()*sy);w=min(round(rectangle.width()*sx),self.original.width()-x);h=min(round(rectangle.height()*sy),self.original.height()-y)
        self.region=[x,y,w,h];self.accept()
