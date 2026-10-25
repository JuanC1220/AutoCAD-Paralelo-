# Limpieza por lotes: AUDIT + PURGE sobre muchos DWG a la vez, un accoreconsole por dibujo.
# Por defecto NO toca tus originales: deja los dibujos limpios en una carpeta de salida.
# Al final escribe informe.csv e informe.html con el tamaño antes/después de cada archivo y los errores.
#
#   powershell -ExecutionPolicy Bypass -File limpiar_lotes.ps1 -Entrada C:\planos [-Recursivo] [-Salida C:\planos_limpios] [-Hilos 8]
#   powershell -ExecutionPolicy Bypass -File limpiar_lotes.ps1               (pide la carpeta con un diálogo)
#
# -EnSitio      reemplaza cada original por su versión limpia (el original queda en <Salida>\respaldo).
# -Geometria    además purga geometría de longitud cero y textos vacíos (sí borra objetos del dibujo).
# -SinAudit     sólo PURGE.   -SinPurge   sólo AUDIT.
# -Hilos 1      corre uno detrás de otro (sirve para medir cuánto gana el paralelo).
param(
    [string[]]$Entrada,
    [string]$Salida,
    [switch]$Recursivo,
    [int]$Hilos = 0,
    [switch]$EnSitio,
    [switch]$Geometria,
    [switch]$SinAudit,
    [switch]$SinPurge,
    [int]$TiempoMax = 600,
    [string]$Acc
)
$ErrorActionPreference = 'Stop'

# --- accoreconsole: el de la versión más nueva instalada, salvo que se indique otro
if (-not $Acc) {
    $c = Get-ChildItem 'C:\Program Files\Autodesk\AutoCAD *\accoreconsole.exe' -ErrorAction SilentlyContinue |
        Sort-Object { $_.Directory.Name } -Descending | Select-Object -First 1
    if (-not $c) { throw 'No encontré accoreconsole.exe en C:\Program Files\Autodesk\AutoCAD *. Indícalo con -Acc.' }
    $Acc = $c.FullName
}
if (-not (Test-Path $Acc)) { throw "No existe $Acc" }

