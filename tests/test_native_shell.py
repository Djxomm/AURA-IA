import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication,QMainWindow
from PySide6.QtGui import QFontDatabase,QFont
from agente_ia.config import AppSettings
from agente_ia.native_shell import build_shell
from agente_ia.native_settings import SettingsHub
from agente_ia.chat_controls import ChatControls
from agente_ia.floating_companion import FloatingCompanion
from agente_ia.hardware_profile import recommended_settings

class Store:
 def __init__(self,path):self.settings=AppSettings(workspace_path=str(path))
 def get_settings(self):return self.settings
 def save_settings(self,s):self.settings=s

class ShellOwner(QMainWindow):
 def __init__(self,path):
  super().__init__();self.store=Store(path);self.prefs={};self.busy=False;self.calls=[];self.client=SimpleNamespace(model=path/'qwen2.5-coder-1.5b-instruct-q4_k_m.gguf',auto_context=True);self.client.model.touch();self.floating=SimpleNamespace(show=lambda:self.calls.append('floating'),setVisible=lambda visible:self.calls.append(('visible',visible)))
 def save_pref(self,key,value):self.prefs[key]=value
 def refresh_chat_controls(self):self.chat_controls.refresh(self.client.model,[self.client.model],self.store.get_settings().thinking_effort)

for method in ['new_chat','project','open_aurax','open_resources','open_archives','open_sql','open_browser','skills_panel','terminal','changes','settings','voice_settings','memory_panel','filter_history','select_chat','select_model','browse_chat_model','select_effort','attach_chat_files','toggle_dictation','stop','send','speak','clear_cache']:
 setattr(ShellOwner,method,lambda self,*args,name=method:self.calls.append(name))

def app():
 application=QApplication.instance() or QApplication([])
 if Path('C:/Windows/Fonts/segoeui.ttf').is_file():QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
 from native_launcher import STYLE
 application.setStyleSheet(STYLE)
 return application

def test_native_shell_fits_small_screen_and_controls_are_in_composer(tmp_path):
 application=app();owner=ShellOwner(tmp_path);owner.resize(760,540);build_shell(owner,Path('agente_ia/static/assets'));owner.show();application.processEvents()
 owner.heading.setText('Una conversación con un título muy largo '*6);application.processEvents()
 assert owner.width()==760
 assert owner.chat_controls.parentWidget().objectName()=='composer'
 assert owner.send_button.geometry().right()<=owner.send_button.parentWidget().width()
 owner.busy=False;owner.send_button.click();assert owner.calls[-1]=='send'
 owner.busy=True;owner.send_button.click();assert owner.calls[-1]=='stop'
 owner.close();owner.deleteLater();application.processEvents()

def test_settings_recommendations_save_actual_values(tmp_path,monkeypatch):
 application=app();owner=ShellOwner(tmp_path);build_shell(owner,Path('agente_ia/static/assets'));monkeypatch.setattr('agente_ia.native_settings.hardware_info',lambda:{'cpu':'Test CPU','cores':4,'logical':8,'ram_gib':16})
 dialog=SettingsHub(owner);assert dialog.sections.count()==7;dialog.recommend();dialog.effort.setCurrentIndex(2);dialog.apply()
 assert owner.store.get_settings().num_thread==4
 assert owner.store.get_settings().num_ctx==4096
 assert owner.store.get_settings().max_predict_tokens==0
 assert owner.store.get_settings().thinking_effort=='profundo'
 assert owner.prefs['intro'] is True
 owner.close();owner.deleteLater();application.processEvents()

def test_companion_alpha_and_animation_only_when_active(tmp_path):
 application=app();owner=ShellOwner(tmp_path);build_shell(owner,Path('agente_ia/static/assets'));pet=FloatingCompanion(owner)
 assert not pet.sprite.isNull() and pet.sprite.hasAlphaChannel()
 assert not pet.timer.isActive()
 pet.show();application.processEvents();pet.update_state(True,'Trabajando');assert pet.timer.isActive()
 owner.prefs['animations']=False;pet.update_state(True,'Trabajando');assert not pet.timer.isActive()
 owner.prefs['animations']=True;pet.update_state(True,'Trabajando');assert pet.timer.isActive()
 pet.set_attention('Revisar cambios');assert 'Revisar' in pet.toolTip()
 pet.update_state(False,'Listo');assert not pet.timer.isActive()
 pet.open();assert 'open_aurax' in owner.calls
 pet.hide_safe();assert owner.prefs['floating'] is False
 pet.close();owner.close();pet.deleteLater();owner.deleteLater();application.processEvents()

def test_hardware_profile_stays_small_on_legacy_machine():
 settings=recommended_settings({'cores':2,'logical':4,'ram_gib':8})
 assert settings['num_thread']==2 and settings['num_ctx']==2048

def test_coder_toolbars_keep_actions_accessible_at_small_width(tmp_path):
 application=app();owner=ShellOwner(tmp_path)
 from agente_ia.aurax_workspace import AuraxWorkspace
 from PySide6.QtWidgets import QToolButton
 workspace=AuraxWorkspace(owner,tmp_path);workspace.resize(400,560);workspace.show();application.processEvents()
 assert workspace.width()<=400
 assert [a.text() for a in workspace.file_toolbar.actions()]==['Proyecto','Nuevo','Guardar','Adjuntar a AURAX','Proyecto web']
 workspace.file_toolbar.actions()[0].trigger();assert owner.calls[-1]=='project'
 extension=workspace.file_toolbar.findChild(QToolButton,'qt_toolbar_ext_button')
 assert extension is not None and extension.isVisible()
 workspace.close();owner.close();workspace.deleteLater();owner.deleteLater();application.processEvents()
