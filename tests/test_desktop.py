import asyncio
import json
from pathlib import Path
import httpx
from fastapi.testclient import TestClient
from agente_ia.config import AppSettings
from agente_ia.desktop_api import execute_command
from agente_ia.providers import LocalLLMClient
from agente_ia.storage import Storage
from agente_ia.web_server import create_app

def test_terminal_requires_confirmation_and_blocks_external_origin(tmp_path):
    storage = Storage(tmp_path/'test.db')
    storage.save_settings(storage.get_settings().model_copy(update={'workspace_path':str(tmp_path)}))
    with TestClient(create_app(storage=storage)) as client:
        assert client.post('/api/terminal/run',json={'command':'echo hola'}).status_code == 422
        assert client.post('/api/terminal/run',json={'command':'echo hola','confirmed':False}).status_code == 422
        assert client.post('/api/terminal/run',json={'command':'echo hola','confirmed':True},headers={'Origin':'https://external.example'}).status_code == 403
        result = client.post('/api/terminal/run',json={'command':'echo codigo-local','confirmed':True}).json()
        assert result['exit_code'] == 0
        assert 'codigo-local' in result['output']
        assert result['workspace'] == str(tmp_path)

def test_zero_budget_uses_available_context():
    bodies=[]
    def handler(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200,text='data: '+json.dumps({'choices':[{'delta':{'content':'ok'}}]})+'\n\ndata: [DONE]\n\n',headers={'content-type':'text/event-stream'})
    async def run():
        settings=AppSettings(provider='llamacpp',tool_mode='xml',max_predict_tokens=0)
        assert settings.num_gpu == 0
        await LocalLLMClient(transport=httpx.MockTransport(handler)).stream_chat(settings,[{'role':'user','content':'hola'}],[])
        assert 0 < bodies[0]['max_tokens'] < settings.num_ctx
        assert bodies[0]['max_tokens'] == 512
    asyncio.run(run())

def test_command_timeout(tmp_path):
    result=asyncio.run(execute_command('ping -n 10 127.0.0.1',str(tmp_path),timeout=0.2))
    assert result['timed_out'] is True
