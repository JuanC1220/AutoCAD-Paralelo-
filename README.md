# AutoCAD Paralelo

Prototipo para medir si vale la pena paralelizar comandos pesados de CAD.
Primer caso: OVERKILL sobre LINE en archivos DXF.

Receta: leer -> copiar -> calcular en paralelo -> reensamblar -> escribir.

```bash
pip install ezdxf numpy
cd overkill
python gen_dxf.py --n 100000 --out s100k.dxf      # DXF sintético + s100k.dxf.json (conteos esperados)
python bench.py check s100k.dxf                    # esperado vs secuencial vs paralelo (1, 2, 4)
python bench.py time  s100k.dxf                    # tiempos por fase
python bench.py write s100k.dxf salida.dxf 4       # aplica OVERKILL paralelo y escribe el DXF
```

- `gen_dxf.py`: segmentos base + defectos plantados (duplicados, invertidos, solapes, contenidos, extremo con extremo, otra capa, casi paralelos).
- `overkill_core.py`: lector DXF rápido, versión secuencial de referencia y versión paralela (partición por recta portadora).
- `bench.py`: verificación de igualdad y medición.
