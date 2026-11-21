import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from agente_ia.message_input import MessageInput

def test_enter_submits_shift_enter_inserts_and_input_grows():
 app=QApplication.instance() or QApplication([]);box=MessageInput();box.resize(400,38);box.show();app.processEvents();events=[];box.submit_requested.connect(lambda:events.append(box.toPlainText()));initial=box.height()
 box.setPlainText('Hola');QTest.keyClick(box,Qt.Key.Key_Return);assert events==['Hola'] and box.toPlainText()=='Hola'
 QTest.keyClick(box,Qt.Key.Key_Return,Qt.KeyboardModifier.ShiftModifier);app.processEvents();assert '\n' in box.toPlainText() and len(events)==1
 box.setPlainText('Texto largo '*80);app.processEvents();assert initial<box.height()<=120
 box.setPlainText('\n'.join(['Línea']*5));app.processEvents();assert initial<box.height()<=154
 box.clear();app.processEvents();assert box.height()==initial
 QTest.keyClick(box,Qt.Key.Key_Return);assert len(events)==1
 box.close();box.deleteLater();app.processEvents()
