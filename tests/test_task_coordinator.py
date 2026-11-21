from agente_ia.task_coordinator import TaskCoordinator, bounded_conversation
from agente_ia.tools import estimate_tokens


def test_checkpoint_survives_restart_and_keeps_project_boundary(tmp_path):
    path=tmp_path/'tasks.db';a=TaskCoordinator(path)
    state=a.begin('one','project-a','Crea un inventario con SQLite')
    a.event('one','project-a',state,'proposal_resolved',{'status':'applied','file_path':'inventory.py'})
    a.event('one','project-a',state,'tool_result',{'summary':'Sintaxis válida; sin prueba de ejecución'})
    b=TaskCoordinator(path);resumed=b.begin('one','project-a','continúa')
    assert resumed['objective']=='Crea un inventario con SQLite'
    assert resumed['files']==['inventory.py']
    assert 'sin prueba' in resumed['evidence'][0]
    b.execution('one','project-a','build','inventory.py',1)
    resumed=b.begin('one','project-a','continúa')
    assert 'salida 1' in resumed['evidence'][-1]
    assert b.begin('one','project-b','continúa')['files']==[]
    assert b.begin('one','project-b','Crea un juego')['objective']=='Crea un juego'


def test_context_keeps_current_request_and_complete_tool_exchanges():
    messages=[{'role':'system','content':'Reglas'}, {'role':'user','content':'Viejo'*1000},
              {'role':'assistant','content':'Anterior'*1000}, {'role':'user','content':'Corrige main.py'},
              {'role':'assistant','content':'Leer','tool_calls':[{'id':'one'}]},
              {'role':'tool','tool_call_id':'one','content':'Código'*1000},
              {'role':'assistant','content':'Aplicar','tool_calls':[{'id':'two'}]},
              {'role':'tool','tool_call_id':'two','content':'Cambio guardado'}]
    result=bounded_conversation(messages,500)
    assert result[1]['content']=='Corrige main.py'
    assert estimate_tokens(result)<=500
    assert [x['role'] for x in result]==['system','user','assistant','tool']
    assert result[-1]['tool_call_id']=='two'


def test_gpu_selection_and_cpu_fallback(tmp_path,monkeypatch):
    from agente_ia import acceleration
    monkeypatch.setattr(acceleration,'devices',lambda root:[('Vulkan0','Intel UHD',8000),('Vulkan1','NVIDIA GeForce GTX 1060',6000)])
    engine,args,note=acceleration.backend(tmp_path,tmp_path,'auto')
    assert engine.name=='motor-vulkan' and args==['--device','Vulkan1','-ngl','28']
    assert acceleration.backend(tmp_path,tmp_path,'cpu')[0].name=='motor'
    monkeypatch.setattr(acceleration,'devices',lambda root:[('Vulkan0','Intel UHD',8000)])
    assert acceleration.backend(tmp_path,tmp_path,'auto')[0].name=='motor'
    assert acceleration.backend(tmp_path,tmp_path,'vulkan')[1][-1]=='12'


def test_inference_retries_cpu_only_before_output(tmp_path,monkeypatch):
    import pytest
    from agente_ia import acceleration
    from agente_ia.native_core import NativeClient
    from agente_ia.providers import ProviderError
    monkeypatch.setattr(acceleration,'backend',lambda *args:(tmp_path/'motor-vulkan',['--device','Vulkan0','-ngl','12'],'Intel'))
    client=NativeClient(tmp_path,tmp_path/'data');calls=[]
    def fake(settings,messages,callback,use_cache,engine,gpu_args):
        calls.append(engine.name)
        if gpu_args:raise ProviderError('Controlador no disponible')
        return 'Correcto',1
    monkeypatch.setattr(client,'_generate',fake)
    assert client.generate(None,[],lambda text:None)[0]=='Correcto'
    assert calls==['motor-vulkan','motor']
    def partial(*args):
        client.first_text=.2
        raise ProviderError('Interrumpido después de texto')
    monkeypatch.setattr(client,'_generate',partial)
    with pytest.raises(ProviderError):client.generate(None,[],lambda text:None)
