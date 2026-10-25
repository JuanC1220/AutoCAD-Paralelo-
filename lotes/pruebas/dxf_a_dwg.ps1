# Convierte los DXF de prueba de una carpeta a DWG (formato 2018) con accoreconsole, varios a la vez.
#   python gen_basura_dxf.py --n 20 --out prueba_lotes
#   powershell -ExecutionPolicy Bypass -File dxf_a_dwg.ps1 -Carpeta prueba_lotes
param([Parameter(Mandatory)][string]$Carpeta, [int]$Hilos = [Environment]::ProcessorCount / 2, [string]$Acc)
$ErrorActionPreference = 'Stop'
if (-not $Acc) {
    $Acc = (Get-ChildItem 'C:\Program Files\Autodesk\AutoCAD *\accoreconsole.exe' | Sort-Object { $_.Directory.Name } -Descending | Select-Object -First 1).FullName
}
$procs = @()
foreach ($f in Get-ChildItem (Resolve-Path $Carpeta) -Filter *.dxf) {
    $dwg = [IO.Path]::ChangeExtension($f.FullName, '.dwg')
    Remove-Item $dwg -ErrorAction SilentlyContinue
    $scr = [IO.Path]::ChangeExtension($f.FullName, '.scr')
    $texto = "(command `"_.SAVEAS`" `"2018`" `"$($dwg -replace '\\', '/')`")`r`n_.QUIT`r`n_Y`r`n"
    [IO.File]::WriteAllText($scr, $texto, [Text.Encoding]::GetEncoding(1252))
    while (@($procs | Where-Object { -not $_.HasExited }).Count -ge $Hilos) { Start-Sleep -Milliseconds 200 }
    $procs += Start-Process $Acc -ArgumentList @('/i', "`"$($f.FullName)`"", '/s', "`"$scr`"") -WindowStyle Hidden -PassThru -RedirectStandardOutput "$scr.log"
}
$procs | ForEach-Object { $_.WaitForExit() }
Get-ChildItem (Resolve-Path $Carpeta) -Filter *.dwg | ForEach-Object { '{0}  {1:N2} MB' -f $_.Name, ($_.Length / 1MB) }
