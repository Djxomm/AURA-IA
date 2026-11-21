import json
import xml.etree.ElementTree as ET
from pathlib import Path
import pytest
from agente_ia.windows_isolation import prepare
from agente_ia.project_actions import ProjectRunner


def test_isolated_configuration_maps_copy_not_original_and_disables_network(tmp_path):
    project=tmp_path/'project';project.mkdir();(project/'main.py').write_text('print(42)');(project/'.env').write_text('PRIVATE');(project/'data.db').write_text('PRIVATE')
    runtime=tmp_path/'runtime';(runtime/'herramientas/python').mkdir(parents=True)
    config,output=prepare(runtime,project,'compila main.py',['build'],'main.py',tmp_path/'jobs')
    tree=ET.parse(config).getroot();assert tree.findtext('Networking')=='Disable' and tree.findtext('ClipboardRedirection')=='Disable'
    assert tree.findtext('vGPU')=='Disable' and tree.findtext('ProtectedClient')=='Enable'
    folders=tree.findall('MappedFolders/MappedFolder');assert len(folders)==4
    assert all(Path(item.findtext('HostFolder'))!=project for item in folders)
    assert sum(item.findtext('ReadOnly')=='false' for item in folders)==1
    assert (config.parent/'input/main.py').exists() and not (config.parent/'input/.env').exists() and not (config.parent/'input/data.db').exists()
    assert json.loads((config.parent/'job.json').read_text())['original_project_mapped'] is False


def test_isolation_never_falls_back_to_normal_execution(tmp_path,monkeypatch):
    from agente_ia import windows_isolation
    monkeypatch.setattr(windows_isolation,'executable',lambda:None)
    with pytest.raises(ValueError,match='No ejecuté la tarea en modo normal'):
        ProjectRunner(tmp_path).run(tmp_path,'compila aislado main.py',['build'])
