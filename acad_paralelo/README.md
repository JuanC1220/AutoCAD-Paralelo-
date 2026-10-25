# AutoCAD Paralelo: plugin para AutoCAD 2027

Comandos de AutoCAD que hacen su cálculo en varios hilos. Todos siguen la misma receta:

1. **leer** las entidades del dibujo (hilo principal: la API de AutoCAD no admite varios hilos),
2. **copiar** lo necesario a arreglos simples,
3. **calcular en paralelo** sin tocar AutoCAD,
4. **aplicar** los cambios en una sola transacción (se deshace con un solo `U`).

| Comando | Qué hace |
|---|---|
| `POVERKILL` | OVERKILL paralelo sobre LINE. Mismo núcleo que `overkill_cs/` (modo AutoCAD): mismo resultado con 1 o N hilos. Opciones: Hilos, Tolerancia, Capa (ignorar capa), Extremo (extremo con extremo). |
| `POVERKILLBENCH` | No modifica el dibujo: mide el cálculo con 1, 2, 4, … hilos y comprueba que el resultado sea idéntico (huella SHA-256). |
| `PLEERMEDIR` | No modifica el dibujo: compara formas de leer las LINE (seleccionar, recorrer el espacio, abrir por bloques de distintos tamaños, transacción normal, `ObjectId.Open`, propiedades como texto) para elegir la más rápida. |
| `PHATCHMEDIR` | Mide dónde se va el tiempo de HATCH: detectar contorno, crear sombreado, generar patrón. Un sombreado ANSI31 por cada POINT seleccionado. |

Todos leen con `Lector.cs`: abre por bloques de 20.000 en transacciones abrir/cerrar y compara capa, color, tipo de línea,
escala de tipo de línea, grosor, altura de objeto, transparencia, estilo de trazado (si es STB), material, normal y elevación
(por ObjectId o valor, nunca por nombre). Omite capas bloqueadas y líneas no planas en XY.

Los tiempos salen en la línea de comandos y se añaden a `<dibujo>.acadparalelo.txt`.

## Compilar

Necesita el SDK de .NET 10 (AutoCAD 2027 corre sobre .NET 10). Las referencias de AutoCAD vienen del paquete NuGet
`AutoCAD.NET.Core` 26.0.0 (sólo AcCoreMgd y AcDbMgd, así también carga en `accoreconsole`).

```bash
cd acad_paralelo
dotnet build -c Release        # -> bin/Release/net10.0/AcadParalelo.dll
```

En AutoCAD: `NETLOAD` y elegir `AcadParalelo.dll`.

## Pruebas con accoreconsole (`pruebas/`)

```powershell
# OVERKILL nativo vs POVERKILL (1 y N hilos) vs POVERKILLBENCH, sobre copias del DXF
powershell -ExecutionPolicy Bypass -File pruebas\probar.ps1 -Modo overkill -Dxf s400k.dxf -Hilos 1,16,32   # -SoloPoverkill
# formas de leer el dibujo
powershell -ExecutionPolicy Bypass -File pruebas\probar.ps1 -Modo leer -Dxf s400k.dxf
# HATCH: rejilla de celdas con un punto interior en cada una
python pruebas\gen_hatch_dxf.py --k 50 --out h50.dxf
powershell -ExecutionPolicy Bypass -File pruebas\probar.ps1 -Modo hatch -Dxf h50.dxf
```

Los resultados quedan en `pruebas/resultados/<dxf>/`.
