# Entrenamiento público de AURA Ligero

Esta receta es independiente del entrenamiento privado de AgroChek y no inicia trabajos automáticamente. No debe ejecutarse al mismo tiempo que un entrenamiento activo en una PC con memoria limitada.

1. Genera datos de demostración: `python training/build_public_dataset.py --output training/generated`. Se generan solo ejemplos sintéticos públicos; no se leen archivos de empresas.
2. Crea un entorno aparte e instala `training/requirements.txt`. El entorno de entrenamiento no es una dependencia del instalador de AURA.
3. Obtén por separado Qwen/Qwen2.5-Coder-1.5B-Instruct y conserva su licencia. Usa una revisión fija de la base y registra su identidad.
4. Ejecuta: `python training/train_public.py --base RUTA_BASE_LOCAL --data training/generated --output training/runs/aura-piloto --steps 32`. El cargador usa archivos locales y no admite código remoto del modelo. No se suben datos ni pesos.
5. Revisa `evaluation.json` y evalúa funcionalmente las respuestas con pruebas no usadas en entrenamiento. Una pérdida menor no es un porcentaje de aciertos. No se sobrescribe la base ni se publica/promueve el candidato automáticamente.

El conjunto pequeño incluido sirve para comprobar la receta y la identidad de AURA; no es un entrenamiento completo de programación. Amplíalo con ejemplos propios o autorizados, revisados y diversos. No incluyas claves, datos de clientes, conversaciones privadas ni código de terceros sin permiso. Mantén la atribución y licencia de cada fuente y separa las pruebas reservadas del corpus.

El ajuste fino consume bastante CPU/RAM. La receta pequeña usa 4 hilos y LoRA; no implica una garantía de ejecución en todo equipo. El i5 antiguo es un objetivo de inferencia, no una promesa de entrenamiento eficiente.

## Utilidades públicas adicionales
- **Verificación WCAG 2.1 (`training/wcag_check.py`)**: calcula relaciones de contraste reales (`>= 4.5:1` AA) para validar ejemplos de UI, CSS y temas oscuros/claros antes de entrenar o evaluar.
- **Expansión experimental de capas (`training/build_2b_llamapro.py`)**: receta estilo LLaMA Pro que clona 10 capas sobre una base local de `Qwen2.5-Coder-1.5B-Instruct` (`28 -> 38` capas, `~2.01B` parámetros) con `o_proj` y `down_proj` inicializados a cero para preservar identidad en el paso 0. No incluye pesos ni garantiza mejoras sin evaluación reservada.
- **Identidad GGUF (`AURA - Lumen 2.0IB_V1`)**: al convertir candidatos a GGUF con `llama.cpp`, pasa `--model-name "AURA - Lumen 2.0IB_V1"` y conserva la atribución a `Qwen/Qwen2.5-Coder-1.5B-Instruct` (`Apache-2.0`). AURA lee `general.name` y muestra el nombre del modelo en el selector del chat, barra de estado y ajustes.