# --- qué dibujos
if (-not $Entrada) {
    Add-Type -AssemblyName System.Windows.Forms
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description = 'Carpeta con los DWG a limpiar (los originales no se tocan)'
    if ($dlg.ShowDialog() -ne 'OK') { return }
    $Entrada = @($dlg.SelectedPath)
}
$trabajos = New-Object System.Collections.Generic.List[object]
foreach ($e in $Entrada) {
    $p = (Resolve-Path $e).Path
    if (Test-Path $p -PathType Container) {
        $raiz = $p.TrimEnd('\')
        if (-not $Salida) { $Salida = "$raiz`_limpios" }
        $fs = Get-ChildItem $raiz -Filter *.dwg -File -Recurse:$Recursivo
        foreach ($f in $fs) { $trabajos.Add([pscustomobject]@{ Origen = $f.FullName; Rel = $f.FullName.Substring($raiz.Length + 1) }) }
    }
    else {
        if (-not $Salida) { $Salida = Join-Path (Split-Path $p) 'limpios' }
        $trabajos.Add([pscustomobject]@{ Origen = $p; Rel = (Split-Path $p -Leaf) })
    }
}
$Salida = [IO.Path]::GetFullPath($Salida)
# no volver a limpiar lo que ya está en la salida (si la salida cuelga de la entrada)
$trabajos = @($trabajos | Where-Object { -not $_.Origen.StartsWith($Salida + '\', 'OrdinalIgnoreCase') })
if ($trabajos.Count -eq 0) { Write-Host 'No hay archivos .dwg.'; return }

if ($Hilos -le 0) {
    $Hilos = (Get-CimInstance Win32_Processor | Measure-Object NumberOfCores -Sum).Sum   # núcleos físicos
    if (-not $Hilos) { $Hilos = [Environment]::ProcessorCount }
}
$Hilos = [Math]::Max(1, [Math]::Min($Hilos, $trabajos.Count))

$trab = Join-Path $Salida '_trabajo'
New-Item -ItemType Directory -Force $trab | Out-Null
$sello = Get-Date -Format 'yyyyMMdd_HHmmss'

# --- guion de AutoCAD (igual para todos; sólo cambia el archivo de resultados)
# Cuenta las tablas antes y después, AUDIT corrigiendo, y PURGE Todo + Regapps repetido hasta que
# no quede nada (bloques dentro de bloques necesitan varias pasadas). Las marcas de AUDIT se arman con
# strcat para que el eco del guion en el log no las contenga.
# Se guarda con SAVEAS 2018 sobre el mismo DWG y no con QSAVE: si en AutoCAD el formato por defecto es
# DXF, QSAVE escribe un .dxf aparte y deja el DWG sin limpiar.
# lp:activo mira el bit 1 de CMDACTIVE (comando en curso; el 4 es el propio guion). Sin comentarios
# dentro del LISP: en un .scr el texto tras ")" se ejecuta como comandos. Respuestas con "_" para que
# funcione en AutoCAD en cualquier idioma.
$lisp = @'
(defun lp:tabla (tb / n d) (setq n 0 d (tblnext tb T)) (while d (setq n (1+ n) d (tblnext tb))) n)
(defun lp:cuentas () (mapcar 'lp:tabla '("BLOCK" "LAYER" "LTYPE" "STYLE" "DIMSTYLE" "APPID")))
(defun lp:txt (l / s) (setq s "") (foreach x l (setq s (strcat s (itoa x) ";"))) s)
(defun lp:activo () (= 1 (logand 1 (getvar "CMDACTIVE"))))
(defun lp:fin () (while (lp:activo) (command "")))
(defun lp:purgar (op)
  (command "_.-PURGE" op)
  (if (lp:activo) (command "*"))
  (while (lp:activo) (command "_N")))
(setq lp:f (open "@RES@" "w"))
(defun lp:w (k v) (write-line (strcat k "=" v) lp:f))
(setq lp:t0 (getvar "MILLISECS") lp:c (lp:cuentas))
(lp:w "antes" (lp:txt lp:c))
(if @AUDIT@ (progn (princ (strcat "\n<<" "AUDIT>>\n")) (command "_.AUDIT" "_Y") (lp:fin) (princ (strcat "\n<</" "AUDIT>>\n"))))
(setq lp:i 0 lp:prev nil)
(if @PURGE@ (while (and (< lp:i 6) (not (equal lp:c lp:prev)))
  (setq lp:prev lp:c lp:i (1+ lp:i))
  (lp:purgar "_A") (lp:purgar "_R")
  (if @GEOM@ (progn (command "_.-PURGE" "_Z") (lp:fin) (command "_.-PURGE" "_E") (lp:fin)))
  (setq lp:c (lp:cuentas))))
(lp:w "despues" (lp:txt lp:c))
(lp:w "pasadas" (itoa lp:i))
(command "_.SAVEAS" "2018" (strcat (getvar "DWGPREFIX") (getvar "DWGNAME")))
(while (lp:activo) (command "_Y"))
(lp:w "dbmod" (itoa (getvar "DBMOD")))
(lp:w "ms" (itoa (- (getvar "MILLISECS") lp:t0)))
(close lp:f)
'@
function Bool([bool]$b) { if ($b) { 'T' } else { 'nil' } }
$lisp = $lisp.Replace('@AUDIT@', (Bool (-not $SinAudit))).Replace('@PURGE@', (Bool (-not $SinPurge))).Replace('@GEOM@', (Bool $Geometria))

function Leer-Log([string]$ruta) {
    if (-not (Test-Path $ruta)) { return '' }
    # el log puede seguir abierto tras salir accoreconsole (lo hereda AcEventSync): leer compartido
    try {
        $fs = [IO.FileStream]::new($ruta, 'Open', 'Read', 'ReadWrite, Delete')
        try { $b = [byte[]]::new($fs.Length); [void]$fs.Read($b, 0, $b.Length) } finally { $fs.Dispose() }
    }
    catch { return '' }
    $ceros = ($b | Select-Object -First 4000 | Where-Object { $_ -eq 0 }).Count
    $enc = if ($ceros -gt 100) { [Text.Encoding]::Unicode } else { [Text.Encoding]::Default }   # accoreconsole escribe UTF-16
    return $enc.GetString($b).Replace("`0", '')
}

# --- lanzar y vigilar: como mucho $Hilos accoreconsole a la vez
$enc1252 = [Text.Encoding]::GetEncoding(1252)
$resultados = New-Object System.Collections.Generic.List[object]
$activos = @{}
$cola = [System.Collections.Queue]::new($trabajos)
$n = 0; $hechos = 0
$reloj = [Diagnostics.Stopwatch]::StartNew()
Write-Host "$($trabajos.Count) dibujos, $Hilos a la vez, con $Acc"
Write-Host "Salida: $Salida"

function Terminar($j, [bool]$vencido) {
    $r = $j.Fila
    $r.Segundos = [Math]::Round(((Get-Date) - $j.Inicio).TotalSeconds, 1)
    $log = Leer-Log $j.Log
    $res = @{}
    if (Test-Path $j.Res) { foreach ($l in Get-Content $j.Res) { $k, $v = $l -split '=', 2; $res[$k] = $v } }
    if ($log -match '(?s)<<AUDIT>>(.*?)<</AUDIT>>') {
        $lin = @($Matches[1] -split "`r?`n" | Where-Object { $_ -match '\d+\D+\d+' })
        if ($lin) {
            $r.Auditoria = $lin[-1].Trim()
            $num = [regex]::Matches($lin[-1], '\d+')
            $r.ErroresEncontrados = [int]$num[0].Value; $r.ErroresCorregidos = [int]$num[1].Value
        }
    }
    if ($res.ContainsKey('antes')) {
        $a = $res['antes'].TrimEnd(';') -split ';'; $d = @(($res['despues'] + '').TrimEnd(';') -split ';')
        $i = 0
        foreach ($t in 'Bloques', 'Capas', 'TiposLinea', 'EstilosTexto', 'EstilosCota', 'Regapps') {
            $r."${t}Antes" = [int]$a[$i]; if ($d.Count -gt $i -and $d[$i] -ne '') { $r."${t}Despues" = [int]$d[$i] }; $i++
        }
    }
    if ($vencido) { $r.Estado = 'ERROR'; $r.Mensaje = "Superó $TiempoMax s; se detuvo." }
    elseif (-not $res.ContainsKey('antes')) { $r.Estado = 'ERROR'; $r.Mensaje = 'AutoCAD no pudo abrir o procesar el dibujo (ver log).' }
    elseif ($res['dbmod'] -ne '0' -or (Get-Item -LiteralPath $j.Destino).LastWriteTime -lt $j.Inicio) { $r.Estado = 'ERROR'; $r.Mensaje = 'No se pudo guardar el dibujo (ver log).' }
    else { $r.Estado = 'OK' }
    Remove-Item ([IO.Path]::ChangeExtension($j.Destino, '.bak')) -ErrorAction SilentlyContinue
    if ($r.Estado -eq 'OK') {
        $r.BytesDespues = (Get-Item $j.Destino).Length
        if ($r.BytesAntes -gt 0) { $r.ReduccionPct = [Math]::Round(100.0 * (1 - $r.BytesDespues / $r.BytesAntes), 1) }
        if ($EnSitio) {
            $resp = Join-Path (Join-Path $Salida 'respaldo') $j.Rel
            New-Item -ItemType Directory -Force (Split-Path $resp) | Out-Null
            Copy-Item -LiteralPath $j.Origen $resp -Force
            Copy-Item -LiteralPath $j.Destino $j.Origen -Force
            $r.Mensaje = 'Original reemplazado; copia en respaldo\'
        }
    }
    else {
        # que en la salida no quede un dibujo a medias
        Remove-Item -LiteralPath $j.Destino -ErrorAction SilentlyContinue
        $r.Log = $j.Log
    }
    $resultados.Add($r)
    $script:hechos++
    $pct = if ($r.ReduccionPct -ne $null) { " ($($r.ReduccionPct) % menos)" } else { '' }
    Write-Host ("[{0}/{1}] {2,-5} {3}{4}  {5} s" -f $script:hechos, $trabajos.Count, $r.Estado, $j.Rel, $pct, $r.Segundos)
}

while ($cola.Count -gt 0 -or $activos.Count -gt 0) {
    while ($cola.Count -gt 0 -and $activos.Count -lt $Hilos) {
        $t = $cola.Dequeue(); $n++
        $destino = Join-Path $Salida $t.Rel
        New-Item -ItemType Directory -Force (Split-Path $destino) | Out-Null
        Copy-Item -LiteralPath $t.Origen $destino -Force
        Set-ItemProperty -LiteralPath $destino -Name IsReadOnly -Value $false
        $base = Join-Path $trab ('{0:d5}' -f $n)
        $resF = "$base.res"; Remove-Item $resF -ErrorAction SilentlyContinue
        $scr = "$base.scr"
        $texto = ($lisp.Replace('@RES@', ($resF -replace '\\', '/')) + "`n_.QUIT`n_Y`n") -replace "`r?`n", "`r`n"
        [IO.File]::WriteAllText($scr, $texto, $enc1252)
        $fila = [ordered]@{ Archivo = $t.Rel; Estado = ''; BytesAntes = (Get-Item -LiteralPath $t.Origen).Length; BytesDespues = $null; ReduccionPct = $null
            Segundos = $null; ErroresEncontrados = $null; ErroresCorregidos = $null; Auditoria = ''
            BloquesAntes = $null; BloquesDespues = $null; CapasAntes = $null; CapasDespues = $null; TiposLineaAntes = $null; TiposLineaDespues = $null
            EstilosTextoAntes = $null; EstilosTextoDespues = $null; EstilosCotaAntes = $null; EstilosCotaDespues = $null; RegappsAntes = $null; RegappsDespues = $null
            Mensaje = ''; Log = ''
        }
        $p = Start-Process -FilePath $Acc -ArgumentList @('/i', "`"$destino`"", '/s', "`"$scr`"") -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput "$base.log" -RedirectStandardError "$base.err"
        $activos[$p.Id] = @{ Proc = $p; Inicio = Get-Date; Origen = $t.Origen; Destino = $destino; Rel = $t.Rel; Res = $resF; Log = "$base.log"; Fila = [pscustomobject]$fila }
    }
    Start-Sleep -Milliseconds 250
    foreach ($id in @($activos.Keys)) {
        $j = $activos[$id]
        $vencido = $false
        if (-not $j.Proc.HasExited) {
            if (((Get-Date) - $j.Inicio).TotalSeconds -lt $TiempoMax) { continue }
            try { $j.Proc.Kill() } catch {}
            $j.Proc.WaitForExit(10000) | Out-Null
            $vencido = $true
        }
        $activos.Remove($id)
        Terminar $j $vencido
    }
}
$reloj.Stop()

# --- informe
$filas = @($resultados | Sort-Object Archivo)
$csv = Join-Path $Salida "informe_$sello.csv"
# decimales con la coma o el punto de tu Windows, para que Excel los lea como números
$cul = Get-Culture
$filas | ForEach-Object {
    $o = $_.PSObject.Copy()
    foreach ($k in 'ReduccionPct', 'Segundos') { if ($o.$k -ne $null) { $o.$k = ([double]$o.$k).ToString($cul) } }
    $o
} | Export-Csv $csv -NoTypeInformation -Encoding UTF8 -Delimiter $cul.TextInfo.ListSeparator

$ok = @($filas | Where-Object Estado -eq 'OK')
$antes = ($ok | Measure-Object BytesAntes -Sum).Sum; $desp = ($ok | Measure-Object BytesDespues -Sum).Sum
$real = [Math]::Round($reloj.Elapsed.TotalSeconds, 1)
function MB($b) { if ($b -eq $null) { '' } else { '{0:N2}' -f ($b / 1MB) } }
function Esc($s) { [Net.WebUtility]::HtmlEncode([string]$s) }
function Par($a, $d) { if ($a -eq $null) { '' } elseif ($d -eq $null -or $a -eq $d) { "$a" } else { "$a &rarr; $d" } }
$sb = [Text.StringBuilder]::new()
foreach ($r in $filas) {
    $cls = if ($r.Estado -eq 'OK') { '' } else { ' class="err"' }
    $aud = if ($r.ErroresEncontrados -ne $null) { "$($r.ErroresEncontrados) / $($r.ErroresCorregidos)" } else { '' }
    $msg = Esc $r.Mensaje; if ($r.Log) { $msg += " <small>$(Esc $r.Log)</small>" }
    [void]$sb.Append("<tr$cls><td>$(Esc $r.Archivo)</td><td>$($r.Estado)</td><td class=n>$(MB $r.BytesAntes)</td><td class=n>$(MB $r.BytesDespues)</td><td class=n>$($r.ReduccionPct)</td><td class=n>$($r.Segundos)</td><td class=n title=`"$(Esc $r.Auditoria)`">$aud</td><td class=n>$(Par $r.BloquesAntes $r.BloquesDespues)</td><td class=n>$(Par $r.CapasAntes $r.CapasDespues)</td><td class=n>$(Par $r.TiposLineaAntes $r.TiposLineaDespues)</td><td class=n>$(Par $r.EstilosTextoAntes $r.EstilosTextoDespues)</td><td class=n>$(Par $r.RegappsAntes $r.RegappsDespues)</td><td>$msg</td></tr>`n")
}
$redTot = if ($antes) { '{0:N1}' -f (100.0 * (1 - $desp / $antes)) } else { '-' }
$porArch = if ($filas.Count) { '{0:N1}' -f ($real / $filas.Count) } else { '-' }
$html = @"
<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Limpieza por lotes</title>
<style>
:root{--fg:#1d1d1f;--bg:#fff;--mut:#666;--lin:#ddd;--err:#fdecec}
@media (prefers-color-scheme:dark){:root{--fg:#eee;--bg:#1b1b1d;--mut:#aaa;--lin:#333;--err:#4a2323}}
body{font:14px system-ui,sans-serif;color:var(--fg);background:var(--bg);margin:24px 16px}
h1{font-size:20px;margin:0 0 4px}p{color:var(--mut);margin:0 0 16px}
.res{display:flex;gap:24px;flex-wrap:wrap;margin:0 0 20px}.res div b{display:block;font-size:22px}
.tabla{overflow-x:auto}table{border-collapse:collapse;width:100%}
th,td{border-bottom:1px solid var(--lin);padding:6px 8px;text-align:left;white-space:nowrap}
th{font-weight:600}.n{text-align:right;font-variant-numeric:tabular-nums}tr.err td{background:var(--err)}
small{color:var(--mut)}
</style></head><body>
<h1>Limpieza por lotes: AUDIT + PURGE</h1>
<p>$(Get-Date -Format 'yyyy-MM-dd HH:mm') &middot; $env:COMPUTERNAME &middot; $(Esc $Acc) &middot; $Hilos a la vez &middot; salida $(Esc $Salida)</p>
<div class="res">
<div><b>$($ok.Count) / $($filas.Count)</b>archivos limpios</div>
<div><b>$(MB $antes) &rarr; $(MB $desp) MB</b>$redTot % menos</div>
<div><b>$real s</b>tiempo real</div>
<div><b>$porArch s</b>por archivo (para la ganancia real, compara con una corrida -Hilos 1)</div>
</div>
<div class="tabla"><table>
<tr><th>Archivo</th><th>Estado</th><th class=n>MB antes</th><th class=n>MB después</th><th class=n>% menos</th><th class=n>s</th><th class=n>Audit encontr./corr.</th><th class=n>Bloques</th><th class=n>Capas</th><th class=n>Tipos línea</th><th class=n>Estilos texto</th><th class=n>Regapps</th><th>Notas</th></tr>
$($sb.ToString())</table></div>
</body></html>
"@
$htmlF = Join-Path $Salida "informe_$sello.html"
[IO.File]::WriteAllText($htmlF, $html, [Text.UTF8Encoding]::new($true))

$errores = $filas.Count - $ok.Count
if ($errores -eq 0) { Remove-Item $trab -Recurse -Force -ErrorAction SilentlyContinue }   # los logs sólo se guardan si hubo errores
Write-Host ''
Write-Host "Listo en $real s: $($ok.Count) OK, $errores con error. $(MB $antes) MB -> $(MB $desp) MB ($redTot % menos)."
Write-Host "$porArch s por archivo. Para medir la ganancia, compara con una corrida -Hilos 1."
Write-Host "Informe: $htmlF"
if (-not $EnSitio) { Write-Host 'Tus originales no se tocaron.' }
