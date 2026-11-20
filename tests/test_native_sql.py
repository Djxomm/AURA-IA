import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sqlite3
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from native_launcher import Window
from agente_ia.native_sql import csv_value


def finish_job(panel):
    loop = QEventLoop()
    if panel.job:
        panel.job.finished.connect(loop.quit)
        QTimer.singleShot(10000, loop.quit)
        loop.exec()
    assert panel.job is None


def test_sql_panel_connects_and_requires_query_confirmation(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    source = tmp_path/'test.db'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE products(name TEXT)')
        db.execute("INSERT INTO products VALUES('Agua')")
    w = Window(tmp_path/'state')
    w.open_sql()
    panel = w.sql_panel
    assert not panel.advanced.isVisible()
    assert not panel.host.isVisible()
    panel.database.setText(str(source))
    panel.connect_database()
    finish_job(panel)
    assert panel.tables.currentText() == 'products', panel.status.text()
    panel.query.setPlainText('SELECT * FROM products')
    monkeypatch.setattr(QMessageBox, 'exec', lambda *args: QMessageBox.StandardButton.Cancel)
    panel.execute()
    assert panel.job is None and panel.result_data is None
    monkeypatch.setattr(QMessageBox, 'exec', lambda *args: QMessageBox.StandardButton.Ok)
    panel.execute()
    finish_job(panel)
    assert panel.result_data['rows'] == [['Agua']]
    panel.inspect_table()
    finish_job(panel)
    assert panel.schema_data['columns'][0][0] == 'name'
    assert panel.result_data is None
    panel.disconnect_database()
    assert panel.config is None
    panel.close()
    app.processEvents()
    w.close();w.store.close();w.memory.close()


def test_csv_formula_is_not_exported_as_executable_spreadsheet_formula():
    assert csv_value('=HYPERLINK("https://example.com")').startswith("'")
    assert csv_value('+1+1').startswith("'")
    assert csv_value('Agua') == 'Agua'


def test_assistant_only_receives_schema_not_rows_or_credentials(tmp_path):
    app = QApplication.instance() or QApplication([])
    w = Window(tmp_path/'state');w.open_sql();panel = w.sql_panel
    panel.received({'columns':['secret'],'rows':[['customer-private-data']],'affected':1,'truncated':False,'committed':False})
    panel.ask_aura()
    assert 'customer-private-data' not in w.input.toPlainText()
    panel.close();app.processEvents();w.close();w.store.close();w.memory.close()

