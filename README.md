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

## Modo AutoCAD

`overkill_core.acad_seq` / `acad_par` imitan la regla medida en AutoCAD 2027 real: dos líneas sólo se
comparan si son casi exactamente paralelas (corte angular interno ~1e-10 rad, independiente de la
Tolerancia); la Tolerancia se usa luego para la distancia entre paralelas y los extremos.
Sobre `s5000.dxf` (seed 1): AutoCAD 2027 deja 6233 / 5924 / 5922 líneas (defecto / extremo con
extremo / ignorar capa); el modo AutoCAD deja 6218 / 5905 / 5907 (0,3 % de diferencia).
`python bench.py acad s5000.dxf`

## Versión C# (overkill_cs/)

Misma regla que el modo AutoCAD de Python, con hilos que comparten memoria (`Parallel.For`).
Da exactamente las mismas líneas que `acad_seq` (misma huella SHA-256 en 9 casos probados).

```bash
cd overkill_cs
dotnet run -c Release -f net8.0 -- ../overkill/s400k.dxf   # o -f net7.0
# --threads 1,2,4,8,16
# o un .exe para Windows sin instalar .NET:
dotnet publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -o publish
```

Nube, 4 núcleos, 600.397 líneas (sólo cálculo): 1 hilo 0,256 s, 4 hilos 0,073 s (Python: 3,3 s y 1,5 s).

## Limpieza por lotes (lotes/)

AUDIT + PURGE sobre muchos DWG a la vez, un `accoreconsole` por dibujo, con informe de tamaño antes/después.
Ver [lotes/README.md](lotes/README.md).
