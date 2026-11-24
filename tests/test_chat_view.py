import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from agente_ia.chat_view import ChatView
from agente_ia.chat_render import markdown_body

def test_one_bubble_per_message_and_streaming_reuses_previous_messages():
 app=QApplication.instance() or QApplication([]);chat=ChatView();chat.resize(480,500);chat.show();chat.set_messages([('user','Hola'),('assistant','Respuesta\n\n---\n\nMás texto')]);app.processEvents()
 assert len(chat.bubbles)==2 and '<hr' not in markdown_body('Respuesta\n\n---\n\nMás texto').lower()
 assert '#162339' in chat.bubbles[0].styleSheet() and '#0f1625' in chat.bubbles[1].styleSheet()
 first=chat.bubbles[0];chat.append_to_last(' adicional');app.processEvents();assert chat.bubbles[0] is first
 assert chat.bubbles[-1].body.toPlainText().endswith(' adicional')
 assert chat.bubbles[0].width()<chat.bubbles[1].width()
 chat.set_messages([('user','Hola'),('assistant','Respuesta final')]);app.processEvents();assert chat.bubbles[0] is first
 assert chat.horizontalScrollBar().maximum()==0
 chat.close();chat.deleteLater();app.processEvents()
