# Dibujo extremo para OVERKILL

`gen_extremo.py` crea un DXF de millones de entidades con 23 **familias** de casos difíciles,
cada una en su propia capa (`F01_...` a `F23_...`). Tras correr OVERKILL (AutoCAD, POVERKILL
o `overkill_core`) se cuenta por capa y se compara con `<dxf>.json`: así se ve qué caso falla.

```
python gen_extremo.py --total 3000000 --out extremo_3M.dxf      # ~40 s, 447 MB
python verificar_extremo.py extremo_3M.dxf.json --motor exacto --e2e
powershell -ExecutionPolicy Bypass -File correr_autocad.ps1 -dxf extremo_3M.dxf -e2e Y
python verificar_extremo.py extremo_3M.dxf.json --csv res_extremo_3M_e2eY.csv --e2e
```

La misma semilla da el mismo archivo. Tolerancia 1e-6, Ignorar = Ninguno.

| Clase | Familias | Qué significa |
|---|---|---|
| seguro | F01 copias exactas, F02 invertidas, F03 contenidas, F04 solapes en cadena, F05 extremo con extremo, F06 mezcla en ejes, F07 mezcla oblicua (~110 000 ángulos) | ya medido en AutoCAD 2027: debe cuadrar exacto (F07: AutoCAD dejó ~1 % sin fusionar en pruebas anteriores) |
| nuevo | F08 coordenadas UTM (~4 500 000), F09 todo a Z=100, F10 una propiedad distinta (color, tipo, grosor, altura, transparencia, escala de tipo, capa), F11 paralelas a 1e-3/1e-4/1e-5, F12 casi duplicados trasladados < 0,3e-6, F13 misma XY a distinta Z / 3D, F14 capa bloqueada, F15 capa congelada, F17 arcos y círculos | la geometría es clara pero aún no se ha visto qué hace AutoCAD |
| frontera | F16 capa apagada, F18 giro de 1e-13 a 1e-6 rad (una capa por ángulo), F19 paralela a 0,5/0,9/1,1/2 e-6, F20 extremos movidos ±0,3e-6, F21 longitud cero, F22 PorCapa vs color/tipo explícito, F23 polilíneas duplicadas | límites a propósito: sirven para comparar motores, no tienen una única respuesta |

Los conteos de las familias seguras y nuevas de LINE se calculan con enteros exactos al generar;
`overkill_core` en modo exacto los reproduce al 100 % en las familias seguras.
