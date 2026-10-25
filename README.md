# AutoCAD Paralelo

**Comandos pesados de AutoCAD, rehechos para usar todos los núcleos del procesador, con el mismo resultado.**

AutoCAD hace casi todo en un solo núcleo. En un PC de 16 núcleos, eso deja 15 sin trabajar mientras esperas a
OVERKILL, HATCH o a limpiar una carpeta de planos. Este proyecto toma esos comandos uno por uno, reparte el cálculo
entre núcleos y **comprueba que el dibujo quede igual** que con el comando original. Si no da lo mismo, no sirve,
por rápido que sea.

*English summary below.*

## Resultados medidos

En AutoCAD 2027 real, PC con Ryzen 9 5950X (16 núcleos / 32 hilos):

| Herramienta | Caso | AutoCAD | Esta herramienta | Estado |
|---|---|---|---|---|
| Limpieza por lotes (AUDIT + PURGE) | 32 DWG | 103,7 s | **18,5 s** (5,6×) | ✅ lista: [`lotes/`](lotes/) |
| `POVERKILL` (plugin) | 1,2 millones de líneas | 9,8 s y deja 50.351 líneas de más | **7,4 s**, exacto | ✅ en [`acad_paralelo/`](acad_paralelo/); paquete [`paquete/`](paquete/) |
| `PHATCH` (plugin) | 2.500 áreas con islas | 98,8 s | **2,5 s** (40×) | ✅ en [`acad_paralelo/`](acad_paralelo/) |
| OVERKILL v2 (motor) | 3,1 millones de entidades, 23 tipos de caso difícil | 37,8 s y deja 118.457 entidades de más | **1,2 s**, 100 % exacto | ✅ motor listo: [`overkill/v2/`](overkill/v2/) |

- `POVERKILL` mide el comando completo dentro de AutoCAD (selección, leer, calcular, aplicar) y usa el motor
  OVERKILL v2: LINE, ARC, CIRCLE y LWPOLYLINE con todas sus propiedades. Deja exactamente las líneas esperadas;
  AutoCAD deja ~5 % de más porque no une tramos alineados extremo con extremo. El cálculo con 32 hilos es 0,6 s;
  el resto es leer y escribir en el dibujo, que AutoCAD sólo permite desde un hilo.
- `PHATCH` encuentra los mismos contornos que AutoCAD: 2.500 de 2.500 iguales comparados con `TraceBoundary`.
- OVERKILL v2 usa la tolerancia como distancia real en 3D y revisa todas las propiedades. Sobre un dibujo de
  prueba hecho para encontrar fallos (coordenadas UTM, Z distinta, capas bloqueadas, arcos, polilíneas...) deja
  exactamente lo esperado, donde el OVERKILL de AutoCAD 2027 se equivoca.

## Qué hay en el repo

