"""A reviewed, runnable starter for empty native 3D racing projects."""
import re
from pathlib import Path


def racing_starter(brief,workspace,runtime):
    if runtime is None:return None
    value=brief.lower()
    if not re.search(r'\b3\s*d\b',value) or not re.search(r'carrer|coches|carros|autos',value):return None
    if re.search(r'html|three\.?js|unreal|unity|navegador|javascript',value):return None
    if any(workspace.root.iterdir()):return None
    source=Path(runtime)/'games/panda3d/main.py'
    if not source.is_file() or source.stat().st_size>128*1024:return None
    return {'path':'main.py','content':source.read_text('utf-8'),'reason':'Crear el prototipo nativo Panda3D de carreras, con controles, curvas, árboles y colisiones. Plantilla local revisable; aún no se ejecutó ni compiló.'}
