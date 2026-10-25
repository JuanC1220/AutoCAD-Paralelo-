# Prototipo OVERKILL paralelo (Python)

Aquí se probó la receta **leer → copiar → calcular en paralelo → reensamblar → escribir** con OVERKILL sobre
LINE en archivos DXF, y se midió desde qué tamaño conviene repartir. El núcleo rápido está en
[`../overkill_cs/`](../overkill_cs/); esto queda como referencia y banco de pruebas.

```bash
pip install ezdxf numpy
cd overkill
python gen_dxf.py --n 100000 --out s100k.dxf      # DXF sintético + s100k.dxf.json (conteos esperados)
python bench.py check s100k.dxf                    # esperado vs secuencial vs paralelo (1, 2, 4)
python bench.py time  s100k.dxf                    # tiempos por fase
python bench.py write s100k.dxf salida.dxf 4       # aplica OVERKILL paralelo y escribe el DXF
python bench.py acad  s5000.dxf                    # modo AutoCAD (ver abajo)
```

- `gen_dxf.py`: segmentos base + defectos plantados (duplicados, invertidos, solapes, contenidos, extremo con
  extremo, otra capa, casi paralelos).
- `overkill_core.py`: lector DXF rápido, versión secuencial de referencia y versión paralela (partición por
  recta portadora: dos líneas que deben compararse siempre caen en el mismo grupo, así que no hay bordes).
- `bench.py`: verificación de igualdad y medición.
- `benchmark_4nucleos.jsonl`: tiempos por fase en una máquina de 4 núcleos, de 1.475 a 600.397 líneas.

## Resultados (4 núcleos)

Secuencial y paralelo dan exactamente las mismas líneas de 1.500 a 600.000. Con 4 hilos: 2,5× en 600.000 líneas,
1,9× en 150.000, empate hacia 30.000. Por debajo de eso, repartir no compensa.

## Modo AutoCAD

`overkill_core.acad_seq` / `acad_par` imitan la regla medida en AutoCAD 2027 real: dos líneas sólo se comparan
si son casi exactamente paralelas (corte angular interno ~1e-10 rad, independiente de la Tolerancia); la
Tolerancia se usa luego para la distancia entre paralelas y los extremos.

Sobre `s5000.dxf` (seed 1): AutoCAD 2027 deja 6233 / 5924 / 5922 líneas (defecto / extremo con extremo /
ignorar capa); el modo AutoCAD deja 6218 / 5905 / 5907 (0,3 % de diferencia).
