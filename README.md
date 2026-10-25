# AutoCAD Paralelo: OVERKILL, HATCH y PURGE más rápidos en AutoCAD

**Herramientas gratuitas para los cálculos de AutoCAD que se hacen eternos, se cuelgan o dejan el dibujo a medias.
Usan todos los núcleos del procesador y dejan el mismo dibujo que el comando original, o uno más correcto.**

¿Te pasa alguna de estas?

- **OVERKILL tarda minutos** o deja líneas duplicadas y solapadas sin borrar.
- **HATCH se queda pensando** ("AutoCAD no responde") al sombrear muchas áreas o al elegir un punto interior.
- **Tienes que purgar y auditar decenas o cientos de DWG** y hacerlo uno por uno te lleva la tarde.
- Tu PC tiene 8, 16 o más núcleos, pero **AutoCAD usa uno solo** y el resto está parado.

Este proyecto toma esos comandos uno por uno y los rehace para repartir el cálculo entre todos los núcleos. Cada
herramienta se comprueba contra el comando de AutoCAD: si no deja el mismo dibujo, no sirve, por rápida que sea.

*English version below: [faster OVERKILL, HATCH and batch PURGE for AutoCAD](#english).*

## Qué resuelve

| Problema en AutoCAD | Herramienta | Resultado medido |
|---|---|---|
| Purgar y auditar muchos dibujos (PURGE + AUDIT por lotes) | Limpieza por lotes, en [`lotes/`](lotes/) | 32 DWG en **18,5 s** en vez de 103,7 s (5,6 veces más rápido) |
| OVERKILL lento o que deja duplicados | Comando `POVERKILL` | 1,2 millones de líneas en **7,4 s**, exacto. OVERKILL: 9,8 s y deja 50.351 líneas de más |
| HATCH que se cuelga buscando el contorno | Comando `PHATCH` | 2.500 áreas con islas en **2,5 s**. HATCH: 98,8 s. Contornos idénticos (2.500 de 2.500) |
| OVERKILL que falla en dibujos difíciles (coordenadas UTM, Z, arcos, polilíneas) | Motor OVERKILL v2 | 3,1 millones de entidades en **1,2 s**, 100 % exacto. OVERKILL: 37,8 s y deja 118.457 de más |

Medido en AutoCAD 2027 real, con un Ryzen 9 5950X (16 núcleos). En un PC con menos núcleos la ganancia es menor,
pero el resultado es el mismo.

## Descargar e instalar

**Para eliminar líneas duplicadas y sombrear rápido (POVERKILL y PHATCH).** Necesitas AutoCAD 2027 en Windows.

1. Baja el zip desde [Versiones (Releases)](https://github.com/JuanC1220/AutoCAD-Paralelo-/releases) y descomprímelo.
2. Doble clic en `instalar.bat`. No hace falta `NETLOAD`: AutoCAD lo carga solo al arrancar.
3. Abre AutoCAD y escribe `POVERKILL`. La primera vez AutoCAD pregunta si cargar la DLL: elige "Cargar siempre".

La versión 0.1.0 trae `POVERKILL` sólo para líneas. `PHATCH` y `POVERKILL` con el motor v2 (arcos, círculos y
polilíneas) ya están en [`acad_paralelo/`](acad_paralelo/): se cargan con `NETLOAD` desde
`acad_paralelo/dist/AcadParalelo.dll` y llegarán al instalador en la próxima versión.
Más detalles y cómo desinstalar: [paquete/README.md](paquete/README.md).

**Para purgar y auditar una carpeta entera de planos.** Sirve con AutoCAD 2018 o posterior. Descarga el repo
(botón verde *Code* → *Download ZIP*), entra en `lotes/`, doble clic en `limpiar_lotes.bat` y elige la carpeta.
Los originales no se tocan: los dibujos limpios quedan en `<carpeta>_limpios`, con un informe de cuánto bajó
cada archivo. Opciones en [lotes/README.md](lotes/README.md).

Prueba siempre primero en copias de tus dibujos.

## Preguntas frecuentes

**¿Por qué OVERKILL es tan lento en dibujos grandes?** Compara cada línea con sus vecinas usando un solo núcleo.
`POVERKILL` agrupa las líneas que pueden solaparse y procesa los grupos a la vez en todos los núcleos.

**¿Por qué OVERKILL deja líneas duplicadas?** En nuestras pruebas, OVERKILL de AutoCAD 2027 sólo compara líneas
casi perfectamente paralelas, falla con coordenadas grandes (UTM) y no une tramos alineados extremo con extremo.
El motor v2 usa la tolerancia como una distancia real y revisa todas las propiedades (capa, color, tipo de línea,
grosor...), así que deja exactamente lo que debería quedar.

**¿Por qué se congela AutoCAD al usar HATCH?** Para cada punto interior, HATCH analiza todo el dibujo otra vez
buscando el contorno. `PHATCH` analiza el dibujo una sola vez y busca todos los contornos en paralelo.

**¿Se puede purgar muchos DWG a la vez?** Sí: la limpieza por lotes abre varios AutoCAD sin ventana
(`accoreconsole`) al mismo tiempo, uno por dibujo, y hace AUDIT y PURGE en cada uno.

**¿Funciona en AutoCAD LT?** No. LT no admite plugins .NET ni `accoreconsole`.

**¿Funciona en AutoCAD 2025 o 2026?** La limpieza por lotes sí. Los comandos `POVERKILL` y `PHATCH` por ahora
sólo en AutoCAD 2027, porque usan .NET 10.

**¿Puedo deshacer?** Sí. Cada comando aplica todos sus cambios de una vez y se deshace con un solo `U`.

**¿Es seguro?** El código es abierto: puedes leer exactamente qué hace. Las herramientas no envían nada a
Internet. Aun así, se entregan sin garantía.

## Cómo funciona

Todos los comandos siguen la misma receta:

1. **Leer** las entidades del dibujo (en el hilo principal: la API de AutoCAD no admite varios hilos).
2. **Copiar** lo necesario a arreglos simples, sin objetos de AutoCAD.
3. **Calcular en paralelo**, repartiendo el trabajo en grupos que no dependen entre sí.
4. **Reensamblar** los resultados en un orden fijo.
5. **Escribir** los cambios en una sola transacción.

El reparto es la parte delicada: si dos piezas que deben compararse caen en grupos distintos, el resultado
cambia. Por eso cada comando se prueba con 1 y con N hilos (la huella SHA-256 del resultado tiene que ser
idéntica) y se compara con lo que deja el comando de AutoCAD.

Lo que aprendimos al medir:

- **En dibujos pequeños no se nota.** Con menos de unas 30.000 líneas, repartir cuesta casi lo mismo que lo que
  se gana. Por encima, la ganancia crece con el tamaño.
- **El cálculo deja de ser el problema enseguida.** Con 32 hilos el cálculo de OVERKILL tarda 0,6 s en 1,2
  millones de líneas; el resto del tiempo es leer y escribir en el dibujo, que AutoCAD sólo permite desde un hilo.
- **Entre archivos es lo más fácil.** La limpieza por lotes reparte dibujos completos, uno por proceso, así que
  no hay ningún riesgo de cambiar el resultado. Pasar de 16 a 32 procesos ya no mejora: manda el disco.

## Qué hay en el repo

| Carpeta | Qué es |
|---|---|
| [`lotes/`](lotes/) | Limpieza por lotes: AUDIT + PURGE sobre muchos DWG a la vez, con informe HTML y CSV. Sólo AutoCAD y PowerShell. |
| [`paquete/`](paquete/) | Instalador del plugin (`.bundle` que AutoCAD carga solo) y cómo publicar versiones. |
| [`acad_paralelo/`](acad_paralelo/) | Plugin .NET para AutoCAD 2027 con `POVERKILL` y `PHATCH`. |
| [`overkill/v2/`](overkill/v2/) | Motor OVERKILL v2 (Python y C#) y, en [`overkill/extremo/`](overkill/extremo/), el dibujo de prueba de 3,1 millones de entidades. |
| [`hatch_cs/`](hatch_cs/) | Búsqueda de contornos de HATCH en paralelo, sin AutoCAD. |
| [`overkill_cs/`](overkill_cs/) | Primer núcleo de OVERKILL en C#: lee un DXF y mide con 1, 2, 4... hilos. |
| [`overkill/`](overkill/) | Prototipo en Python donde se probó la idea. |

## Próximos comandos

1. `PJOIN`: unir líneas y arcos en polilíneas en muchos grupos a la vez.
2. `PHATCH` con arcos y círculos como contorno e islas anidadas; `PBOUNDARY`.

¿Hay un comando que se te hace eterno? Abre un [issue](https://github.com/JuanC1220/AutoCAD-Paralelo-/issues/new/choose)
con el comando, el tamaño del dibujo y cuánto tarda. Ver [CONTRIBUTING.md](CONTRIBUTING.md).

## Licencia: gratis, también para tu trabajo; lo que no se puede es venderla

**Puedes usar estas herramientas gratis en tu trabajo**, aunque ese trabajo sea pagado: como empleado, en tu
empresa o como independiente, para hacer y entregar tus planos. También puedes estudiarlas, modificarlas y
compartirlas gratis.

**Lo que no se puede es comercializar la herramienta**: venderla, cobrar por ella o por una versión modificada,
ni ofrecer un producto o servicio que la reemplace o compita con ella, aunque sea gratis. Si te interesa algo de
eso, abre un *issue* y lo conversamos.

Texto completo: [LICENSE](LICENSE) ([PolyForm Shield 1.0.0](https://polyformproject.org/licenses/shield/1.0.0/)).
Se entrega sin garantía.

La versión 0.1.0 de POverkill se publicó con licencia MIT; desde las versiones siguientes rige esta licencia.

**Sin relación con Autodesk.** Este es un proyecto independiente: no está hecho, aprobado ni respaldado por
Autodesk, Inc. AutoCAD es una marca registrada de Autodesk, Inc. Cada persona usa estas herramientas con su propia
licencia de AutoCAD, y el repo no incluye ni redistribuye ningún archivo de Autodesk.

---

<a id="english"></a>

## English: faster OVERKILL, HATCH and batch PURGE for AutoCAD

**Free tools for the AutoCAD operations that take forever, freeze or leave the drawing half done.** They use every
CPU core and leave the same drawing as the native command, or a more correct one.

- **OVERKILL is slow** or leaves duplicate and overlapping lines: `POVERKILL` handles 1.2 million lines in 7.4 s
  instead of 9.8 s, with the exact expected result (OVERKILL leaves 50,351 extra lines).
- **HATCH freezes** ("AutoCAD not responding") when picking internal points: `PHATCH` fills 2,500 areas in 2.5 s
  instead of 98.8 s, with identical boundaries.
- **Purge and audit many DWG files at once**: batch cleanup does 32 drawings in 18.5 s instead of 103.7 s.
- **AutoCAD uses a single core** while the rest of your CPU sits idle: every tool here runs in parallel.

Measured in AutoCAD 2027 on a 16-core Ryzen 9 5950X. Download the installer from
[Releases](https://github.com/JuanC1220/AutoCAD-Paralelo-/releases) (AutoCAD 2027, Windows; version 0.1.0 has
`POVERKILL` for lines only, the rest is in `acad_paralelo/`). Batch cleanup works
with AutoCAD 2018 or later. Not for AutoCAD LT. Docs are in Spanish; issues in English are welcome.

**License:** free to use, including in your paid work (as an employee, at your company or as a freelancer).
What is not allowed is commercializing the tool itself: selling it, charging for it or for a modified version, or
offering a product that competes with it. [PolyForm Shield 1.0.0](LICENSE). Version 0.1.0 of POverkill was released under MIT.

**Not affiliated with Autodesk.** AutoCAD is a registered trademark of Autodesk, Inc. No Autodesk files are
included or redistributed.
