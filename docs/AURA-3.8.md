# AURA 3.8 · Uso e instalación

Cierra AURA y ejecuta el instalador de Windows x64. Incluye el modelo ligero y conserva la ruta x64/SSE4.2 para equipos antiguos; el motor selecciona las instrucciones compatibles. No se ha probado todavía el i5 de primera generación físico.

La interfaz utiliza el azul oscuro de AURA: iconos, proyectos e historial a la izquierda, conversación al centro y escritura compacta abajo. Cada mensaje tiene una burbuja: gris claro para el usuario y azul oscuro para AURA. No hay líneas separadoras entre mensajes.

Escribe y pulsa Enter para enviar. Shift + Enter agrega una línea. El cuadro crece con el contenido y vuelve a su tamaño compacto después de enviarlo. Durante la respuesta, el botón de envío permite detenerla.

El modelo y el razonamiento se eligen en la barra inferior. Rápido, Equilibrado y Profundo cambian la profundidad solicitada y los presupuestos automáticos; no convierten el modelo en otro ni garantizan razonamiento nativo. Busca un GGUF Qwen2/Qwen2.5 Instruct desde ese menú para añadirlo a la lista. Solo se carga un modelo por respuesta y el proceso se libera al terminar.

La configuración agrupa General, Modelos, Rendimiento, Voz, Memoria, Proyecto y habilidades, y Cambios y seguridad. Rendimiento muestra el hardware y permite aplicar recomendaciones. Para un equipo antiguo conserva el modelo ligero y 2048–4096 tokens de contexto. Un 7B necesita más memoria y tiempo.

El personaje azul es AURAX. Un clic abre el codificador, arrastrar lo mueve y el clic derecho ofrece dictado, lectura y ocultación. Su animación se detiene en reposo y al ocultarse; también se puede desactivar en General.

Para programar, elige la carpeta del proyecto y pide crear un archivo. Revisa la propuesta antes de guardarla. Después usa Verificar, Ejecutar y Compilar en AURAX. En una ventana estrecha, las barras de acciones ofrecen un menú de desbordamiento. Si no hay espacio para el editor junto al chat, se abre flotante.

El asistente y sus modelos pueden cometer errores. Estas funciones no garantizan la capacidad de servicios con modelos mayores ni respuestas iniciales en 1.5–3.5 segundos. Las pruebas de generación se realizaron en un i5-10210U con 16 GB de RAM, por CPU.

Los modelos y las grabaciones personales no forman parte del repositorio de código. El instalador de prueba incluye el modelo ligero; los modelos adicionales descargados se seleccionan desde la PC. Las integraciones de otras familias de modelos continúan siendo trabajo independiente.
