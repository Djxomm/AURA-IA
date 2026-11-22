"""Organized native settings, with editable controls rather than placeholder pages."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QHBoxLayout,QVBoxLayout,QWidget,QListWidget,QLabel,QStackedWidget,QScrollArea,QFormLayout,QCheckBox,QComboBox,QSpinBox,QDoubleSpinBox,QSlider,QPushButton,QDialogButtonBox,QLineEdit
from .chat_controls import model_label
from .hardware_profile import hardware_info,recommended_settings
from .model_library import context_profile

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
        model=page('Modelos','El modelo y el nivel de razonamiento se eligen también desde la barra de escritura del chat.')
        label=model_label(owner.client.model)
        current_text=label if label==owner.client.model.name else f'{label} ({owner.client.model.name})'
        current=QLabel(current_text);current.setWordWrap(True);model.addRow('Modelo actual',current);choose=QPushButton('Buscar modelo en la PC…');choose.clicked.connect(lambda:self.launch(owner.browse_chat_model));model.addRow(choose)
        form=page('Rendimiento','Para un i5 antiguo: modelo ligero y contexto de 2048–4096. Más contexto y modelos grandes necesitan más tiempo y memoria.')
        self.effort=QComboBox();self.effort.addItem('Rápido','rapido');self.effort.addItem('Equilibrado','equilibrado');self.effort.addItem('Profundo','profundo');self.effort.setCurrentIndex(self.effort.findData(s.thinking_effort));form.addRow('Razonamiento',self.effort)
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
        for text,callback in [('Cambiar carpeta del proyecto…',owner.project),('Administrar habilidades…',owner.skills_panel)]:
            b=QPushButton(text);b.clicked.connect(lambda checked=False,cb=callback:self.launch(cb));projects.addRow(b)
        security=page('Cambios y seguridad','AURAX pide revisar los cambios antes de escribir archivos. Los comandos requieren autorización. Puedes consultar y deshacer cambios aplicados.')
        b=QPushButton('Revisar cambios y deshacer…');b.clicked.connect(lambda:self.launch(owner.changes));security.addRow(b)
        self.sections.currentRowChanged.connect(self.stack.setCurrentIndex);self.sections.setCurrentRow(0)
        search.textChanged.connect(lambda text:[self.sections.item(i).setHidden(text.lower() not in self.sections.item(i).text().lower()) for i in range(self.sections.count())])

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
        w=self.owner;s=w.store.get_settings();w.store.save_settings(s.model_copy(update={'thinking_effort':self.effort.currentData(),'max_predict_tokens':self.length.value(),'num_ctx':self.context.value(),'num_thread':self.threads.value(),'temperature':self.temperature.value(),'tool_mode':'xml','num_batch':64}))
        w.save_pref('stable_code',self.stable_code.isChecked())
        w.client.acceleration=self.accelerator.currentData();w.save_pref("acceleration",w.client.acceleration)
        w.client.auto_context=self.automatic.isChecked();w.save_pref('auto_context',self.automatic.isChecked());w.save_pref('intro',self.intro.isChecked());w.save_pref('floating',self.floating.isChecked());w.save_pref('animations',self.motion.isChecked());w.auto_voice.setChecked(self.autovoice.isChecked());w.floating.setVisible(self.floating.isChecked());w.refresh_chat_controls();self.accept()
    def launch(self,callback):self.apply();callback()
