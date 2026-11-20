---
name: Juegos con Pygame
description: Crear juegos 2D con el Pygame incluido, eventos, recursos y compilación a EXE desde AURAX.
---
Usa el Python incluido en AURA. Pygame 2.6.1 ya está instalado; no descargues paquetes sin revisar si realmente faltan.
Mantén un ciclo de eventos que atienda QUIT y Escape. Usa Clock.tick para limitar FPS y delta de tiempo para el movimiento. Evita ciclos ocupados.
Inicializa únicamente los módulos necesarios. La plantilla inicia pantalla y fuentes; abre audio solo si el juego lo necesita.
Usa aura-game.json para nombre, icono y carpetas de recursos. Conserva todas las rutas dentro del proyecto. Para EXE busca recursos bajo sys._MEIPASS o una ruta basada en __file__.
Verificar revisa sintaxis; Ejecutar abre el juego sin límite automático de dos minutos; Compilar genera un EXE que incluye recursos y bibliotecas; Detener termina el juego y sus procesos secundarios.
No presentes las pruebas con SDL dummy como prueba de GPU, audio físico o teclado real. Distingue código generado de compilación y ejecución efectivamente comprobadas.
NumPy y otras bibliotecas opcionales se agregan solo si el juego las necesita. Conserva licencias de Pygame, SDL y recursos al distribuir.
