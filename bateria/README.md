# Batería de dibujos variados (POVERKILL y PHATCH)

Prueba los comandos del plugin con dibujos pequeños, medianos y grandes, densos y poco densos, y con todo tipo de
entidad, y los compara con OVERKILL y HATCH de AutoCAD. Responde las tres preguntas del proyecto en cada dibujo:
¿deja el mismo dibujo?, ¿cuánto más rápido es? y ¿desde qué tamaño conviene?

```
python gen_bateria.py --out dibujos                 # ~1,5 min, 20 DXF, ~250 MB (--rapido: 6 pequeños)
& .\correr_bateria.ps1 -Carpeta dibujos -Dll ..\acad_paralelo\dist\AcadParalelo.dll -Hilos 1,32
python verificar_bateria.py dibujos                 # -> dibujos\resultados\informe.md
```

Necesita Python con `ezdxf` y `numpy` (el verificador usa el motor de referencia `overkill/v2/overkill_v2.py`),
y AutoCAD 2027 para la corrida. `correr_bateria.ps1` trabaja sobre copias y no repite lo que ya tiene resultado
(`-Repetir` para forzar, `-Solo overkill|hatch`, `-Filtro densa_50000` para uno solo, `-SinNativo`).

## Dibujos

| Comando | Densa | Poco densa |
|---|---|---|
| OVERKILL `o_*.dxf` | 300, 1 000, 3 000, 10 000, 50 000, 150 000 y 400 000 entidades apretadas (se cruzan mucho), ~60 % de las bases con copias o solapes | 1 000, 50 000 y 400 000 entidades dispersas en un área enorme, ~5 % con copias |
| HATCH `h_*.dxf` | rejilla deformada de 2×2 a 50×50 celdas que comparten lados | 8×8, 25×25 y 50×50 celdas sueltas, giradas y separadas |

Cada familia de casos está en su capa, así el informe dice qué caso falla.

**OVERKILL** (clase *v2*: el motor de referencia sabe qué debe quedar, POVERKILL debe cuadrar exacto; clase *fuera*:
POVERKILL no toca ese tipo y se mira qué hace AutoCAD)

| Capa | Clase | Casos |
|---|---|---|
| L_COPIAS | v2 | líneas con copias exactas, invertidas, contenidas, solapes, continuaciones, otro color, paralelas a 1e-3 |
| L_AZAR | v2 | líneas que se cruzan, nada que borrar |
| P_RECTAS, P_CURVAS | v2 | polilíneas rectas y con arcos (bulge), abiertas y cerradas: copias exactas, invertidas, con otro inicio, otro color, un vértice movido |
| A_ARCOS | v2 | arcos sobre la misma circunferencia: copias, solapes, contenidos, continuaciones, que pasan por 0° |
| C_CIRCULOS | v2 | copias, concéntricos, desplazados 1e-3, arcos encima del círculo |
| S_SPLINES | fuera | splines por puntos de control: copias exactas y de otro color |
| E_ELIPSES | fuera | elipses y arcos de elipse repetidos |
| X_LINEA_EN_POLI | fuera | LINE encima de un tramo de polilínea, igual o parcial |
| O_PUNTOS_TEXTOS | fuera | POINT y TEXT repetidos |

**HATCH** (un POINT por área; `<dxf>.puntos.txt` para el -HATCH nativo)

| Familia | PHATCH la soporta | Caso |
|---|---|---|
| H_LINEAS, H_POLIS | sí | celda de LINE o de LWPOLYLINE cerrada (sus lados también cierran las vecinas) |
| H_DIAGONAL | sí | celda partida por una diagonal |
| H_ISLA, H_ISLA_POLI | sí | isla cuadrada de LINE o de polilínea |
| H_RUIDO | sí | segmentos sueltos dentro de la celda (no cambian el área) |
| H_ANIDADA | no | isla con otra isla dentro: Normal y Exterior dan áreas distintas |
| H_CIRCULO, H_ARCOS, H_ELIPSE, H_SPLINE | no | islas curvas: círculo, polilínea con arcos, elipse, spline |

## Qué compara el verificador

- **OVERKILL:** reduce cada entidad a una clave (tipo, capa, color y números redondeados a 1e-5; las polilíneas igual
  aunque estén invertidas o empiecen en otro vértice) y cuenta, por capa, las que faltan y sobran frente a lo que
  calcula `overkill_v2` sobre el DXF. También comprueba que POVERKILL deje el mismo dibujo con 1 y con N hilos y
  que lo que lee v2 del DXF sea lo que abrió AutoCAD (volcado `original`).
- **HATCH:** rehace cada sombreado desde sus lazos (líneas, arcos, elipses, splines, polilíneas con bulge), calcula su
  área y la asigna al punto que contiene. Por familia cuenta: ok, ok sólo en estilo Normal o Exterior, área distinta,
  sin sombreado, y sombreados que se salen de su área y cubren varios puntos.
- **Punto de corte:** con la serie densa compara el tiempo del comando (medido dentro de AutoCAD, con la selección)
  del nativo contra POVERKILL/PHATCH, y da el tamaño desde el que el nuestro gana siempre.

El volcado lo hace AutoLISP dentro de accoreconsole (`entget` de cada entidad), así no depende de cómo AutoCAD
guarde el archivo.
