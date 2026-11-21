import asyncio
import json
import httpx
import pytest
from agente_ia.agent import AgentEngine, ApprovalRegistry, ApprovalDecision
from agente_ia.config import AppSettings
from agente_ia.providers import LocalLLMClient
from agente_ia.storage import Storage
from agente_ia.workspace import SafeWorkspace
from agente_ia.code_artifacts import file_task_requested, task_brief, expected_language, code_proposal

HTML = '<!doctype html><html><body><canvas></canvas><script>let level=1;</script></body></html>'

def test_language_refinement_and_continuation():
    history=[{'role':'user','content':'hola hasme un juego en 2d de carreras de autos'}, {'role':'assistant','content':'```python\n# ...'}, {'role':'user','content':'has el guego de 10 niveles en jaba script para html'}]
    assert file_task_requested('continua',history)
    assert expected_language(task_brief(history,'continua'))=='html'
    assert not file_task_requested('Explícame cómo crear un juego')
    assert not file_task_requested('no crees un juego')

@pytest.mark.parametrize('body', ['```python\n# ...\n```','```html\n<html><script>','Ideas para tu juego','```python\nprint(1)\n```'])
def test_incomplete_or_wrong_language_not_saved(tmp_path,body):
    with pytest.raises(ValueError):code_proposal(body,'html',SafeWorkspace(str(tmp_path)))
    assert not list(tmp_path.iterdir())

@pytest.mark.parametrize('approved',[True,False])
def test_code_becomes_reviewable_file_and_respects_rejection(tmp_path,approved):
    async def scenario():
        calls=0
        async def respond(request):
            nonlocal calls
            calls+=1
            return httpx.Response(200,text=json.dumps({'message':{'role':'assistant','content':'```html\n'+HTML+'\n```'},'done':True})+'\n')
        store=Storage(':memory:')
        client=LocalLLMClient(transport=httpx.MockTransport(respond))
        engine=AgentEngine(store,client,ApprovalRegistry())
        session=store.create_session(title='Test',workspace_path=str(tmp_path),provider='ollama',model='test')
        async def approve(proposal):
            assert not (tmp_path/'index.html').exists()
            return ApprovalDecision(approved=approved)
        async def emit(name,data):pass
        result=await engine.run_turn(session_id=session['id'],user_message='Hazme un juego HTML',settings=AppSettings(workspace_path=str(tmp_path),provider='ollama',model='test'),emit=emit,approval_handler=approve)
        assert result['status']=='done'
        assert calls==1
        assert (tmp_path/'index.html').exists()==approved
    asyncio.run(scenario())

def test_no_false_success_after_incomplete_answers(tmp_path):
    async def scenario():
        async def respond(request):return httpx.Response(200,text=json.dumps({'message':{'role':'assistant','content':'Aquí tienes ideas para programarlo.'},'done':True})+'\n')
        store=Storage(':memory:');client=LocalLLMClient(transport=httpx.MockTransport(respond))
        engine=AgentEngine(store,client,ApprovalRegistry())
        session=store.create_session(title='Test',workspace_path=str(tmp_path),provider='ollama',model='test')
        async def emit(name,data):pass
        result=await engine.run_turn(session_id=session['id'],user_message='Hazme un juego HTML',settings=AppSettings(workspace_path=str(tmp_path),provider='ollama',model='test'),emit=emit)
        assert result['status']=='incomplete'
        assert not (tmp_path/'index.html').exists()
    asyncio.run(scenario())

def test_windows_output_does_not_duplicate_carriage_returns():
    from agente_ia.native_core import NativeOutputFilter
    output=NativeOutputFilter()
    actual=''.join(output.feed(chunk) for chunk in ['hola\r','\r\n','mundo\r\r\r\n'])+output.finish()
    assert actual=='hola\nmundo\n'


def test_explicit_filename_is_preserved_in_recovered_proposal(tmp_path):
    from agente_ia.code_artifacts import requested_code_path
    path=requested_code_path('Crea utilidades/total.py con una función de suma.','python')
    assert path=='utilidades/total.py'
    name,args=code_proposal('```python\ndef sumar(a,b): return a+b\n```','python',SafeWorkspace(str(tmp_path)),preferred_path=path)
    assert name=='create_file' and args['path']==path


def test_explicit_edit_request_uses_real_file_workflow():
    from agente_ia.code_artifacts import file_task_requested
    assert file_task_requested('Ajusta total.py para rechazar cantidades negativas')
    assert file_task_requested('Corrige src/app.js: no abre la ventana')
    assert not file_task_requested('Explícame cómo funciona total.py')
