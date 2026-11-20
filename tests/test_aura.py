import asyncio,json,time
from pathlib import Path
import httpx,pytest
from fastapi.testclient import TestClient
from agente_ia.config import AppSettings
from agente_ia.model_manager import ModelManager
from agente_ia.storage import Storage
from agente_ia.providers import LocalLLMClient,ProviderError
from agente_ia.web_server import create_app

class FakeBackend:
    token='secret-not-for-ui'
    url='http://127.0.0.1:19091/v1'
    def __init__(self):self.loaded=[];self.running=False;self.peak=0
    def start(self,path,settings):
        self.stop()
        if path.name=='bad.gguf':raise ValueError('incompatible')
        self.running=True;self.peak=max(self.peak,1);self.loaded.append(path.name)
        return {'model':'aura-local','reasoning_supported':False,'url':self.url}
    def stop(self):self.running=False
    def close(self):self.stop()

def manager_fixture(tmp_path):
    base=tmp_path/'app';(base/'modelos').mkdir(parents=True)
    (base/'modelos/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf').write_bytes(b'GGUFmodel')
    db=Storage(tmp_path/'data/aura.db');db.save_settings(db.get_settings().model_copy(update={'workspace_path':str(tmp_path),'thinking_effort':'profundo','temperature':.2,'max_steps':8}))
    backend=FakeBackend();manager=ModelManager(base,tmp_path/'data',db,backend)
    manager.start_initial();return manager,db,backend

def finish(manager):
    manager.worker.join(timeout=3);assert not manager.worker.is_alive()

def test_switch_preserves_rules_and_settings_and_rolls_back(tmp_path):
    manager,db,backend=manager_fixture(tmp_path);old=db.get_settings()
    other=tmp_path/'coder3b.gguf';other.write_bytes(b'GGUFnew')
    record=manager.import_model(str(other),'Coder 3B')
    assert manager.import_model(str(other))['id']==record['id']
    manager.change(record['id'],8192,2);finish(manager)
    new=db.get_settings();assert new.local_model_id==record['id'];assert new.num_ctx==8192
    for name in ('workspace_path','thinking_effort','temperature','max_steps'):
        assert getattr(new,name)==getattr(old,name)
    bad=tmp_path/'bad.gguf';bad.write_bytes(b'GGUFbad');bad_id=manager.import_model(str(bad))['id']
    manager.change(bad_id);finish(manager)
    assert manager.status()['phase']=='ready' and manager.status()['warning']
    assert db.get_settings().local_model_id==record['id']
    assert backend.peak==1
    with pytest.raises(ValueError):manager.import_model(str(tmp_path/'no.exe'))
    assert manager.auth_for(backend.url)==backend.token
    assert manager.auth_for('https://example.org/v1')=='local'
    assert backend.token not in json.dumps(manager.status())

def test_model_switch_blocked_during_agent_run(tmp_path):
    manager,db,_=manager_fixture(tmp_path);app=create_app(storage=db,model_manager=manager)
    async def test():
        app.state.registry.register_run('busy')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
            result=await client.post('/api/local-models/load',json={'id':'incluido'})
            assert result.status_code==409
        app.state.registry.cleanup_run('busy')
    asyncio.run(test())

def test_chat_mode_streams_text_without_tools_and_persists(tmp_path):
    captured=[]
    def handler(request):
        captured.append(json.loads(request.content))
        content='data: '+json.dumps({'choices':[{'delta':{'content':'Hola, soy AURA.'}}]})+'\n\ndata: [DONE]\n\n'
        return httpx.Response(200,text=content,headers={'content-type':'text/event-stream'})
    db=Storage(tmp_path/'aura.db');client=LocalLLMClient(transport=httpx.MockTransport(handler));app=create_app(storage=db,llm_client=client)
    with TestClient(app) as api:
        result=api.post('/api/chat/stream',json={'message':'Hola','mode':'chat'})
        assert result.status_code==200 and 'Hola, soy AURA.' in result.text and '"type": "done"' in result.text
        session=api.get('/api/sessions').json()['sessions'][0]
        messages=api.get('/api/sessions/'+session['id']).json()['messages']
        assert [m['role'] for m in messages]==['user','assistant']
        assert messages[-1]['content']=='Hola, soy AURA.'
    assert 'tools' not in captured[0]
    assert 'AURA' in captured[0]['messages'][0]['content']
    assert captured[0]['max_tokens']<4096

def test_output_budget_and_private_engine_authorization():
    captured=[]
    def handler(req):
        captured.append((json.loads(req.content),req.headers['authorization']))
        return httpx.Response(200,text='data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n')
    async def run():
        settings=AppSettings(max_predict_tokens=2048)
        client=LocalLLMClient(transport=httpx.MockTransport(handler),auth_provider=lambda base:'private-key')
        await client.stream_chat(settings,[{'role':'user','content':'a'*7000}],[])
        body,auth=captured[0]
        assert 32<=body['max_tokens']<600 and auth=='Bearer private-key'
        with pytest.raises(ProviderError):await client.stream_chat(settings,[{'role':'user','content':'a'*20000}],[])
    asyncio.run(run())

def test_ui_no_remote_runtime_dependencies_and_branding():
    static=Path(__file__).resolve().parents[1]/'agente_ia/static'
    html=(static/'index.html').read_text('utf-8')
    assert 'generativelanguage.googleapis.com' not in html and 'cdn.tailwindcss.com' not in html
    assert '/static/assets/aura-inicio.mp4' in html
    assert '/static/assets/aura-portada.png' in html and '/static/assets/aura-icono.png' in html
    assert 'AURA' in html and '/static/aura.js' in html
