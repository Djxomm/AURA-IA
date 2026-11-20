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

## Bases de datos SQL · uso sencillo

1. Abre **Bases de datos SQL** y elige el motor.
2. Selecciona el archivo SQLite o completa los datos del servidor y pulsa **Conectar**.
3. Elige una tabla para ver su estructura. Escribe una consulta o pulsa **Pedir ayuda a AURAX**. Revisa el SQL antes de ejecutarlo.

Los ajustes avanzados se muestran bajo demanda. **Permitir cambios** habilita instrucciones de escritura; cada ejecución muestra una confirmación. Las consultas se ejecutan en segundo plano. Las contraseñas de conexión no se guardan en archivos ni se incorporan a mensajes del asistente. Solo se comparte la estructura seleccionada y el SQL del editor cuando se pulsa Pedir ayuda; el mensaje queda editable antes de enviarlo.

Conectores incluidos: SQLite, SQL Server/Express (pyodbc), PostgreSQL (pg8000), MySQL/MariaDB (PyMySQL) y Oracle (oracledb Thin). La opción ODBC/DSN permite otros motores con un controlador de Windows de 64 bits. SQL Server necesita además un [controlador ODBC compatible instalado en Windows](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server). La compatibilidad de versiones depende del controlador y del [dialecto de SQLAlchemy](https://docs.sqlalchemy.org/en/20/dialects/); no se garantizan todas las versiones históricas o futuras. Oracle antiguo puede conectarse mediante un DSN/cliente compatible.

Probado con operaciones reales de SQLite, incluyendo consultas, escrituras, protección de archivo de solo lectura y respaldo verificado. Se comprobó también la carga de los cinco conectores restantes, sin afirmar una prueba real contra servidores remotos. La verificación del EXE se puede ejecutar con `--sql-self-test --data-dir CARPETA_DE_PRUEBA`.

Límites: una instrucción por ejecución, hasta 12000 caracteres de SQL, 500 filas, 100 columnas y 2000 caracteres por celda. Exportar CSV guarda las filas mostradas y protege campos que una hoja de cálculo podría interpretar como fórmulas. No es un respaldo completo. El botón de respaldo es para SQLite; otros motores usan herramientas nativas.

Los filtros de consultas no sustituyen los permisos del servidor: usa una cuenta de solo lectura cuando corresponda. DDL puede confirmar cambios automáticamente en algunos motores. Conserva un respaldo antes de modificar datos o estructuras. Las excepciones de certificados del explorador web no se aplican a las bases de datos.

## JavaScript, Java, HTML5 y PHP

Los mismos botones de AURAX reconocen el lenguaje por la extensión del archivo:

| Archivo | Verificar | Ejecutar | Compilar |
| --- | --- | --- | --- |
| Python | Revisa sintaxis | Ejecuta Python | Genera EXE con PyInstaller |
| C/C++ | Revisa sintaxis | Ejecuta el EXE compilado | Genera EXE con GCC |
| JavaScript `.js/.mjs/.cjs` | Node.js `--check` | Node.js | No genera EXE automáticamente |
| Java `.java` | Compila con javac | Ejecuta el archivo fuente | Genera `.class` en `build/aurax-java` |
| HTML5 `.html/.htm` | Revisión básica de lectura | Vista previa nativa con JavaScript del navegador | No requiere compilación |
| PHP `.php` | Comprueba sintaxis | PHP por consola | No genera EXE automáticamente |

La vista previa HTML5 se abre dentro de AURA, sin iniciar un servidor web. La comprobación básica no sustituye un validador HTML5 completo. PHP CLI no crea por sí solo un servidor ni una petición HTTP. Los proyectos con bibliotecas necesitan sus dependencias; Node incluye npm. La terminal usa las herramientas incluidas sin cambiar permanentemente el PATH de Windows.

El paquete privado incluye Node.js 22.23.5, Eclipse Temurin JDK 25.0.4.1+1 y PHP 8.4.28 NTS x64. No se cargan al iniciar AURA. Los límites iniciales son 256 MB de heap en Node y Java y 128 MB en PHP; Java utiliza dos procesadores activos. Los proyectos grandes pueden necesitar ajustar estos parámetros desde la terminal. Las herramientas y los paquetes adicionales no modifican la capacidad del modelo local ni garantizan que genere código correcto.

Se probaron programas reales de los tres lenguajes, compilación Java y una página HTML5 que modificó el DOM mediante JavaScript. La habilidad **Programación multilenguaje** se puede activar desde Habilidades.

Para construir desde fuente, coloca las distribuciones oficiales en `runtime/herramientas/node`, `runtime/herramientas/jdk` y `runtime/herramientas/php`. Versiones, procedencia y licencias están en `licenses/languages/`. El instalador incluye estas herramientas; el repositorio contiene su código de integración y avisos, sin duplicar los binarios.

## React y Vue.js sin perder la sencillez

1. En AURAX abre **Proyecto web → Nuevo React** o **Nuevo Vue.js**.
2. Escribe el nombre de una carpeta nueva y revisa la preparación de dependencias.
3. Usa **Ejecutar**, **Verificar**, **Compilar** y **Detener**.

El instalador incluye las plantillas y una caché npm verificada. React y Vue se pueden preparar sin Internet en Windows x64. Si un proyecto necesita paquetes adicionales, utiliza **Instalar dependencias con Internet**. Las dos opciones desactivan scripts de instalación; proyectos que necesiten pasos especiales pueden ejecutarlos después de revisarlos en Terminal.

Ejecutar abre Vite en `127.0.0.1` y muestra el proyecto en una ventana de AURA. Detener y salir cierran el comando y sus descendientes mediante un Job Object de Windows. El lanzador crea el proceso suspendido, lo asigna al Job y solo entonces lo ejecuta. Este mecanismo controla su duración; no constituye un aislamiento de seguridad para código desconocido. La interfaz principal de AURA sigue siendo nativa, sin servidor web propio.

Verificar utiliza `typecheck`, `type-check`, `lint` o `build`, según los scripts disponibles. Compilar ejecuta `build` y genera archivos web, normalmente `dist`, sin convertirlos automáticamente a EXE. Otros proyectos npm pueden usar sus scripts de verificación y compilación; la vista previa automática está preparada para Vite. No se garantiza todo framework o versión.

Se probaron ambas plantillas: preparación con `npm ci --offline`, compilación, renderizado, clic en un botón y cierre del servidor con sus procesos secundarios. Las versiones incluidas son React 19.3.1, Vue 3.5.46 y Vite 7.3.8.

Para reproducir el paquete desde fuente, prepara Node y w64devkit y ejecuta `python scripts/prepare_frameworks.py`. El script usa los archivos de bloqueo, genera la caché y compila el lanzador de procesos. No se guardan `node_modules` ni la caché binaria en GitHub. El instalador copia `runtime/frameworks`, `runtime/herramientas/aura-web` y las licencias junto a los demás componentes.
