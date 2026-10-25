# Cómo colaborar

Gracias por interesarte. Toda ayuda sirve, también la que no es código.

## Contar un comando lento

La forma más útil de ayudar es decirnos qué comando de AutoCAD te hace esperar. Abre un *issue* con la plantilla
"Comando lento" e indica:

- el comando y las opciones que usas,
- cuántas entidades tiene el dibujo y de qué tipo (líneas, polilíneas, sombreados, bloques...),
- cuánto tarda y en qué AutoCAD y procesador.

Si puedes compartir un dibujo de ejemplo sin información privada, mejor. Si no, una descripción basta.

## Reportar un error

Si una herramienta deja un dibujo distinto del que deja el comando de AutoCAD, eso es un error grave para este
proyecto: usa la plantilla "Error" y di qué esperabas y qué obtuviste. Prueba siempre en copias de tus dibujos.

## Proponer código

1. Haz un *fork* y una rama.
2. Respeta la receta: leer en el hilo principal, copiar a arreglos simples, calcular en paralelo sin tocar
   AutoCAD, reensamblar en orden fijo y escribir en una transacción.
3. Demuestra que el resultado es idéntico con 1 y con N hilos (huella SHA-256) y, si se puede, igual al del
   comando de AutoCAD. Incluye los tiempos y la máquina donde mediste.
4. Abre un *pull request* explicando qué cambia y cómo lo probaste.

La documentación está en español; se aceptan *issues* y *pull requests* en inglés.

Al contribuir aceptas que tu aporte se publique bajo la licencia del proyecto ([PolyForm Shield 1.0.0](LICENSE))
y que el autor pueda ofrecerlo también bajo otras condiciones.
