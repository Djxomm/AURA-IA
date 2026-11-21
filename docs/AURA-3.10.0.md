# AURA IA 3.10.0

Mantén el instalador EXE y todos sus archivos BIN en la misma carpeta. Abre el EXE y sigue los pasos. No abras los BIN. Cierra la versión anterior antes de instalar. Se necesitan aproximadamente 17 GB libres para el programa y los modelos, más espacio temporal.

Incluye OpenAI gpt-oss-20b MXFP4 (12.1 GB), con integridad SHA-256 comprobada, y Qwen Coder 1.5B para equipos antiguos. El ligero sigue seleccionado inicialmente. Cambia el modelo debajo del chat. Solo se carga un modelo a la vez. GPT-oss es un modelo de pesos abiertos; no es el servicio ChatGPT. En el i5-10210U con 16 GB, la prueba aritmética tardó 109 segundos hasta el primer texto. No se promete una respuesta de 3.5 segundos con este modelo.

En modo de programación, selecciona una carpeta de proyecto. Puedes escribir «compila main.py», «compila y ejecuta main.cpp» o «prueba main.py». La consola muestra salida real, errores y archivo generado. Detener cancela el trabajo. Ejecutar programas normales utiliza los permisos de tu usuario.

El menú adicional incluye monitor de CPU, RAM y procesos de AURA y manejo de ZIP/TAR. La extracción rechaza rutas fuera de destino, enlaces y archivos excesivos. La opción de ejecución aislada exige Windows Sandbox habilitado; si no existe, se detiene y no ejecuta fuera del aislamiento. No se habilitan características de Windows automáticamente. Esto reduce riesgos, no garantiza seguridad absoluta.

La biblioteca adicional queda en D:\IA\Modelos_AURA. Los modelos grandes 32B/72B son experimentales y pueden resultar imprácticos con 16 GB. Se registran cuando terminan y se verifican. No todos van dentro del instalador.

La memoria privada de AgroChek 7 y 10 queda separada en D:\IA\Memoria_Proyectos. No se publica ni se incorpora a este instalador distribuible. La aplicación recupera referencias de la versión correspondiente, sin tratar documentos históricos como órdenes nuevas.

Para juegos nuevos de carreras 3D en una carpeta vacía hay un punto de partida Panda3D. Pygame corresponde a juegos 2D. Revisa el resultado antes de distribuirlo.
