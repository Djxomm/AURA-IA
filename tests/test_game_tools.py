import json
from pathlib import Path
import pytest
from agente_ia.game_tools import create_game,is_pygame_file,pygame_arguments


def test_detects_actual_import_not_text_example(tmp_path):
    source=tmp_path/'main.py'
    source.write_text('print("import pygame")')
    assert not is_pygame_file(tmp_path,source)
    source.write_text('from pygame import display')
    assert is_pygame_file(tmp_path,source)


def test_game_build_includes_assets_and_graphics_libraries(tmp_path):
    (tmp_path/'assets').mkdir();(tmp_path/'main.py').write_text('import pygame')
    (tmp_path/'aura-game.json').write_text(json.dumps({'engine':'pygame','name':'MiJuego','asset_folders':['assets']}))
    args=pygame_arguments(tmp_path,tmp_path/'main.py','build')
    assert '--windowed' in args and '--collect-binaries' in args
    assert str(tmp_path/'assets')+';assets' in args
    assert args[args.index('--name')+1]=='MiJuego'
    assert pygame_arguments(tmp_path,tmp_path/'main.py','check')[:2]==['-m','py_compile']


@pytest.mark.parametrize('folder',['../outside','assets/..','C:/Windows',''])
def test_game_assets_cannot_escape_project(tmp_path,folder):
    (tmp_path/'main.py').write_text('import pygame')
    (tmp_path/'aura-game.json').write_text(json.dumps({'engine':'pygame','asset_folders':[folder]}))
    with pytest.raises(ValueError):pygame_arguments(tmp_path,tmp_path/'main.py','build')


def test_game_template_does_not_replace_existing_folder(tmp_path):
    root=Path(__file__).resolve().parents[1]
    # Source repository keeps the same template layout as the installed runtime.
    destination=tmp_path/'game'
    create_game(root,destination)
    assert (destination/'main.py').is_file() and (destination/'assets/game.json').is_file()
    with pytest.raises(ValueError):create_game(root,destination)
