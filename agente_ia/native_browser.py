"""On-demand native browser with explicit, temporary certificate decisions."""
from urllib.parse import quote_plus

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView


def navigation_url(text):
    text = text.strip()
    if not text:
        return None
    if '://' not in text:
        text = ('https://' + text) if '.' in text or text.startswith('localhost') else ('https://www.google.com/search?q=' + quote_plus(text))
    url = QUrl(text)
    if not url.isValid() or url.scheme().lower() not in {'https', 'http'} or not url.host() or url.userInfo():
        raise ValueError('Introduce una dirección HTTP o HTTPS sin contraseñas en la dirección.')
    return url


def decide_certificate(error, ask):
    """Never accept non-overridable failures or make a persistent exception."""
    if not error.isOverridable():
        error.rejectCertificate()
        return False
    accepted = bool(ask(error.url().host(), error.description()))
    if accepted:
        error.acceptCertificate()
    else:
        error.rejectCertificate()
    return accepted


class BrowserWindow(QMainWindow):
    def __init__(self, owner=None):
        super().__init__(owner)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle('AURA · Explorador de Internet')
        self.resize(1100, 740)
        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        bar = QHBoxLayout()
        self.view = QWebEngineView(self)
        # An unnamed profile keeps cookies, storage and certificate decisions in memory.
        self.profile = QWebEngineProfile(self)
        self.page = QWebEnginePage(self.profile, self.view)
        self.view.setPage(self.page)
        for label, callback in [('Atrás', self.view.back), ('Adelante', self.view.forward), ('Recargar', self.view.reload), ('Detener', self.view.stop)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            bar.addWidget(button)
        self.address = QLineEdit()
        self.address.setPlaceholderText('Dirección del sitio o búsqueda…')
        self.address.returnPressed.connect(self.navigate)
        bar.addWidget(self.address, 1)
        go = QPushButton('Ir')
        go.clicked.connect(self.navigate)
        bar.addWidget(go)
        layout.addLayout(bar)
        self.status = QLabel('Navegación privada · los datos de sesión se eliminan al cerrar.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addWidget(self.view, 1)
        self.page.certificateError.connect(self.certificate_error)
        self.page.featurePermissionRequested.connect(lambda origin, feature: self.page.setFeaturePermission(origin, feature, QWebEnginePage.PermissionPolicy.PermissionDeniedByUser))
        self.profile.downloadRequested.connect(lambda item: item.cancel())
        self.view.urlChanged.connect(self.url_changed)
        self.view.loadProgress.connect(lambda progress: self.status.setText(f'Cargando sitio… {progress}%'))
        self.view.loadFinished.connect(lambda ok: self.status.setText(('Sitio cargado · ' if ok else 'No se pudo cargar · ') + ('HTTP sin cifrar' if self.view.url().scheme() == 'http' else 'HTTPS; consulta los avisos de certificado')))
        self.view.setHtml('<html><body style="background:#0b1424;color:#e4eaf4;font-family:Segoe UI;padding:40px"><h1>Explorador AURA</h1><p>Escribe una dirección para comenzar.</p></body></html>')

    def navigate(self):
        try:
            url = navigation_url(self.address.text())
            if url:
                self.view.setUrl(url)
        except ValueError as error:
            QMessageBox.information(self, 'Dirección', str(error))

    def url_changed(self, url):
        if url.scheme() in {'https', 'http'}:
            self.address.setText(url.toString())

    def certificate_error(self, error):
        if not error.isOverridable():
            error.rejectCertificate()
            self.status.setText('Certificado rechazado: este error no permite una excepción. ' + error.description())
            return
        error.defer()
        # Keep the deferred request alive until the dialog has been answered.
        QTimer.singleShot(0, lambda request=error: decide_certificate(request, self.ask_certificate))

    def ask_certificate(self, host, description):
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle('Certificado no válido · decisión bajo tu responsabilidad')
        dialog.setText(f'No se puede verificar la identidad de {host}.')
        dialog.setInformativeText(description + '\n\nLa conexión podría ser interceptada. Evita introducir contraseñas o datos de pago. La excepción dura esta sesión del explorador; al cerrar se elimina.')
        enter = dialog.addButton('Entrar bajo mi responsabilidad', QMessageBox.ButtonRole.AcceptRole)
        cancel = dialog.addButton('No entrar', QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(cancel)
        dialog.setEscapeButton(cancel)
        dialog.exec()
        return dialog.clickedButton() is enter

    def closeEvent(self, event):
        self.view.stop()
        super().closeEvent(event)