| Carpeta | Qué es | Para quién |
|---|---|---|
| [`lotes/`](lotes/) | **Limpieza por lotes**: AUDIT + PURGE sobre una carpeta entera de DWG, varios a la vez, con informe HTML/CSV de cuánto bajó cada archivo. Sólo AutoCAD y PowerShell. | Usuarios de AutoCAD |
| [`paquete/`](paquete/) | **Instalador** del plugin: un `.bundle` que AutoCAD carga solo al arrancar (sin `NETLOAD`) y un `instalar.bat`. | Usuarios de AutoCAD |
| `acad_paralelo/` | Plugin .NET para AutoCAD 2027 con `POVERKILL` y `PHATCH`. | Desarrolladores |
| [`overkill/v2/`](overkill/v2/) | **OVERKILL v2**: motor exacto con tolerancia real en 3D, arcos, círculos y polilíneas (Python y C#), y [`overkill/extremo/`](overkill/extremo/), que genera el dibujo de prueba de 3,1 millones de entidades y verifica lo que debe quedar. | Desarrolladores |
| [`overkill_cs/`](overkill_cs/) | Núcleo de OVERKILL en C#, sin AutoCAD: lee un DXF y mide con 1, 2, 4... hilos. | Desarrolladores |
| [`overkill/`](overkill/) | Prototipo en Python donde se probó la idea y se midió cuándo conviene repartir. | Curiosos, investigación |

## Empezar

**Limpiar una carpeta de planos.** Necesitas AutoCAD (no LT) en Windows. Descarga el repo, entra en `lotes/`, haz
doble clic en `limpiar_lotes.bat` y elige la carpeta. Los originales no se tocan: los dibujos limpios quedan en
`<carpeta>_limpios`, con el informe al lado. Más opciones en [lotes/README.md](lotes/README.md).

**Instalar POVERKILL.** Necesitas AutoCAD 2027. Descomprime el paquete `POverkill-<versión>.zip`, doble clic en
`instalar.bat`, abre AutoCAD y escribe `POVERKILL`. Cómo armar el zip y cómo desinstalar:
[paquete/README.md](paquete/README.md).

**Compilar y medir.** El núcleo C# corre en cualquier sistema con .NET 7 u 8:

```bash
cd overkill_cs
dotnet run -c Release -f net8.0 -- dibujo.dxf --threads 1,2,4,8
```

## Cómo funciona

Todos los comandos siguen la misma receta:

1. **Leer** las entidades del dibujo (en el hilo principal: la API de AutoCAD no admite varios hilos).
2. **Copiar** lo necesario a arreglos simples, sin objetos de AutoCAD.
3. **Calcular en paralelo**, repartiendo el trabajo en grupos que no dependen entre sí.
4. **Reensamblar** los resultados en un orden fijo.
5. **Escribir** los cambios en una sola transacción (se deshacen con un solo `U`).

El reparto es la parte delicada: si dos piezas que deben compararse caen en grupos distintos, el resultado
cambia. Por eso cada comando se prueba con 1 y con N hilos y se compara la huella SHA-256 del resultado, que
tiene que ser idéntica, y además se compara con lo que deja el comando de AutoCAD.

Lo que aprendimos al medir:

- **En dibujos pequeños no conviene.** Con menos de unas 30.000 líneas, repartir cuesta lo mismo que lo que se
  gana. Por encima, la ganancia crece con el tamaño.
- **El cálculo deja de ser el problema enseguida.** Con 16 hilos el cálculo de OVERKILL tarda centésimas; el
  tiempo se va en leer y escribir el dibujo. Leer bien importa más que paralelizar: abrir cada objeto por
  separado en vez de todos en una transacción bajó la lectura de 1,2 millones de líneas de 92 s a 0,4 s.
- **Entre archivos es lo más fácil.** La limpieza por lotes reparte dibujos completos, uno por proceso, así
  que no hay ningún riesgo de cambiar el resultado. Pasar de 16 a 32 procesos ya no mejora: manda el disco.

## Próximos comandos

1. `PJOIN`: unir líneas y arcos en polilíneas en muchos grupos a la vez.
2. `PHATCH` con arcos y círculos como contorno e islas anidadas; `PBOUNDARY`.

¿Tienes un comando que se te hace eterno? Abre un *issue* con el comando, el tamaño del dibujo y cuánto tarda.
Ver [CONTRIBUTING.md](CONTRIBUTING.md).

## Requisitos y límites

- Windows con AutoCAD 2027 para el plugin (está compilado para .NET 10, que es lo que usa AutoCAD 2027).
  AutoCAD 2025/2026 usan .NET 8 y no lo cargan todavía.
- La limpieza por lotes funciona con AutoCAD 2018 o posterior (usa `accoreconsole` y guarda en formato 2018).
- No funciona en AutoCAD LT: LT no admite plugins ni `accoreconsole`.
- `PHATCH` sólo usa tramos rectos (LINE y polilíneas sin arcos) como contorno por ahora.

## Licencia y marcas

Código bajo licencia [MIT](LICENSE): puedes usarlo, modificarlo y repartirlo, también en proyectos comerciales,
conservando el aviso de copyright. Se entrega sin garantía: prueba primero en copias de tus dibujos.

Proyecto independiente, sin relación con Autodesk. AutoCAD es una marca registrada de Autodesk, Inc. Cada persona
usa estas herramientas con su propia licencia de AutoCAD; el repo no incluye nada de Autodesk.

---

## English summary

**Heavy AutoCAD commands rebuilt to use every CPU core, with the same result.** Each command reads the drawing on
the main thread, copies the data into plain arrays, computes in parallel, reassembles in a fixed order and writes
the changes in one transaction. Every tool is checked to give an identical result with 1 and N threads (SHA-256
fingerprint) and compared against the native AutoCAD command.

Measured in AutoCAD 2027 on a 16-core Ryzen 9 5950X: batch AUDIT + PURGE of 32 DWG files in 18.5 s instead of
103.7 s (5.6×); `POVERKILL` on 1.2 million lines in 7.4 s instead of 9.8 s, with the exact expected result; `PHATCH` 30–40×
faster than HATCH with identical boundaries; OVERKILL v2 engine exact on a 3.1-million-entity
stress drawing in 1.2 s, where AutoCAD takes 37.8 s and leaves 118,457 extra entities. Ready to use: [`lotes/`](lotes/) (batch cleanup,
PowerShell only) and [`paquete/`](paquete/) (installer for the plugin, AutoCAD 2027). Docs are in Spanish;
issues in English are welcome. MIT license. Not affiliated with Autodesk.
