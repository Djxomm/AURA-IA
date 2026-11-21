"""ZIP/TAR tools with bounded extraction and no paths outside the chosen new folder."""
from pathlib import Path
import shutil
import stat
import tarfile
import zipfile


def extract(source,destination,max_bytes=1024**3,max_files=10000):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if destination.exists():raise ValueError('Elige una carpeta nueva para conservar los archivos existentes.')
    def target(name):
        value=(destination/name.replace('\\','/')).resolve()
        if not value.is_relative_to(destination) or ':' in name:raise ValueError('El comprimido contiene una ruta no permitida.')
        return value
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as package:
            members=package.infolist()
            if len(members)>max_files or sum(m.file_size for m in members)>max_bytes:raise ValueError('El archivo supera el límite de extracción de 1 GiB o 10000 entradas.')
            if any(stat.S_ISLNK(m.external_attr>>16) for m in members):raise ValueError('No se extraen enlaces simbólicos.')
            paths=[target(m.filename) for m in members]
            destination.mkdir(parents=True)
            for member,path in zip(members,paths):
                if member.is_dir():path.mkdir(parents=True,exist_ok=True);continue
                path.parent.mkdir(parents=True,exist_ok=True)
                with package.open(member) as data,path.open('xb') as output:shutil.copyfileobj(data,output)
            return len(members)
    with tarfile.open(source,'r:*') as package:
        members=[];total=0
        for member in package:
            members.append(member);total+=member.size
            if len(members)>max_files or total>max_bytes:raise ValueError('El archivo supera el límite de extracción.')
            if not member.isdir() and not member.isfile():raise ValueError('No se extraen enlaces ni dispositivos de un TAR.')
            target(member.name)
        destination.mkdir(parents=True)
        for member in members:
            path=target(member.name)
            if member.isdir():path.mkdir(parents=True,exist_ok=True);continue
            path.parent.mkdir(parents=True,exist_ok=True)
            with package.extractfile(member) as data,path.open('xb') as output:shutil.copyfileobj(data,output)
        return len(members)


def create_zip(project,output,max_bytes=1024**3):
    project=Path(project).resolve();output=Path(output).resolve()
    if output.exists():raise ValueError('El ZIP ya existe; elige un nombre nuevo.')
    excluded={'.git','.venv','node_modules','__pycache__','.cache'};files=[];total=0
    for file in project.rglob('*'):
        relative=file.relative_to(project)
        if any(part in excluded for part in relative.parts) or file.name.startswith('.env') or file.suffix.lower() in {'.pem','.key','.pfx','.db','.sqlite','.dpapi'}:continue
        if file.is_symlink() or not file.is_file() or file.resolve()==output:continue
        if not file.resolve().is_relative_to(project):raise ValueError('Hay un archivo fuera del proyecto.')
        total+=file.stat().st_size
        if total>max_bytes or len(files)>=10000:raise ValueError('El proyecto supera el límite de 1 GiB o 10000 archivos.')
        files.append(file)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as package:
        for file in files:package.write(file,file.relative_to(project).as_posix())
    return len(files)


def open_dialog(owner):
    from PySide6.QtCore import QObject,Signal,QThread
    from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QPushButton,QFileDialog
    class ArchiveDialog(QDialog):
        def reject(self):
            if hasattr(self,'worker') and self.worker.isRunning():return
            super().reject()
    dialog=ArchiveDialog(owner);dialog.setWindowTitle('AURA · Archivos comprimidos');dialog.resize(520,240);layout=QVBoxLayout(dialog)
    status=QLabel('Crear ZIP del proyecto o extraer ZIP/TAR en una carpeta nueva. Se omiten bases locales, claves y archivos .env al empaquetar.');status.setWordWrap(True);layout.addWidget(status)
    create=QPushButton('Crear ZIP del proyecto');unpack=QPushButton('Extraer ZIP / TAR');layout.addWidget(create);layout.addWidget(unpack)
    class Worker(QThread):
        result=Signal(str)
        def __init__(self,action):super().__init__(dialog);self.action=action
        def run(self):
            try:self.result.emit('Terminado: '+str(self.action())+' entradas procesadas.')
            except Exception as error:self.result.emit('No se completó: '+str(error))
    def start(action):
        create.setEnabled(False);unpack.setEnabled(False);status.setText('Trabajando con los archivos…');worker=Worker(action);dialog.worker=worker
        worker.result.connect(status.setText);worker.finished.connect(lambda:(create.setEnabled(True),unpack.setEnabled(True)));worker.start()
    def make():
        path,_=QFileDialog.getSaveFileName(dialog,'Crear ZIP nuevo','proyecto.zip','ZIP (*.zip)')
        if path:start(lambda:create_zip(owner.store.get_settings().workspace_path,path))
    def expand():
        source,_=QFileDialog.getOpenFileName(dialog,'Archivo para extraer','','Archivos (*.zip *.tar *.tar.gz *.tgz *.tar.xz)')
        if not source:return
        parent=QFileDialog.getExistingDirectory(dialog,'Carpeta donde crear la extracción')
        if parent:start(lambda:extract(source,Path(parent)/(Path(source).stem+'-extraido')))
    create.clicked.connect(make);unpack.clicked.connect(expand)
    # Keep the parent dialog alive until its worker is done.
    from PySide6.QtCore import QEvent
    class Guard(QObject):
        def eventFilter(self,obj,event):
            return event.type()==QEvent.Type.Close and hasattr(dialog,'worker') and dialog.worker.isRunning()
    dialog.guard=Guard(dialog);dialog.installEventFilter(dialog.guard);dialog.exec()
