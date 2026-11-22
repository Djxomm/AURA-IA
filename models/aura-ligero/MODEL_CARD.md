---
language:
- es
- en
base_model: Qwen/Qwen2.5-Coder-1.5B-Instruct
pipeline_tag: text-generation
tags:
- aura
- code
- local
---
# AURA Ligero · Ficha de desarrollo

**Estado: receta pública; pesos propios públicos aún no publicados ni validados.**

AURA Ligero es la línea de adaptación para programación y asistencia local del proyecto AURA. La base prevista es Qwen2.5-Coder-1.5B-Instruct, mantenida con atribución y sus condiciones Apache-2.0. No es un modelo fundacional entrenado desde cero ni equivale a servicios ChatGPT o Claude.

## Objetivos
Instrucciones en español, herramientas estructuradas, cambios localizados, conservación del código y tareas de programación verificables. El reconocimiento de imágenes se realiza en otro componente de AURA.

## Datos
El ejemplo público de `training/build_public_dataset.py` genera datos sintéticos originales sin leer archivos de proyectos, bases de datos, conversaciones o documentos de empresas. Es un conjunto pequeño de demostración: no alcanza por sí solo para obtener competencia general ni un porcentaje objetivo. Los corpus y adaptadores privados de AgroChek no forman parte de esta versión pública.

## Entrenamiento
Receta LoRA separada del programa principal, con datos en formato ChatML, pérdida solo sobre la respuesta y validación independiente. Consulte `training/`. El resultado es un candidato, no una promoción automática.

## Evaluación y límites
Todavía no hay métricas de un modelo AURA público entrenado con esta receta. No trasladar resultados de experimentos privados a esta ficha. Antes de publicar, evaluar funcionalidad, llamadas a herramientas, conservación del código y memoria/latencia en hardware identificado. Distinguir resultados del primer intento y resultados tras corregir errores. No prometer ausencia de fallos ni conocimiento de cambios futuros.

## Distribución
La aplicación usa licencia MIT. La licencia final de cada adaptación y sus datos se documentará con el lanzamiento y mantendrá las obligaciones de los componentes de base. No se incluyen pesos de modelos en Git.

Base y licencia: https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct
