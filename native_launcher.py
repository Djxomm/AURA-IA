"""AURA 3 native desktop: Qt widgets, local subprocess inference, memory and voice."""
from __future__ import annotations
import argparse,asyncio,json,os,re,subprocess,sys,threading,time
from pathlib import Path
from PySide6.QtCore import Qt,Signal,QObject,QTimer,QUrl
from PySide6.QtGui import QIcon,QPixmap,QTextCursor,QFont
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QListWidget,QListWidgetItem,QTextBrowser,QPlainTextEdit,QComboBox,QSplitter,QDialog,QFormLayout,QLineEdit,QCheckBox,QSpinBox,QDoubleSpinBox,QFileDialog,QMessageBox,QDialogButtonBox,QTreeView,QScrollArea,QSlider,QDockWidget)
from PySide6.QtWidgets import QFileSystemModel
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from agente_ia.storage import Storage
from agente_ia.native_core import NativeClient,Memory,Dictation,spoken_text,conversation_prompt
from agente_ia.native_voice import VoiceKey,voices,synthesize
from agente_ia.agent import AgentEngine,ApprovalRegistry,ApprovalDecision
from agente_ia.skills import SkillStore
from agente_ia.aurax_workspace import AuraxWorkspace
from agente_ia.chat_controls import ChatControls
from agente_ia.native_shell import build_shell,icon
from agente_ia.native_settings import SettingsHub
from agente_ia.hardware_profile import hardware_info,recommended_settings
from agente_ia.chat_render import conversation_html
from agente_ia.floating_companion import FloatingCompanion as FloatingAssistant

ROOT=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent/'runtime'
ASSETS=Path(__file__).resolve().parent/'agente_ia/static/assets'
STYLE='''QWidget{background:#07101e;color:#e5edf9;font-family:Segoe UI;font-size:13px;} QMainWindow,QDialog{background:#07101e;} QPushButton{background:#10253a;border:1px solid #24506a;border-radius:8px;padding:10px 13px;} QPushButton:hover{background:#164052;border-color:#00d8e6;} QPushButton:pressed{background:#086578;} QPushButton:disabled{color:#8493a8;background:#14202c;} QLineEdit,QPlainTextEdit,QTextBrowser,QListWidget,QTreeView,QComboBox,QSpinBox,QDoubleSpinBox{background:#0b1829;border:1px solid #234258;border-radius:8px;padding:8px;selection-background-color:#126176;selection-color:white;} QListWidget::item{padding:9px;} QListWidget::item:selected{background:#16455a;color:white;} QLabel#brand{font-size:25px;font-weight:bold;color:#00e9f1;} QLabel#status{color:#91dce1;padding:6px;} QSplitter::handle{background:#183446;width:2px;} QCheckBox{padding:5px;} QScrollBar:vertical{background:#091524;width:10px;} QScrollBar::handle:vertical{background:#28566b;min-height:28px;border-radius:4px;}'''
STYLE += """
QWidget#iconRail{background:#060e1a;} QWidget#chatArea{background:#0b1424;} QLabel#sectionLabel{color:#99adc7;font-size:11px;padding-top:8px;} QToolButton{color:#dae7f8;background:transparent;border:none;border-radius:8px;padding:4px;} QToolButton:hover{background:#18344f;} QToolButton:focus{border:1px solid #8bd2ff;} QLineEdit:focus,QPlainTextEdit:focus,QComboBox:focus{border:1px solid #8bd2ff;} QToolButton#sendButton{background:#2878c6;border-radius:18px;} QToolButton#sendButton:hover{background:#246cb5;} QToolButton#localMenu{text-align:left;padding:10px;background:#102239;}

QWidget{background:#0b1424;color:#e4eaf4;}
QMainWindow,QDialog{background:#0b1424;}
QWidget#sidebar{background:#07101d;}
QWidget#sidebar QLabel{background:transparent;}
QWidget#sidebar QPushButton#navButton{background:transparent;border:none;text-align:left;border-radius:7px;padding:7px 10px;color:#c9d5e6;}
QWidget#sidebar QPushButton#navButton:hover{background:#16273c;color:#ffffff;}
QWidget#sidebar QPushButton#newChatButton{background:#152b45;border:1px solid #294563;text-align:left;padding:10px;}
QWidget#sidebar QListWidget{background:transparent;border:none;}
QWidget#sidebar QLineEdit{background:#0d1b2d;border:1px solid #24354d;}
QLabel#chatTitle{font-size:16px;font-weight:600;}
QLabel#status{color:#9cb3cf;font-size:12px;}
QTextBrowser#conversation{background:#0b1424;border:none;font-size:15px;padding:18px 22px;}
QWidget#composer{background:#142238;border:1px solid #2a3d58;border-radius:10px;}
QWidget#composer QPlainTextEdit{background:transparent;border:none;font-size:14px;padding:2px 8px;}
QWidget#composer QPushButton{background:transparent;border:none;padding:7px 10px;}
QWidget#composer QPushButton:hover{background:#213b59;}
QWidget#composer QPushButton#sendButton{background:#2563eb;color:white;border:none;border-radius:10px;padding:9px 18px;font-weight:600;}
QWidget#composer QPushButton#sendButton:hover{background:#3478f6;}
QWidget#composer QPushButton#sendButton:disabled{background:#21324b;color:#8295b2;}
QWidget#composer QCheckBox{background:transparent;font-size:12px;}
QLabel#footer{color:#8c9db6;font-size:11px;background:transparent;}
QSplitter::handle{background:#1b2a40;width:1px;}
"""
class Bus(QObject):event=Signal(str,object)
def btn(text,fn):
 b=QPushButton(text);b.clicked.connect(fn);return b

class StartupSplash(QWidget):
 """Loading animation shown before the main window, until the model is ready."""
 def __init__(self,owner,path):
  super().__init__(None,Qt.WindowType.SplashScreen|Qt.WindowType.FramelessWindowHint)
  self.owner=owner;self.setWindowTitle('Iniciando AURA');self.setWindowIcon(QIcon(str(ASSETS/'aura.ico')));self.resize(760,500);layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0);video=QVideoWidget();layout.addWidget(video);self.setStyleSheet('background:black;')
  self.audio=QAudioOutput(self);self.audio.setMuted(True);self.player=QMediaPlayer(self);self.player.setAudioOutput(self.audio);self.player.setVideoOutput(video);self.player.setLoops(QMediaPlayer.Loops.Infinite);self.player.setSource(QUrl.fromLocalFile(str(path)));area=QApplication.primaryScreen().availableGeometry();self.move(area.center()-self.rect().center())
 def begin(self):self.show();self.player.play()
 def release(self):self.player.stop();self.player.setSource(QUrl());self.hide();self.deleteLater()

class Window(QMainWindow):
 def __init__(self,data):
  super().__init__();self.data=Path(data).resolve();self.data.mkdir(parents=True,exist_ok=True);self.prefs_path=self.data/'native-settings.json'
  try:self.prefs=json.loads(self.prefs_path.read_text('utf-8'))
  except (OSError,ValueError):self.prefs={}
  existing_database=(self.data/'aura.db').exists();self.store=Storage(self.data/'aura.db');projects=self.data/'Proyectos';projects.mkdir(exist_ok=True)
  settings=self.store.get_settings()
  if not existing_database or not Path(settings.workspace_path).is_dir():self.store.save_settings(settings.model_copy(update={'workspace_path':str(projects),'tool_mode':'xml',**recommended_settings(hardware_info())}))
  self.memory=Memory(self.data/'memoria.db');self.skills=SkillStore(self.data/'skills');self.skills.install_defaults(ROOT/'skills')
  if (ROOT/'skills/reverse-engineer-anything/SKILL.md').is_file():self.skills.install_bundled(ROOT/'skills','reverse-engineer-anything')
  if (ROOT/'skills/blender-3d/SKILL.md').is_file():self.skills.install_bundled(ROOT/'skills','blender-3d')
  if (ROOT/'skills/impeccable/SKILL.md').is_file():self.skills.install_bundled(ROOT/'skills','impeccable')
  if (ROOT/'skills/control-pc/SKILL.md').is_file():self.skills.install_bundled(ROOT/'skills','control-pc')
  if (ROOT/'skills/android-adb-dev/SKILL.md').is_file():self.skills.install_bundled(ROOT/'skills','android-adb-dev')
  if (ROOT/'skills/kicad-diagramas/SKILL.md').is_file():self.skills.install_bundled(ROOT/'skills','kicad-diagramas')
  if (ROOT/'skills/video-diseno-studio/SKILL.md').is_file():self.skills.install_bundled(ROOT/'skills','video-diseno-studio')
  if (ROOT/'skills/entrenar-modelos-ia/SKILL.md').is_file():self.skills.install_bundled(ROOT/'skills','entrenar-modelos-ia')
  self.registry=ApprovalRegistry()
  self.client=NativeClient(ROOT,self.data/'nativo',self.prefs.get('model'));self.client.auto_context=self.prefs.get('auto_context',True);self.client.acceleration=self.prefs.get('acceleration','auto');self.engine=AgentEngine(self.store,self.client,self.registry,self.skills)
  self.dictation=Dictation(ROOT);self.bus=Bus();self.bus.event.connect(self.handle_event);self.busy=False;self.warming=False;self.sid=None;self.items=[];self.answer='';self.last_answer='';self.voice_process=None;self.dictating=False;self.live_conversation=False;self.voice_generation=0;self.voice_key=VoiceKey(self.data)
  self.setWindowTitle('AURA Â· Inteligencia Artificial â€” Escritorio');self.setWindowIcon(QIcon(str(ASSETS/'aura-icono-transparente.png')));self.resize(1180,760);self.setMinimumSize(760,540)
  build_shell(self,ASSETS)
  self.audio=QAudioOutput();self.player=QMediaPlayer();self.player.setAudioOutput(self.audio);self.audio.setVolume(self.prefs.get('volume',90)/100);self.player.playbackStateChanged.connect(self._on_voice_playback_changed)
  self.floating=FloatingAssistant(self)
  self.new_chat();self.refresh_history();self.timer=QTimer(self);self.timer.timeout.connect(self.progress);self.timer.start(300)
  self.startup=None;self.startup_finished=False;self.attached_files=[];self.aurax=None;self.aurax_dock=None;self.terminal_panel=None;self.terminal_dock=None;self.mode.currentIndexChanged.connect(lambda index:self.open_aurax() if index==1 else None);self.autonomous.toggled.connect(self.toggle_autonomous)
  from agente_ia.slash_palette import SlashPopup
  self.slash_popup=SlashPopup(self);self.input.popup=self.slash_popup;self.slash_popup.entry_chosen.connect(self._apply_slash_entry);self.input.textChanged.connect(self._update_slash_popup)
 def open_slash_palette(self):
  if self.busy or self.warming:return
  if not self.input.toPlainText().startswith('/'):self.input.setPlainText('/')
  self.input.setFocus();cursor=self.input.textCursor();cursor.movePosition(cursor.MoveOperation.End);self.input.setTextCursor(cursor);self._update_slash_popup()
 def _update_slash_popup(self):
  from agente_ia.slash_palette import build_slash_catalog,filter_slash_entries,list_workspace_mentions
  txt=self.input.toPlainText()
  entries=[]
  if txt.startswith('/') and ' ' not in txt and '\n' not in txt:
   entries=filter_slash_entries(build_slash_catalog(getattr(self,'skills',None)),txt)
  else:
   match=re.search(r'(?:^|\s)@([^\s]*)$',txt)
   if match:entries=list_workspace_mentions(self.store.get_settings().workspace_path,match.group(1))
  if not entries:self.slash_popup.hide();return
  self.slash_popup.set_entries(entries);pos=self.input.mapToGlobal(self.input.rect().topLeft());w=max(380,self.input.width());h=min(240,36*min(len(entries),7)+12);self.slash_popup.setGeometry(pos.x(),max(10,pos.y()-h-6),w,h);self.slash_popup.show()
 def _apply_slash_entry(self,entry):
  txt=self.input.toPlainText()
  if entry.kind=='file':
   rel=entry.payload['path'];new_txt=re.sub(r'(?:^|\s)@[^\s]*$',lambda m:(' ' if m.group(0).startswith(' ') else '')+'@'+rel+' ',txt)
   self.input.setPlainText(new_txt)
   if rel not in self.attached_files and len(self.attached_files)<4:self.attached_files.append(rel)
   self.status.setText('Archivo mencionado y adjuntado: '+rel)
  else:
   self.input.setPlainText(entry.command+' ')
  self.input.setFocus();cursor=self.input.textCursor();cursor.movePosition(cursor.MoveOperation.End);self.input.setTextCursor(cursor)
 def toggle_autonomous(self,enabled):
  s=self.store.get_settings()
  if bool(s.autonomous_mode)!=bool(enabled):self.store.save_settings(s.model_copy(update={'autonomous_mode':bool(enabled)}))
  if enabled and not self.busy:
   self.temporary.setChecked(False)
   if self.mode.currentIndex()!=1:self.open_aurax()
   self.status.setText('Modo constructor autÃ³nomo activo Â· edita, prueba y compila dentro del proyecto')
  elif not enabled and not self.busy:
   self.status.setText('Modo revisiÃ³n manual activo Â· pide aprobaciÃ³n antes de cada cambio o comando')
 def open_archives(self):
  from agente_ia.archive_tools import open_dialog
  open_dialog(self)
 def open_resources(self):
  from agente_ia.resource_panel import ResourcePanel
  dialog=ResourcePanel(self);dialog.exec()
 def open_sql(self):
  from agente_ia.native_sql import SqlWindow
  if (ROOT/'skills/bases-sql/SKILL.md').is_file():self.skills.install_bundled(ROOT/'skills','bases-sql')
  panel=getattr(self,'sql_panel',None)
  if panel is None:
   panel=SqlWindow(self);self.sql_panel=panel;panel.destroyed.connect(lambda:setattr(self,'sql_panel',None));panel.setWindowIcon(self.windowIcon())
  panel.show();panel.raise_();panel.activateWindow()
 def open_browser(self):
  from agente_ia.native_browser import BrowserWindow
  browser=BrowserWindow(self);browser.setWindowIcon(self.windowIcon());browser.show()
 def open_aurax(self):
  if not self.busy and not self.warming and not self.prefs.get('coder_profile_initialized',False):
   from agente_ia.hardware_profile import hardware_info
   from agente_ia.model_library import curate_proven_models,discover
   machine=hardware_info()
   if (machine.get('ram_gib') or 0)>=15 and machine.get('cores',1)>=4 and '1.5b' in self.client.model.name.lower():
    raw=[*(ROOT/'modelos').glob('*.gguf'),*[Path(p) for p in self.prefs.get('models',[]) if isinstance(p,str)],*discover(self.prefs.get('model_directories',['D:/IA/Modelos_AURA']))]
    curated=curate_proven_models(raw,extra_runs_dirs=[Path(d) for d in self.prefs.get('model_runs_dirs',[]) if isinstance(d,str) and Path(d).is_dir()])
    preferred=next((p for p in curated if '1.5b' not in p.name.lower()),None)
    if preferred:self.select_model(preferred)
   self.save_pref('coder_profile_initialized',True)

  if (ROOT/'skills/multilenguaje/SKILL.md').is_file():self.skills.install_bundled(ROOT/'skills','multilenguaje')
  if self.aurax is None:
   self.aurax=AuraxWorkspace(self,ROOT);self.aurax.attach_requested.connect(self.attach_aurax_file);self.aurax_dock=QDockWidget('QbitX Â· Agente y herramientas',self);self.aurax_dock.setWidget(self.aurax);self.aurax_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea|Qt.DockWidgetArea.BottomDockWidgetArea);compact=self.width()<self.centralWidget().minimumSizeHint().width()+self.aurax.minimumSizeHint().width()+12;previous=self.size();self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,self.aurax_dock)
   if compact:
    self.aurax_dock.setFloating(True);area=self.screen().availableGeometry();self.aurax_dock.resize(min(860,area.width()-40),min(620,area.height()-40));self.resize(previous)
  self.aurax_dock.show();self.aurax_dock.raise_()
  if self.mode.currentIndex()!=1:self.mode.setCurrentIndex(1)
  self.temporary.setChecked(False);self.input.setPlaceholderText('Pide a AURAX crear, revisar o corregir archivos del proyectoâ€¦')
 def attach_chat_files(self):
  if self.guarded():return
  root=Path(self.store.get_settings().workspace_path).resolve()
  paths,_=QFileDialog.getOpenFileNames(self,'Adjuntar archivos del proyecto',str(root),'Archivos (*)')
  for path in paths:
   target=Path(path).resolve()
   from agente_ia.image_evidence import IMAGE_SUFFIXES
   if target.suffix.lower() in IMAGE_SUFFIXES:
    try:
     from agente_ia.image_region import ImageRegionDialog
     if target.stat().st_size>20*1024**2:raise ValueError('La imagen supera 20 MB.')
     dialog=ImageRegionDialog(target,self)
     if dialog.exec():
      if not hasattr(self,'image_regions'):self.image_regions={}
      self.image_regions[str(target)]=dialog.region;self.attach_aurax_file(str(target))
     dialog.deleteLater()
    except (OSError,ValueError) as error:self.error(str(error))
    continue
   if not target.is_relative_to(root):self.error('Selecciona archivos dentro de la carpeta del proyecto. Puedes cambiarla en Proyecto y archivos.');continue
   self.attach_aurax_file(target.relative_to(root).as_posix())
 def attach_aurax_file(self,path):
  if path not in self.attached_files and len(self.attached_files)>=4:self.error('Adjunta hasta cuatro archivos por solicitud.');return
  if path not in self.attached_files:self.attached_files.append(path)
  self.open_aurax();self.status.setText('Adjuntos para AURAX: '+', '.join(self.attached_files));self.input.setFocus()
 def start(self):
  path=ASSETS/'aura-inicio.mp4'
  if self.prefs.get('intro',True) and path.is_file():
   self.startup=StartupSplash(self,path);self.startup.begin()
  else:self.finish_startup()
  QTimer.singleShot(0,self.prepare_model)
 def finish_startup(self):
  if self.startup_finished:return
  self.startup_finished=True;self.showNormal();self.input.setFocus()
  if self.prefs.get('floating',True):self.floating.show()
  splash=self.startup;self.startup=None
  if splash is not None:splash.release()
 def save_pref(self,key,value):self.prefs[key]=value;self.prefs_path.write_text(json.dumps(self.prefs,ensure_ascii=False,indent=2),'utf-8')
 def error(self,e):QMessageBox.warning(self,'AURA',str(e))
 def guarded(self):
  if self.busy or self.warming:self.error('DetÃ©n o espera la respuesta antes de cambiar esta configuraciÃ³n.');return True
  return False
 def dialog(self,title):
  d=QDialog(self);d.setWindowTitle(title);d.resize(760,560);outer=QVBoxLayout(d);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();layout=QVBoxLayout(body);scroll.setWidget(body);outer.addWidget(scroll);return d,layout
 def new_chat(self):
  if self.busy:return
  self.sid=None;self.items=[];self.heading.setText('Nueva conversaciÃ³n');self.render()
 def refresh_history(self):
  self.history.clear()
  for s in self.store.list_sessions(limit=200):
   item=QListWidgetItem(s['title']);item.setData(Qt.ItemDataRole.UserRole,s['id']);self.history.addItem(item)
  self.filter_history(self.search.text())
 def filter_history(self,text):
  for i in range(self.history.count()):self.history.item(i).setHidden(text.lower() not in self.history.item(i).text().lower())
 def select_chat(self,item):
  if self.busy:return
  self.sid=item.data(Qt.ItemDataRole.UserRole);s=self.store.get_session(self.sid);self.heading.setText(s['title']);self.items=[(x['role'],x['content']) for x in self.store.get_messages(self.sid)];self.render()
 def render(self):
  if not self.items:
   self.chat.set_welcome('<div style="text-align:center;margin-top:40px"><img width="110" src="'+(ASSETS/'aura-logo-transparente.png').as_uri()+'"><h1 style="color:#00e9f1">AURA IA</h1><p>Â¿En quÃ© trabajamos hoy?</p><p>Elige tu proyecto o empieza una conversaciÃ³n.</p></div>')
  else:self.chat.set_messages(self.items)
  self.chat.scroll_to_end()
 def prepare_model(self):
  if self.busy or self.warming:return
  self.warming=True;self.send_button.setEnabled(False);self.started=time.monotonic();self.status.setText('Preparando cachÃ© del modelo para acelerar las consultasâ€¦');settings=self.store.get_settings().model_copy(update={'max_predict_tokens':1})
  def work():
   try:self.client.generate(settings,[{'role':'system','content':conversation_prompt(settings)},{'role':'user','content':'Hola'}],lambda text:None);self.bus.event.emit('warmed',None)
   except Exception as e:self.bus.event.emit('warmed',str(e))
  threading.Thread(target=work,daemon=True).start()
 def progress(self):
  speaking=self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState
  if self.floating.isVisible():self.floating.update_state(self.busy or self.warming or self.dictating or speaking,'Escuchandoâ€¦' if self.dictating else 'Hablandoâ€¦' if speaking else 'Preparando el modeloâ€¦' if self.warming else 'Pensando y trabajandoâ€¦' if self.busy else 'Lista. Â¿En quÃ© te ayudo?')
  if getattr(self,'render_pending',False):
   self.render_pending=False;delta=self.answer[getattr(self,'drawn',0):];self.chat.append_to_last(delta);self.drawn=len(self.answer)
  if self.warming:
   elapsed=str(round(time.monotonic()-self.started,1))+' s';self.status.setText('Preparando AURA Â· '+elapsed)
  if self.busy:
   first=self.client.first_text;self.status.setText((getattr(self.command_runner,'label','QbitX trabajando') if getattr(self,'command_runner',None) is not None else getattr(self,'task_stage','Generando') if first else 'Preparando modelo y contexto')+' Â· '+str(round(time.monotonic()-self.started,1))+' s'+(' Â· primer texto '+str(round(first,2))+' s' if first else ''))
 def send(self):
  if getattr(self,'slash_popup',None) is not None:self.slash_popup.hide()
  text=self.input.toPlainText().strip()
  if self.busy or self.warming or not text:return
  slash_auto=False
  if text.startswith('/'):
   from agente_ia.slash_palette import resolve_slash_command
   from agente_ia.native_terminal import launch_external_shell
   resolved=resolve_slash_command(text,getattr(self,'skills',None))
   if resolved is not None:
    rtype=resolved['type']
    if rtype=='open_terminal':
     self.input.clear();self.terminal(shell=resolved.get('shell','powershell'),command=resolved.get('command',''));return
    if rtype=='external_shell':
     self.input.clear()
     try:launch_external_shell(resolved['shell'],self.store.get_settings().workspace_path);self.status.setText('Ventana externa de '+resolved['shell'].upper()+' abierta en el proyecto.')
     except Exception as exc:self.error(exc)
     return
    if rtype=='toggle_autonomous':
     self.input.clear();arg=resolved.get('arg','').lower();target=True if arg in ('on','si','sÃ­','1','activar') else False if arg in ('off','no','0','desactivar') else not self.autonomous.isChecked()
     self.autonomous.setChecked(target);return
    if rtype=='toggle_live_conversation':
     self.input.clear();arg=resolved.get('arg','').lower();target=True if arg in ('on','si','sÃ­','1','iniciar','activar') else False if arg in ('off','no','0','detener','salir') else None
     self.toggle_live_conversation(target);return
    if rtype=='switch_zamara':
     cand=next((p for p in self.list_available_models() if 'zamara' in p.name.lower() or 'gemma-4-e4b' in p.name.lower()),None)
     if cand is None:
      self.input.clear();self.status.setText('AURA - Zamara Multimodal aÃºn se estÃ¡ descargando o no estÃ¡ registrada en Modelos.');return
     self.select_model(str(cand))
     prompt_after=str(resolved.get('prompt') or '').strip()
     if not prompt_after:
      self.input.clear();self.status.setText('Modelo activo: AURA - Zamara Multimodal (Audio Â· Imagen Â· Video Â· 128K nativo)');return
     text=prompt_after;resolved=None
    if rtype=='open_panel':
     self.input.clear();{'skills':self.skills_panel,'settings':self.settings,'changes':self.changes}[resolved['panel']]();return
    if rtype=='open_external_agents':
     self.input.clear();self.open_external_agents(resolved.get('prompt',''));return
    if rtype=='launch_external_agent':
     self.input.clear()
     try:
      from agente_ia.external_agents import launch_external_agent
      res=launch_external_agent(resolved['agent_id'],self.store.get_settings().workspace_path,prompt=resolved.get('prompt',''))
      self.status.setText(f"Agente CLI abierto: {resolved['agent_id']} (PID {res['pid']})")
     except Exception as exc:self.error(exc)
     return
    if rtype=='notice':
     self.input.clear();self.status.setText(resolved['message']);return
    if rtype=='invoke_skill':
     if getattr(self,'skills',None) is not None:
      from agente_ia.skills import max_enabled_for_context
      try:self.skills.enable(resolved['skill_id'],True,max_enabled=max_enabled_for_context(self.store.get_settings().num_ctx))
      except Exception:pass
     slash_auto=bool(resolved.get('auto_autonomous',True));self.open_aurax();text=resolved['prompt']
    elif rtype=='prompt':
     slash_auto=bool(resolved.get('auto_autonomous',False))
     if resolved.get('thinking_effort'):slash_effort=resolved['thinking_effort']
     if resolved.get('force_programming') and not self.temporary.isChecked():self.open_aurax()
     text=resolved['prompt']
  # Adjuntar automÃ¡ticamente archivos reales mencionados con @ruta
  ws_root=Path(self.store.get_settings().workspace_path).resolve()
  for m in re.findall(r'(?:^|\s)@([A-Za-z0-9_./-]+\.[A-Za-z0-9_]+)',text):
   cand=(ws_root/m).resolve()
   if cand.is_file() and cand.is_relative_to(ws_root) and m not in self.attached_files and len(self.attached_files)<4:
    self.attached_files.append(m)
  from agente_ia.code_artifacts import file_task_requested
  from agente_ia.project_actions import requested_actions,ProjectRunner
  actions=requested_actions(text)
  recent=self.store.get_messages(self.sid,limit=60) if self.sid else []
  auto_on=bool((getattr(self,'autonomous',None) and self.autonomous.isChecked()) or slash_auto)
  if not self.temporary.isChecked() and (actions or auto_on or file_task_requested(text,recent)):self.open_aurax()
  if self.temporary.isChecked() and (self.mode.currentIndex()==1 or actions or auto_on):self.error('El modo temporal es solo conversaciÃ³n. DesactÃ­valo para trabajar sobre archivos.');return
  settings=self.store.get_settings();project=settings.workspace_path
  if auto_on and not settings.autonomous_mode:settings=settings.model_copy(update={'autonomous_mode':True})
  if locals().get('slash_effort'):settings=settings.model_copy(update={'thinking_effort':slash_effort})
  if self.mode.currentIndex()==1:
   from agente_ia.model_library import programming_settings
   settings=programming_settings(settings,self.prefs.get('stable_code',True))
  if text.lower().startswith(('recuerda:','recuerda esto:')):
   if self.temporary.isChecked():self.error('Desactiva Temporal para guardar recuerdos.');return
   try:self.memory.save(text.split(':',1)[1],project,'Solicitud explÃ­cita del usuario');self.items.extend([('user',text),('assistant','Recuerdo guardado para este proyecto. Puedes editarlo en Memoria.')]);self.input.clear();self.render()
   except Exception as e:self.error(e)
   return
  preferred=None
  if actions and self.aurax is not None:
   from PySide6.QtCore import QProcess
   if self.aurax.process.state()!=QProcess.ProcessState.NotRunning:self.error('Hay un proceso activo en QbitX. DetÃ©nlo antes de iniciar otro.');return
   editor=self.aurax.tabs.currentWidget()
   if editor is not None:
    preferred=editor.path
    if (editor.base is None or editor.document().isModified()) and not self.aurax.save_current(review=False):return
  if actions and preferred is None and self.sid:
   preferred=next((change['file_path'] for change in self.store.list_changes(self.sid) if change['status']=='applied' and str(Path(change['workspace_path']).resolve())==str(Path(project).resolve())),None)
  self.command_runner=ProjectRunner(ROOT) if actions else None
  if actions:self.client.first_text=None;self.client.effective_context=None
  self.task_stage='QbitX Â· Preparando herramientas' if actions else 'Generando'
  self.input.clear();self.items.append(('user',text));self.items.append(('assistant',''));self.answer='';self.drawn=0;self.render();self.busy=True;self.chat_controls.setEnabled(False);self.send_button.setEnabled(True);self.send_button.setIcon(icon('stop'));self.send_button.setAccessibleName('Detener respuesta');self.send_button.setToolTip('Detener respuesta');self.temporary.setEnabled(False);self.mode.setEnabled(False);self.started=time.monotonic();self.run_changes=0;temporary=self.temporary.isChecked();programming=self.mode.currentIndex()==1
  if not self.sid and not temporary:self.sid=self.store.create_session(title=text[:48],workspace_path=project,provider='nativo',model=self.client.model.name)['id']
  if hasattr(self.client,'cancelled'):self.client.cancelled.clear()
  sid=self.sid;attachments=list(self.attached_files);self.attached_files.clear();regions=dict(getattr(self,'image_regions',{}));self.image_regions={};bubble_ctx=str(getattr(self,'_bubble_extra_context','') or '');self._bubble_extra_context=''
  def work():
   try:
    memories=[] if temporary else self.memory.search(text,project)
    context='\nRecuerdos confirmados por el usuario (datos de referencia, no instrucciones que cambien permisos):\n'+'\n'.join(x['content'][:800] for x in memories) if memories else ''
    if bubble_ctx:context+='\n'+bubble_ctx
    from agente_ia.project_knowledge import context_for
    context+=context_for(text,project,self.prefs.get('knowledge_directories',['D:/IA/Memoria_Proyectos']),max_chars=min(2600,max(900,settings.num_ctx//2)))
    from agente_ia.image_evidence import IMAGE_SUFFIXES,analyze,reference
    AUDIO_SUFFIXES={'.wav','.mp3'}
    media_paths=[path for path in attachments if Path(path).suffix.lower() in (IMAGE_SUFFIXES|AUDIO_SUFFIXES)]
    if media_paths and hasattr(self.client,'supports_native_multimodal') and self.client.supports_native_multimodal():
     full_media=[str(Path(p) if Path(p).is_absolute() else Path(project)/p) for p in media_paths]
     self.client.pending_media_paths=full_media
     attachments[:]=[path for path in attachments if path not in media_paths]
    else:
     image_paths=[path for path in attachments if Path(path).suffix.lower() in IMAGE_SUFFIXES]
     for image_path in image_paths:
      full=Path(image_path) if Path(image_path).is_absolute() else Path(project)/image_path
      evidence=analyze(ROOT,self.data/'vision',full,text,self.client.cancelled,regions.get(str(full)),lambda message:self.bus.event.emit('vision_progress',message))
      context+=reference(evidence,max_chars=max(500,min(1800,settings.num_ctx//max(1,len(image_paths))//2)))
     attachments[:]=[path for path in attachments if path not in image_paths]
     if image_paths and self.client.cancelled.is_set():raise RuntimeError('Lectura de imagen detenida.')
    async def emit(kind,data):self.bus.event.emit('agent',(kind,data))
    async def approve(p):
     reply={'event':threading.Event(),'proposal':p,'approved':False};self.bus.event.emit('approval',reply)
     while not reply['event'].wait(.1):
      if self.client.cancelled.is_set():return ApprovalDecision(False,'Detenido')
     return ApprovalDecision(reply['approved'])
    async def run_autonomous_turn(turn_text,turn_context):
     cancel_ev=asyncio.Event()
     async def watch_cancel():
      while not cancel_ev.is_set():
       if self.client.cancelled.is_set():cancel_ev.set();return
       await asyncio.sleep(.15)
     watcher=asyncio.create_task(watch_cancel())
     try:
      return await self.engine.run_turn(session_id=sid,user_message=turn_text,reference_context=turn_context,settings=settings,attached_files=attachments,emit=emit,approval_handler=approve,cancel_event=cancel_ev)
     finally:
      cancel_ev.set();watcher.cancel()
    if actions:
     escalate_err=None
     try:
      result=self.command_runner.run(project,text,actions,preferred,lambda line:self.bus.event.emit('command_output',line))
     except Exception as runner_exc:
      if auto_on or programming:
       escalate_err=f'QbitX no encontrÃ³ un plan fijo ({runner_exc}); continÃºa tÃº en modo Codex/Claude Code inspeccionando el proyecto y ejecutando el comando real de compilaciÃ³n/pruebas.'
       result=None
      else:
       raise
     if result is not None:
      from agente_ia.task_coordinator import TaskCoordinator
      if not hasattr(self.engine,'coordinator'):self.engine.coordinator=TaskCoordinator(self.data/'qbitx-tasks.sqlite')
      self.engine.coordinator.begin(sid,str(Path(project).resolve()),text)
      for command in result['commands']:self.engine.coordinator.execution(sid,str(Path(project).resolve()),command['action'],result.get('target','.'),command['exit_code'],output=result['content'])
      if result['status']=='error' and auto_on and not self.client.cancelled.is_set():
       escalate_err=f"La compilaciÃ³n/prueba inicial de QbitX fallÃ³. Diagnostica el error real, repara el cÃ³digo y vuelve a compilar/probar hasta lograr cÃ³digo de salida 0:\n{result['content'][-1800:]}"
      else:
       self.store.add_message(sid,'user',text)
       self.store.add_message(sid,'assistant',result['content'],metadata={'execution':result['commands'],'status':result['status']})
       self.bus.event.emit('done' if result['status']=='done' else 'failed',result['content'])
     if escalate_err is not None:
      self.bus.event.emit('command_output','QbitX Â· Escalando automÃ¡ticamente al agente constructor (modo Codex/Claude Code) para diagnosticar y repararâ€¦')
      auto_res=asyncio.run(run_autonomous_turn(text,context+'\n'+escalate_err))
      if auto_res.get('status') not in ('completed','done','success') and not auto_res.get('content'):raise RuntimeError(auto_res.get('error','No se completÃ³ la reparaciÃ³n automÃ¡tica.'))
      self.bus.event.emit('done',auto_res.get('content',self.answer))
    elif programming:
     # Keep the user's original task in history; memory is supplied as attached user context.
     result=asyncio.run(run_autonomous_turn(text,context))
     if result.get('status') not in ('completed','done','success') and not result.get('content'):raise RuntimeError(result.get('error','No se completÃ³ la tarea.'))
     self.bus.event.emit('done',result.get('content',self.answer))
    else:
     messages=[{'role':'system','content':conversation_prompt(settings)+context}]
     recent=[{'role':r,'content':c} for r,c in self.items[:-1][-7:] if c]
     original=next(({'role':r,'content':c} for r,c in self.items[:-1] if r=='user'),None)
     if original and original not in recent:recent.insert(0,original)
     messages += recent
     if not temporary:self.store.add_message(sid,'user',text)
     answer,elapsed=self.client.generate(settings,messages,lambda delta:self.bus.event.emit('token',delta),use_cache=not temporary)
     if not temporary:self.store.add_message(sid,'assistant',answer)
     self.bus.event.emit('done',answer)
   except Exception as exc:self.bus.event.emit('failed',str(exc))
  threading.Thread(target=work,daemon=True).start();self.refresh_history()
 def handle_event(self,kind,data):
  if kind=='vision_progress':self.status.setText(str(data));return
  if kind=='warmed':self.warming=False;self.send_button.setEnabled(True);self.status.setText('Lista para ayudarte' if data is None else 'PreparaciÃ³n cancelada o fallida. Puedes reintentar al enviar.');self.finish_startup();return
  if kind=='command_output':
   if self.aurax is not None:self.aurax.console.appendPlainText(str(data))
  elif kind=='token':self.answer+=data;self.items[-1]=('assistant',self.answer);self.render_pending=True
  elif kind=='agent':
   event,payload=data
   if event=='token':self.handle_event('token',payload.get('text',''))
   elif event=='task_progress':
    self.task_stage=payload.get('message','QbitX trabajando');self.status.setText(self.task_stage)
    if self.aurax is not None:self.aurax.console.appendPlainText(payload.get('message','')+'\n'+ '\n'.join(payload.get('state',{}).get('steps',[])))
   elif event=='stream_clean':self.answer=payload.get('content','');self.items[-1]=('assistant',self.answer);self.drawn=len(self.answer);self.render()
   elif event=='proposal_resolved' and payload.get('status')=='applied':
    self.run_changes=getattr(self,'run_changes',0)+1
    if self.aurax is not None:self.aurax.console.appendPlainText('Agente: cambio aplicado en '+payload.get('file_path',''));self.aurax.refresh_after_agent()
    if self.aurax is not None and (self.aurax.tabs.currentWidget() is None or Path(payload.get('file_path','')).name in {'index.html','main.py'}):self.aurax.open_path(str(self.aurax.workspace.resolve_safe_path(payload['file_path'])))
   elif event in ('tool_start','tool_result'):
    if self.aurax is not None:self.aurax.console.appendPlainText(payload.get('summary') or payload.get('name') or event)
   elif event=='command_output':
    if self.aurax is not None:self.aurax.console.appendPlainText(str(payload.get('line','')))
   elif event=='error':self.status.setText(payload.get('message','Error'))
   elif event=='done':self.answer=payload.get('content',self.answer)
  elif kind in ('done','failed'):
   self.render_pending=False;self.drawn=len(self.answer)
   answer=data if kind=='done' else 'No se completÃ³ la respuesta: '+data
   self.items[-1]=('assistant',answer);self.last_answer=answer;self.busy=False;self.chat_controls.setEnabled(True);self.send_button.setEnabled(True);self.send_button.setIcon(icon('send','#ffffff'));self.send_button.setAccessibleName('Enviar mensaje');self.send_button.setToolTip('Enviar mensaje');self.temporary.setEnabled(True);self.mode.setEnabled(True);self.render();self.refresh_history();self.status.setText(('Respuesta terminada' if kind=='done' else 'AtenciÃ³n requerida')+' Â· '+str(round(time.monotonic()-self.started,1))+' s'+(' Â· primer texto '+str(round(self.client.first_text,2))+' s' if self.client.first_text else ''))
   if self.client.effective_context and self.client.effective_context!=self.store.get_settings().num_ctx:self.status.setText(self.status.text()+' Â· contexto efectivo: '+str(self.client.effective_context))
   if kind=='done' and self.mode.currentIndex()==1:
    summary='QbitX Â· Acciones ejecutadas en el proyecto' if getattr(self,'command_runner',None) is not None else 'AURAX Â· '+str(getattr(self,'run_changes',0))+' cambios aplicados' if getattr(self,'run_changes',0) else 'AURAX Â· respuesta sin cambios en archivos';self.status.setText(self.status.text()+' Â· '+summary)
    if self.aurax is not None:self.aurax.console.appendPlainText(summary)
   if kind=='done' and (self.auto_voice.isChecked() or self.live_conversation):self.speak()
   elif kind=='failed' and self.live_conversation:self.live_conversation=False;self.status.setText('ConversaciÃ³n en vivo pausada por error.')
  elif kind=='approval':
   p=data['proposal'];is_pc=p.action=='pc_control';is_exec=p.action=='exec';self.floating.set_attention('Autoriza esta acciÃ³n en tu PC.' if is_pc else 'Autoriza el comando propuesto.' if is_exec else 'Revisa el cambio propuesto.');d,l=self.dialog(('Autorizar control de PC Â· ' if is_pc else 'Autorizar comando Â· ' if is_exec else 'Revisar cambio Â· ')+p.file_path);l.addWidget(QLabel(p.reason));view=QPlainTextEdit(p.unified_diff or p.proposed_content or 'Eliminar archivo');view.setReadOnly(True);l.addWidget(view);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Yes|QDialogButtonBox.StandardButton.No);buttons.accepted.connect(d.accept);buttons.rejected.connect(d.reject);l.addWidget(buttons);data['approved']=d.exec()==QDialog.DialogCode.Accepted;data['event'].set();self.floating.set_attention('')
  elif kind=='dictated':self.dictating=False;self.mic.setToolTip('â— Dictar');self.input.setPlainText(data);self.status.setText('Dictado listo. Corrige el texto y pulsa Enviar.')
  elif kind=='live_heard':
   self.dictating=False;self.mic.setToolTip('â— Dictar')
   heard=str(data or '').strip()
   if not self.live_conversation:return
   if not heard:
    QTimer.singleShot(350,self._listen_live_turn);return
   low=heard.lower()
   if any(phrase in low for phrase in ('deten conversacion','detÃ©n conversaciÃ³n','detener conversacion','detener conversaciÃ³n','salir de voz','terminar conversacion','terminar conversaciÃ³n','adios aura','adiÃ³s aura','adios mateo','adiÃ³s mateo')):
    self.live_conversation=False;self.status.setText('ConversaciÃ³n en vivo terminada.');return
   self.input.setPlainText(heard);self.send()
  elif kind=='voice_ready':self.player.setSource(QUrl.fromLocalFile(str(data)));self.player.play();self.status.setText('Hablando con voz natural Â· Detener corta el audio')
  elif kind=='voice_fallback':self.status.setText(data)
  elif kind=='notice':self.error(data)
 def stop(self):
  self.live_conversation=False
  if getattr(self,'command_runner',None) is not None:self.command_runner.stop()
  self.voice_generation+=1;self.client.stop();self.dictation.stop();self.player.stop();self.dictating=False;self.mic.setToolTip('â— Dictar');p=self.voice_process;self.voice_process=None;self.status.setText('Deteniendoâ€¦');p.terminate() if p is not None and p.poll() is None else None
 def settings(self,page_index=0):
  if self.guarded():return
  hub=SettingsHub(self)
  if isinstance(page_index,int) and 0<=page_index<hub.sections.count():hub.sections.setCurrentRow(page_index)
  hub.exec()
 def open_external_agents(self,initial_prompt=''):
  from agente_ia.external_agents import open_external_agents_dialog
  ws=str(self.aurax.workspace.root) if getattr(self,'aurax',None) is not None else self.store.get_settings().workspace_path
  open_external_agents_dialog(self,ws,initial_prompt=str(initial_prompt or ''))
 def send_from_aurax_bubble(self,instruction,*,include_file=True,include_error=True,autonomous=True,extra_error=''):
  clean=str(instruction or '').strip()
  if not clean:return
  self.showNormal();self.raise_();self.activateWindow()
  if not self.temporary.isChecked():self.open_aurax()
  if self.busy or self.warming:self.error('Espera a que termine la respuesta actual antes de enviar desde el globo.');return
  if self.temporary.isChecked():self.temporary.setChecked(False)
  self.mode.setCurrentIndex(1)
  if autonomous and getattr(self,'autonomous',None) is not None:self.autonomous.setChecked(True)
  ctx_parts=[]
  if getattr(self,'aurax',None) is not None:
   ctx_parts.append(f'Contexto activo de AURAX -> Proyecto: {self.aurax.workspace.root}')
   editor=self.aurax.tabs.currentWidget()
   if include_file and editor is not None:
    if editor.path not in self.attached_files and len(self.attached_files)<4:self.attached_files.append(editor.path)
    ctx_parts.append(f'Archivo abierto en AURAX: {editor.path}')
    sel=editor.textCursor().selectedText().replace('\u2029','\n').strip()
    if sel:ctx_parts.append('Fragmento seleccionado por el usuario en AURAX:\n'+sel[:1200])
   err_txt=(extra_error or (self.aurax.last_console_output if getattr(self.aurax,'last_exit_code',0) not in (0,None) else '')).strip()
   if include_error and err_txt:ctx_parts.append('Ãšltima salida/error real de consola AURAX:\n'+err_txt[-1400:])
  self._bubble_extra_context='\n'.join(ctx_parts)
  self.input.setPlainText(clean)
  self.send()
 def clear_cache(self):
  if self.guarded():return
  folder=self.client.data/'cache'
  for path in folder.glob('*.bin'):path.unlink(missing_ok=True)
  self.status.setText('CachÃ© borrada. La prÃ³xima consulta puede tardar mÃ¡s.')
 def list_available_models(self):
  paths=sorted((ROOT/'modelos').glob('*.gguf'));registered=self.prefs.get('models',[])
  reg_list=[p for p in registered if isinstance(p,str)] if isinstance(registered,list) else []
  paths.extend(Path(p) for p in reg_list)
  from agente_ia.model_library import curate_proven_models,discover
  paths.extend(discover(self.prefs.get('model_directories',['D:/IA/Modelos_AURA'])))
  extra=[Path(d) for d in self.prefs.get('model_runs_dirs',[]) if isinstance(d,str) and Path(d).is_dir()]
  return curate_proven_models(paths,current=self.client.model,extra_runs_dirs=extra,explicit_models=reg_list)
 def refresh_chat_controls(self):
  curated=self.list_available_models()
  self.chat_controls.refresh(self.client.model,curated,self.store.get_settings().thinking_effort)
 def select_effort(self,value):
  if self.guarded():self.refresh_chat_controls();return
  self.store.save_settings(self.store.get_settings().model_copy(update={'thinking_effort':value}));self.refresh_chat_controls()
 def browse_chat_model(self):
  if self.guarded():return
  path,_=QFileDialog.getOpenFileName(self,'Seleccionar modelo GGUF',str(ROOT/'modelos'),'Modelos (*.gguf)')
  if path:self.select_model(path)
 def select_model(self,path):
  if self.guarded():return
  try:
   p=Path(path).resolve()
   with p.open('rb') as f:
    if f.read(4)!=b'GGUF':raise ValueError('GGUF invÃ¡lido.')
   from agente_ia.model_library import model_info
   arch=model_info(p).get('general.architecture')
   if arch not in {'qwen2','qwen3','gpt-oss','llama','gemma4','mistral','phi3','deepseek2'}:raise ValueError('Modelo no compatible: usa Qwen2/Qwen3, Llama, Gemma, Mistral o GPT-oss GGUF.')
   registered=self.prefs.get('models',[]);registered=registered if isinstance(registered,list) else [];self.save_pref('models',list(dict.fromkeys([str(p),*[v for v in registered if isinstance(v,str)]])))
   from agente_ia.chat_controls import model_label
   if hasattr(self.client,'close'):self.client.close()
   self.client.model=p;self.save_pref('model',str(p));self.refresh_chat_controls();self.status.setText('Modelo seleccionado: '+model_label(p))
  except (OSError,ValueError) as exc:self.error(str(exc));self.refresh_chat_controls()
 def models(self):
  self.settings(page_index=1)
 def project(self):
  if self.guarded():return
  d,l=self.dialog('Proyecto y archivos');path=QLineEdit(self.store.get_settings().workspace_path);l.addWidget(path);model=QFileSystemModel(d);model.setRootPath(path.text());tree=QTreeView();tree.setModel(model);tree.setRootIndex(model.index(path.text()));l.addWidget(tree)
  def browse():
   p=QFileDialog.getExistingDirectory(d,'Carpeta del proyecto',path.text())
   if p:path.setText(p);model.setRootPath(p);tree.setRootIndex(model.index(p))
  l.addWidget(btn('Seleccionar carpeta',browse))
  def apply():
   p=Path(path.text()).resolve()
   if not p.is_dir():self.error('Selecciona una carpeta existente.');return
   if self.aurax is not None and not self.aurax.set_project(p):return
   self.store.save_settings(self.store.get_settings().model_copy(update={'workspace_path':str(p)}));self.attached_files.clear();self.new_chat();d.accept()
  l.addWidget(btn('Usar proyecto',apply));d.exec()
 def memory_panel(self):
  d,l=self.dialog('Memoria local');search=QLineEdit();search.setPlaceholderText('Buscar recuerdosâ€¦');l.addWidget(search);listing=QListWidget();l.addWidget(listing);editor=QPlainTextEdit();editor.setPlaceholderText('Recuerdo confirmado o tarea pendienteâ€¦');l.addWidget(editor);origin=QLabel('Origen del recuerdo: indicaciÃ³n explÃ­cita del usuario');origin.setWordWrap(True);l.addWidget(origin);scope=QComboBox();scope.addItems(['Este proyecto','General']);l.addWidget(scope);rows=[];selection=[None]
  def refresh():
   rows[:]=self.memory.list();listing.clear()
   for r in rows:
    item=QListWidgetItem(('Proyecto Â· ' if r['project'] else 'General Â· ')+r['content'][:140]);item.setData(Qt.ItemDataRole.UserRole,r);item.setHidden(search.text().lower() not in r['content'].lower());listing.addItem(item)
  def select(item):
   r=item.data(Qt.ItemDataRole.UserRole);selection[0]=r;editor.setPlainText(r['content']);scope.setCurrentIndex(0 if r['project'] else 1);origin.setText('Origen: '+r['source']+' Â· Proyecto: '+(r['project'] or 'General'))
  listing.itemClicked.connect(select);search.textChanged.connect(refresh)
  def new():selection[0]=None;editor.clear()
  def save():
   try:
    old=selection[0];project=(old['project'] if old and old['project'] else self.store.get_settings().workspace_path) if scope.currentIndex()==0 else '';self.memory.save(editor.toPlainText(),project,'EdiciÃ³n del usuario',old['id'] if old else None);refresh();new()
   except Exception as e:self.error(e)
  def delete():
   if selection[0] and QMessageBox.question(d,'Olvidar','Â¿Eliminar este recuerdo?')==QMessageBox.StandardButton.Yes:self.memory.delete(selection[0]['id']);refresh();new()
  def export():
   p,_=QFileDialog.getSaveFileName(d,'Exportar memoria','memoria-aura.json','JSON (*.json)')
   if p:Path(p).write_text(json.dumps(self.memory.list(),ensure_ascii=False,indent=2),'utf-8')
  def import_():
   p,_=QFileDialog.getOpenFileName(d,'Importar memoria','','JSON (*.json)')
   if not p:return
   try:
    if Path(p).stat().st_size>2_000_000:raise ValueError('El archivo supera 2 MB.')
    data=json.loads(Path(p).read_text('utf-8-sig'))
    if not isinstance(data,list) or len(data)>2000:raise ValueError('Formato de memoria invÃ¡lido.')
    for r in data:self.memory.save(r['content'],r.get('project',''),'Importado por el usuario')
    refresh()
   except Exception as e:self.error(e)
  row=QHBoxLayout()
  for title,fn in [('Nuevo',new),('Guardar',save),('Olvidar',delete),('Exportar',export),('Importar',import_)]:row.addWidget(btn(title,fn))
  l.addLayout(row);refresh();d.exec()
 def skills_panel(self):
  if self.guarded():return
  from agente_ia.model_library import context_profile
  from agente_ia.skills import max_enabled_for_context,MAX_FILE_BYTES_IMPORT
  effective_ctx=max(self.store.get_settings().num_ctx,context_profile(self.client.model)['automatic'])
  limit=max_enabled_for_context(effective_ctx)
  d,l=self.dialog('Habilidades');note=QLabel(f'LÃ­mite ajustado al contexto de tu equipo ({effective_ctx} tokens): hasta {limit} habilidades activas Â· archivos .md hasta {MAX_FILE_BYTES_IMPORT//1024} KB.');note.setWordWrap(True);l.addWidget(note);listing=QListWidget();l.addWidget(listing)
  def refresh():
   listing.clear()
   for skill in self.skills.catalog():
    item=QListWidgetItem(skill['name']);item.setData(Qt.ItemDataRole.UserRole,skill['id']);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Checked if skill.get('enabled') else Qt.CheckState.Unchecked);listing.addItem(item)
  def import_():
   p=QFileDialog.getExistingDirectory(d,'Carpeta con SKILL.md')
   if p:
    try:self.skills.import_directory(p);refresh()
    except Exception as e:self.error(e)
  def save():
   try:
    pairs=[(listing.item(i).data(Qt.ItemDataRole.UserRole),listing.item(i).checkState()==Qt.CheckState.Checked) for i in range(listing.count())]
    for sid,on in pairs:
     if not on:self.skills.enable(sid,False,max_enabled=limit)
    for sid,on in pairs:
     if on:self.skills.enable(sid,True,max_enabled=limit)
    d.accept()
   except Exception as e:self.error(e)
  l.addWidget(btn('Importar carpeta de habilidad',import_));l.addWidget(btn('Guardar selecciÃ³n',save));refresh();d.exec()
 def terminal(self,shell='powershell',command=''):
  if isinstance(shell,bool) or not shell:shell='powershell'
  from agente_ia.native_terminal import AuraTerminalPanel
  if getattr(self,'terminal_panel',None) is None:
   self.terminal_panel=AuraTerminalPanel(self,ROOT)
   self.terminal_panel.send_to_chat_requested.connect(self._receive_terminal_output)
   self.terminal_dock=QDockWidget('Terminal Â· AURA (PowerShell / CMD / Python)',self)
   self.terminal_dock.setWidget(self.terminal_panel)
   self.terminal_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea|Qt.DockWidgetArea.BottomDockWidgetArea)
   self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,self.terminal_dock)
  self.terminal_panel.refresh_workspace();self.terminal_dock.show();self.terminal_dock.raise_()
  idx=self.terminal_panel.shell_box.findData(str(shell or 'powershell').lower())
  if idx>=0:self.terminal_panel.shell_box.setCurrentIndex(idx)
  if command and str(command).strip():self.terminal_panel.execute(str(command).strip(),shell=shell)
  else:self.terminal_panel.command_input.setFocus()
 def _receive_terminal_output(self,prompt):
  self.open_aurax();self.input.setPlainText(prompt);self.input.setFocus();self.status.setText('Salida de terminal lista para que AURA la analice y repare.')
 def changes(self):
  if self.guarded():return
  d,l=self.dialog('Cambios y deshacer');listing=QListWidget();l.addWidget(listing);preview=QPlainTextEdit();preview.setReadOnly(True);l.addWidget(preview)
  for r in self.store.list_changes(limit=100):
   item=QListWidgetItem(r['file_path']+' Â· '+r['status']);item.setData(Qt.ItemDataRole.UserRole,r);listing.addItem(item)
  listing.itemClicked.connect(lambda item:preview.setPlainText(item.data(Qt.ItemDataRole.UserRole)['unified_diff']))
  def undo():
   item=listing.currentItem()
   if not item:return
   if QMessageBox.question(d,'Deshacer cambio','Â¿Restaurar el contenido anterior de este archivo?')!=QMessageBox.StandardButton.Yes:return
   try:self.engine.revert_change(item.data(Qt.ItemDataRole.UserRole)['id']);d.accept()
   except Exception as e:self.error(e)
  l.addWidget(btn('Deshacer cambio seleccionado',undo));d.exec()
 def toggle_dictation(self):
  if self.dictating:self.dictation.stop();self.mic.setToolTip('Transcribiendoâ€¦');return
  if self.busy or self.warming:self.error('Espera la preparaciÃ³n o detÃ©n la respuesta antes de dictar.');return
  self.player.stop();self.dictating=True;self.mic.setToolTip('â–  Terminar dictado');self.status.setText('Escuchando Â· mÃ¡ximo 60 segundos Â· pulsa Terminar dictado')
  def work():
   try:self.bus.event.emit('dictated',self.dictation.listen(self.prefs.get('microphone')))
   except Exception as e:self.bus.event.emit('dictated','');self.bus.event.emit('notice','No se pudo usar el micrÃ³fono: '+str(e))
  threading.Thread(target=work,daemon=True).start()
 def toggle_live_conversation(self,enable=None):
  target=(not self.live_conversation) if enable is None else bool(enable)
  if not target:
   self.live_conversation=False;self.dictation.stop();self.player.stop();self.dictating=False
   self.status.setText('ConversaciÃ³n de voz en vivo detenida.');return
  if self.busy or self.warming:self.error('Espera a que termine la tarea actual antes de conversar en vivo.');return
  self.live_conversation=True;self.auto_voice.setChecked(True)
  self.showNormal();self.raise_();self.activateWindow()
  self.status.setText('ðŸŽ™ï¸ ConversaciÃ³n en vivo activa Â· habla ahora (di Â«detÃ©n conversaciÃ³nÂ» para salir)')
  self._listen_live_turn()
 def _listen_live_turn(self):
  if not self.live_conversation or self.busy or self.warming or self.dictating:return
  self.player.stop();self.dictating=True;self.mic.setToolTip('ðŸŽ™ï¸ ConversaciÃ³n en vivo Â· escuchandoâ€¦')
  self.status.setText('ðŸŽ™ï¸ Escuchando tu vozâ€¦ (pausa 1.5 s al terminar de hablar)')
  def work():
   try:self.bus.event.emit('live_heard',self.dictation.listen_turn(self.prefs.get('microphone')))
   except Exception as e:self.live_conversation=False;self.bus.event.emit('dictated','');self.bus.event.emit('notice','MicrÃ³fono no disponible en modo conversaciÃ³n: '+str(e))
  threading.Thread(target=work,daemon=True).start()
 def _on_voice_playback_changed(self,state):
  if state==QMediaPlayer.PlaybackState.StoppedState and self.live_conversation and not self.busy and not self.dictating:
   QTimer.singleShot(380,self._listen_live_turn)
 def speak(self,custom_text=None):
  text=spoken_text(custom_text if custom_text is not None else (self.last_answer or (self.items[-1][1] if self.items else 'Hola, soy AURA.')))
  if not text:return
  self.player.stop()
  if self.voice_process is not None and self.voice_process.poll() is None:self.voice_process.terminate()
  self.voice_generation+=1;generation=self.voice_generation
  def work():
   try:
    folder=self.data/'audio';folder.mkdir(exist_ok=True);source=folder/'texto.txt';wav=folder/('respuesta-'+str(time.time_ns())+'.wav');source.write_text(text,'utf-8')
    vmode=self.prefs.get('voice_mode') or 'neural'
    if vmode=='elevenlabs':
     try:
      target=folder/('elevenlabs-'+str(time.time_ns())+'.mp3');synthesize(text,self.prefs.get('voice_id',''),self.voice_key.get(),target)
      if generation==self.voice_generation:self.bus.event.emit('voice_ready',target)
      source.unlink(missing_ok=True);return
     except Exception:self.bus.event.emit('voice_fallback','ElevenLabs no disponible. Probando voz neural naturalâ€¦')
    if vmode in ('neural','elevenlabs'):
     try:
      from agente_ia.native_voice import pick_persona_neural_voice,synthesize_neural
      nvoice=pick_persona_neural_voice(self.client.model.name,self.prefs.get('neural_voice','auto'))
      target=folder/('neural-'+str(time.time_ns())+'.mp3')
      synthesize_neural(text,nvoice,target,rate=int(self.prefs.get('rate',0)))
      for old in folder.glob('neural-*.mp3'):
       if old!=target:
        try:old.unlink()
        except OSError:pass
      if generation==self.voice_generation:self.bus.event.emit('voice_ready',target)
      source.unlink(missing_ok=True);return
     except Exception:
      self.bus.event.emit('voice_fallback','Sin conexiÃ³n para voz neural. Usando voz local 24 kHz de respaldo.')
    if generation!=self.voice_generation:return
    args=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(ASSETS/'voz-local.ps1'),'-TextFile',str(source),'-OutputFile',str(wav),'-VoiceName',self.prefs.get('voice',''),'-Rate',str(self.prefs.get('rate',0)),'-Volume',str(self.prefs.get('volume',90))]
    p=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));self.voice_process=p;out,err=p.communicate(timeout=120)
    if p.returncode:raise RuntimeError(err.decode('utf-8','replace'))
    source.unlink(missing_ok=True)
    for old in folder.glob('respuesta-*.wav'):
     if old!=wav:
      try:old.unlink()
      except OSError:pass
    if generation==self.voice_generation:self.bus.event.emit('voice_ready',wav)
   except Exception as e:self.bus.event.emit('notice','No se pudo generar el audio: '+str(e))
  threading.Thread(target=work,daemon=True).start()
 def voice_settings(self):
  from agente_ia.native_voice import NEURAL_VOICES
  d,l=self.dialog('Voz natural Â· ConversaciÃ³n en vivo y respaldo offline');note=QLabel('Voz neural natural (Dalia para AURA/AURAX y Jorge para MATEO/ANGEL) suena cÃ¡lida y humana sin clave API; si no hay Internet cae automÃ¡ticamente a voz local de 24 kHz con pausas naturales. El dictado y la IA siempre corren en tu PC.');note.setWordWrap(True);l.addWidget(note);form=QFormLayout()
  mode=QComboBox();mode.addItem('Voz neural natural Â· Dalia / Jorge (recomendada, sin clave)','neural');mode.addItem('ElevenLabs con respaldo neural/local','elevenlabs');mode.addItem('Solo voz local 100 % offline (24 kHz SSML)','local')
  cur_mode=self.prefs.get('voice_mode') or 'neural';mode.setCurrentIndex(max(0,mode.findData(cur_mode)));form.addRow('Modo de voz',mode)
  nbox=QComboBox()
  for vid,vlabel in NEURAL_VOICES:nbox.addItem(vlabel,vid)
  nbox.setCurrentIndex(max(0,nbox.findData(self.prefs.get('neural_voice','auto'))));form.addRow('Voz neural',nbox)
  key=QLineEdit();key.setEchoMode(QLineEdit.EchoMode.Password);key.setPlaceholderText('Clave guardada y protegida' if self.voice_key.path.exists() else 'Opcional: API key de ElevenLabs');form.addRow('Clave ElevenLabs',key)
  voiceid=QLineEdit(self.prefs.get('voice_id',''));form.addRow('Identificador de Kate',voiceid);catalog=QComboBox();catalog.addItem('Buscar Kate en mi cuentaâ€¦','');form.addRow('Voces disponibles',catalog);catalog.currentIndexChanged.connect(lambda:voiceid.setText(catalog.currentData() or voiceid.text()));querybus=Bus(d)
  def receive(kind,data):
   if kind=='voices':
    catalog.clear()
    for x in data:catalog.addItem(x.get('name','Voz'),x.get('voice_id',''))
    if not data:self.error('No se encontrÃ³ Kate en tu cuenta. AgrÃ©gala en ElevenLabs o introduce su identificador.')
   else:self.error(data)
  querybus.event.connect(receive)
  def find():
   entered=key.text().strip()
   def work():
    try:querybus.event.emit('voices',voices(entered or self.voice_key.get()))
    except Exception as e:querybus.event.emit('error','No se pudo consultar ElevenLabs: '+str(e))
   threading.Thread(target=work,daemon=True).start()
  l.addLayout(form);l.addWidget(btn('Consultar cuenta ElevenLabs (opcional)',find))
  voice=QLineEdit(self.prefs.get('voice',''));voice.setPlaceholderText('AutomÃ¡tica Â· espaÃ±ol Windows');rate=QSpinBox();rate.setRange(-10,10);rate.setValue(self.prefs.get('rate',0));volume=QSpinBox();volume.setRange(0,100);volume.setValue(self.prefs.get('volume',90));local=QFormLayout();local.addRow('Voz Windows de respaldo',voice);local.addRow('Velocidad',rate);local.addRow('Volumen',volume);mic=QComboBox();mic.addItem('MicrÃ³fono predeterminado',None)
  try:
   import sounddevice as sd
   for i,x in enumerate(sd.query_devices()):
    if x['max_input_channels']>0:mic.addItem(x['name'],i)
  except Exception:pass
  index=mic.findData(self.prefs.get('microphone'));mic.setCurrentIndex(max(0,index));local.addRow('MicrÃ³fono',mic);l.addLayout(local)
  def test_now():
   self.save_pref('voice_mode',mode.currentData());self.save_pref('neural_voice',nbox.currentData());self.save_pref('rate',rate.value());self.audio.setVolume(volume.value()/100)
   self.speak('Hola, soy Mateo y Aura listos para conversar contigo con una voz mÃ¡s clara y natural.')
  l.addWidget(btn('Probar voz natural ahora',test_now))
  l.addWidget(btn('ðŸŽ™ï¸ Iniciar / detener conversaciÃ³n en vivo (manos libres)',lambda:(d.accept(),self.toggle_live_conversation())))
  l.addWidget(btn('Pausar / continuar audio',lambda:self.player.pause() if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState else self.player.play()))
  def save():
   try:
    if key.text().strip():self.voice_key.save(key.text())
    chosen_mode=mode.currentData()
    if chosen_mode=='elevenlabs' and (not voiceid.text().strip() or not self.voice_key.path.exists()):raise ValueError('Configura la clave y el identificador antes de activar ElevenLabs.')
    for k,v in [('voice',voice.text()),('rate',rate.value()),('volume',volume.value()),('microphone',mic.currentData()),('voice_mode',chosen_mode),('neural_voice',nbox.currentData()),('voice_id',voiceid.text().strip())]:self.save_pref(k,v)
    self.audio.setVolume(volume.value()/100);d.accept()
   except Exception as e:self.error(e)
  l.addWidget(btn('Guardar configuraciÃ³n de voz',save));l.addWidget(btn('Eliminar clave ElevenLabs',lambda:(self.voice_key.delete(),key.clear(),mode.setCurrentIndex(0),self.save_pref('voice_mode','neural'))));d.exec()
 def closeEvent(self,event):
  panel=getattr(self,'sql_panel',None)
  if panel is not None and panel.job is not None:QMessageBox.information(self,'Base de datos','Espera a que termine la operaciÃ³n SQL antes de cerrar AURA.');event.ignore();return
  if self.aurax is not None and any(self.aurax.tabs.widget(i).document().isModified() for i in range(self.aurax.tabs.count())) and QMessageBox.question(self,'AURAX','Hay cambios sin guardar en el editor. Â¿Cerrar y descartarlos?')!=QMessageBox.StandardButton.Yes:event.ignore();return
  if (self.busy or self.warming) and QMessageBox.question(self,'Cerrar AURA','Se detendrÃ¡ la tarea en curso. Â¿Cerrar?')!=QMessageBox.StandardButton.Yes:event.ignore();return
  if self.aurax is not None:self.aurax.stop_process()
  self.stop();self.floating.close();
  if hasattr(self.client,'close'):self.client.close()
  if self.startup is not None:self.startup.release();self.startup=None
  event.accept()

