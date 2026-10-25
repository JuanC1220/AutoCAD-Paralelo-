# Corre OVERKILL real de AutoCAD (accoreconsole) sobre una COPIA del dibujo extremo y
# cuenta entidades por capa. Uso:
#   powershell -ExecutionPolicy Bypass -File correr_autocad.ps1 -dxf extremo_3M.dxf -e2e N
# Resultado: res_<tag>.csv (capa;cantidad) y res_<tag>.txt (tiempo). Luego:
#   python verificar_extremo.py extremo_3M.dxf.json --csv res_<tag>.csv [--e2e]
param([string]$dxf = "extremo_3M.dxf", [ValidateSet("Y","N")][string]$e2e = "N", [int]$minutos = 120)
$w = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = (Resolve-Path (Join-Path $w $dxf)).Path
$tag = [IO.Path]::GetFileNameWithoutExtension($src) + "_e2e$e2e"
$copia = "$w\copia_$tag.dxf"; Copy-Item $src $copia -Force
Remove-Item "$w\res_$tag.*","$w\log_$tag.txt" -ErrorAction SilentlyContinue
$exe = Get-ChildItem "C:\Program Files\Autodesk\AutoCAD 20*\accoreconsole.exe" | Sort-Object FullName | Select-Object -Last 1
$lsp = '(setq f (open (strcat (getvar "DWGPREFIX") "res_' + $tag + '.csv") "w") L (tblnext "LAYER" T))' +
       '(while L (setq s (ssget "_X" (list (cons 8 (cdr (assoc 2 L)))))) (write-line (strcat (cdr (assoc 2 L)) ";" (itoa (if s (sslength s) 0))) f) (setq L (tblnext "LAYER")))(close f)'
@"
(setq t0 (getvar "MILLISECS"))
_.-OVERKILL
_ALL

_O
0.000001
_I
_N
_T
_Y
_E
_$e2e

(setq t1 (- (getvar "MILLISECS") t0))
$lsp
(setq f (open (strcat (getvar "DWGPREFIX") "res_$tag.txt") "w"))(write-line (strcat "overkill_ms " (itoa t1)) f)(close f)
_.QUIT
_Y
"@ | Set-Content "$w\$tag.scr" -Encoding ASCII
"Usando $($exe.FullName)"
$sw = [Diagnostics.Stopwatch]::StartNew()
$p = Start-Process $exe.FullName -ArgumentList "/i `"$copia`" /s `"$w\$tag.scr`" /l en-US" -WorkingDirectory $w -RedirectStandardOutput "$w\log_$tag.txt" -NoNewWindow -PassThru
try { Wait-Process -Id $p.Id -Timeout ($minutos * 60) -ErrorAction Stop } catch { Stop-Process -Id $p.Id -Force; "TIEMPO AGOTADO" }
$sw.Stop()
"total (abrir + overkill + contar) = $([math]::Round($sw.Elapsed.TotalSeconds,1)) s"
if (Test-Path "$w\res_$tag.txt") { Get-Content "$w\res_$tag.txt" } else { "Sin resultado: revisa log_$tag.txt" }
Remove-Item $copia -ErrorAction SilentlyContinue
