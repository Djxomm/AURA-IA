# AURA 3.9 · AURAX y QbitX

AURAX conserva el objetivo y los avances del trabajo. QbitX es el espacio de archivos y herramientas. Ambos usan el mismo modelo por turnos; no se cargan dos modelos en RAM.

## Perfiles

- i5 antiguo: modelo Coder 1.5B Q4, 2–4 hilos físicos, contexto 2048–4096; motor CPU con variantes x64/SSE4.2 conservadas.
- Este i5-10210U, 16 GB, Intel UHD: 4 hilos, contexto 4096, lote 64. El Coder 7B Q4 ya descargado se prefiere al abrir programación si está registrado y completo. Consume más memoria y tarda más, pero permite usar un modelo de programación mayor. Se puede volver al ligero desde el selector.
- i7 de octava generación con GTX 1060 6 GB: hasta 6 hilos físicos. Motor Vulkan separado; selección automática de NVIDIA con al menos 5 GB detectados y descarga de hasta 28 capas. Si el controlador o la reserva de memoria falla antes de producir texto, reintenta en CPU. No hay una GTX 1060 física en este equipo para verificar velocidad.

## Intel UHD

La GPU está disponible en Configuración → Rendimiento → Aceleración. En la prueba sintética de este equipo, el modelo 1.5B produjo 22.10 tokens/s por CPU, 11.55 con Vulkan completo y 13.04 con 12 capas en Intel. Solo se hizo una repetición corta; no son tiempos de respuesta garantizados. Automático conserva CPU para esta Intel. El 7B no está comparado aquí en GPU.

## Tareas largas

Los objetivos, archivos aplicados y resultados reales de herramientas se guardan en qbitx-tasks.sqlite junto a los datos de AURA. Al reiniciar, abre el mismo chat y proyecto y escribe «continúa». AURAX recupera el objetivo y QbitX recibe el avance resumido. El historial completo permanece guardado; se acota el contexto enviado al modelo y se conservan juntas las llamadas y sus resultados.

Se inspecciona una lista acotada del proyecto y los archivos nombrados antes de generar cambios. Se comprueba sintaxis de Python, HTML y JavaScript también en ediciones. La sintaxis no demuestra corrección funcional: usa las herramientas Verificar, Ejecutar y Compilar, que muestran resultados reales. Los cambios siguen pasando por revisión y se pueden revertir.

No es una garantía de inteligencia equivalente a Codex. El modelo puede equivocarse y las tareas complejas siguen necesitando pruebas y revisión. El instalador no instala controladores, no borra conversaciones ni instala por sí solo modelos grandes.

## Verificación de esta entrega

108 pruebas de aplicación aprobadas. Prueba real con Qwen Coder 7B en CPU: creó total.py y pasó cinco casos de IVA (45 s); una nueva instancia del agente retomó el chat, aplicó la validación de cantidad negativa y pasó seis casos (73.5 s). Son ejemplos pequeños, no pruebas de proyectos largos completos. La segunda ejecución coincidió con preparación de la compilación; los tiempos no son una comparación controlada.

La ruta de inferencia Intel Vulkan también respondió LISTO usando el cliente de AURA. El perfil GTX 1060 se comprobó mediante selección simulada y recuperación por CPU; no se dispone de esa GPU física.

Se corrigió un fallo detectado en esta prueba: «ajusta total.py» antes podía devolver un bloque correcto sin aplicarlo; ahora activa el flujo de archivo revisable. Los errores del modelo siguen siendo posibles.
