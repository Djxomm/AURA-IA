import sys
from pathlib import Path
import pytest
from agente_ia.project_actions import requested_actions,choose_target,ProjectRunner,Command


def test_explicit_commands_and_not_explanations():
    assert requested_actions('compila y ejecuta main.py')==['build','run']
    assert requested_actions('Puedes compilarlo y probamos')==['build','test']
    assert requested_actions('prueba main.py')==['test']
    assert requested_actions('¿Por qué no compila?')==[]
    assert requested_actions('No compiles todavía')==[]
    assert requested_actions('```\ncompila main.py\n```')==[]


def test_project_paths_are_explicit_and_bounded(tmp_path):
    (tmp_path/'main.py').write_text('print(42)')
    assert choose_target(tmp_path,'compila main.py').name=='main.py'
    with pytest.raises(ValueError):choose_target(tmp_path,'compila missing.py')
    from agente_ia.workspace import WorkspaceError
    with pytest.raises(WorkspaceError):choose_target(tmp_path,'compila ../outside.py')


def test_real_process_output_and_failure(tmp_path,monkeypatch):
    from agente_ia import project_actions
    (tmp_path/'main.py').write_text('print(42)')
    monkeypatch.setattr(project_actions,'plan',lambda *args:[Command(Path(sys.executable),['-I','-c','print("REAL 42")'],tmp_path,'Prueba')])
    output=[];runner=ProjectRunner(tmp_path/'runtime')
    result=runner.run(tmp_path,'ejecuta main.py',['run'],on_output=output.append)
    assert result['status']=='done' and 'REAL 42' in result['content']
    assert any('REAL 42' in line for line in output)
    monkeypatch.setattr(project_actions,'plan',lambda *args:[Command(Path(sys.executable),['-I','-c','raise SystemExit(3)'],tmp_path,'Prueba')])
    result=runner.run(tmp_path,'ejecuta main.py',['run'])
    assert result['status']=='error' and result['commands'][0]['exit_code']==3


def test_build_requires_real_artifact(tmp_path,monkeypatch):
    from agente_ia import project_actions
    (tmp_path/'main.py').write_text('print(42)')
    monkeypatch.setattr(project_actions,'plan',lambda *args:[Command(Path(sys.executable),['-I','-c','print("no artifact")'],tmp_path,'Compilar',artifact=tmp_path/'dist/main.exe')])
    result=ProjectRunner(tmp_path).run(tmp_path,'compila main.py',['build'])
    assert result['status']=='error'
