"""Native blue desktop shell and shared small SVG icons."""
from pathlib import Path
from PySide6.QtCore import Qt,QByteArray
from PySide6.QtGui import QIcon,QPixmap,QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget,QSplitter,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QToolButton,QMenu,QLineEdit,QListWidget,QComboBox,QCheckBox,QTextBrowser,QPlainTextEdit,QSizePolicy
from .chat_controls import ChatControls, model_label
from .message_input import MessageInput
from .chat_view import ChatView
from .avatar_3d import AvatarStageWidget

PATHS={
 'plus':'<path d="M12 5v14M5 12h14"/>',
 'mic':'<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M6 10v2a6 6 0 0012 0v-2M12 18v3M9 21h6"/>',
 'send':'<path d="M12 19V5M6 11l6-6 6 6"/>',
 'stop':'<rect x="6" y="6" width="12" height="12" rx="2"/>',
 'dots':'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
 'home':'<path d="M3 11l9-8 9 8M5 10v11h5v-7h4v7h5V10"/>',
 'folder':'<path d="M3 7V5h7l2 3h9v12H3z"/>',
 'code':'<path d="M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16"/>',
 'terminal':'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M12 15h5"/>',
 'slash':'<path d="M15 5L9 19"/>',
 'history':'<path d="M3 6v5h5M4 10a8 8 0 111 8M12 7v5l3 2"/>',
 'settings':'<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/>'}

def icon(name,color='#c8d8eb'):
    svg='<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><g fill="none" stroke="'+color+'" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'+PATHS[name]+'</g></svg>'
    pix=QPixmap(24,24);pix.fill(Qt.GlobalColor.transparent);paint=QPainter(pix);QSvgRenderer(QByteArray(svg.encode())).render(paint);paint.end();return QIcon(pix)

def tool(owner,name,tip,callback):
    b=QToolButton(owner);b.setIcon(icon(name));b.setToolTip(tip);b.setAccessibleName(tip);b.setFixedSize(34,34);b.clicked.connect(callback);return b

