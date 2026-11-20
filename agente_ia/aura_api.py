"""AURA conversation mode, inference settings and model-management endpoints."""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
from typing import Literal
from fastapi import HTTPException, Query
from pydantic import BaseModel, Field


def effort_instruction(settings):
    text={
        'rapido':'Prioriza una respuesta breve y directa. Comprueba lo esencial sin agregar pasos innecesarios.',
        'equilibrado':'Responde con precisión y claridad. Comprueba las suposiciones relevantes y explica brevemente el resultado.',
        'profundo':'Revisa con cuidado supuestos y casos límite antes de responder. Presenta el resultado y un resumen breve de comprobaciones, sin exponer razonamiento privado.'
    }[settings.thinking_effort]
    if not settings.show_explanation:text+=' Entrega solo el resultado, salvo que el usuario pida explicaciones.'
    return text

def conversation_system_prompt(settings):
    return 'Eres AURA, asistente local en español. Ayuda con claridad y honestidad. En Conversación no puedes modificar archivos ni ejecutar comandos; usa Programación para eso. '+effort_instruction(settings)

async def conversation_turn(db, client, session_id, message, settings, emit):
    history=[m for m in db.get_messages(session_id,limit=6) if m['role'] in ('user','assistant') and m.get('content')]
    db.add_message(session_id,'user',message,metadata={'mode':'chat'})
    session=db.get_session(session_id)
    if session and session['title'] in ('Nueva sesión','Nueva conversación'):
        db.update_session(session_id,title=' '.join(message.split())[:55])
    messages=[{'role':'system','content':conversation_system_prompt(settings)}]
    recent=[{'role':m['role'],'content':m['content']} for m in history]
    while recent and (sum(len(m['content']) for m in recent)+len(message))>settings.num_ctx:
        recent.pop(0)
    messages.extend(recent);messages.append({'role':'user','content':message})
    await emit('phase',{'message':'Preparando contexto y generando respuesta local…'})
    async def token(piece):await emit('token',{'delta':piece})
    response=await client.stream_chat(settings.model_copy(update={'tool_mode':'native'}),messages,[],on_token=token)
    if not response.content.strip():raise ValueError('El modelo terminó sin texto. Prueba una conversación nueva o revisa el modelo en Ajustes.')
    db.add_message(session_id,'assistant',response.content,metadata={'mode':'chat','tokens_generated':response.tokens_generated,'elapsed_ms':response.elapsed_ms})
    await emit('done',{'content':response.content,'tokens_generated':response.tokens_generated,'elapsed_ms':response.elapsed_ms,'tok_per_sec':response.tok_per_sec})

class ModelImport(BaseModel):
    path: str=Field(min_length=1,max_length=2000)
    name: str=Field(default='',max_length=100)
class ModelLoad(BaseModel):
    id: str=Field(min_length=1,max_length=100)
    context: int | None=None
    threads: int | None=None


def register_aura_routes(app,db):
    def manager():
        value=app.state.model_manager
        if value is None:raise HTTPException(503,'El gestor local se inicia desde AURA.exe.')
        return value
    @app.get('/api/aura/status')
    async def status():
        m=app.state.model_manager
        return {'brand':'AURA Inteligencia Artificial','engine':m.status() if m else {'phase':'ready','detail':'Motor externo'},'busy':app.state.registry.has_active_runs,'settings':db.get_settings().model_dump()}
    @app.get('/api/local-models')
    async def models():
        m=manager()
        return {'models':m.catalog(),'state':m.status(),'recommendations':[
            {'name':'Qwen2.5 Coder 3B Instruct GGUF','url':'https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF','note':'Más capacidad que el incluido; será más lento en el i5 antiguo.'},
            {'name':'Qwen2.5 Coder 7B Instruct GGUF','url':'https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF','note':'Modelo considerablemente más pesado; para este equipo conviene probarlo con cautela o usar otro PC.'}
        ]}
    @app.post('/api/local-models/import')
    async def import_model(payload: ModelImport):
        try:return {'model':manager().import_model(payload.path,payload.name)}
        except (ValueError,OSError) as exc:raise HTTPException(400,str(exc)) from exc
    @app.post('/api/local-models/load')
    async def load(payload: ModelLoad):
        if app.state.registry.has_active_runs:raise HTTPException(409,'Detén o termina la respuesta antes de cambiar de modelo.')
        try:return manager().change(payload.id,payload.context,payload.threads)
        except (ValueError,OSError) as exc:raise HTTPException(400,str(exc)) from exc
    @app.get('/api/local-models/browse')
    async def browse(path: str | None=Query(None,max_length=2000)):
        m=manager();target=Path(path or m.base/'modelos').expanduser().resolve()
        if not target.is_dir():raise HTTPException(400,'La carpeta no existe.')
        entries=[]
        try:
            for item in sorted(target.iterdir(),key=lambda p:(not p.is_dir(),p.name.lower())):
                if len(entries)>=200:break
                if item.is_dir() and not item.name.startswith(('.', '$')) or item.is_file() and item.suffix.lower()=='.gguf':
                    entries.append({'name':item.name,'path':str(item),'directory':item.is_dir()})
        except OSError as exc:raise HTTPException(403,'No se puede leer esa carpeta.') from exc
        drives=[f'{letter}:\\' for letter in 'CDEFGHIJKLMNOPQRSTUVWXYZ' if Path(f'{letter}:\\').is_dir()] if os.name=='nt' else ['/']
        return {'path':str(target),'parent':str(target.parent),'entries':entries,'drives':drives}
