"""A small native database panel, loaded only when requested."""
import csv
import re
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from .sql_manager import ConnectionConfig, MOTORS, PORTS, SqlManager, backup_sqlite, safe_error


class SqlJob(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, config, action, kwargs, parent):
        super().__init__(parent)
        self.config, self.action, self.kwargs = config, action, kwargs

    def run(self):
        try:
            if self.action == 'backup':
                result = {'backup': backup_sqlite(self.config.database, self.kwargs['destination'])}
            else:
                result = SqlManager(self.config).perform(self.action, **self.kwargs)
            self.result.emit(result)
        except Exception as error:
            self.failed.emit(safe_error(error, self.config))


def csv_value(value):
    if isinstance(value, str) and value.startswith(('=', '+', '-', '@', '\t', '\r')):
        return "'" + value
    return '' if value is None else value


class SqlWindow(QMainWindow):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner, self.config, self.job, self.result_data = owner, None, None, None
        self.schema_data = None
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle('AURA · Bases de datos SQL')
        self.resize(1080, 740)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        title = QLabel('Bases de datos · Conecta, consulta y administra')
        layout.addWidget(title)
        form = QFormLayout()
        self.form = form
        self.motor = QComboBox()
        self.motor.addItems(MOTORS)
        form.addRow('Motor', self.motor)
        self.host = QLineEdit('localhost')
        form.addRow('Servidor', self.host)
        database_row = QWidget()
        row = QHBoxLayout(database_row)
        row.setContentsMargins(0, 0, 0, 0)
        self.database = QLineEdit()
        row.addWidget(self.database)
        self.browse = QPushButton('Buscar archivo…')
        self.browse.clicked.connect(self.choose_database)
        row.addWidget(self.browse)
        form.addRow('Base / servicio / DSN', database_row)
        self.user = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow('Usuario', self.user)
        form.addRow('Contraseña', self.password)
        layout.addLayout(form)
        advanced_toggle = QPushButton('Mostrar ajustes avanzados')
        self.advanced_toggle = advanced_toggle
        advanced_toggle.setCheckable(True)
        self.advanced = QWidget()
        advanced_form = QFormLayout(self.advanced)
        self.advanced_form = advanced_form
        self.port = QSpinBox()
        self.port.setRange(0, 65535)
        self.port.setSpecialValueText('Automático')
        self.driver = QLineEdit('ODBC Driver 18 for SQL Server')
        self.tls = QCheckBox('Conexión cifrada y certificado verificado')
        self.tls.setChecked(True)
        advanced_form.addRow('Puerto (0 = predeterminado)', self.port)
        advanced_form.addRow('Controlador SQL Server', self.driver)
        advanced_form.addRow(self.tls)
        self.advanced.hide()
        advanced_toggle.toggled.connect(self.advanced.setVisible)
        advanced_toggle.toggled.connect(lambda checked: advanced_toggle.setText('Ocultar ajustes avanzados' if checked else 'Mostrar ajustes avanzados'))
        layout.addWidget(advanced_toggle)
        layout.addWidget(self.advanced)
        controls = QHBoxLayout()
        self.connect_button = QPushButton('Conectar')
        self.disconnect_button = QPushButton('Desconectar')
        self.disconnect_button.setEnabled(False)
        self.connect_button.clicked.connect(self.connect_database)
        self.disconnect_button.clicked.connect(self.disconnect_database)
        controls.addWidget(self.connect_button)
        controls.addWidget(self.disconnect_button)
        refresh = QPushButton('Actualizar tablas')
        refresh.clicked.connect(self.refresh_catalog)
        controls.addWidget(refresh)
        self.schemas = QComboBox()
        self.schemas.setPlaceholderText('Esquema')
        self.schemas.activated.connect(self.refresh_catalog)
        controls.addWidget(self.schemas)
        self.tables = QComboBox()
        self.tables.setPlaceholderText('Tabla')
        self.tables.activated.connect(self.inspect_table)
        controls.addWidget(self.tables, 1)
        layout.addLayout(controls)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        split = QSplitter(Qt.Orientation.Vertical)
        self.query = QPlainTextEdit()
        self.query.setPlaceholderText('Escribe una consulta SQL o pulsa Pedir ayuda a AURAX…')
        split.addWidget(self.query)
        self.grid = QTableWidget()
        self.grid.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.grid.setAlternatingRowColors(True)
        self.grid.setStyleSheet('QTableWidget{background:#0b1829;alternate-background-color:#142238;color:#e4eaf4;gridline-color:#26374e;selection-background-color:#2563eb;selection-color:white;} QHeaderView::section{background:#16273c;color:#e4eaf4;padding:6px;border:1px solid #26374e;}')
        split.addWidget(self.grid)
        split.setSizes([120, 200])
        layout.addWidget(split, 1)
        actions = QHBoxLayout()
        self.changes = QCheckBox('Permitir cambios')
        self.changes.setToolTip('INSERT, UPDATE, DELETE y cambios de estructura requieren confirmación. Usa una cuenta con permisos apropiados.')
        actions.addWidget(self.changes)
        self.action_buttons = []
        for label, callback in [('Ejecutar', self.execute), ('Pedir ayuda a AURAX', self.ask_aura), ('Usar SQL de AURA', self.import_query), ('Exportar CSV', self.export_csv), ('Respaldo SQLite', self.backup)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            self.action_buttons.append(button)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.status = QLabel('Sin conexión. Las contraseñas solo permanecen en esta sesión.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.motor.currentTextChanged.connect(self.motor_changed)
        self.motor_changed(self.motor.currentText())

    def motor_changed(self, motor):
        sqlite = motor == 'SQLite'
        self.browse.setVisible(sqlite)
        for field in (self.host, self.user, self.password):
            field.setEnabled(not sqlite)
        self.port.setValue(0)
        self.form.setRowVisible(self.host, motor not in {'SQLite', 'ODBC / DSN'})
        self.form.setRowVisible(self.user, not sqlite)
        self.form.setRowVisible(self.password, not sqlite)
        self.advanced_toggle.setVisible(not sqlite)
        self.advanced_form.setRowVisible(self.driver, motor == 'SQL Server')
        self.advanced_form.setRowVisible(self.port, motor not in {'SQLite', 'ODBC / DSN'})
        self.advanced_form.setRowVisible(self.tls, motor not in {'SQLite', 'ODBC / DSN'})
        if sqlite:
            self.advanced_toggle.setChecked(False)
            self.advanced.hide()
        self.driver.setEnabled(motor == 'SQL Server')
        self.tls.setEnabled(motor not in {'SQLite', 'ODBC / DSN'})
        self.hint.setText({'SQLite': 'Selecciona un archivo existente. Puedes crear un respaldo antes de modificarlo.', 'SQL Server': 'Conecta con SQL Server y Express mediante un controlador ODBC de Windows. Usuario vacío utiliza tu cuenta de Windows.', 'Oracle': 'Oracle usa el controlador incluido en modo Thin. Para versiones antiguas usa ODBC con un cliente compatible.', 'ODBC / DSN': 'Escribe un DSN configurado en ODBC de 64 bits en Windows. Su controlador define cifrado, versiones y permisos.'}.get(motor, 'Introduce el servidor, base de datos y cuenta. Se verificará el certificado de la conexión cifrada.'))

    def choose_database(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Seleccionar base SQLite', '', 'Bases SQLite (*.db *.sqlite *.sqlite3);;Todos los archivos (*)')
        if path:
            self.database.setText(path)

    def connect_database(self):
        if self.job:
            return
        config = ConnectionConfig(self.motor.currentText(), self.host.text().strip(), self.port.value(), self.database.text().strip(), self.user.text().strip(), self.password.text(), self.driver.text().strip(), self.tls.isChecked())
        self.config = config
        self.password.clear()
        self.changes.setChecked(False)
        self.launch('catalog')

    def disconnect_database(self):
        if self.job:
            return
        self.config = None
        self.password.clear()
        self.schemas.clear()
        self.tables.clear()
        self.grid.clear()
        self.grid.setRowCount(0)
        self.query.clear()
        self.result_data = None
        self.schema_data = None
        self.disconnect_button.setEnabled(False)
        self.status.setText('Desconectado. Credenciales de sesión eliminadas del panel.')

    def launch(self, action, **kwargs):
        if self.job or not self.config:
            return
        self.status.setText('Trabajando… ' + {'catalog': 'consultando las tablas', 'columns': 'leyendo la estructura', 'query': 'ejecutando la consulta', 'backup': 'generando y verificando el respaldo'}[action])
        self.set_busy(True)
        job = SqlJob(self.config, action, kwargs, self)
        self.job = job
        job.result.connect(self.received)
        job.failed.connect(self.failed)
        job.finished.connect(self.finished)
        job.start()

    def set_busy(self, busy):
        for widget in [self.connect_button, self.disconnect_button, self.schemas, self.tables, self.motor, self.database, self.host, self.user, self.password, self.changes, *self.action_buttons]:
            widget.setEnabled(not busy)
        if not busy:
            self.disconnect_button.setEnabled(self.config is not None)
            for field in (self.host, self.user, self.password):
                field.setEnabled(self.motor.currentText() != 'SQLite')

    def finished(self):
        job = self.job
        self.job = None
        if job:
            job.deleteLater()
        self.set_busy(False)

    def failed(self, message):
        self.status.setText('No se completó la operación: ' + message)

    def received(self, data):
        if 'tables' in data:
            self.schema_data = None
            self.result_data = None
            self.schemas.clear()
            self.schemas.addItems(data['schemas'])
            if data.get('schema'):
                self.schemas.setCurrentText(data['schema'])
            self.tables.clear()
            self.tables.addItems(data['tables'])
            if data['tables']:
                self.tables.setCurrentIndex(0)
            self.status.setText(f"Conectado · {data['motor']} {data['version']} · {len(data['tables'])} tablas mostradas. Usa una cuenta de solo lectura para restringir permisos en el servidor.")
        elif 'backup' in data:
            self.status.setText('Respaldo SQLite verificado: ' + data['backup'])
        elif 'table' in data:
            self.schema_data = data
            self.result_data = None
            self.show_grid(['Columna', 'Tipo', 'Permite NULL'], data['columns'])
            self.status.setText('Estructura de ' + data['table'] + ' · no se han leído sus datos.')
        else:
            self.result_data = data
            self.show_grid(data['columns'], data['rows'])
            self.status.setText(f"Consulta terminada · {len(data['rows'])} filas mostradas · afectadas: {data['affected']}" + (' · resultado recortado' if data['truncated'] else '') + (' · cambios confirmados' if data['committed'] else ' · transacción cerrada sin confirmar cambios'))

    def show_grid(self, columns, rows):
        self.grid.clear()
        self.grid.setColumnCount(len(columns))
        self.grid.setRowCount(len(rows))
        self.grid.setHorizontalHeaderLabels(columns)
        for y, row in enumerate(rows):
            for x, value in enumerate(row):
                self.grid.setItem(y, x, QTableWidgetItem('NULL' if value is None else str(value)))
        self.grid.resizeColumnsToContents()
        for column in range(len(columns)):
            self.grid.setColumnWidth(column, min(350, self.grid.columnWidth(column)))

    def refresh_catalog(self):
        self.launch('catalog', schema=self.schemas.currentText() or None)

    def inspect_table(self):
        if self.tables.currentText():
            self.launch('columns', schema=self.schemas.currentText() or None, table=self.tables.currentText())

    def execute(self):
        if not self.config:
            self.status.setText('Primero conecta una base de datos.')
            return
        sql = self.query.toPlainText().strip()
        if not sql:
            return
        from .sql_manager import validate_statement
        try:
            validate_statement(sql, self.changes.isChecked())
        except ValueError as error:
            self.status.setText(str(error))
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle('Revisar consulta SQL')
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(f'Motor: {self.config.motor}\nBase: {self.config.database}\n\n' + ('Se permitirán cambios. DDL y algunos motores pueden confirmar cambios sin posibilidad de deshacer. Conserva un respaldo.\n\n' if self.changes.isChecked() else 'Modo consultas. Los permisos de la cuenta del servidor son la protección definitiva.\n\n') + sql[:12000])
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if dialog.exec() == QMessageBox.StandardButton.Ok:
            self.launch('query', sql=sql, allow_changes=self.changes.isChecked())

    def ask_aura(self):
        schema = '\n'.join(' | '.join(row) for row in (self.schema_data or {}).get('columns', [])[:30])
        self.owner.open_aurax()
        self.owner.input.setPlainText(f'Ayúdame a preparar SQL para {self.config.motor if self.config else self.motor.currentText()}. Tabla seleccionada: {self.tables.currentText()}.\nEstructura seleccionada:\n{schema[:4000]}\nConsulta a revisar:\n{self.query.toPlainText()[:5000]}\nDevuelve una propuesta SQL y explica su efecto. No ejecutes cambios.')
        self.owner.raise_()
        self.status.setText('Borrador enviado al cuadro de AURAX. Revisa y pulsa Enviar; no se ejecutó SQL.')

    def import_query(self):
        match = re.search(r'```sql\s*\n(.*?)```', self.owner.last_answer or '', re.S | re.I)
        if match:
            self.query.setPlainText(match.group(1))
            self.status.setText('Propuesta cargada. Revisa el SQL antes de ejecutarlo.')
        else:
            self.status.setText('La última respuesta de AURA no contiene un bloque SQL.')

    def export_csv(self):
        if not self.result_data:
            self.status.setText('Ejecuta una consulta antes de exportar.')
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Exportar las filas mostradas', '', 'CSV (*.csv)')
        if path:
            try:
                with open(path, 'w', encoding='utf-8-sig', newline='') as stream:
                    writer = csv.writer(stream)
                    writer.writerow([csv_value(v) for v in self.result_data['columns']])
                    writer.writerows([[csv_value(v) for v in row] for row in self.result_data['rows']])
                self.status.setText('Exportadas las filas mostradas. Celdas limitadas a 2000 caracteres; no es un respaldo completo.')
            except OSError as error:
                self.status.setText(str(error))

    def backup(self):
        if not self.config or self.config.motor != 'SQLite':
            self.status.setText('Este botón respalda SQLite. Para otros motores prepara el respaldo nativo con AURAX y las herramientas del servidor.')
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Crear un respaldo nuevo', '', 'SQLite (*.db)')
        if path:
            self.launch('backup', destination=path)

    def closeEvent(self, event):
        if self.job:
            self.status.setText('Espera a que termine la operación antes de cerrar esta ventana.')
            event.ignore()
            return
        self.config = None
        self.password.clear()
        super().closeEvent(event)
