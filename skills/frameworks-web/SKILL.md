---
name: React Vue y proyectos web
description: Desarrollar React, Vue.js y otros proyectos npm con scripts revisados, Vite y dependencias preparadas sin conexión.
---
Inspecciona package.json y el archivo de bloqueo antes de elegir comandos. Respeta versiones y la estructura del proyecto.
AURAX incluye plantillas React y Vue con Vite. El botón Proyecto web crea una carpeta nueva y prepara dependencias después de la aprobación del usuario.
Verificar usa typecheck, type-check, lint o build según lo que exista; no inventes un resultado ni lo describas como comprobación de tipos si solo se compiló.
Ejecutar inicia Vite en 127.0.0.1 y abre una ventana propia. Detener cierra el servidor y sus procesos secundarios. Esto es una vista previa local, no alojamiento de producción.
Compilar ejecuta el script build y genera los archivos web que defina el proyecto, normalmente dist; no genera automáticamente un EXE Windows.
Las dependencias de las plantillas están incluidas en una caché npm verificada para preparación offline. Otros paquetes pueden necesitar Internet. Nunca instales paquetes automáticamente sin revisión.
La preparación desactiva scripts de instalación. Si un proyecto necesita postinstall u otros pasos, explica qué falta y permite que el usuario revise los comandos desde Terminal.
En React usa componentes y hooks correctamente; en Vue respeta Composition API o el estilo existente. Mantén accesibilidad, contraste y estados de carga claros.
