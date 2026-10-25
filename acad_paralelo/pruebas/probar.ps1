# Corre comandos nativos de AutoCAD y los del plugin sobre COPIAS de un DXF con accoreconsole y anota resultados.
# No toca tus dibujos; los ajustes que cambia (SECURELOAD, OSMODE, HPASSOC) se devuelven a su valor al terminar.
#   powershell -ExecutionPolicy Bypass -File probar.ps1 -Modo overkill -Dxf s400k.dxf [-Hilos 1,16,32] [-TimeoutMin 30]
#   powershell -ExecutionPolicy Bypass -File probar.ps1 -Modo hatch -Dxf h50.dxf     (h50.puntos.txt al lado)
param(
    [Parameter(Mandatory)][ValidateSet('overkill', 'hatch', 'leer')][string]$Modo,
    [Parameter(Mandatory)][string]$Dxf,
    [string[]]$Hilos = @('1', [Environment]::ProcessorCount),
    [string]$Dll = '',
    [int]$TimeoutMin = 30,
    [switch]$SoloPoverkill   # salta el OVERKILL nativo y POVERKILLBENCH
)
$ErrorActionPreference = 'Stop'
# PowerShell 5.1 deja $PSScriptRoot vacío en los valores por defecto de param()
if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $Dll) { $Dll = Join-Path $PSScriptRoot 'AcadParalelo.dll' }
# con -File, "1,32" llega como un solo texto
$Hilos = @($Hilos -join ',' -split '[,\s]+' | Where-Object { $_ } | ForEach-Object { [int]$_ })
$acc = Get-ChildItem 'C:\Program Files\Autodesk\AutoCAD 2027\accoreconsole.exe'
$dxf = (Resolve-Path $Dxf).Path
$base = [IO.Path]::GetFileNameWithoutExtension($dxf)
$out = Join-Path $PSScriptRoot "resultados\$base"
New-Item -ItemType Directory -Force $out | Out-Null
# AutoCAD bloquea el DLL que carga: se carga una copia temporal para que el original se pueda reemplazar siempre
$sombra = Join-Path $env:TEMP ("AcadParalelo_" + [Guid]::NewGuid().ToString('N') + '.dll')
Copy-Item (Resolve-Path $Dll).Path $sombra
$dllL = $sombra -replace '\\', '/'

$cargar = @"
(setq sl (getvar "SECURELOAD"))
(setvar "SECURELOAD" 0)
(command "_.NETLOAD" "$dllL")
(setvar "SECURELOAD" sl)

"@

function Correr([string]$nombre, [string]$cuerpo) {
    $copia = Join-Path $out "$nombre.dxf"
    Copy-Item $dxf $copia -Force
    Remove-Item (Join-Path $out "$nombre.acadparalelo.txt") -ErrorAction SilentlyContinue
    $res = (Join-Path $out "$nombre.txt") -replace '\\', '/'
    Remove-Item $res -ErrorAction SilentlyContinue
    $scr = Join-Path $out "$nombre.scr"
    $texto = ($cuerpo.Replace('@RES@', $res) + "`n_.QUIT`n_Y`n") -replace "`r?`n", "`r`n"
    [IO.File]::WriteAllText($scr, $texto, [Text.Encoding]::GetEncoding(1252))
    Write-Host "Corriendo $nombre ..."
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $p = Start-Process $acc.FullName -ArgumentList "/i `"$copia`" /s `"$scr`"" -NoNewWindow -PassThru `
        -RedirectStandardOutput (Join-Path $out "$nombre.log")
    if (-not $p.WaitForExit($TimeoutMin * 60000)) { $p.Kill(); Write-Host "  cortado tras $TimeoutMin min" }
    Write-Host ("  reloj: {0:F1} s" -f $sw.Elapsed.TotalSeconds)
    if (Test-Path $res) { Get-Content $res } else { Write-Host "  (sin resultado: revisa $nombre.log)" }
    $inf = Join-Path $out "$nombre.acadparalelo.txt"
    if (Test-Path $inf) { Get-Content $inf }
}

$anota = { param($etq, $tipo) "(setq f (open `"@RES@`" `"w`"))(write-line (strcat `"$etq`: `" (itoa (sslength (ssget `"_X`" '((0 . `"$tipo`"))))) `" $tipo, `" (itoa (- (getvar `"MILLISECS`") t0)) `" ms`") f)(close f)" }

if ($Modo -eq 'leer') {
    # compara formas de leer las LINE (no modifica el dibujo)
    Correr 'pleermedir' ($cargar + "(setq t0 (getvar `"MILLISECS`"))`nPLEERMEDIR`n`n" + (& $anota 'pleermedir' 'LINE'))
}
elseif ($Modo -eq 'overkill') {
    if (-not $SoloPoverkill) {
    # OVERKILL nativo con los ajustes de fábrica (tolerancia 1e-6, no ignorar nada, extremo con extremo Sí)
    Correr 'overkill_nativo' (@"
(setq t0 (getvar "MILLISECS"))
_.-OVERKILL
_ALL

_O
0.000001
_I
_N
_E
_Y


"@ + (& $anota 'overkill_nativo' 'LINE'))
    }
    foreach ($t in $Hilos) {
        Correr "poverkill_$($t)hilos" ($cargar + @"
(setq t0 (getvar "MILLISECS"))
POVERKILL
_ALL

H
$t


"@ + (& $anota "poverkill_$($t)hilos" 'LINE'))
    }
    if (-not $SoloPoverkill) { Correr 'poverkillbench' ($cargar + @"
(setq t0 (getvar "MILLISECS"))
POVERKILLBENCH
_ALL



"@ + (& $anota 'poverkillbench' 'LINE')) }
}
else {
    $pts = Get-Content ([IO.Path]::ChangeExtension($dxf, '.puntos.txt'))
    $vars = "(setq osm (getvar `"OSMODE`") hpa (getvar `"HPASSOC`"))(setvar `"OSMODE`" 0)(setvar `"HPASSOC`" 0)`n_.ZOOM`n_E`n"
    $fin = "(setvar `"OSMODE`" osm)(setvar `"HPASSOC`" hpa)"
    # -HATCH nativo: un sombreado por punto interior, patrón ANSI31 escala 1
    $sb = [Text.StringBuilder]::new()
    [void]$sb.Append($vars + "(setq t0 (getvar `"MILLISECS`"))`n_.-HATCH`n_P`nANSI31`n1`n0`n$($pts[0])`n`n")
    foreach ($p in $pts[1..($pts.Count - 1)]) { [void]$sb.Append("_.-HATCH`n$p`n`n") }
    Correr 'hatch_nativo' ($sb.ToString() + (& $anota 'hatch_nativo' 'HATCH') + "`n" + $fin)
    foreach ($t in $Hilos) {
        Correr "phatch_$($t)hilos" ($cargar + $vars + @"
(setq t0 (getvar "MILLISECS"))
PHATCH
Hilos
$t
Puntos
_ALL



"@ + (& $anota "phatch_$($t)hilos" 'HATCH') + "`n" + $fin)
    }
    # PHATCH comparando cada contorno con el de AutoCAD (TraceBoundary)
    Correr 'phatch_verificar' ($cargar + $vars + @"
(setq t0 (getvar "MILLISECS"))
PHATCH
Verificar
Si
Puntos
_ALL



"@ + (& $anota 'phatch_verificar' 'HATCH') + "`n" + $fin)
    Correr 'phatchmedir' ($cargar + $vars + @"
(setq t0 (getvar "MILLISECS"))
PHATCHMEDIR
_ALL


"@ + (& $anota 'phatchmedir' 'HATCH') + "`n" + $fin)
}
