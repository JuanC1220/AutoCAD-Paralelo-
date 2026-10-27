# Corre la batería en AutoCAD (accoreconsole) sobre COPIAS de los dibujos de gen_bateria.py y vuelca el resultado.
# Por cada o_*.dxf: original (sólo volcar), OVERKILL nativo y POVERKILL con cada número de hilos.
# Por cada h_*.dxf: -HATCH nativo (un punto por área) y PHATCH con cada número de hilos.
# Cada corrida deja en resultados\<dibujo>\: <corrida>.txt (volcado: una entidad por línea), <corrida>.ms (tiempo del
# comando), <corrida>.acadparalelo.txt (tiempos internos de POVERKILL/PHATCH) y <corrida>.log. No toca tus dibujos;
# OSMODE y HPASSOC se devuelven a su valor al terminar.
#   & .\correr_bateria.ps1 -Carpeta dibujos -Dll ..\acad_paralelo\dist\AcadParalelo.dll [-Hilos 1,32] [-Solo overkill] [-Filtro densa]
# Luego:  python verificar_bateria.py dibujos
param(
    [string]$Carpeta = 'dibujos',
    [string]$Dll = '',
    [string[]]$Hilos = @('1', [Environment]::ProcessorCount),
    [ValidateSet('', 'overkill', 'hatch')][string]$Solo = '',
    [string]$Filtro = '',           # sólo dibujos cuyo nombre contenga este texto
    [int]$TimeoutMin = 30,
    [switch]$SinNativo,             # salta OVERKILL/HATCH de AutoCAD
    [switch]$Repetir                # vuelve a correr aunque ya haya resultado
)
$ErrorActionPreference = 'Stop'
if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $Dll) { $Dll = Join-Path $PSScriptRoot '..\acad_paralelo\dist\AcadParalelo.dll' }
$Hilos = @($Hilos -join ',' -split '[,\s]+' | Where-Object { $_ } | ForEach-Object { [int]$_ })
$acc = Get-ChildItem 'C:\Program Files\Autodesk\AutoCAD 20*\accoreconsole.exe' | Sort-Object FullName | Select-Object -Last 1
Write-Host "Usando $($acc.FullName)"
$dir = (Resolve-Path $Carpeta).Path
# AutoCAD bloquea el DLL que carga: se carga una copia temporal
$sombra = Join-Path $env:TEMP ("AcadParalelo_" + [Guid]::NewGuid().ToString('N') + '.dll')
Copy-Item (Resolve-Path $Dll).Path $sombra
$dllL = $sombra -replace '\\', '/'
$cargar = "(setq sl (getvar `"SECURELOAD`"))(setvar `"SECURELOAD`" 0)`n(command `"_.NETLOAD`" `"$dllL`")`n(setvar `"SECURELOAD`" sl)`n"

# volcado: TIPO|código=valor|... con todos los grupos de entget salvo nombres y punteros
$volcar = '(defun bvf (v) (cond ((= (type v) (quote REAL)) (rtos v 2 10)) ((= (type v) (quote INT)) (itoa v)) ((= (type v) (quote STR)) v) ((= (type v) (quote LIST)) (bvl v)) (T "?")))' + "`n" +
          '(defun bvl (l / s) (setq s (bvf (car l))) (foreach x (cdr l) (setq s (strcat s "," (bvf x)))) s)' + "`n" +
          '(defun bvol (arch flt / f s i e o) (setq f (open arch "w") s (if flt (ssget "_X" flt) (ssget "_X")) i 0) (if s (repeat (sslength s) (setq e (entget (ssname s i)) i (1+ i) o (cdr (assoc 0 e))) (foreach p e (if (not (member (car p) (quote (-1 0 5 330 360 100 102 410 -3)))) (setq o (strcat o "|" (itoa (car p)) "=" (bvf (cdr p)))))) (write-line o f))) (close f) nil)' + "`n"

