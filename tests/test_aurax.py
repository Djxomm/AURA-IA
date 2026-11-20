import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication
from native_launcher import Window

def make(tmp_path):
 app=QApplication.instance() or QApplication([]);w=Window(tmp_path/'state');w.open_aurax();return app,w,w.aurax

def cleanup(w):
 for i in range(w.aurax.tabs.count()):w.aurax.tabs.widget(i).document().setModified(False)
 w.close();w.store.close();w.memory.close()

def test_aurax_is_visible_and_save_requires_review(tmp_path,monkeypatch):
 app,w,p=make(tmp_path);assert w.mode.currentIndex()==1;assert w.aurax_dock is not None
 editor=p.open_editor('programa.py','print(42)\n',None);monkeypatch.setattr(p,'review',lambda *args:False);assert not p.save_current();assert not (p.workspace.root/'programa.py').exists()
 monkeypatch.setattr(p,'review',lambda *args:True);assert p.save_current();assert (p.workspace.root/'programa.py').read_text()=='print(42)\n';assert w.store.list_changes(w.sid)[0]['status']=='applied';cleanup(w)

def test_aurax_detects_external_edits_and_restricts_paths(tmp_path,monkeypatch):
 app,w,p=make(tmp_path);target=p.workspace.root/'a.py';target.write_text('original');p.open_path(str(target));p.tabs.currentWidget().setPlainText('edited');target.write_text('external');errors=[];monkeypatch.setattr(p,'message',errors.append);monkeypatch.setattr(p,'review',lambda *args:True);assert not p.save_current();assert target.read_text()=='external';p.open_path(str(tmp_path/'outside.py'));assert errors;cleanup(w)

def test_aurax_attaches_saved_files_to_agent_request(tmp_path):
 app,w,p=make(tmp_path);target=p.workspace.root/'a.py';target.write_text('print(1)');p.open_path(str(target));p.attach();assert w.attached_files==['a.py'];cleanup(w)


def test_json_tool_fence_is_recognized_but_examples_and_unknown_tools_are_not():
 from agente_ia.tools import parse_xml_tool_calls
 text='```json\n{"name":"create_file","arguments":{"path":"a.py","content":"print(1)"}}\n```'
 clean,calls=parse_xml_tool_calls(text);assert clean=='' and calls[0]['name']=='create_file'
 assert parse_xml_tool_calls('Ejemplo: '+text)[1]==[]
 assert parse_xml_tool_calls('```json\n{"name":"run_shell","arguments":{"command":"x"}}\n```')[1]==[]


def test_ai_code_opens_as_unsaved_proposal(tmp_path,monkeypatch):
 from PySide6.QtWidgets import QInputDialog
 app,w,p=make(tmp_path);w.last_answer='```python\ndef sumar(a,b):\n    return a+b\n```';monkeypatch.setattr(QInputDialog,'getText',lambda *args,**kwargs:('suma.py',True));p.import_response();assert p.tabs.currentWidget().document().isModified();assert not (p.workspace.root/'suma.py').exists();cleanup(w)


def test_cpp_and_inno_commands_require_approval(tmp_path,monkeypatch):
 from PySide6.QtWidgets import QMessageBox
 app,w,p=make(tmp_path)
 p.runtime=tmp_path/'runtime'
 for tool in ['herramientas/w64devkit/bin/g++.exe','herramientas/inno/ISCC.exe']:
  path=p.runtime/tool;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'not executed')
 for relative,kind in [('programa.cpp','build'),('instalador.iss','installer')]:
  target=p.workspace.root/relative;target.write_text('test');p.open_path(str(target))
  calls=[]
  monkeypatch.setattr(QMessageBox,'question',lambda *args:calls.append(args) or QMessageBox.StandardButton.No)
  p.run(kind)
  assert calls and p.process.state()==p.process.ProcessState.NotRunning
 cleanup(w)
