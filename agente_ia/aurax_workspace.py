"""AURAX native coding workspace. Uses the same agent, approvals and project boundary."""
from __future__ import annotations
import os,re,shutil,sys,uuid
from pathlib import Path
from PySide6.QtCore import Qt,Signal,QProcess,QProcessEnvironment,QTimer
from PySide6.QtGui import QFont,QSyntaxHighlighter,QTextCharFormat,QColor
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QSplitter,QTreeView,QFileSystemModel,QTabWidget,QPlainTextEdit,QInputDialog,QMessageBox,QDialog,QDialogButtonBox
from .workspace import SafeWorkspace,compute_file_hash,build_diff,WorkspaceError

class CodeColors(QSyntaxHighlighter):
 def highlightBlock(self,text):
  for pattern,color in [(r'\b(def|class|return|import|from|if|else|elif|for|while|try|except|with|as|async|await|True|False|None|function|const|let|var|public|private|new)\b','#82baff'),(r'\b\d+(?:\.\d+)?\b','#e8be86'),(r'"[^"\n]*"|\x27[^\x27\n]*\x27','#96d7ac'),(r'#.*$|//.*$','#8293ad')]:
   style=QTextCharFormat();style.setForeground(QColor(color))
   for match in re.finditer(pattern,text):self.setFormat(match.start(),match.end()-match.start(),style)

class CodeEditor(QPlainTextEdit):
 def __init__(self,path,content,base):
  super().__init__();self.path=path;self.base=base;self.setPlainText(content);self.document().setModified(False);self.setFont(QFont('Consolas',11));self.setStyleSheet('font-family:Consolas;font-size:13px;');self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap);self.highlighter=CodeColors(self.document());self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ')*4)

