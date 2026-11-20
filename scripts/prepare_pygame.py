"""Prepare the offline Pygame SDK for the bundled Windows Python 3.13."""
from pathlib import Path
import hashlib
import shutil
import struct
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
FILENAME = 'pygame-2.6.1-cp313-cp313-win_amd64.whl'
URL = 'https://files.pythonhosted.org/packages/7e/11/17f7f319ca91824b86557e9303e3b7a71991ef17fd45286bf47d7f0a38e6/'+FILENAME
SHA256 = '813af4fba5d0b2cb8e58f5d95f7910295c34067dcc290d34f1be59c48bd1ea6a'


def main():
    if sys.platform != 'win32' or sys.version_info[:2] != (3,13) or struct.calcsize('P') != 8:
        raise RuntimeError('Prepara este paquete con Python 3.13 de 64 bits para Windows.')
    runtime = ROOT/'runtime'
    python = runtime/'herramientas/python'
    if not (python/'python.exe').is_file():
        raise RuntimeError('Prepara primero el Python portable con PyInstaller en runtime/herramientas/python.')
    wheel = python/'wheels'/FILENAME
    wheel.parent.mkdir(parents=True, exist_ok=True)
    if not wheel.exists():
        urllib.request.urlretrieve(URL, wheel)
    with wheel.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != SHA256:
            raise RuntimeError('La rueda Pygame no coincide con la huella esperada.')
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps', '--upgrade', '--target', str(python/'Lib/site-packages'), str(wheel)], check=True)
    shutil.copytree(ROOT/'games', runtime/'games', dirs_exist_ok=True)
    wrapper = runtime/'herramientas/aura-web/aura-job.exe'
    if not wrapper.is_file():
        compiler = runtime/'herramientas/w64devkit/bin/g++.exe'
        if not compiler.is_file():
            raise RuntimeError('Compila scripts/windows_job.cpp con w64devkit para preparar el controlador de procesos.')
        wrapper.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([str(compiler), '-std=c++17', '-O2', '-static', '-municode', str(ROOT/'scripts/windows_job.cpp'), '-o', str(wrapper)], check=True)
    print('Pygame está listo para ejecutar y compilar juegos sin conexión.')


if __name__ == '__main__':
    main()