def build_shell(w,assets):
    split=QSplitter();w.setCentralWidget(split)
    rail=QWidget();rail.setObjectName('iconRail');rail.setFixedWidth(48);r=QVBoxLayout(rail);r.setContentsMargins(7,12,7,12);r.setSpacing(12)
    r.addWidget(tool(w,'home','Inicio AURA',w.new_chat));r.addWidget(tool(w,'plus','Nueva conversación',w.new_chat));r.addWidget(tool(w,'folder','Proyecto y archivos',w.project));r.addWidget(tool(w,'code','AURAX · Codificador',w.open_aurax));r.addWidget(tool(w,'terminal','Terminal integrada (PowerShell / CMD)',w.terminal))
    more=tool(w,'dots','Más herramientas',lambda:None);menu=QMenu(more)
    for title,callback in [('Recursos y tareas',w.open_resources),('Archivos comprimidos',w.open_archives),('Bases de datos SQL',w.open_sql),('Explorador de Internet',w.open_browser),('Habilidades',w.skills_panel),('Terminal y compilación',w.terminal),('Cambios y deshacer',w.changes)]:menu.addAction(title,callback)
    more.setMenu(menu);more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);r.addWidget(more);r.addStretch();r.addWidget(tool(w,'settings','Configuración',w.settings))
    side=QWidget();side.setObjectName('sidebar');side.setMinimumWidth(170);side.setMaximumWidth(300);sl=QVBoxLayout(side);sl.setContentsMargins(12,14,12,12);sl.setSpacing(8)
    brand=QLabel('AURA IA');brand.setObjectName('brand');sl.addWidget(brand)
    w.avatar_stage=AvatarStageWidget(side,compact=True);w.avatar_stage.set_animations_enabled(bool(w.prefs.get('animations',True)))
    w.avatar_stage.set_model(getattr(getattr(w,'client',None),'model',None),model_label(getattr(getattr(w,'client',None),'model',None)))
    w.avatar_stage.clicked.connect(lambda:w.floating.show() if hasattr(w,'floating') else None)
    sl.addWidget(w.avatar_stage)
    new=QPushButton('Nuevo chat');new.setObjectName('newChatButton');new.setIcon(icon('plus'));new.clicked.connect(w.new_chat);sl.addWidget(new)
    label=QLabel('WORKSPACE Y AGENTES');label.setObjectName('sectionLabel');sl.addWidget(label)
    project=QPushButton((Path(w.store.get_settings().workspace_path).name or 'Mi proyecto')[:20]);project.setObjectName('navButton');project.setIcon(icon('folder'));project.setToolTip(w.store.get_settings().workspace_path);project.clicked.connect(w.project);sl.addWidget(project)
    coder=QPushButton('AURAX · QbitX');coder.setObjectName('navButton');coder.setIcon(icon('code'));coder.clicked.connect(w.open_aurax);sl.addWidget(coder)
    codex_btn=QPushButton('Codex / OpenCode · AURA');codex_btn.setObjectName('navButton');codex_btn.setIcon(icon('terminal'));codex_btn.setToolTip('Abrir Codex CLI u OpenCode conectados a tu modelo local de AURA IA');codex_btn.clicked.connect(lambda:w.open_external_agents('') if hasattr(w,'open_external_agents') else w.terminal());sl.addWidget(codex_btn)
    w.search=QLineEdit();w.search.setPlaceholderText('Buscar conversación…');w.search.textChanged.connect(w.filter_history);sl.addWidget(w.search)
    recent=QLabel('RECIENTES');recent.setObjectName('sectionLabel');sl.addWidget(recent);w.history=QListWidget();w.history.itemClicked.connect(w.select_chat);sl.addWidget(w.history,1)
    local=QToolButton();local.setText('AURA · Local');local.setObjectName('localMenu');local.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon);local.setIcon(QIcon(str(assets/'aura.ico')));local.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);local_menu=QMenu(local)
    for title,callback in [('Mostrar asistente flotante',lambda:w.floating.show()),('Configuración',w.settings),('Voz y audio',w.voice_settings),('Memoria',w.memory_panel)]:local_menu.addAction(title,callback)
    local.setMenu(local_menu);sl.addWidget(local)
    right=QWidget();right.setObjectName('chatArea');rl=QVBoxLayout(right);rl.setContentsMargins(12,14,12,8);rl.setSpacing(8)
    top=QHBoxLayout();w.heading=QLabel('Nueva conversación');w.heading.setObjectName('chatTitle');w.heading.setMinimumWidth(0);w.heading.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);top.addWidget(w.heading,1)
    w.mode=QComboBox();w.mode.addItems(['Conversación','AURAX · Programación']);w.mode.setMaximumWidth(175);top.addWidget(w.mode);w.autonomous=QCheckBox('Autónomo');w.autonomous.setToolTip('Elabora tu orden en automático (edita, prueba, compila, busca e inspecciona) y pide aprobación de 1 clic solo en acciones sensibles (borrar, instalar o controlar la PC).');w.autonomous.setChecked(bool(w.store.get_settings().autonomous_mode));top.addWidget(w.autonomous);w.temporary=QCheckBox('Temporal');w.temporary.setToolTip('Sin historial ni memoria.');top.addWidget(w.temporary);rl.addLayout(top)
    w.status=QLabel('Preparando AURA…');w.status.setObjectName('status');w.status.setWordWrap(True);rl.addWidget(w.status)
    w.chat=ChatView();w.chat.setObjectName('conversation');w.chat.setMaximumWidth(820);chat_row=QHBoxLayout();chat_row.addStretch(1);chat_row.addWidget(w.chat,10);chat_row.addStretch(1);rl.addLayout(chat_row,1)
    composer=QWidget();composer.setObjectName('composer');composer.setMaximumWidth(620);cl=QVBoxLayout(composer);cl.setContentsMargins(6,2,6,2);cl.setSpacing(0)
    w.input=MessageInput();w.input.setPlaceholderText('Escribe a AURA · @ archivos · / acciones, habilidades y terminal…');w.input.submit_requested.connect(w.send);cl.addWidget(w.input)
    row=QHBoxLayout();row.setSpacing(4);row.addWidget(tool(w,'plus','Adjuntar archivos del proyecto',w.attach_chat_files))
    w.slash_button=tool(w,'slash','Acciones (/terminal, /powershell, /cmd, /pc, /rea, /impeccable, /blender, /imagen)',getattr(w,'open_slash_palette',lambda:None));w.slash_button.setFixedSize(28,34);row.addWidget(w.slash_button)
    w.chat_controls=ChatControls(w);w.chat_controls.model_requested.connect(w.select_model);w.chat_controls.browse_requested.connect(w.browse_chat_model);w.chat_controls.effort_requested.connect(w.select_effort);w.chat_controls.settings_requested.connect(w.settings);row.addWidget(w.chat_controls,1);w.refresh_chat_controls();w.chat_controls.model_menu.aboutToShow.connect(w.refresh_chat_controls)
    w.mic=tool(w,'mic','Dictar un mensaje',w.toggle_dictation);row.addWidget(w.mic)
    w.send_button=tool(w,'send','Enviar mensaje / detener respuesta',lambda:w.stop() if w.busy else w.send());w.send_button.setIcon(icon('send','#ffffff'));w.send_button.setObjectName('sendButton');w.send_button.setFixedSize(36,36);row.addWidget(w.send_button);cl.addLayout(row);composer_row=QHBoxLayout();composer_row.addStretch(1);composer_row.addWidget(composer,10);composer_row.addStretch(1);rl.addLayout(composer_row)
    w.auto_voice=QCheckBox(w);w.auto_voice.hide();w.auto_voice.setChecked(w.prefs.get('auto_voice',False));w.auto_voice.toggled.connect(lambda value:w.save_pref('auto_voice',value))
    footer=QLabel('AURA puede cometer errores. Revisa el código y los cambios.');footer.setObjectName('footer');footer.setAlignment(Qt.AlignmentFlag.AlignCenter);rl.addWidget(footer)
    split.addWidget(rail);split.addWidget(side);split.addWidget(right);split.setChildrenCollapsible(False);split.setSizes([48,225,907]);return split
