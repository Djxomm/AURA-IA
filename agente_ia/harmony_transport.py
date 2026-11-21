"""Minimal Harmony transport for the pinned GPT-oss GGUF. Never displays raw analysis."""
import json
import re
from datetime import datetime
from .providers import ProviderError


def prompt(messages,effort):
    level={'rapido':'low','equilibrado':'medium','profundo':'high'}.get(effort,'medium')
    header='You are ChatGPT, a large language model trained by OpenAI.\nKnowledge cutoff: 2024-06\nCurrent date: '+datetime.now().strftime('%Y-%m-%d')+'\n\nReasoning: '+level+'\n\n# Valid channels: analysis, commentary, final. Channel must be included for every message.'
    output='<|start|>system<|message|>'+header+'<|end|>'
    for message in messages:
        role=message['role'];content=str(message.get('content','')).replace('\r','')
        if role=='system':role='developer'
        if role=='assistant':output+='<|start|>assistant<|channel|>final<|message|>'+content+'<|end|>'
        elif role in ('developer','user'):output+='<|start|>'+role+'<|message|>'+content+'<|end|>'
        else:output+='<|start|>user<|message|>Resultado de herramienta:\n'+content+'<|end|>'
    return output+'<|start|>assistant'


class HarmonyOutput:
    def __init__(self):
        self.pending='';self.header=True;self.channel=None;self.recipient=None;self.tool_body='';self.calls=[];self.seen_final=False;self.completed=False

    def _close_tool(self):
        if self.recipient and self.tool_body.strip():
            try:arguments=json.loads(self.tool_body)
            except ValueError as error:raise ProviderError('GPT-oss devolvió argumentos de herramienta incompletos.') from error
            if not isinstance(arguments,dict):raise ProviderError('Argumentos de herramienta no válidos.')
            self.calls.append({'name':self.recipient,'arguments':arguments})
        self.recipient=None;self.tool_body=''

    def _body(self,text):
        if self.channel=='final':self.seen_final=True;return text
        if self.recipient:
            self.tool_body+=text
            if len(self.tool_body)>512*1024:raise ProviderError('La llamada de herramienta supera el límite.')
        return ''

    def feed(self,text):
        self.pending+=text;output=[]
        while self.pending:
            if self.header:
                match=re.search(r'<\|(?:message|im_sep)\|>',self.pending)
                if not match:
                    if len(self.pending)>4096:raise ProviderError('Cabecera Harmony no válida.')
                    break
                value=self.pending[:match.start()];self.pending=self.pending[match.end():]
                channel=re.search(r'<\|(?:channel|meta_sep)\|>(\w+)',value)
                recipient=re.search(r'\bto=functions\.([a-zA-Z_][a-zA-Z0-9_]*)',value)
                self.channel=channel[1] if channel else None;self.recipient=recipient[1] if recipient else None;self.header=False
                continue
            start=self.pending.find('<|')
            if start<0:
                keep=1 if self.pending.endswith('<') else 0
                value=self.pending[:-keep] if keep else self.pending
                output.append(self._body(value));self.pending=self.pending[-keep:] if keep else '';break
            output.append(self._body(self.pending[:start]));self.pending=self.pending[start:]
            end=self.pending.find('|>')
            if end<0:break
            marker=self.pending[:end+2];self.pending=self.pending[end+2:]
            if marker=='<|start|>':self._close_tool();self.header=True;self.channel=None
            elif marker in ('<|end|>','<|call|>','<|ghissue|>'):
                self._close_tool();self.channel=None
            elif marker in ('<|return|>','<|fim_suffix|>'):
                self._close_tool();self.channel=None;self.completed=True
            else:output.append(self._body(marker))
        return ''.join(output)

    def finish(self):
        text=''
        if self.pending:
            if not self.header and not self.pending.startswith('<|'):text=self._body(self.pending)
            self.pending=''
        self._close_tool()
        if not self.seen_final and not self.calls:
            raise ProviderError('GPT-oss no terminó una respuesta final. Aumenta la longitud de respuesta o divide la tarea; no se mostró su análisis interno.')
        for call in self.calls:text+='<tool_call>'+json.dumps(call,ensure_ascii=False)+'</tool_call>'
        return text