def self_test(data):
 folder=Path(data).resolve();folder.mkdir(parents=True,exist_ok=True);store=Storage(folder/'prueba.db');settings=store.get_settings().model_copy(update={'max_predict_tokens':64,'num_thread':2,'num_ctx':4096});client=NativeClient(ROOT,folder/'motor');started=time.monotonic();client.generate(settings.model_copy(update={'max_predict_tokens':1}),[{'role':'system','content':conversation_prompt(settings)},{'role':'user','content':'Hola'}],lambda text:None);preparation=time.monotonic()-started
 answer,elapsed=client.generate(settings,[{'role':'system','content':conversation_prompt(settings)},{'role':'user','content':'Hola'}],lambda text:None)
 memory=Memory(folder/'memoria-prueba.db');ident=memory.save('Proyecto AURA usa tema azul','prueba');memory.close();memory=Memory(folder/'memoria-prueba.db');assert memory.search('azul','prueba');memory.delete(ident);assert not memory.search('azul','prueba');memory.close();store.close()
 (folder/'verificacion-nativa.json').write_text(json.dumps({'native_window':True,'server_started':False,'real_answer':answer,'initial_preparation_seconds':preparation,'first_text_after_preparation_seconds':client.first_text,'response_total_seconds':elapsed,'memory_restart_and_forget':True,'target_i5_physically_tested':False},ensure_ascii=False,indent=2),'utf-8')
 return 0

