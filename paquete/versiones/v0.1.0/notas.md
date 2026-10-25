## POverkill 0.1.0: OVERKILL en paralelo para AutoCAD 2027

Primer comando de AutoCAD Paralelo listo para instalar. `POVERKILL` hace lo mismo que OVERKILL sobre líneas, pero reparte el cálculo entre todos los núcleos.

**Medido en AutoCAD 2027** (Ryzen 9 5950X, 16 núcleos): 1,2 millones de líneas en 6,3 s, frente a 9,8 s de OVERKILL. El resultado es idéntico con 1 o con N hilos.

### Instalar
1. Descarga `POverkill-0.1.0.zip` (abajo, en *Assets*) y descomprímelo.
2. Doble clic en `instalar.bat`.
3. Abre AutoCAD 2027 y escribe `POVERKILL`. La primera vez AutoCAD pregunta si cargar la DLL (no está firmada): elige "Cargar siempre".

Para quitarlo: `desinstalar.bat`. Para instalar para todos los usuarios: `instalar.bat -TodosLosUsuarios` (pide administrador).

### Comandos
- `POVERKILL`: OVERKILL paralelo sobre LINE. Opciones: Hilos, Tolerancia, Capa, Extremo.
- `POVERKILLBENCH`: no cambia el dibujo; mide con 1, 2, 4... hilos y comprueba que el resultado sea idéntico.

### Límites
- Sólo AutoCAD 2027 (.NET 10). No funciona en AutoCAD LT.
- Sólo líneas (LINE) por ahora; arcos y polilíneas llegarán con OVERKILL v2.
- Prueba primero en una copia de tu dibujo. Se entrega sin garantía (licencia MIT).

Proyecto independiente, sin relación con Autodesk. AutoCAD es marca registrada de Autodesk, Inc.
