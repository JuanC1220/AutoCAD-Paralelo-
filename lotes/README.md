# Limpieza por lotes: AUDIT + PURGE en muchos DWG

Lanza un `accoreconsole` (el AutoCAD sin ventana que viene con AutoCAD) por dibujo, varios a la vez, y entrega
un informe con cuánto bajó cada archivo. No usa nada fuera de AutoCAD y PowerShell de Windows.

Aquí el paralelo es entre archivos: cada dibujo va en su propio proceso, así que no hay riesgo de que el
resultado cambie por repartir. Cada archivo queda igual que si le hicieras AUDIT y PURGE a mano.

## Uso

Doble clic en `limpiar_lotes.bat`, elegir la carpeta. O en PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File limpiar_lotes.ps1 -Entrada C:\planos -Recursivo
```

| Parámetro | Qué hace |
|---|---|
| `-Entrada` | Carpeta(s) o archivo(s) .dwg. Sin él, abre un diálogo. |
| `-Recursivo` | Incluye subcarpetas (la estructura se repite en la salida). |
| `-Salida` | Dónde dejar los dibujos limpios. Por defecto `<carpeta>_limpios`. |
| `-Hilos` | Cuántos AutoCAD a la vez. Por defecto, los núcleos físicos. `-Hilos 1` sirve para medir la ganancia. |
| `-EnSitio` | Reemplaza cada original por su versión limpia, sólo si salió bien. El original queda en `<Salida>\respaldo`. |
| `-Geometria` | Además purga geometría de longitud cero y textos vacíos (esto sí borra objetos). |
| `-SinAudit` / `-SinPurge` | Hace sólo una de las dos cosas. |
| `-TiempoMax` | Segundos por dibujo antes de cortarlo (600). |
| `-Acc` | Ruta a otro `accoreconsole.exe`. Por defecto el del AutoCAD más nuevo instalado. |

## Qué hace con cada dibujo

1. Copia el DWG a la carpeta de salida (el original no se abre).
2. `AUDIT` corrigiendo errores.
3. `-PURGE` Todo y Regapps, repetido hasta que ya no cambie nada (los bloques dentro de bloques sin usar
   necesitan varias pasadas; máximo 6).
4. Guarda (`QSAVE`). Ojo: AutoCAD guarda en su formato por defecto, así que un DWG antiguo sale en formato 2018.

Las respuestas van con `_` (`_A`, `_R`, `_Y`), así funciona en AutoCAD en cualquier idioma. Las cuentas de
bloques, capas, tipos de línea, estilos y regapps se toman con AutoLISP antes y después, no leyendo el texto.

## Informe

En la carpeta de salida quedan `informe_<fecha>.html` e `informe_<fecha>.csv` con, por archivo: estado,
MB antes y después, % de reducción, segundos, errores de AUDIT encontrados/corregidos, y bloques, capas, tipos
de línea, estilos de texto y de cota y regapps antes → después. Arriba, el total y la ganancia frente a hacerlos
uno por uno (suma de los tiempos de cada archivo / tiempo real).

Si un archivo falla (no abre, no guarda, se pasa de tiempo) se marca ERROR, no queda una copia a medias en la
salida, y su log de accoreconsole se guarda en `<Salida>\_trabajo`.

## Prueba con dibujos sintéticos (`pruebas/`)

```powershell
python pruebas\gen_basura_dxf.py --n 32 --out prueba_lotes    # DXF con capas, bloques, estilos y regapps sin usar
powershell -ExecutionPolicy Bypass -File pruebas\dxf_a_dwg.ps1 -Carpeta prueba_lotes
Remove-Item prueba_lotes\*.dxf, prueba_lotes\*.scr*
powershell -ExecutionPolicy Bypass -File limpiar_lotes.ps1 -Entrada prueba_lotes -Hilos 1
powershell -ExecutionPolicy Bypass -File limpiar_lotes.ps1 -Entrada prueba_lotes -Salida prueba_lotes_16 -Hilos 16
```

Cada `plano_NNN.dxf.json` dice lo que debería quedar (10 capas usadas + la 0, el bloque `USADO`).
