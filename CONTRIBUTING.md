# Colaborar en AURA

Gracias por participar. Puedes reportar errores, mejorar documentación, probar compatibilidad o enviar código.

1. Abre un issue para cambios grandes y explica el problema con un ejemplo.
2. Crea una rama y mantén el cambio enfocado.
3. Ejecuta `python -m pytest tests -q` y documenta cualquier prueba manual.
4. Incluye capturas si cambias la interfaz y mediciones comparables si cambias rendimiento.
5. Envía un pull request explicando el comportamiento antes y después y las limitaciones.

Mantén la interfaz principal nativa, sin servidor web. Conserva la revisión de cambios, la autorización de comandos y el funcionamiento offline. No reduzcas silenciosamente el modelo ni elimines requisitos para mejorar una medición.

No subas claves, bases de datos, historiales, audios personales, pesos de modelos ni instaladores grandes a Git. Respeta las licencias de terceros. Describe honestamente qué se verificó: no marques voz clonada, compatibilidad de hardware o rendimiento como comprobados sin una prueba real.

Las contribuciones al código original se realizan bajo la licencia MIT del proyecto. Mantén una comunicación respetuosa y útil.

Para aportar al entrenamiento público, incluye procedencia y licencia de los datos, separación entre entrenamiento y evaluación y resultados reproducibles. No envíes datos de AgroChek ni de otros clientes. La receta de demostración no representa un modelo ya entrenado; los candidatos deben superar pruebas funcionales antes de distribuir sus pesos por un canal adecuado.
