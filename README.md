# AURA Inteligencia Artificial

<p align="center"><img src="agente_ia/static/assets/aura-logo-transparente.png" width="240" alt="AURA IA"></p>

Asistente de escritorio para **Windows 10 x64**, con programación local, memoria persistente y asistente flotante. **Las contribuciones son bienvenidas.**

La interfaz principal tiene una distribución de chat en azul oscuro, con navegación lateral compacta. Utiliza PySide6/Qt: no necesita un navegador externo ni inicia un servidor web para la interfaz. El explorador de Internet opcional se abre en una ventana integrada. El motor de texto se comunica por procesos locales y está preparado con bibliotecas CPU SSE4.2/x64 para equipos antiguos. El objetivo de desarrollo incluye un i5 de primera generación y 16 GB RAM; todavía falta probar ese equipo físico.

## AURAX · Codificador integrado

Abre **AURAX · Codificador** en la barra lateral. Incluye explorador del proyecto, editor por pestañas con colores de código, archivos nuevos, guardado con revisión de diferencias y adjuntos al agente. La consola permite verificar y ejecutar Python y generar un EXE con PyInstaller, siempre con autorización.

El agente utiliza el mismo modelo local y las aprobaciones de cambios. Las respuestas sin archivos aplicados se identifican como tales. **Revisar código IA** abre un bloque de la respuesta como borrador, sin escribirlo hasta que se revise y guarde.

Se comprobó una compilación desde el panel y se ejecutó el EXE resultante. Un modelo pequeño puede equivocarse en rutas o código; revisa las propuestas. La preparación de una tarea de programación larga puede tardar bastante más que una consulta corta con caché.

## Funciones

- Conversación y modo Programación, propuestas de cambios con revisión, historial y deshacer.
- Modelo Qwen2.5-Coder 1.5B Q4_K_M; admite otros Qwen2/Qwen2.5 Instruct ChatML GGUF.
- Caché de contexto, preparación inicial y dibujo incremental para ahorrar trabajo.
- Barra de contexto de 2048–8192 tokens; recomendación inicial 4096, con ampliación automática opcional.
- Memoria local en SQLite: recuerdos por proyecto o generales, edición, búsqueda, exportación y borrado. Modo temporal sin historial ni caché de conversación.
- Asistente flotante arrastrable, dictado offline con Vosk y reproducción de voz local de Windows.
- ElevenLabs opcional, con clave cifrada mediante DPAPI y respaldo local. Requiere una cuenta y una voz configuradas por el usuario.
- Habilidades Markdown y terminal autorizada para pruebas y compilación.

## Estado real

Proyecto en desarrollo. Las consultas cortas medidas con caché preparada dieron aproximadamente **1,2 y 2,5 segundos hasta el primer texto** en el equipo de prueba. La carga inicial y las conversaciones largas pueden tardar mucho más. No se garantiza ese rendimiento en otro procesador.

La clonación local de una voz de referencia **no está terminada ni validada**. Un archivo MP3 no es un modelo de voz. No se incluyen grabaciones personales, credenciales ni datos de conversaciones en este repositorio. El video de presentación de AURA se incluye con autorización expresa y se muestra mientras se prepara la IA, antes del chat. El audio de referencia personal no se distribuye aquí.

No hay cuotas de uso de tokens; cada consulta está limitada por el contexto y la longitud elegidos. La memoria ayuda a recuperar información, pero no vuelve ilimitado el contexto del modelo.

## Ejecutar desde código

Requiere Python 3.13 de 64 bits y Windows. En PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-native.txt
.venv\Scripts\python scripts/prepare_runtime.py
.venv\Scripts\python native_launcher.py
```

La preparación descarga aproximadamente 1,2 GB desde los proveedores oficiales, comprueba sus SHA-256 y selecciona los componentes CPU sin AVX del motor. Después, conversación y dictado funcionan sin Internet. ElevenLabs es una opción en línea; la voz local depende de las voces instaladas de Windows.

Los datos se guardan en `%LOCALAPPDATA%\AURA_IA`. El motor no abre puertos. El modo de voz ElevenLabs sí envía el texto que se va a leer a ese servicio cuando el usuario lo activa.

Para compilar proyectos desde la terminal se necesita Python y PyInstaller en el entorno de desarrollo. Los instaladores privados de prueba incluyen herramientas portátiles; este repositorio no contiene esos binarios ni el modelo.

## Pruebas

```powershell
.venv\Scripts\python -m pytest tests -q
```

Las pruebas unitarias no descargan el modelo. Para una comprobación real del motor y la memoria, prepara antes el runtime y ejecuta:

```powershell
.venv\Scripts\python native_launcher.py --self-test --data-dir build\smoke
```

## Compilar la aplicación

```powershell
.venv\Scripts\python -m pip install pyinstaller
.venv\Scripts\python -m PyInstaller AURA-Nativa.spec
```

La especificación genera la ventana nativa. Para un paquete completo hay que copiar motor, modelos, licencias y voz desde `runtime` al directorio de distribución. El archivo NSIS es una base para empaquetar en Windows y requiere preparar también las herramientas portátiles de Python si se quieren incluir.

## Colaborar

Lee [CONTRIBUTING.md](CONTRIBUTING.md), abre un issue o envía un pull request. Son especialmente útiles las pruebas en procesadores antiguos, mejoras de accesibilidad, recuperación de contexto, voz local eficiente y documentación.

Código original de AURA bajo [MIT](LICENSE). Modelos, Qt y otras dependencias conservan sus propias licencias: consulta [THIRD_PARTY.md](THIRD_PARTY.md). Proyecto independiente de OpenAI Codex.

## Explorador de Internet

El menú **Explorador de Internet** abre Qt WebEngine únicamente cuando se solicita. Admite direcciones HTTP/HTTPS y búsquedas. Usa un perfil privado en memoria; al cerrar se eliminan cookies y excepciones de certificado.

Ante un certificado inválido, se muestra el dominio, el motivo y la decisión **Entrar bajo mi responsabilidad**. Cancelar es la opción predeterminada. Los errores que Chromium no permite anular se rechazan. Una excepción puede mantenerse durante esa sesión del explorador; no modifica los certificados de Windows ni desactiva TLS globalmente. HTTP se identifica como conexión sin cifrar.

Las descargas y los permisos de cámara, micrófono y ubicación están bloqueados en esta versión. No se comparte automáticamente el contenido de los sitios con el modelo. Se comprobó en un servidor HTTPS local aislado el rechazo y la aceptación explícita de un certificado autofirmado.

El instalador 3.2 se genera con Inno Setup y el archivo `instalador-nativo.iss`.

### Inicio automático sin controles

La pantalla de inicio contiene únicamente el video, sin botones ni textos superpuestos. Se reproduce automáticamente en silencio, se repite durante la preparación y da paso al chat cuando termina la carga del modelo. Si la preparación falla, se abre la interfaz con el aviso correspondiente.

### C/C++ e instaladores

AURAX admite verificar archivos C/C++, compilar un archivo a EXE y ejecutar el resultado, además de Python. El paquete privado incorpora w64devkit 2.11.0 (GCC); no es Visual Studio ni un gestor automático de dependencias CMake. Para proyectos de varios archivos se puede utilizar la terminal. Cada proceso requiere aprobación.

Abre un archivo `.iss` y pulsa **Crear instalador** para invocar Inno Setup 7.1.1. Revisa los scripts de terceros antes de autorizarlos: sus directivas pueden ejecutar procesos. El paquete incluye el compilador y sus avisos de licencia.

Para preparar estas herramientas al construir desde código fuente, instala o extrae w64devkit bajo `runtime/herramientas/w64devkit` e Inno Setup bajo `runtime/herramientas/inno`; los ejecutables deben ser `bin/g++.exe` e `ISCC.exe`. La instalación del modelo sigue usando `scripts/prepare_runtime.py`.
