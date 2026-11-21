"""Native rounded message bubbles with incremental streaming updates."""
import math
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QScrollArea,QWidget,QVBoxLayout,QHBoxLayout,QFrame,QTextBrowser,QSizePolicy
from .chat_render import markdown_body

class Bubble(QFrame):
    def __init__(self,role,content,parent=None):
        super().__init__(parent);self.role=role;self.content='';self.width_cap=600;self.setObjectName('userBubble' if role=='user' else 'auraBubble')
        background='#d9dfe7' if role=='user' else '#14283f';foreground='#142238' if role=='user' else '#e7eff9'
        self.setStyleSheet('QFrame#'+self.objectName()+'{background:'+background+';border:0;border-radius:10px;} QTextBrowser{background:transparent;color:'+foreground+';border:0;padding:0;selection-background-color:#316a98;selection-color:white;}')
        layout=QVBoxLayout(self);layout.setContentsMargins(10,6,10,6);self.body=QTextBrowser();self.body.setFrameShape(QFrame.Shape.NoFrame);self.body.setOpenLinks(False);self.body.setOpenExternalLinks(False);self.body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded);self.body.setAccessibleName('Tu mensaje' if role=='user' else 'Respuesta de AURA');self.body.document().setDocumentMargin(0);layout.addWidget(self.body)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Fixed);self.body.document().documentLayout().documentSizeChanged.connect(lambda size:self.fit_height());self.set_content(content)
    def set_content(self,content):
        self.content=content
        if self.role=='user':self.body.setPlainText(content)
        else:self.body.setHtml(markdown_body(content))
        self.fit_width(self.width_cap);QTimer.singleShot(0,self.fit_height)
    def fit_width(self,cap):
        self.width_cap=cap
        width=max((self.body.fontMetrics().horizontalAdvance(line) for line in self.body.toPlainText().splitlines()),default=20)+24
        self.setFixedWidth(min(cap,max(40,width)))
    def append_text(self,text):
        self.content+=text;self.body.moveCursor(QTextCursor.MoveOperation.End);self.body.insertPlainText(text);self.fit_width(self.width_cap);self.fit_height()
    def fit_height(self):
        height=max(20,math.ceil(self.body.document().size().height())+4)
        if self.body.document().idealWidth()>self.body.viewport().width()+1:height+=self.body.horizontalScrollBar().sizeHint().height()
        if self.body.height()!=height:self.body.setFixedHeight(height)
        if self.height()!=height+12:self.setFixedHeight(height+12)
    def resizeEvent(self,event):super().resizeEvent(event);QTimer.singleShot(0,self.fit_height)

class ChatView(QScrollArea):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWidgetResizable(True);self.setFrameShape(QFrame.Shape.NoFrame);self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.rows=[];self.bubbles=[];self.welcome=None
        self.content=QWidget();self.content.setObjectName('chatTranscript');self.layout=QVBoxLayout(self.content);self.layout.setContentsMargins(18,16,18,16);self.layout.setSpacing(10);self.layout.setAlignment(Qt.AlignmentFlag.AlignTop);self.setWidget(self.content);self.setStyleSheet('QScrollArea{background:#0b1424;border:0;} QWidget#chatTranscript{background:#0b1424;}')
    def clear_rows(self):
        while self.layout.count():
            item=self.layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.rows=[];self.bubbles=[];self.welcome=None
    def set_welcome(self,html):
        self.clear_rows();self.welcome=QTextBrowser();self.welcome.setFrameShape(QFrame.Shape.NoFrame);self.welcome.setStyleSheet('background:transparent;border:0;color:#e7eff9;');self.welcome.setHtml(html);self.welcome.setMinimumHeight(280);self.layout.addWidget(self.welcome)
    def set_messages(self,items):
        if self.welcome is not None or len(items)<len(self.bubbles) or any(bubble.role!=items[i][0] for i,bubble in enumerate(self.bubbles[:len(items)])):self.clear_rows()
        for index,(role,text) in enumerate(items):
            if index<len(self.bubbles):
                if self.bubbles[index].content!=text:self.bubbles[index].set_content(text)
            else:
                row=QWidget();row.setStyleSheet('background:transparent;');layout=QHBoxLayout(row);layout.setContentsMargins(0,0,0,0);bubble=Bubble(role,text,row)
                if role=='user':layout.addStretch(1)
                layout.addWidget(bubble)
                if role!='user':layout.addStretch(1)
                self.layout.addWidget(row);self.rows.append(row);self.bubbles.append(bubble)
        self.fit_widths();self.scroll_to_end()
    def fit_widths(self):
        available=max(120,self.viewport().width()-38)
        for bubble in self.bubbles:bubble.fit_width(max(90,int(available*(.80 if bubble.role=='user' else .96))))
    def append_to_last(self,text):
        if self.bubbles:self.bubbles[-1].append_text(text);self.scroll_to_end()
    def scroll_to_end(self):QTimer.singleShot(0,self._scroll_end)
    def _scroll_end(self):self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
    def resizeEvent(self,event):super().resizeEvent(event);self.fit_widths()