function Correr([string]$out, [string]$src, [string]$nombre, [string]$cuerpo) {
    $txt = Join-Path $out "$nombre.txt"
    if ((Test-Path $txt) -and -not $Repetir) { Write-Host "  $nombre ya está (usa -Repetir)"; return }
    $copia = Join-Path $out "$nombre.dxf"
    Copy-Item $src $copia -Force
    Remove-Item (Join-Path $out "$nombre.acadparalelo.txt"), (Join-Path $out "$nombre.ms"), $txt -ErrorAction SilentlyContinue
    $txtL = $txt -replace '\\', '/'
    $msL = (Join-Path $out "$nombre.ms") -replace '\\', '/'
    $scr = Join-Path $out "$nombre.scr"
    $texto = ($volcar + $cuerpo.Replace('@TXT@', $txtL).Replace('@MS@', $msL) + "`n_.QUIT`n_Y`n") -replace "`r?`n", "`r`n"
    [IO.File]::WriteAllText($scr, $texto, [Text.Encoding]::GetEncoding(1252))
    Write-Host "  $nombre ..." -NoNewline
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $p = Start-Process $acc.FullName -ArgumentList "/i `"$copia`" /s `"$scr`" /l en-US" -NoNewWindow -PassThru `
        -RedirectStandardOutput (Join-Path $out "$nombre.log")
    if (-not $p.WaitForExit($TimeoutMin * 60000)) { $p.Kill(); Write-Host " cortado tras $TimeoutMin min" -NoNewline }
    $ms = if (Test-Path (Join-Path $out "$nombre.ms")) { (Get-Content (Join-Path $out "$nombre.ms")) -join ' ' } else { 'sin tiempo' }
    Write-Host (" reloj {0:F1} s, comando {1}" -f $sw.Elapsed.TotalSeconds, $ms)
    if (-not (Test-Path $txt)) { Write-Host "    (sin volcado: revisa $nombre.log)" }
    Remove-Item $copia -ErrorAction SilentlyContinue
}

$t0 = "(setq t0 (getvar `"MILLISECS`"))`n"
$t1 = "(setq f (open `"@MS@`" `"w`"))(write-line (itoa (- (getvar `"MILLISECS`") t0)) f)(close f)`n"

$dibujos = Get-ChildItem $dir -Filter '*.dxf' | Where-Object { $_.Name -match '^(o|h)_' -and $_.Name -like "*$Filtro*" } | Sort-Object Length
foreach ($d in $dibujos) {
    $esH = $d.Name.StartsWith('h_')
    if (($Solo -eq 'overkill' -and $esH) -or ($Solo -eq 'hatch' -and -not $esH)) { continue }
    $base = $d.BaseName
    $out = Join-Path $dir "resultados\$base"
    New-Item -ItemType Directory -Force $out | Out-Null
    Write-Host "$($d.Name) ($([math]::Round($d.Length / 1MB, 1)) MB)"
    if (-not $esH) {
        $vol = "(bvol `"@TXT@`" nil)`n"
        Correr $out $d.FullName 'original' ($t0 + $t1 + $vol)
        # OVERKILL de AutoCAD: tolerancia 1e-6, no ignorar nada, solapes parciales Sí, extremo con extremo Sí
        if (-not $SinNativo) {
            Correr $out $d.FullName 'overkill_nativo' ($t0 + "_.-OVERKILL`n_ALL`n`n_O`n0.000001`n_I`n_N`n_T`n_Y`n_E`n_Y`n`n" + $t1 + $vol)
        }
        foreach ($t in $Hilos) {
            Correr $out $d.FullName "poverkill_$($t)hilos" ($cargar + $t0 + "POVERKILL`n_ALL`n`nH`n$t`n`n" + $t1 + $vol)
        }
    }
    else {
        $vol = "(bvol `"@TXT@`" (list (cons 0 `"HATCH`")))`n"
        $vars = "(setq osm (getvar `"OSMODE`") hpa (getvar `"HPASSOC`"))(setvar `"OSMODE`" 0)(setvar `"HPASSOC`" 0)`n_.ZOOM`n_E`n"
        $fin = "(setvar `"OSMODE`" osm)(setvar `"HPASSOC`" hpa)`n"
        if (-not $SinNativo) {
            $pts = Get-Content (Join-Path $dir ($base + '.puntos.txt'))
            $sb = [Text.StringBuilder]::new()
            [void]$sb.Append($vars + $t0 + "_.-HATCH`n_P`nANSI31`n1`n0`n$($pts[0])`n`n")
            foreach ($p in $pts | Select-Object -Skip 1) { [void]$sb.Append("_.-HATCH`n$p`n`n") }
            Correr $out $d.FullName 'hatch_nativo' ($sb.ToString() + $t1 + $vol + $fin)
        }
        foreach ($t in $Hilos) {
            Correr $out $d.FullName "phatch_$($t)hilos" ($cargar + $vars + $t0 + "PHATCH`nHilos`n$t`nPuntos`n_ALL`n`n`n" + $t1 + $vol + $fin)
        }
    }
}
Remove-Item $sombra -ErrorAction SilentlyContinue
Write-Host "Listo. Siguiente paso: python verificar_bateria.py $Carpeta"
