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


def test_context_adaptive_skill_limits_and_large_markdown_import(tmp_path):
    from agente_ia.skills import max_enabled_for_context, read_chunk_for_context, MAX_FILE_BYTES_IMPORT
    assert max_enabled_for_context(2048) == 4
    assert max_enabled_for_context(4096) == 6
    assert max_enabled_for_context(8192) == 8
    assert max_enabled_for_context(16384) == 10
    assert max_enabled_for_context(32768) == 12
    assert read_chunk_for_context(8192) == 2400
    assert read_chunk_for_context(16384) == 3200
    assert MAX_FILE_BYTES_IMPORT == 512 * 1024

    # Archivo > 128 KB (antes rechazado) ahora se importa limpio hasta 512 KB
    folder = tmp_path / 'grande'
    (folder / 'references').mkdir(parents=True)
    (folder / 'SKILL.md').write_text('---\nname: Habilidad Grande\ndescription: prueba 200KB\n---\nContenido', encoding='utf-8')
    (folder / 'references' / 'manual.md').write_text('X' * (220 * 1024), encoding='utf-8')
    store = SkillStore(tmp_path / 'store')
    sid = store.import_directory(folder)
    assert store.get(sid)['bytes'] > 200 * 1024

    # Límite dinámico de 8 activas para contexto 8192
    store.enable(sid, True, max_enabled=8)
    for i in range(7):
        s = store.add(f'name: Extra {i}\nGuia {i}')
        store.enable(s, True, max_enabled=8)
    s9 = store.add('name: Novena\nGuia 9')
    with pytest.raises(ValueError):
        store.enable(s9, True, max_enabled=8)
    assert len(store.manifest(max_enabled=8).splitlines()) >= 9


def test_bundled_rea_skill_complete_and_reasoning_effort(tmp_path):
    from agente_ia.aura_api import effort_instruction
    from agente_ia.native_core import conversation_prompt
    rea_dir = Path('D:/IA/AURA_IA/runtime/skills/reverse-engineer-anything')
    if rea_dir.is_dir():
        store = SkillStore(tmp_path / 'skills')
        sid = store.install_bundled(rea_dir.parent, 'reverse-engineer-anything')
        rec = store.get(sid)
        assert rec is not None and len(rec['files']) == 8
        store.enable(sid, True, max_enabled=8)
        head = store.read(sid, chunk_chars=2400)
        assert len(head['available_files']) == 8
        ref = store.read(sid, file='references/native-and-artifacts.md', chunk_chars=2400)
        assert len(ref['content']) > 1000
    prof = effort_instruction(AppSettings(thinking_effort='profundo'))
    assert 'pasos' in prof and 'casos límite' in prof and 'read_file' in prof
    assert 'pasos' in conversation_prompt(AppSettings(thinking_effort='profundo'))
