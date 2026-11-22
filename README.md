# AURA · Inteligencia Artificial

<p align="center"><img src="agente_ia/static/assets/aura-logo-transparente.png" width="220" alt="AURA"></p>

**AURA es un asistente de escritorio de código abierto para conversar, programar y trabajar con proyectos locales. Las colaboraciones son bienvenidas.**

Su interfaz nativa mantiene una identidad azul oscuro y funciona en Windows sin navegador externo ni servidor web para el chat. AURA reúne memoria, habilidades, referencias visuales y herramientas de desarrollo con cambios revisables.

## Qué puedes hacer

- Conversar y elegir el modelo y nivel de razonamiento debajo del chat.
- Programar con AURAX y QbitX: explorar archivos, proponer cambios, compilar, ejecutar y probar.
- Adjuntar capturas y marcar una zona: OCR de Windows y lector visual local opcional.
- Guardar recuerdos y avances de proyectos, revisar diferencias y deshacer cambios.
- Usar voz local, dictado offline y ElevenLabs opcional con una cuenta propia.
- Ajustar contexto y recursos según modelo y RAM, conservando un perfil ligero para equipos antiguos.

Los modelos y herramientas necesarios deben estar instalados. Leer imágenes no habilita visión directamente en un modelo de texto. Los modelos pequeños pueden equivocarse: revisa los cambios y ejecuta pruebas. El filtro contra eliminación accidental de funciones no garantiza ausencia de regresiones.

## AURA como modelo propio

**AURA** identifica al proyecto y a su asistente. **AURA Ligero** identifica la línea de modelos adaptados para equipos modestos. La base inicial es Qwen2.5-Coder-1.5B-Instruct: se reconoce su procedencia; no afirmamos haber entrenado un modelo fundacional desde cero.

La aplicación y la receta de entrenamiento son públicas. **Todavía no se han publicado pesos propios de AURA validados y aptos para distribución.** Los experimentos privados no son una versión pública del modelo.

- [Ficha de AURA Ligero](models/aura-ligero/MODEL_CARD.md)
- [Receta pública de entrenamiento](training/README.md)
- [Hoja de ruta](ROADMAP.md)

## Instalar o desarrollar

Windows x64, Python 3.13 para desarrollar. Instala las dependencias de `requirements-native.txt` en un entorno virtual y prepara los recursos descritos en `scripts/prepare_runtime.py`. El SDK de compilación y los modelos se obtienen por separado. La aplicación utiliza la ventana nativa de `native_launcher.py`.

Para pruebas: `python -m pytest tests -q`. La compatibilidad física con i5 de primera generación sigue pendiente, aunque se conserva la ruta CPU para equipos antiguos. Los contextos grandes y modelos de mayor tamaño consumen más memoria y pueden ser lentos.

Las funciones visuales requieren el modelo y proyector de `scripts/prepare_vision.py` y un motor multimodal compatible; el OCR necesita un idioma compatible instalado en Windows. Las capturas se procesan localmente.

## Colaborar

Abre un issue con un problema reproducible o envía un pull request. Son útiles las mejoras de programación, accesibilidad, memoria, rendimiento, pruebas y compatibilidad. Consulta [CONTRIBUTING.md](CONTRIBUTING.md).

## Licencias y privacidad

El código original de AURA se distribuye bajo [MIT](LICENSE). Los modelos, Qt, llama.cpp y otras dependencias mantienen sus propias licencias; consulta `licenses/`. La receta pública parte de un modelo Qwen con licencia Apache-2.0. La licencia del código no cambia la licencia de los pesos.

No se publican bases de datos, claves, conversaciones, corpus privados de empresas ni pesos derivados de esos corpus. Las futuras versiones públicas de modelos requieren datos autorizados y evaluaciones documentadas. No se garantiza un porcentaje universal de aciertos.

[Historial técnico y versiones anteriores](docs/HISTORIAL_PUBLICO.md)
