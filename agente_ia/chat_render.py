"""Small cached rich-text transcript with blue user messages."""
from functools import lru_cache
from html import escape
import re
from PySide6.QtGui import QTextDocument,QFont

@lru_cache(maxsize=256)
def markdown_body(content):
    doc=QTextDocument();doc.setDefaultFont(QFont('Segoe UI',10));doc.setMarkdown(content,QTextDocument.MarkdownFeature.MarkdownDialectGitHub|QTextDocument.MarkdownFeature.MarkdownNoHTML)
    body=re.search(r'<body[^>]*>(.*?)</body>',doc.toHtml(),re.S)[1]
    body=re.sub(r'<hr\b[^>]*>','',body,flags=re.I)
    return re.sub(r'<pre[^>]*>', '<pre style="font-family:Consolas;margin-top:0px;margin-bottom:0px;">',body)

def conversation_html(items):
    blocks=[]
    for role,content in items:
        if role=='user':
            text=escape(content).replace('\n','<br>')
            blocks.append('<table align="right" cellspacing="0" cellpadding="12" bgcolor="#1c416b"><tr><td style="color:#f1f6ff">'+text+'</td></tr></table><p><br></p>')
        else:blocks.append('<p style="color:#68dbe5;font-size:9pt;margin-top:18px">AURA</p>'+markdown_body(content)+'<p><br></p>')
    return '<html><body style="color:#e3edf9;font-family:Segoe UI;font-size:10pt">'+''.join(blocks)+'</body></html>'
