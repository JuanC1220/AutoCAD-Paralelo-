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
4. Guarda con `SAVEAS 2018` sobre el mismo DWG (no `QSAVE`: si el formato por defecto de AutoCAD es DXF, QSAVE
   escribe un .dxf aparte). Ojo: un DWG más antiguo sale en formato 2018 y ya no abre en AutoCAD anterior a 2018.
   Si el DWG no quedó reescrito, el archivo se marca ERROR.

PURGE también quita la capa Defpoints si no se usa; AutoCAD la vuelve a crear cuando hace falta.

Las respuestas van con `_` (`_A`, `_R`, `_Y`), así funciona en AutoCAD en cualquier idioma. Las cuentas de
bloques, capas, tipos de línea, estilos y regapps se toman con AutoLISP antes y después, no leyendo el texto.

## Informe

En la carpeta de salida quedan `informe_<fecha>.html` e `informe_<fecha>.csv` con, por archivo: estado,
MB antes y después, % de reducción, segundos, errores de AUDIT encontrados/corregidos, y bloques, capas, tipos
de línea, estilos de texto y de cota y regapps antes → después. Arriba, el total, el tiempo real y los
segundos por archivo. Para la ganancia, compara con una corrida `-Hilos 1` (sumar los segundos de cada archivo
exagera, porque en paralelo cada uno tarda más).

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

## Resultado medido (AutoCAD 2027, Ryzen 9 5950X 16 núcleos / 32 hilos, 32 GB)

32 DWG sintéticos (0,40 a 1,74 MB, 32,70 MB en total), 32/32 OK en todas las corridas:

| A la vez | Tiempo real | Ganancia |
|---|---|---|
| 1 | 103,7 s | 1,0× |
| 4 | 32,5 s | 3,2× |
| 16 | 18,5 s | 5,6× |
| 32 | 18,3 s | 5,7× |

Pasar de 16 a 32 no mejora: cada dibujo sube de unos 3 s a unos 8 s por la competencia entre procesos
(disco, memoria). Por eso el valor por defecto son los núcleos físicos. Verificado con LISP: cada dibujo limpio
conserva todas sus LINE e INSERT y queda con 11 capas y el bloque usado, como dice su `.json`.
