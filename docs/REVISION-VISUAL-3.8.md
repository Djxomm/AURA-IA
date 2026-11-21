# Revisión visual y de uso · AURA 3.8

Se aplicó Impeccable sobre la implementación existente y las capturas de referencia del usuario. Esta revisión corresponde a una aplicación Windows Qt; el detector devolvió una lista vacía al recorrer los archivos Python. Eso no prueba por sí mismo la accesibilidad de los widgets. Se complementó con inspección de componentes renderizados, cálculos de contraste y pruebas de interacción.

## Cambios comprobados

- Iconos, proyectos e historial a la izquierda; escritura compacta y centrada abajo, con modelo y razonamiento.
- Cuadro inicial de una línea que crece con el texto. Enter envía; Shift + Enter añade línea. El contenido largo conserva desplazamiento.
- Una burbuja redondeada por mensaje, usuario gris claro y AURA azul oscuro, sin separadores horizontales.
- Menús con selección visible, búsqueda de modelos, registro persistente de modelos añadidos y estado deshabilitado durante la generación.
- Configuración agrupada por secciones con campos reales y valores recomendados según el equipo.
- Asistente AURAX transparente, movible, con menú contextual, aviso de revisión y animación desactivable. La animación se detiene al ocultarlo y en reposo.
- Editor AURAX con barras de acciones que desbordan a un menú en ventanas estrechas. El acoplamiento considera el espacio disponible.
- Foco de teclado visible, nombres accesibles para botones de iconos y selección de texto legible.

## Contrastes calculados

| Superficie | Relación |
|---|---:|
| usuario | 11.9:1 |
| aura | 12.89:1 |
| texto | 15.24:1 |
| secundario | 8.32:1 |
| placeholder | 6.37:1 |
| deshabilitado | 7.3:1 |
| menu_seleccionado | 7.24:1 |
| accion_enviar | 4.57:1 |
| foco | 9.7:1 |

Los pares de texto medidos superan 4.5:1. Los valores provienen de la configuración de colores; no constituyen una certificación de toda la aplicación.

## Evidencia y límites

Pruebas de componentes nativos con pantalla fuera de vista: ventana de 760 × 540, captura de 1366 × 728, nombres de conversación largos, barras de edición a 400 px, crecimiento y envío del mensaje, guardado de ajustes, animación y transparencia. La captura de chat utiliza el código real de interfaz y el resultado real de la prueba de generación de total.py; es una vista previa aislada, no una captura de los chats personales del usuario.

P0/P1 encontrados durante el trabajo: expansión de ancho, texto recortado por el cuadro compacto y barra de herramientas demasiado ancha. Se corrigieron y se añadieron pruebas. Quedan por comprobar en hardware físico el i5 de primera generación, escalado de pantalla de Windows distinto y lectura con Narrador. No se probó interacción táctil.