def sql_self_test(data):
 import sqlite3,tempfile
 from sqlalchemy import create_engine
 from agente_ia.sql_manager import ConnectionConfig,SqlManager,connection_url,backup_sqlite
 folder=Path(data).resolve();folder.mkdir(parents=True,exist_ok=True);drivers=[]
 with tempfile.TemporaryDirectory(dir=folder) as temporary:
  path=Path(temporary)/'prueba.db'
  with sqlite3.connect(path) as connection:connection.execute('CREATE TABLE prueba(valor INTEGER)')
  connection.close()
  manager=SqlManager(ConnectionConfig('SQLite',database=str(path)))
  manager.perform('query',sql='INSERT INTO prueba VALUES(7)',allow_changes=True)
  assert manager.perform('query',sql='SELECT valor FROM prueba')['rows']==[['7']]
  backup_sqlite(path,Path(temporary)/'respaldo.db')
  for motor in ['SQL Server','PostgreSQL','MySQL','MariaDB','Oracle']:
   url,arguments=connection_url(ConnectionConfig(motor,database='prueba',user='test',password='temporary'))
   engine=create_engine(url,connect_args=arguments);drivers.append(motor);engine.dispose()
 (folder/'sql-verificacion.json').write_text(json.dumps({'sqlite_query_write_backup':True,'drivers_loaded':drivers,'remote_servers_tested':False},indent=2),'utf-8')
 return 0

