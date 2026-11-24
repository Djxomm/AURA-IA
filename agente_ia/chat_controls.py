"""Compact conversation toolbar for model and response-depth selection."""
from pathlib import Path
import re
from PySide6.QtCore import Signal,QSize,Qt
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import QWidget,QHBoxLayout,QToolButton,QMenu,QStylePainter,QStyleOptionToolButton,QStyle

LEVELS={'rapido':'Rápido','equilibrado':'Equilibrado','profundo':'Profundo','maximo':'Máximo'}

def model_label(path):
    p=Path(path);name=p.stem;low=name.lower()
    if 'aura-zamara' in low or 'zamara' in low:return 'AURA - Zamara V8.2'
    if 'aura-mateo-pro' in low:return 'AURA - MATEO Pro'
    if 'aura-mateo-nano' in low:return 'AURA - MATEO-Nano (desde 0)'
    if "gpt-oss-20b" in low:return "OpenAI gpt-oss · 20B · Experimental"
    if 'qwen2.5-coder-1.5b-instruct' in low:return 'AURA Ligero · 1.5B'
    if 'qwen2.5-coder-7b-instruct' in low:
        quant=re.search(r'q[2-8]',low);return 'Qwen Coder · 7B'+(' · '+quant[0].upper() if quant else '')
    if p.suffix.lower()=='.gguf' and p.is_file():
        try:
            from .model_library import model_info
            gname=str(model_info(p).get('general.name') or '').strip()
            if gname and gname.lower() not in {'merged','model','unknown'}:return gname[:48]
        except (OSError,ValueError):pass
    if 'aura-angel-5.6' in low:return 'AURA - ANGEL 5.6'
    if 'aura-lumen-2.0ib_v2' in low:return 'AURA - Lumen 2.0IB_V2'
    if 'aura-lumen-2.0ib_v1' in low:return 'AURA - Lumen 2.0IB_V1'
    match=re.search(r'qwen(2(?:\.5)?)(-coder)?-([0-9._]+b)-instruct',low)
    if match:
        label='Qwen'+match[1]+(' Coder' if match[2] else '')+' · '+match[3].replace('_','.').upper()+' · Q4'
        if match[3] in {'32b','72b'}:label+=' · Experimental'
        return label
    return name[:48]

class MenuButton(QToolButton):
    compact_text=''
    def minimumSizeHint(self):
        hint=super().minimumSizeHint();return QSize(94,hint.height())
    def sizeHint(self):
        hint=super().sizeHint();return QSize(min(250,hint.width()),hint.height())
    def paintEvent(self,event):
        option=QStyleOptionToolButton();self.initStyleOption(option)
        available=max(10,self.width()-38)
        if self.compact_text and self.fontMetrics().horizontalAdvance(option.text)>available:option.text=self.compact_text
        option.text=self.fontMetrics().elidedText(option.text,Qt.TextElideMode.ElideRight,available)
        painter=QStylePainter(self);painter.drawComplexControl(QStyle.ComplexControl.CC_ToolButton,option)

class ChatControls(QWidget):
    model_requested=Signal(str)
    browse_requested=Signal()
    effort_requested=Signal(str)
    settings_requested=Signal()

    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName('chatControls')
        row=QHBoxLayout(self);row.setContentsMargins(0,3,0,3);row.setSpacing(8)
        self.model_button=MenuButton(self);self.model_button.setObjectName('chatModelButton');self.model_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);self.model_button.setMinimumWidth(94);self.model_button.setMaximumWidth(330)
        self.model_menu=QMenu(self);self.model_button.setMenu(self.model_menu)
        self.effort_button=MenuButton(self);self.effort_button.setObjectName('chatEffortButton');self.effort_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.effort_menu=QMenu(self);self.effort_button.setMenu(self.effort_menu)
        self.effort_button.setToolTip('Rápido: breve. Equilibrado: balanceado. Profundo: análisis por pasos (2048 tokens). Máximo: razonamiento extremo (4096 tokens) + contexto ampliado hasta 16K para peticiones complejas o ambiguas.')
        self.settings_button=QToolButton(self);self.settings_button.setText('…');self.settings_button.setFixedWidth(38);self.settings_button.setStyleSheet('padding:5px;');self.settings_button.setToolTip('Contexto y ajustes de rendimiento');self.settings_button.setAccessibleName('Configuración y rendimiento');self.settings_button.clicked.connect(self.settings_requested.emit)
        row.addWidget(self.model_button);row.addWidget(self.effort_button);row.addStretch(1);row.addWidget(self.settings_button)
        self.setStyleSheet('QToolButton{color:#e4eaf4;background:#142238;border:1px solid #294563;border-radius:8px;padding:8px 18px 8px 10px;} QToolButton:hover{background:#213b59;} QToolButton:focus{border:1px solid #8bd2ff;} QToolButton:disabled{color:#a0b1c7;} QMenu{background:#102035;color:#edf4ff;border:1px solid #34506c;padding:5px;} QMenu::item{padding:8px 20px;} QMenu::item:selected{background:#23547a;color:white;} QMenu::separator{height:1px;background:#294563;margin:6px 10px;}')

    def refresh(self,current,paths,effort):
        from .model_library import model_skill_profile
        self.model_button.setText(model_label(current));self.model_button.setToolTip(str(current));self.model_menu.clear();
        if hasattr(self,'models_group'):self.models_group.deleteLater()
        self.models_group=QActionGroup(self.model_menu);self.models_group.setExclusive(True)
        seen=set();grouped={};order=[]
        cur_resolved=Path(current).resolve()
        for path in [Path(current),*[Path(p) for p in paths]]:
            if not path.is_file():continue
            resolved=path.resolve();key=str(resolved)
            if key in seen:continue
            seen.add(key);prof=model_skill_profile(resolved);cat=prof['category']
            if cat not in grouped:grouped[cat]=[];order.append(cat)
            grouped[cat].append((resolved,prof))
        for cat in order:
            self.model_menu.addSection(cat)
            for resolved,prof in grouped[cat]:
                label=model_label(resolved);skills=prof.get('skills','')
                text=f'{label} · {skills}' if skills and prof.get('proven') else label
                action=self.model_menu.addAction(text);action.setCheckable(True);action.setChecked(resolved==cur_resolved);action.setData(str(resolved))
                if skills:action.setToolTip(f'{label}\nHabilidades: {skills}\n{resolved}')
                self.models_group.addAction(action);action.triggered.connect(lambda checked=False,value=str(resolved):self.model_requested.emit(value))
        self.model_menu.addSeparator();self.model_menu.addAction('Buscar otro modelo en la PC…',self.browse_requested.emit)
        self.effort_button.setText('Razonamiento · '+LEVELS[effort]);self.effort_button.compact_text='◌ '+LEVELS[effort];self.effort_button.setAccessibleName('Razonamiento: '+LEVELS[effort]);self.effort_menu.clear();
        if hasattr(self,'effort_group'):self.effort_group.deleteLater()
        self.effort_group=QActionGroup(self.effort_menu);self.effort_group.setExclusive(True)
        for key,label in LEVELS.items():
            action=self.effort_menu.addAction(label);action.setCheckable(True);action.setChecked(key==effort);action.setData(key);self.effort_group.addAction(action);action.triggered.connect(lambda checked=False,value=key:self.effort_requested.emit(value))
