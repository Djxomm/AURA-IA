from pathlib import Path
import pytest
from agente_ia.language_tools import check_html, language_plan


@pytest.mark.parametrize('name,kind,executable', [('a.js','check','node.exe'),('a.mjs','run','node.exe'),('a.php','check','php.exe'),('a.php','run','php.exe'),('A.java','build','javac.exe'),('A.java','run','java.exe')])
def test_language_uses_bundled_executable_and_project_boundary(tmp_path,name,kind,executable):
    plan = language_plan(tmp_path/'runtime',tmp_path,tmp_path/name,kind)
    assert plan.program.name == executable
    assert str(tmp_path/name) in plan.arguments
    assert not (tmp_path/'build').exists()
    with pytest.raises(ValueError): language_plan(tmp_path/'runtime',tmp_path,tmp_path.parent/name,kind)


@pytest.mark.parametrize('name', ['a.js','a.php','a.html'])
def test_interpreted_languages_do_not_claim_to_produce_exe(tmp_path,name):
    with pytest.raises(ValueError): language_plan(tmp_path/'runtime',tmp_path,tmp_path/name,'build')


def test_html_preview_and_basic_check(tmp_path):
    target = tmp_path/'index.html';target.write_text('<!doctype html><html><title>Prueba</title><body>Hola</body></html>')
    assert language_plan(tmp_path/'runtime',tmp_path,target,'run').preview
    assert not language_plan(tmp_path/'runtime',tmp_path,target,'check').preview
    assert 'básica' in check_html(target)


def test_java_output_cannot_escape_via_link(tmp_path):
    # Windows symlink privileges vary; the normal path still stays in the project.
    plan = language_plan(tmp_path/'runtime',tmp_path,tmp_path/'Main.java','build')
    assert plan.output_directory.is_relative_to(tmp_path)
    assert '-proc:none' in plan.arguments
    assert '-J-Xmx256m' in plan.arguments
