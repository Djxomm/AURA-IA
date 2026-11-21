import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import threading
from types import SimpleNamespace
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMainWindow,QPlainTextEdit,QCheckBox,QComboBox,QToolButton,QWidget
from PySide6.QtTest import QTest
from agente_ia.storage import Storage
from agente_ia.config import AppSettings
from native_launcher import Window,Bus


def test_chat_execute_routes_to_real_tool_without_model(tmp_path,monkeypatch):
    import sys
    from agente_ia import project_actions
    (tmp_path/'main.py').write_text('print("DESDE CHAT")')
    monkeypatch.setattr(project_actions,'plan',lambda *args:[project_actions.Command(Path(sys.executable),['-I',str(tmp_path/'main.py')],tmp_path,'Ejecutar')])
    application=QApplication.instance() or QApplication([])
    class Owner(Window):
        def __init__(self):
            QMainWindow.__init__(self);self.data=tmp_path;self.store=Storage(tmp_path/'state.db');self.store.save_settings(AppSettings(workspace_path=str(tmp_path)))
            self.input=QPlainTextEdit();self.input.setPlainText('ejecuta main.py');self.busy=False;self.warming=False;self.sid=None;self.temporary=QCheckBox();self.mode=QComboBox();self.mode.addItems(['Chat','AURAX'])
            self.prefs={};self.items=[];self.chat_controls=QWidget();self.send_button=QToolButton();self.attached_files=[];self.aurax=None
            self.client=SimpleNamespace(model=Path('unused.gguf'),first_text=None,effective_context=None);self.engine=SimpleNamespace();self.memory=SimpleNamespace(search=lambda *args:[])
            self.bus=Bus(self);self.received=[];self.bus.event.connect(lambda kind,data:self.received.append((kind,data)))
        def open_aurax(self):self.mode.setCurrentIndex(1)
        def render(self):pass
        def refresh_history(self):pass
        def error(self,message):raise AssertionError(message)
    owner=Owner();owner.send()
    for _ in range(250):
        application.processEvents()
        if any(kind in ('done','failed') for kind,data in owner.received):break
        QTest.qWait(20)
    final=[(kind,data) for kind,data in owner.received if kind in ('done','failed')]
    assert final and final[-1][0]=='done' and 'DESDE CHAT' in final[-1][1]
    owner.store.close();owner.deleteLater();application.processEvents()
