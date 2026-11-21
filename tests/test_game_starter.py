import asyncio
from agente_ia.agent import AgentEngine,ApprovalRegistry,ApprovalDecision
from agente_ia.storage import Storage
from agente_ia.config import AppSettings


def test_native_racing_starter_creates_reviewed_file_not_generic_advice(tmp_path):
    runtime=tmp_path/'runtime';template=runtime/'games/panda3d/main.py';template.parent.mkdir(parents=True);template.write_text('print("prototipo")')
    project=tmp_path/'project';project.mkdir()
    class Client:
        async def stream_chat(self,**kwargs):raise AssertionError('No se necesita generación para copiar la plantilla')
    client=Client();client.runtime=runtime
    store=Storage(':memory:');session=store.create_session(workspace_path=str(project),provider='nativo',model='test');engine=AgentEngine(store,client,ApprovalRegistry())
    async def approve(proposal):
        assert not (project/'main.py').exists()
        return ApprovalDecision(True)
    result=asyncio.run(engine.run_turn(session_id=session['id'],user_message='Crea un juego 3D de carreras con árboles y coches',settings=AppSettings(workspace_path=str(project)),approval_handler=approve))
    assert result['status']=='done' and (project/'main.py').read_text()=='print("prototipo")'