class AuraxWorkspace(QWidget):
 attach_requested=Signal(str)
 def __init__(self,owner,runtime):
  super().__init__();self.owner=owner;self.runtime=Path(runtime);self.workspace=SafeWorkspace(owner.store.get_settings().workspace_path);self.process=QProcess(self);self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels);self.process.readyReadStandardOutput.connect(self.read_output);self.process.finished.connect(self.finished);self.process.errorOccurred.connect(lambda error:self.console.appendPlainText('No se pudo ejecutar el proceso: '+self.process.errorString()));self.timeout=QTimer(self);self.timeout.setSingleShot(True);self.timeout.timeout.connect(self.stop_process)
  layout=QVBoxLayout(self);layout.setContentsMargins(8,8,8,8);title=QLabel('AURAX · Codificador');title.setFont(QFont('Segoe UI',15,QFont.Weight.Bold));titlebar=QHBoxLayout();titlebar.addWidget(title,1);import_code=QPushButton('Revisar código IA');import_code.clicked.connect(self.import_response);titlebar.addWidget(import_code);layout.addLayout(titlebar);self.path_label=QLabel(str(self.workspace.root));self.path_label.setWordWrap(True);layout.addWidget(self.path_label)
  toolbar=QHBoxLayout()
  for text,fn in [('Proyecto',owner.project),('Nuevo',self.new_file),('Guardar',self.save_current),('Adjuntar a AURAX',self.attach)]:
   button=QPushButton(text);button.clicked.connect(fn);toolbar.addWidget(button)
  layout.addLayout(toolbar);split=QSplitter();self.model=QFileSystemModel(self);self.model.setRootPath(str(self.workspace.root));self.tree=QTreeView();self.tree.setModel(self.model);self.tree.setHeaderHidden(True);self.tree.setRootIndex(self.model.index(str(self.workspace.root)));self.tree.doubleClicked.connect(lambda index:self.open_path(self.model.filePath(index)))
  for column in (1,2,3):self.tree.hideColumn(column)
  self.tabs=QTabWidget();self.tabs.setTabsClosable(True);self.tabs.tabCloseRequested.connect(self.close_tab);split.addWidget(self.tree);split.addWidget(self.tabs);split.setSizes([150,420]);layout.addWidget(split,1)
  row=QHBoxLayout()
  for text,kind in [('Verificar','check'),('Ejecutar','run'),('Compilar','build'),('Crear instalador','installer')]:
   button=QPushButton(text);button.clicked.connect(lambda checked=False,kind=kind:self.run(kind));row.addWidget(button)
  stop=QPushButton('Detener');stop.clicked.connect(self.stop_process);row.addWidget(stop);layout.addLayout(row)
  self.console=QPlainTextEdit();self.console.setReadOnly(True);self.console.setMaximumBlockCount(1500);self.console.setMaximumHeight(175);self.console.setPlaceholderText('Consola de AURAX: aquí aparecen comandos, errores y resultados reales.');self.console.setFont(QFont('Consolas',10));self.console.setStyleSheet('font-family:Consolas;font-size:12px;');layout.addWidget(self.console)
 def message(self,text):QMessageBox.warning(self,'AURAX',str(text))
 def set_project(self,path):
  root=Path(path).resolve()
  if root==self.workspace.root:return True
  if any(self.tabs.widget(i).document().isModified() for i in range(self.tabs.count())):self.message('Guarda o cierra las pestañas modificadas antes de cambiar de proyecto.');return False
  if self.process.state()!=QProcess.ProcessState.NotRunning:self.message('Detén el proceso antes de cambiar de proyecto.');return False
  self.tabs.clear();self.workspace=SafeWorkspace(root);self.path_label.setText(str(root));self.model.setRootPath(str(root));self.tree.setRootIndex(self.model.index(str(root)));return True
 def open_path(self,path):
  try:
   candidate=Path(path).resolve();relative=candidate.relative_to(self.workspace.root).as_posix();target=self.workspace.resolve_safe_path(relative)
   if target.is_dir():return
   if target.stat().st_size>512*1024:raise ValueError('El editor admite archivos de texto de hasta 512 KB.')
   raw=target.read_bytes()
   if b'\0' in raw:raise ValueError('Este archivo es binario. No se abre como texto.')
   text=raw.decode('utf-8-sig');self.open_editor(relative,text,text)
  except Exception as exc:self.message(exc)
 def open_editor(self,relative,text,base):
  for i in range(self.tabs.count()):
   if self.tabs.widget(i).path==relative:self.tabs.setCurrentIndex(i);return self.tabs.widget(i)
  editor=CodeEditor(relative,text,base);index=self.tabs.addTab(editor,relative);self.tabs.setCurrentIndex(index);editor.document().modificationChanged.connect(lambda modified,e=editor:self.rename_tab(e,modified));return editor
 def rename_tab(self,editor,modified):
  index=self.tabs.indexOf(editor)
  if index>=0:self.tabs.setTabText(index,editor.path+(' *' if modified else ''))
 def import_response(self):
  text=self.owner.last_answer or '';match=re.search(r'```([a-zA-Z0-9_+-]*)\s*\n(.*?)```',text,re.S)
  if not match:self.message('La última respuesta no contiene un bloque de código. Pídele a AURAX que lo genere.');return
  suffix={'python':'.py','py':'.py','javascript':'.js','js':'.js','json':'.json','html':'.html','css':'.css','c':'.c','cpp':'.cpp','java':'.java','php':'.php','html5':'.html'}.get(match.group(1).lower(),'.txt');name,ok=QInputDialog.getText(self,'AURAX · Revisar código IA','Archivo del proyecto para esta propuesta:',text='propuesta'+suffix)
  if not ok or not name.strip():return
  try:
   target=self.workspace.resolve_safe_path(name.strip(),allow_write=True);before=target.read_text('utf-8-sig') if target.exists() else None;editor=self.open_editor(self.workspace.to_rel_posix(target),before or '',before)
   if editor.document().isModified():raise ValueError('Esta pestaña tiene cambios pendientes. Guárdalos antes de cargar otra propuesta.')
   editor.setPlainText(match.group(2));editor.document().setModified(True);self.console.appendPlainText('Propuesta cargada en el editor. Revisa y pulsa Guardar para aprobar el cambio; todavía no se modificó el archivo.')
  except Exception as exc:self.message(exc)
 def new_file(self):
  name,ok=QInputDialog.getText(self,'AURAX · Nuevo archivo','Ruta relativa, por ejemplo src/programa.py:')
  if not ok or not name.strip():return
  try:
   target=self.workspace.resolve_safe_path(name.strip(),allow_write=True)
   if target.exists():raise ValueError('Ese archivo ya existe. Ábrelo desde el explorador.')
   self.open_editor(self.workspace.to_rel_posix(target),'',None)
  except Exception as exc:self.message(exc)
 def review(self,path,diff):
  dialog=QDialog(self);dialog.setWindowTitle('AURAX · Revisar '+path);dialog.resize(760,520);layout=QVBoxLayout(dialog);text=QPlainTextEdit(diff);text.setReadOnly(True);layout.addWidget(text);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons);return dialog.exec()==QDialog.DialogCode.Accepted
 def save_current(self):
  editor=self.tabs.currentWidget()
  if editor is None:return False
  if self.owner.busy:self.message('Espera al agente antes de guardar cambios manuales.');return False
  try:
   content=editor.toPlainText();before,after,base,diff=self.workspace.prepare_write(editor.path,content)
   if base!=compute_file_hash(editor.base):raise ValueError('El archivo cambió en disco. Cierra y vuelve a abrir la pestaña para revisar la versión nueva.')
   if before==after and before is not None:return True
   if not self.review(editor.path,diff['unified_diff']):return False
   action='create' if before is None else 'write';self.workspace.apply_change(editor.path,action,after,base)
   if not self.owner.sid:self.owner.sid=self.owner.store.create_session(title='AURAX · '+editor.path,workspace_path=str(self.workspace.root),provider='nativo',model=self.owner.client.model.name)['id']
   self.owner.store.add_change_record(change_id=uuid.uuid4().hex,session_id=self.owner.sid,workspace_path=str(self.workspace.root),file_path=editor.path,action=action,reason='Edición manual revisada en AURAX',before_content=before,after_content=after,unified_diff=diff['unified_diff'],added_lines=diff['added'],removed_lines=diff['removed'],status='applied')
   editor.base=after;editor.document().setModified(False);self.console.appendPlainText('Guardado: '+editor.path);self.owner.refresh_history();return True
  except Exception as exc:self.message(exc);return False
 def close_tab(self,index):
  editor=self.tabs.widget(index)
  if editor.document().isModified() and QMessageBox.question(self,'AURAX','¿Cerrar esta pestaña y descartar sus cambios sin guardar?')!=QMessageBox.StandardButton.Yes:return
  self.tabs.removeTab(index);editor.deleteLater()
 def attach(self):
  editor=self.tabs.currentWidget()
  if editor is None:self.message('Abre primero el archivo que quieres adjuntar.');return
  if editor.base is None or editor.document().isModified():
   if not self.save_current():return
  self.attach_requested.emit(editor.path)
 def run(self,kind):
  editor=self.tabs.currentWidget()
  if editor is None:self.message('Abre un archivo del proyecto para verificarlo, ejecutarlo o compilarlo.');return
  if self.owner.busy or self.owner.warming:self.message('Espera a que AURA termine su tarea.');return
  if self.process.state()!=QProcess.ProcessState.NotRunning:self.message('Ya hay un proceso activo.');return
  if Path(editor.path).suffix.lower() in {'.js','.mjs','.cjs','.java','.php','.html','.htm'} and kind!='installer':
   self.run_language(editor,kind);return
  if Path(editor.path).suffix.lower() in {'.cpp','.cc','.cxx','.c'} and kind!='installer':
   self.run_cpp(editor,kind);return
  if kind=='installer':
   self.run_installer(editor);return
  if not editor.path.lower().endswith('.py'):self.message('Usa Crear instalador para archivos .iss; estos botones son para Python.');return
  if editor.base is None or editor.document().isModified():
   if not self.save_current():return
  python=self.runtime/'herramientas/python/python.exe'
  if not python.exists():python=Path(sys.executable) if not getattr(sys,'frozen',False) else Path(shutil.which('python') or '')
  if not python.is_file():self.message('No se encontró Python. Configura las herramientas antes de compilar.');return
  target=str(self.workspace.resolve_safe_path(editor.path));args={'check':['-m','py_compile',target],'run':[target],'build':['-m','PyInstaller','--noconfirm','--onefile','--name',Path(editor.path).stem,target]}[kind]
  command=str(python)+' '+ ' '.join(args)
  if QMessageBox.question(self,'AURAX · Autorizar proceso','Se ejecutará en el proyecto seleccionado:\n\n'+command)!=QMessageBox.StandardButton.Yes:return
  env=QProcessEnvironment.systemEnvironment();env.insert('PYTHONUTF8','1');env.insert('PYTHONIOENCODING','utf-8');env.insert('PATH',str(python.parent)+os.pathsep+env.value('PATH'));self.process.setProcessEnvironment(env);self.process.setWorkingDirectory(str(self.workspace.root));self.console.appendPlainText('> '+command);self.process.start(str(python),args);self.timeout.start(300000 if kind=='build' else 120000)
 def run_language(self,editor,kind):
  from .language_tools import language_plan,check_html
  if editor.base is None or editor.document().isModified():
   if not self.save_current():return
  try:
   target=self.workspace.resolve_safe_path(editor.path);plan=language_plan(self.runtime,self.workspace.root,target,kind)
   if plan.program is None and not plan.preview:self.console.appendPlainText(check_html(target));return
   if plan.program is not None and not plan.program.is_file():self.message('No se encontró la herramienta incluida para este lenguaje.');return
   command=('Vista previa local de '+str(target)) if plan.preview else str(plan.program)+' '+' '.join(plan.arguments)
   if QMessageBox.question(self,'AURAX · Revisar ejecución',command+'\n\n'+plan.note)!=QMessageBox.StandardButton.Yes:return
   if plan.preview:
    from .native_browser import BrowserWindow
    from PySide6.QtCore import QUrl
    from PySide6.QtWebEngineCore import QWebEngineSettings
    preview=BrowserWindow(self.owner);preview.setWindowTitle('AURAX · Vista previa HTML5');preview.address.setText(str(target));preview.address.setReadOnly(True);preview.page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,False);preview.view.setUrl(QUrl.fromLocalFile(str(target)));preview.show();self.console.appendPlainText('Vista previa HTML5 abierta sin servidor web.');return
   if plan.output_directory:plan.output_directory.mkdir(parents=True,exist_ok=True)
   env=QProcessEnvironment.systemEnvironment();env.insert('PATH',str(plan.program.parent)+os.pathsep+env.value('PATH'));self.process.setProcessEnvironment(env);self.process.setWorkingDirectory(str(self.workspace.root));self.console.appendPlainText('> '+command);self.process.start(str(plan.program),plan.arguments);self.timeout.start(300000 if kind=='build' else 120000)
  except Exception as error:self.message(error)
 def run_cpp(self,editor,kind):
  if editor.base is None or editor.document().isModified():
   if not self.save_current():return
  compiler=self.runtime/'herramientas/w64devkit/bin'/('gcc.exe' if editor.path.endswith('.c') else 'g++.exe')
  if not compiler.is_file():self.message('No se encontró el compilador C/C++ incluido.');return
  target=self.workspace.resolve_safe_path(editor.path);output=self.workspace.root/'dist'/(target.stem+'.exe')
  if kind=='run':
   if not output.is_file():self.message('Primero pulsa Compilar para generar el EXE de este archivo C/C++.');return
   program=output;args=[]
  else:
   program=compiler;args=['-std=c11' if target.suffix=='.c' else '-std=c++17','-Wall','-Wextra']
   if kind=='check':args+=['-fsyntax-only',str(target)]
   else:args+=['-O2',str(target),'-o',str(output)]
  command=str(program)+' '+' '.join(args)
  if QMessageBox.question(self,'AURAX · C/C++','Se ejecutará este proceso en el proyecto:\n\n'+command)!=QMessageBox.StandardButton.Yes:return
  if kind=='build':output.parent.mkdir(exist_ok=True)
  env=QProcessEnvironment.systemEnvironment();env.insert('PATH',str(compiler.parent)+os.pathsep+env.value('PATH'));self.process.setProcessEnvironment(env);self.process.setWorkingDirectory(str(self.workspace.root));self.console.appendPlainText('> '+command);self.process.start(str(program),args);self.timeout.start(300000 if kind=='build' else 120000)
 def run_installer(self,editor):
  if not editor.path.lower().endswith('.iss'):self.message('Abre un script de Inno Setup (.iss).');return
  if editor.base is None or editor.document().isModified():
   if not self.save_current():return
  compiler=self.runtime/'herramientas/inno/ISCC.exe'
  if not compiler.is_file():self.message('No se encontró el compilador Inno Setup incluido.');return
  target=str(self.workspace.resolve_safe_path(editor.path));command=str(compiler)+' '+target
  if QMessageBox.question(self,'AURAX · Crear instalador','Compilar este script puede ejecutar instrucciones de su autor. Revisa primero el contenido.\n\n'+command)!=QMessageBox.StandardButton.Yes:return
  self.process.setWorkingDirectory(str(self.workspace.root));self.console.appendPlainText('> '+command);self.process.start(str(compiler),[target]);self.timeout.start(300000)
 def read_output(self):self.console.appendPlainText(bytes(self.process.readAllStandardOutput()).decode('utf-8','replace').rstrip())
 def finished(self,code,status):self.timeout.stop();self.read_output();self.console.appendPlainText('Proceso terminado · código de salida: '+str(code))
 def stop_process(self):
  if self.process.state()!=QProcess.ProcessState.NotRunning:self.process.kill();self.console.appendPlainText('Proceso detenido por el usuario o por límite de tiempo.')
 def refresh_after_agent(self):
  for i in range(self.tabs.count()):
   editor=self.tabs.widget(i)
   if editor.document().isModified():continue
   try:
    target=self.workspace.resolve_safe_path(editor.path)
    if target.exists():editor.base=target.read_text('utf-8-sig');editor.setPlainText(editor.base);editor.document().setModified(False)
   except (OSError,ValueError,WorkspaceError):pass
