import asyncio
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from agente_ia.skills import SkillStore
from agente_ia.storage import Storage
from agente_ia.web_server import create_app
from agente_ia.agent import AgentEngine, ApprovalRegistry
from agente_ia.providers import LocalLLMClient, ToolCall
from agente_ia.config import AppSettings
from agente_ia.workspace import SafeWorkspace, WorkspaceSecurityError
from agente_ia.binary_inspection import inspect_binary

def test_catalog_is_metadata_only_and_chunk_reading(tmp_path):
    store=SkillStore(tmp_path/'skills')
    content='---\nname: Pruebas\ndescription: guía de calidad\n---\n'+'A'*4000+'\nCONTRASTE\nFin'
    sid=store.add(content)
    assert store.add(content)==sid
    assert 'content' not in store.catalog()[0]
    assert all('content' not in r for r in json.loads((tmp_path/'skills'/'index.json').read_text('utf-8')))
    assert store.manifest()==''
    with pytest.raises(ValueError): store.read(sid)
    store.enable(sid,True)
    assert 'Pruebas' in store.manifest() and 'CONTRASTE' not in store.manifest()
    first=store.read(sid)
    assert len(first['content'])==1600 and first['next_offset']==1600
    assert 'CONTRASTE' in store.read(sid,query='contraste')['content']
    with pytest.raises(ValueError): store.read('../secreto')
    store.delete(sid);assert store.catalog()==[]

def test_activation_limit_and_defaults_once(tmp_path):
    store=SkillStore(tmp_path/'skills');defaults=tmp_path/'defaults';defaults.mkdir()
    (defaults/'programacion.md').write_text('# Programación',encoding='utf-8')
    store.install_defaults(defaults);store.install_defaults(defaults)
    assert len(store.catalog())==1
    for i in range(4):
        sid=store.add(f'name: Habilidad {i}\nContenido {i}');store.enable(sid,True)
    sid=store.add('name: Quinta\ncontenido')
    with pytest.raises(ValueError): store.enable(sid,True)

def test_api_and_agent_tool(tmp_path):
    storage=Storage(tmp_path/'app.db');storage.save_settings(storage.get_settings().model_copy(update={'workspace_path':str(tmp_path)}))
    app=create_app(storage=storage)
    with TestClient(app) as client:
        sid=client.post('/api/skills',json={'content':'name: Diseño\nRevisar CONTRASTE de botones.'}).json()['id']
        assert client.put('/api/skills/'+sid,json={'enabled':True}).status_code==200
        assert 'content' not in client.get('/api/skills').json()['skills'][0]
        ok,output,_=app.state.engine._execute_read_tool(SafeWorkspace(str(tmp_path)),ToolCall('s1','read_skill',{'id':sid,'query':'CONTRASTE'}),AppSettings())
        assert ok and 'CONTRASTE' in output
        ok,output,_=app.state.engine._execute_read_tool(SafeWorkspace(str(tmp_path)),ToolCall('s2','read_skill',{'id':'0'*24}),AppSettings())
        assert not ok
        assert client.delete('/api/skills/'+sid).status_code==200
        assert client.post('/api/skills',json={'content':'x'*524289}).status_code==422

def test_binary_inspection_is_read_only_and_scoped(tmp_path):
    target=tmp_path/'sample.bin';target.write_bytes(b'Hello world strings\x00another message')
    before=target.read_bytes();report=inspect_binary(SafeWorkspace(str(tmp_path)),'sample.bin')
    assert not report['executed'] and report['size']==len(before)
    assert report['strings_sample'][0]=='Hello world strings'
    assert target.read_bytes()==before
    with pytest.raises(WorkspaceSecurityError):inspect_binary(SafeWorkspace(str(tmp_path)),'../escape.exe')
    target.write_bytes(b'MZbroken')
    with pytest.raises(ValueError): inspect_binary(SafeWorkspace(str(tmp_path)),'sample.bin')
