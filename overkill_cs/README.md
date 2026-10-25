# Núcleo OVERKILL en C#

Misma regla que el modo AutoCAD del prototipo Python ([`../overkill/`](../overkill/)), con hilos que comparten
memoria (`Parallel.For`). Da exactamente las mismas líneas que `acad_seq` (misma huella SHA-256 en 9 casos
probados), con 1 o con N hilos. No necesita AutoCAD: lee un DXF.

```bash
cd overkill_cs
dotnet run -c Release -f net8.0 -- dibujo.dxf      # o -f net7.0
dotnet run -c Release -f net8.0 -- dibujo.dxf --threads 1,2,4,8,16
# un .exe para Windows sin instalar .NET:
dotnet publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -o publish
```

## Tiempos (sólo cálculo)

| Máquina | Líneas | 1 hilo | N hilos |
|---|---|---|---|
| Nube, 4 núcleos | 600.397 | 0,256 s | 0,073 s (4) |
| Ryzen 9 5950X, 16 núcleos | 600.397 | 0,190 s | 0,035 s (16) |
| Ryzen 9 5950X, 16 núcleos | 1.200.734 | 0,330 s | 0,047 s (32) |

Python en la misma máquina de 4 núcleos: 3,3 s y 1,5 s. AutoCAD 2027 tarda 4,9 s en OVERKILL sobre las 600.397
líneas. Con este núcleo, lo que pesa ya es leer el DXF (unos 2,6 s), no el cálculo.
