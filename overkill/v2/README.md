# OVERKILL v2

Motor OVERKILL con tolerancia geométrica real. Saca el 100 % en el dibujo extremo
(`../extremo`), también en los casos donde el OVERKILL de AutoCAD 2027 falla.

- `overkill_v2.py`: referencia en Python (lectura DXF, líneas, arcos/círculos, polilíneas).
- `cs/OverkillV2Core.cs`: núcleo C# sin dependencias de AutoCAD, para el plugin. Entradas en
  columnas (`Lineas`, `Arcos`, `Polis`) con las propiedades ya codificadas en un entero.
- `cs/Program.cs`: consola para DXF (`OverkillV2 dibujo.dxf [--e2e] [--hilos N] [--csv f] [--bench 1,4,16]`).
- `prueba_fuerza_bruta.py`: escenas aleatorias hostiles comparadas con la regla aplicada a todos los pares.

## Regla

Tolerancia `tol` (1e-6 por defecto) como distancia en 3D:

- Dos líneas con las mismas propiedades se fusionan si los dos extremos de la más corta están
  a `tol` o menos de la recta de la más larga **y** se solapan más de `tol` (o se tocan a `tol`
  con "extremo a extremo"). Queda la primera del archivo, estirada a los extremos más lejanos.
- Propiedades comparadas: capa, color, color verdadero, tipo de línea, escala de tipo, grosor,
  altura, transparencia, estilo de trazado, material y normal. La Z cuenta.
- Líneas de longitud <= `tol`: duplicadas si están a `tol`.
- Arcos y círculos: misma circunferencia (centro y radio a `tol`); los arcos solapados se unen,
  un círculo absorbe los arcos de su circunferencia.
- Polilíneas: se borran las copias idénticas (también invertidas o con otro inicio si son cerradas).
- Capas bloqueadas y congeladas no se tocan.

## Cómo encuentra los pares sin compararlo todo

Cubetas angulares de ancho exacto pi/31416 con una normal fija por cubeta. Cada línea se
registra en las cubetas que cubre su incertidumbre angular `2·tol/L`, así que dos líneas
colineales siempre comparten una. Dentro de la cubeta se agrupa por distancia a esa normal y
se barre por intervalos; cada par candidato se verifica con la geometría exacta y se une
(union-find). Las cubetas son independientes: se reparten entre hilos y el resultado es el
mismo con 1 o N hilos.
