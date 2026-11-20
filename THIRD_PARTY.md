# Dependencias y licencias

La licencia MIT del proyecto se aplica al código original de AURA, no sustituye las licencias de sus dependencias.

- Qwen2.5-Coder 1.5B Instruct: Apache 2.0. https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF
- llama.cpp: MIT; OpenMP tiene sus avisos adicionales. https://github.com/ggml-org/llama.cpp
- PySide6/Qt 6.8.3: LGPLv3/GPL u opción comercial, según el componente. Se usan bibliotecas dinámicas. https://doc.qt.io/qtforpython-6/licenses.html
- Vosk y el modelo pequeño español: Apache 2.0. https://alphacephei.com/vosk/models
- Python: PSF; PyInstaller conserva sus condiciones y excepción de distribución. https://www.python.org/psf/license/
- Impeccable, cuando se incorpore como habilidad: Apache 2.0. No está incluido en el repositorio runtime vacío.
- ElevenLabs: servicio externo opcional sujeto a la cuenta y condiciones del usuario. No se incluye su voz como modelo local.

Los textos de licencias disponibles se conservan en `licenses/`. No se incluyen claves ni grabaciones de referencia en el repositorio.

- SQLAlchemy, pg8000, PyMySQL, pyodbc, python-oracledb, sqlparse y dependencias: versiones y textos de licencia en `licenses/sql-drivers/`. Los controladores nativos ODBC de otros fabricantes se instalan por separado.

- Node.js/OpenJS Foundation: MIT y avisos de sus dependencias en `licenses/languages/Node-LICENSE.txt`.
- PHP Group: PHP License 3.01; texto incluido en `licenses/languages/PHP-LICENSE.txt`.
- Eclipse Temurin/OpenJDK: GPLv2 con Classpath Exception y licencias por componente, conservadas en `licenses/languages/JDK-legal/`; el JDK incluye `lib/src.zip`. La licencia MIT de AURA no sustituye estas licencias.

- React, Vue, Vite, sus plugins y dependencias de las plantillas: versiones en `frameworks/manifest.json`, integridades en los lockfiles y avisos en `licenses/frameworks/`. La caché offline incluida conserva los paquetes de origen.
