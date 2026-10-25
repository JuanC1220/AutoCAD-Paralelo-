# Instala (o desinstala) el plugin en el cargador automático de AutoCAD: copia la carpeta .bundle a
# ApplicationPlugins y AutoCAD la carga sola al arrancar, sin NETLOAD.
#   instalar.bat                      -> sólo para este usuario (no pide administrador)
#   instalar.bat -TodosLosUsuarios    -> para todos los usuarios del PC (pide administrador; AutoCAD la trata como ruta de confianza)
#   desinstalar.bat                   -> quita el plugin de las dos ubicaciones
param(
    [switch]$TodosLosUsuarios,
    [switch]$Desinstalar
)
$ErrorActionPreference = 'Stop'

$aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
$bundle = Get-ChildItem -Path $aqui -Directory -Filter *.bundle | Select-Object -First 1
if (-not $bundle) { Write-Host "No encuentro la carpeta .bundle junto a este script." -ForegroundColor Red; exit 1 }
$nombre = $bundle.Name

$porUsuario = Join-Path $env:APPDATA 'Autodesk\ApplicationPlugins'
$todos = Join-Path $env:ProgramFiles 'Autodesk\ApplicationPlugins'

function EsAdmin {
    $p = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Program Files necesita administrador: relanzar elevado con los mismos parámetros
$necesitaAdmin = $TodosLosUsuarios -or ($Desinstalar -and (Test-Path (Join-Path $todos $nombre)))
if ($necesitaAdmin -and -not (EsAdmin)) {
    $args2 = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$($MyInvocation.MyCommand.Path)`"")
    if ($TodosLosUsuarios) { $args2 += '-TodosLosUsuarios' }
    if ($Desinstalar) { $args2 += '-Desinstalar' }
    Write-Host "Pidiendo permiso de administrador..."
    Start-Process powershell -Verb RunAs -ArgumentList $args2 -Wait
    exit
}

if (Get-Process -Name acad, accoreconsole -ErrorAction SilentlyContinue) {
    Write-Host "AutoCAD está abierto: el cambio se nota la próxima vez que lo abras." -ForegroundColor Yellow
}

if ($Desinstalar) {
    $quitado = $false
    foreach ($base in @($porUsuario, $todos)) {
        $dest = Join-Path $base $nombre
        if (Test-Path $dest) { Remove-Item -Recurse -Force $dest; Write-Host "Quitado: $dest"; $quitado = $true }
    }
    if (-not $quitado) { Write-Host "No estaba instalado." }
    exit 0
}

# Aviso (no bloquea) si no hay una versión de AutoCAD compatible
$req = ([xml](Get-Content -Raw -Encoding UTF8 (Join-Path $bundle.FullName 'PackageContents.xml'))).ApplicationPackage.RuntimeRequirements
$compatibles = @(Get-ChildItem 'HKLM:\SOFTWARE\Autodesk\AutoCAD' -ErrorAction SilentlyContinue |
    Where-Object { $_.PSChildName -ge $req.SeriesMin -and $_.PSChildName -le $req.SeriesMax })
if ($compatibles.Count -eq 0) {
    Write-Host "Aviso: no encuentro AutoCAD $($req.SeriesMin) (AutoCAD 2027) en este PC. Se instala igual, pero sólo carga en esa versión." -ForegroundColor Yellow
}

$base = if ($TodosLosUsuarios) { $todos } else { $porUsuario }
$dest = Join-Path $base $nombre
New-Item -ItemType Directory -Force -Path $base | Out-Null
if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }     # reemplaza la versión anterior
Copy-Item -Recurse $bundle.FullName $dest
# Un zip descargado marca cada archivo como "venido de Internet" y .NET se niega a cargar la DLL: quitar la marca
Get-ChildItem -Recurse -File $dest | Unblock-File

Write-Host ""
Write-Host "Instalado en $dest" -ForegroundColor Green
Write-Host "Abre AutoCAD 2027 y escribe el comando (ver LEEME.txt)."
if (-not $TodosLosUsuarios) {
    Write-Host "La primera vez AutoCAD puede preguntar si cargar el archivo: elige 'Cargar siempre'."
}
