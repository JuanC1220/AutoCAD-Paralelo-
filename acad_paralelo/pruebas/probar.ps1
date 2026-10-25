# Corre comandos nativos de AutoCAD y los del plugin sobre COPIAS de un DXF con accoreconsole y anota resultados.
# No toca tus dibujos; los ajustes que cambia (SECURELOAD, OSMODE, HPASSOC) se devuelven a su valor al terminar.
#   powershell -ExecutionPolicy Bypass -File probar.ps1 -Modo overkill -Dxf s400k.dxf [-Hilos 1,16,32]
#   powershell -ExecutionPolicy Bypass -File probar.ps1 -Modo hatch -Dxf h50.dxf     (h50.puntos.txt al lado)
param(
    [Parameter(Mandatory)][ValidateSet('overkill', 'hatch')][string]$Modo,
    [Parameter(Mandatory)][string]$Dxf,
    [int[]]$Hilos = @(1, [Environment]::ProcessorCount),
    [string]$Dll = (Join-Path $PSScriptRoot 'AcadParalelo.dll')
)
$ErrorActionPreference = 'Stop'
$acc = Get-ChildItem 'C:\Program Files\Autodesk\AutoCAD 2027\accoreconsole.exe'
$dxf = (Resolve-Path $Dxf).Path
$base = [IO.Path]::GetFileNameWithoutExtension($dxf)
$out = Join-Path $PSScriptRoot "resultados\$base"
New-Item -ItemType Directory -Force $out | Out-Null
$dllL = (Resolve-Path $Dll).Path -replace '\\', '/'

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
    & $acc.FullName /i $copia /s $scr | Out-File (Join-Path $out "$nombre.log")
    if (Test-Path $res) { Get-Content $res } else { Write-Host "  (sin resultado: revisa $nombre.log)" }
    $inf = Join-Path $out "$nombre.acadparalelo.txt"
    if (Test-Path $inf) { Get-Content $inf }
}

$anota = { param($etq, $tipo) "(setq f (open `"@RES@`" `"w`"))(write-line (strcat `"$etq`: `" (itoa (sslength (ssget `"_X`" '((0 . `"$tipo`"))))) `" $tipo, `" (itoa (- (getvar `"MILLISECS`") t0)) `" ms`") f)(close f)" }

if ($Modo -eq 'overkill') {
    # OVERKILL nativo con los ajustes de fábrica (tolerancia 1e-6, no ignorar nada, extremo con extremo Sí)
    Correr 'overkill_nativo' (@"
(setq t0 (getvar "MILLISECS"))
_.-OVERKILL
_ALL

_T
0.000001
_I
_N
_E
_Y

"@ + (& $anota 'overkill_nativo' 'LINE'))
    foreach ($t in $Hilos) {
        Correr "poverkill_$($t)hilos" ($cargar + @"
(setq t0 (getvar "MILLISECS"))
POVERKILL
_ALL

H
$t

"@ + (& $anota "poverkill_$($t)hilos" 'LINE'))
    }
    Correr 'poverkillbench' ($cargar + @"
(setq t0 (getvar "MILLISECS"))
POVERKILLBENCH
_ALL


"@ + (& $anota 'poverkillbench' 'LINE'))
}
else {
    $pts = Get-Content ([IO.Path]::ChangeExtension($dxf, '.puntos.txt'))
    $vars = "(setq osm (getvar `"OSMODE`") hpa (getvar `"HPASSOC`"))(setvar `"OSMODE`" 0)(setvar `"HPASSOC`" 0)`n_.ZOOM`n_E`n"
    $fin = "(setvar `"OSMODE`" osm)(setvar `"HPASSOC`" hpa)`n"
    # -HATCH nativo: un sombreado por punto interior, patrón ANSI31 escala 1
    $sb = [Text.StringBuilder]::new()
    [void]$sb.Append($vars + "(setq t0 (getvar `"MILLISECS`"))`n_.-HATCH`n_P`nANSI31`n1`n0`n$($pts[0])`n`n")
    foreach ($p in $pts[1..($pts.Count - 1)]) { [void]$sb.Append("_.-HATCH`n$p`n`n") }
    Correr 'hatch_nativo' ($sb.ToString() + (& $anota 'hatch_nativo' 'HATCH') + "`n" + $fin)
    Correr 'phatchmedir' ($cargar + $vars + @"
(setq t0 (getvar "MILLISECS"))
PHATCHMEDIR
_ALL

"@ + (& $anota 'phatchmedir' 'HATCH') + "`n" + $fin)
}
