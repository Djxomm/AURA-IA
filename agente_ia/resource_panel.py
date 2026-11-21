"""On-demand resource panel. No monitoring timer runs when the panel is closed."""
import json
import os
from pathlib import Path
import psutil
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QPushButton,QFileDialog,QHeaderView


class ResourcePanel(QDialog):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.setWindowTitle('AURA · Recursos y tareas');self.resize(750,490)
        layout=QVBoxLayout(self);self.summary=QLabel('Midiendo CPU y memoria…');self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['Proceso de AURA','PID','CPU %','RAM MiB']);self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch);self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);layout.addWidget(self.table)
        note=QLabel('Solo se muestran AURA y sus procesos secundarios. Detener tarea cancela el trabajo activo; no cierra programas ajenos. Los programas del proyecto conservan los permisos de tu usuario de Windows.');note.setWordWrap(True);layout.addWidget(note)
        row=QHBoxLayout();stop=QPushButton('Detener tarea activa');stop.clicked.connect(owner.stop);row.addWidget(stop);export=QPushButton('Guardar diagnóstico');export.clicked.connect(self.export);row.addWidget(export);layout.addLayout(row)
        from .windows_isolation import executable
        isolation=QLabel('Windows Sandbox: disponible para órdenes «compila aislado».' if executable() else 'Windows Sandbox no está habilitado. El modo normal controla procesos, pero conserva los permisos de tu usuario.');isolation.setWordWrap(True);layout.addWidget(isolation)
        self.processes={};self.report={};psutil.cpu_percent();self.sample();self.timer=QTimer(self);self.timer.timeout.connect(self.sample);self.timer.start(2000);self.finished.connect(self.timer.stop)

    def sample(self):
        memory=psutil.virtual_memory();items=[];seen=set()
        try:processes=[psutil.Process(os.getpid()),*psutil.Process(os.getpid()).children(recursive=True)]
        except psutil.Error:processes=[]
        for process in processes[:80]:
            try:
                key=(process.pid,process.create_time());seen.add(key)
                cached=self.processes.setdefault(key,process)
                items.append({'name':'AURA (principal)' if process.pid==os.getpid() else process.name(),'pid':process.pid,'cpu':round(cached.cpu_percent(),1),'ram_mib':round(process.memory_info().rss/1024**2,1)})
            except psutil.Error:pass
        self.processes={key:value for key,value in self.processes.items() if key in seen}
        backend=getattr(self.owner.client,'backend_note','CPU / GPU según configuración')
        task=getattr(getattr(self.owner,'command_runner',None),'label','Sin comando activo') if self.owner.busy else 'Sin tarea activa'
        self.report={'cpu_system_percent':psutil.cpu_percent(),'ram_used_percent':memory.percent,'ram_available_gib':round(memory.available/1024**3,2),'backend':backend,'task':task,'processes':items}
        self.summary.setText(f"CPU del equipo: {self.report['cpu_system_percent']:.0f}% · RAM: {memory.percent:.0f}% · Disponible: {self.report['ram_available_gib']} GiB\nMotor: {backend}\n{task}")
        self.table.setRowCount(len(items))
        for row,item in enumerate(items):
            for column,key in enumerate(('name','pid','cpu','ram_mib')):self.table.setItem(row,column,QTableWidgetItem(str(item[key])))

    def export(self):
        name,_=QFileDialog.getSaveFileName(self,'Guardar diagnóstico','AURA-recursos.json','JSON (*.json)')
        if name:Path(name).write_text(json.dumps(self.report,ensure_ascii=False,indent=2),encoding='utf-8')
