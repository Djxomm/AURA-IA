"""Organized native settings, with editable controls rather than placeholder pages."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QHBoxLayout,QVBoxLayout,QWidget,QListWidget,QListWidgetItem,QLabel,QStackedWidget,QScrollArea,QFormLayout,QCheckBox,QComboBox,QSpinBox,QDoubleSpinBox,QSlider,QPushButton,QDialogButtonBox,QLineEdit,QFileDialog,QMessageBox
from .chat_controls import model_label
from .hardware_profile import hardware_info,recommended_settings
from .model_library import context_profile,model_info,model_skill_profile

class SettingsHub(QDialog):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.setWindowTitle('AURA · Configuración');self.resize(940,650);self.setMinimumSize(730,500)
        s=owner.store.get_settings();outer=QHBoxLayout(self);left=QWidget();left.setFixedWidth(190);nav=QVBoxLayout(left);nav.addWidget(QLabel('CONFIGURACIÓN'));search=QLineEdit();search.setPlaceholderText('Buscar sección…');nav.addWidget(search);self.sections=QListWidget();self.sections.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.sections.setWordWrap(True);nav.addWidget(self.sections);outer.addWidget(left)
        content=QVBoxLayout();self.stack=QStackedWidget();content.addWidget(self.stack,1);buttons=QDialogButtonBox();save=buttons.addButton('Guardar',QDialogButtonBox.ButtonRole.AcceptRole);close=buttons.addButton('Cerrar',QDialogButtonBox.ButtonRole.RejectRole);save.clicked.connect(self.apply);close.clicked.connect(self.reject);content.addWidget(buttons);outer.addLayout(content,1)
        def page(title,description):
            body=QWidget();layout=QVBoxLayout(body);heading=QLabel(title);heading.setStyleSheet('font-size:22px;font-weight:600;color:#edf5ff;');layout.addWidget(heading);note=QLabel(description);note.setWordWrap(True);note.setStyleSheet('color:#9eb4ce;');layout.addWidget(note)
            card=QWidget();card.setObjectName('settingsCard');form=QFormLayout(card);form.setContentsMargins(18,18,18,18);form.setVerticalSpacing(18);layout.addWidget(card);layout.addStretch();scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(body);self.sections.addItem(title);self.stack.addWidget(scroll);return form
        self.setStyleSheet('QWidget#settingsCard{background:#122237;border:1px solid #29405b;border-radius:12px;} QWidget#settingsCard QLabel,QWidget#settingsCard QCheckBox{background:transparent;} QListWidget{background:#091523;border:none;} QListWidget::item{padding:12px;} QListWidget::item:selected{background:#1a3b5d;color:white;} QScrollArea{border:none;}')
        general=page('General','Personaliza AURA en este equipo. Tus proyectos y conversaciones permanecen guardados localmente.')
        self.floating=QCheckBox('Mostrar el asistente AURAX');self.floating.setChecked(owner.prefs.get('floating',True));general.addRow(self.floating)
        self.intro=QCheckBox('Reproducir la animación al iniciar');self.intro.setChecked(owner.prefs.get('intro',True));general.addRow(self.intro)
        self.motion=QCheckBox('Animaciones suaves del asistente');self.motion.setChecked(owner.prefs.get('animations',True));general.addRow(self.motion)
        general.addRow('Apariencia',QLabel('Azul oscuro · AURA'))
        model=page('Modelos','Gestor de modelos locales GGUF: activa, agrega archivos o carpetas, revisa arquitectura/capas/contexto y administra tus modelos (AURA ANGEL 5.6, MATEO Pro, MATEO-Nano, Qwen, Llama, GPT-oss).')
        self.current_model_label=QLabel('');self.current_model_label.setWordWrap(True);model.addRow('Modelo activo',self.current_model_label)
        self.model_list=QListWidget();self.model_list.setMinimumHeight(210);self.model_list.setStyleSheet('QListWidget{background:#091523;border:1px solid #29405b;border-radius:8px;} QListWidget::item{padding:8px;}')
        self.model_list.itemDoubleClicked.connect(lambda _item:self.activate_selected_model())
        model.addRow(self.model_list)
        self.model_detail=QLabel('Selecciona un modelo de la lista para ver arquitectura, capas y ruta.');self.model_detail.setWordWrap(True);self.model_detail.setStyleSheet('color:#93c5fd;font-size:12px;')
        model.addRow(self.model_detail)
        self.model_list.currentItemChanged.connect(self._on_model_item_changed)
        mrow1=QHBoxLayout()
        btn_use=QPushButton('Activar seleccionado');btn_use.clicked.connect(self.activate_selected_model)
        btn_add=QPushButton('Agregar .gguf…');btn_add.clicked.connect(self.add_model_file)
        btn_dir=QPushButton('Agregar carpeta…');btn_dir.clicked.connect(self.add_model_directory)
        btn_scan=QPushButton('Escanear');btn_scan.clicked.connect(self.refresh_model_manager)
        btn_rem=QPushButton('Quitar de lista');btn_rem.clicked.connect(self.remove_selected_model)
        for b in (btn_use,btn_add,btn_dir,btn_scan,btn_rem):mrow1.addWidget(b)
        mwrap=QWidget();mwrap.setLayout(mrow1);model.addRow(mwrap)
        self.dirs_label=QLabel('');self.dirs_label.setWordWrap(True);self.dirs_label.setStyleSheet('color:#94a3b8;font-size:11px;');model.addRow('Carpetas escaneadas',self.dirs_label)
        self.refresh_model_manager()
        form=page('Rendimiento','Para un i5 antiguo: modelo ligero y contexto de 2048–4096. Más contexto y modelos grandes necesitan más tiempo y memoria.')
        self.effort=QComboBox();self.effort.addItem('Rápido','rapido');self.effort.addItem('Equilibrado','equilibrado');self.effort.addItem('Profundo','profundo');self.effort.addItem('Máximo · 16K + razonamiento extendido','maximo');self.effort.setCurrentIndex(self.effort.findData(s.thinking_effort));form.addRow('Razonamiento',self.effort)
        self.length=QSpinBox();self.length.setRange(0,16384);self.length.setSingleStep(128);self.length.setSpecialValueText('Automático');self.length.setValue(s.max_predict_tokens);form.addRow('Longitud máxima',self.length)
        self.hardware=hardware_info();self.context_profile=context_profile(owner.client.model,self.hardware)
        self.context=QSlider(Qt.Orientation.Horizontal);self.context.setRange(512,self.context_profile['maximum']);self.context.setSingleStep(1024);self.context.setPageStep(1024);self.context.setValue(s.num_ctx)
        self.context_label=QLabel();self.context_label.setWordWrap(True)
        self.context.valueChanged.connect(self.context_changed);self.context_changed(self.context.value());form.addRow('Contexto de programación',self.context);form.addRow(self.context_label)
        self.automatic=QCheckBox('Ampliar el contexto cuando haga falta');self.automatic.setChecked(owner.client.auto_context);form.addRow(self.automatic)
        self.accelerator=QComboBox();self.accelerator.addItem('Automática · CPU / GPU verificada','auto');self.accelerator.addItem('Solo procesador · i5 compatible','cpu');self.accelerator.addItem('Probar GPU Vulkan · Intel / NVIDIA','vulkan');self.accelerator.setCurrentIndex(max(0,self.accelerator.findData(getattr(owner.client,'acceleration','auto'))));form.addRow('Aceleración',self.accelerator)
        self.threads=QSpinBox();self.threads.setRange(1,64);self.threads.setValue(s.num_thread);form.addRow('Hilos del procesador',self.threads)
        self.temperature=QDoubleSpinBox();self.temperature.setRange(0,1.5);self.temperature.setSingleStep(.05);self.temperature.setValue(s.temperature);form.addRow('Creatividad',self.temperature)
        self.stable_code=QCheckBox('Programación estable: creatividad máxima de 0.20');self.stable_code.setChecked(owner.prefs.get('stable_code',True));form.addRow(self.stable_code)
        machine=QLabel(self.hardware['cpu']+'\n'+str(self.hardware['cores'])+' núcleos · '+str(self.hardware['ram_gib'])+' GiB RAM');machine.setWordWrap(True);form.addRow('Este equipo',machine);recommend=QPushButton('Usar valores recomendados para esta PC');recommend.clicked.connect(self.recommend);form.addRow(recommend)
        voice=page('Voz','Dicta mensajes y escucha respuestas. La voz local funciona sin Internet; ElevenLabs es una opción adicional.')
        self.autovoice=QCheckBox('Leer las respuestas automáticamente');self.autovoice.setChecked(owner.auto_voice.isChecked());voice.addRow(self.autovoice);configure=QPushButton('Configurar voz y audio…');configure.clicked.connect(lambda:self.launch(owner.voice_settings));voice.addRow(configure);read=QPushButton('Leer última respuesta');read.clicked.connect(owner.speak);voice.addRow(read)
        memory=page('Memoria','Revisa lo que AURA recuerda y administra la caché del modelo. Borrar la caché no borra tus conversaciones.')
        for text,callback in [('Administrar recuerdos…',owner.memory_panel),('Borrar caché del modelo',owner.clear_cache)]:
            b=QPushButton(text);b.clicked.connect(lambda checked=False,cb=callback:self.launch(cb));memory.addRow(b)
        projects=page('Proyecto y habilidades','El proyecto define la carpeta donde AURAX puede trabajar. Las habilidades añaden instrucciones para sus tareas.')
        proj_actions=[('Cambiar carpeta del proyecto…',owner.project),('Administrar habilidades…',owner.skills_panel)]
        if hasattr(owner,'open_external_agents'):proj_actions.append(('Apps CLI (Codex / Claude Code / OpenCode / Ollama)…',owner.open_external_agents))
        for text,callback in proj_actions:
            b=QPushButton(text);b.clicked.connect(lambda checked=False,cb=callback:self.launch(cb));projects.addRow(b)
        security=page('Cambios y seguridad','AURAX pide revisar los cambios antes de escribir archivos salvo que actives el modo constructor autónomo. Todo cambio aplicado queda registrado para deshacerlo.')
        self.autonomous=QCheckBox('Modo constructor autónomo: editar, probar y compilar automáticamente dentro del proyecto');self.autonomous.setChecked(bool(s.autonomous_mode));security.addRow(self.autonomous)
        b=QPushButton('Revisar cambios y deshacer…');b.clicked.connect(lambda:self.launch(owner.changes));security.addRow(b)
        self.sections.currentRowChanged.connect(self.stack.setCurrentIndex);self.sections.setCurrentRow(0)
        search.textChanged.connect(lambda text:[self.sections.item(i).setHidden(text.lower() not in self.sections.item(i).text().lower()) for i in range(self.sections.count())])

    def _collect_models(self):
        if hasattr(self.owner,'list_available_models'):
            return self.owner.list_available_models()
        paths=[Path(self.owner.client.model)]
        for p in (self.owner.prefs.get('models') or []):
            if isinstance(p,str) and Path(p).is_file():paths.append(Path(p))
        return list(dict.fromkeys(p.resolve() for p in paths if p.is_file()))

    def refresh_model_manager(self):
        cur=Path(self.owner.client.model).resolve() if Path(self.owner.client.model).is_file() else Path(self.owner.client.model)
        lbl=model_label(cur)
        self.current_model_label.setText(lbl if lbl==cur.name else f'{lbl} ({cur.name})')
        self.model_list.clear()
        for path in self._collect_models():
            rp=Path(path).resolve()
            prof=model_skill_profile(rp)
            sz_gb=round(rp.stat().st_size/(1024**3),2) if rp.is_file() else 0.0
            active_tag='✓ ACTIVO · ' if rp==cur else ''
            title=f"{active_tag}{model_label(rp)}  [{sz_gb:.2f} GB] — {prof['skills']}"
            item=QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole,str(rp))
            self.model_list.addItem(item)
            if rp==cur:self.model_list.setCurrentItem(item)
        dirs=self.owner.prefs.get('model_directories') or []
        self.dirs_label.setText(' | '.join(str(d) for d in dirs) if dirs else '(solo modelos integrados y registrados)')

    def _on_model_item_changed(self,current,_previous=None):
        if current is None:self.model_detail.setText('Selecciona un modelo de la lista.');return
        rp=Path(current.data(Qt.ItemDataRole.UserRole))
        try:
            info=model_info(rp)
            arch=str(info.get('general.architecture','?'))
            layers=info.get(f'{arch}.block_count','?')
            ctx=info.get(f'{arch}.context_length','?')
            sz_gb=round(rp.stat().st_size/(1024**3),2)
            self.model_detail.setText(f'Arquitectura: {arch} · Capas: {layers} · Contexto nativo: {ctx} · Tamaño: {sz_gb:.2f} GB\nRuta: {rp}')
        except Exception as exc:
            self.model_detail.setText(f'Ruta: {rp}\nDetalle GGUF: {exc}')

    def activate_selected_model(self):
        item=self.model_list.currentItem()
        if item is None:return
        path=item.data(Qt.ItemDataRole.UserRole)
        self.owner.select_model(path)
        self.context_profile=context_profile(self.owner.client.model,self.hardware)
        self.context.setMaximum(self.context_profile['maximum'])
        self.context_changed(self.context.value())
        self.refresh_model_manager()

    def add_model_file(self):
        path,_=QFileDialog.getOpenFileName(self,'Agregar modelo GGUF',str(Path(self.owner.client.model).parent),'Modelos (*.gguf)')
        if not path:return
        self.owner.select_model(path)
        self.refresh_model_manager()

    def add_model_directory(self):
        folder=QFileDialog.getExistingDirectory(self,'Agregar carpeta de modelos GGUF',str(Path(self.owner.client.model).parent))
        if not folder:return
        dirs=list(self.owner.prefs.get('model_directories') or [])
        if folder not in dirs:
            dirs.append(folder)
            self.owner.save_pref('model_directories',dirs)
        self.owner.refresh_chat_controls()
        self.refresh_model_manager()

    def remove_selected_model(self):
        item=self.model_list.currentItem()
        if item is None:return
        target=str(Path(item.data(Qt.ItemDataRole.UserRole)).resolve())
        if target==str(Path(self.owner.client.model).resolve()):
            QMessageBox.information(self,'Modelos','No puedes quitar el modelo actualmente activo. Activa otro primero.')
            return
        registered=[p for p in (self.owner.prefs.get('models') or []) if isinstance(p,str) and str(Path(p).resolve())!=target]
        self.owner.save_pref('models',registered)
        self.owner.refresh_chat_controls()
        self.refresh_model_manager()

    def context_changed(self,value):
        snapped=max(self.context.minimum(),round(value/1024)*1024)
        snapped=min(snapped,self.context.maximum())
        if snapped!=value:self.context.setValue(snapped);return
        profile=self.context_profile
        message=f"{value:,} tokens · Recomendado: {profile['recommended']:,} · Máximo: {profile['maximum']:,}".replace(',', ' ')
        if value>profile['recommended']:message+='\nExperimental: más RAM y más espera. No acelera las respuestas.'
        message+='\nLa ampliación automática conserva un límite prudente; los valores mayores se eligen manualmente.'
        self.context_label.setText(message)

    def recommend(self):
        values=recommended_settings(self.hardware);self.threads.setValue(values['num_thread']);self.context.setValue(self.context_profile['recommended']);self.length.setValue(values['max_predict_tokens']);self.temperature.setValue(.2);self.stable_code.setChecked(True)

    def apply(self):
        w=self.owner;s=w.store.get_settings();w.store.save_settings(s.model_copy(update={'thinking_effort':self.effort.currentData(),'max_predict_tokens':self.length.value(),'num_ctx':self.context.value(),'num_thread':self.threads.value(),'temperature':self.temperature.value(),'tool_mode':'xml','num_batch':64,'autonomous_mode':self.autonomous.isChecked()}))
        if hasattr(w,'autonomous'):w.autonomous.setChecked(self.autonomous.isChecked())
        w.save_pref('stable_code',self.stable_code.isChecked())
        w.client.acceleration=self.accelerator.currentData();w.save_pref("acceleration",w.client.acceleration)
        w.client.auto_context=self.automatic.isChecked();w.save_pref('auto_context',self.automatic.isChecked());w.save_pref('intro',self.intro.isChecked());w.save_pref('floating',self.floating.isChecked());w.save_pref('animations',self.motion.isChecked());w.auto_voice.setChecked(self.autovoice.isChecked());w.floating.setVisible(self.floating.isChecked());w.refresh_chat_controls();self.accept()
    def launch(self,callback):self.apply();callback()
