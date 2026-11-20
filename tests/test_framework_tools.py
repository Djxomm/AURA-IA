import json
from pathlib import Path
import pytest
from agente_ia.framework_tools import create_template,find_web_project,npm_command


def make_project(root, framework='react', scripts=None):
    root.mkdir(parents=True,exist_ok=True)
    (root/'package.json').write_text(json.dumps({'dependencies':{framework:'1.0'},'scripts':scripts or {'dev':'vite','build':'vite build'}}))
    return root


def test_nearest_package_and_loopback_preview(tmp_path):
    project=make_project(tmp_path/'app');(project/'src').mkdir()
    found=find_web_project(tmp_path,project/'src/App.jsx')
    assert found.label=='React' and found.root==project
    program,args,script=npm_command(tmp_path/'runtime',found,'run',54321)
    assert program.name=='node.exe' and args[-5:]==['--host','127.0.0.1','--port','54321','--strictPort']


def test_check_uses_build_without_inventing_lint(tmp_path):
    project=find_web_project(make_project(tmp_path))
    assert npm_command(tmp_path,project,'check')[2]=='build'


def test_unknown_server_not_started_automatically(tmp_path):
    project=find_web_project(make_project(tmp_path,scripts={'dev':'custom-server','build':'build'}))
    with pytest.raises(ValueError):npm_command(tmp_path,project,'run')


def test_template_does_not_overwrite_existing_files(tmp_path):
    make_project(tmp_path/'runtime/frameworks/templates/vue','vue')
    destination=tmp_path/'my-vue'
    create_template(tmp_path/'runtime',destination,'vue')
    assert (destination/'package.json').is_file()
    with pytest.raises(ValueError):create_template(tmp_path/'runtime',destination,'vue')
    with pytest.raises(ValueError):create_template(tmp_path/'runtime',tmp_path/'x','unknown')


def test_script_manifest_must_be_strings(tmp_path):
    make_project(tmp_path,scripts={'build':123})
    with pytest.raises(ValueError):find_web_project(tmp_path)