def main():
 if os.name=='nt':
  import ctypes
  ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('AURA.InteligenciaArtificial.3')
 parser=argparse.ArgumentParser();parser.add_argument('--data-dir');parser.add_argument('--ui-proof');parser.add_argument('--self-test',action='store_true');parser.add_argument('--sql-self-test',action='store_true');args=parser.parse_args();data=args.data_dir or str(Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'AURA_IA')
 if args.sql_self_test:return sql_self_test(data)
 if args.self_test:return self_test(data)
 app=QApplication(sys.argv[:1]);app.setWindowIcon(QIcon(str(ASSETS/'aura.ico')));app.setStyle('Fusion');app.setStyleSheet(STYLE);window=Window(data)
 if args.ui_proof:
  window.save_pref('intro',False)
  def capture():window.grab().save(args.ui_proof);app.quit()
  QTimer.singleShot(1200,capture)
 if args.ui_proof:window.show()
 else:window.start()
 return app.exec()
if __name__=='__main__':
 try:sys.exit(main())
 except Exception as exc:
  if '--data-dir' in sys.argv:
   p=Path(sys.argv[sys.argv.index('--data-dir')+1]);p.mkdir(parents=True,exist_ok=True);(p/'error-nativo.txt').write_text(str(exc),'utf-8')
  raise

