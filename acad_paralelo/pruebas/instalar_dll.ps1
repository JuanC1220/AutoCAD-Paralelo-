# Instala una versión del plugin desde GitHub, fijada a un commit, y comprueba su huella SHA-256.
#   powershell -ExecutionPolicy Bypass -File instalar_dll.ps1 -Commit 644f41c97ca9f22a64ed6261147f70f0ae43fcc9 -Sha256 6908DBA7...
# Si la huella no coincide no instala nada. El DLL anterior queda en anteriores\.
param(
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{40}$')][string]$Commit,
    [Parameter(Mandatory)][ValidatePattern('^[0-9A-Fa-f]{64}$')][string]$Sha256,
    [string]$Destino = ''
)
$ErrorActionPreference = 'Stop'
if (-not $PSScriptRoot) { $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $Destino) { $Destino = Join-Path $PSScriptRoot 'AcadParalelo.dll' }
$url = "https://raw.githubusercontent.com/JuanC1220/AutoCAD-Paralelo-/$Commit/acad_paralelo/dist/AcadParalelo.dll"
$tmp = Join-Path $env:TEMP ("AcadParalelo_descarga_" + [Guid]::NewGuid().ToString('N') + '.dll')
Invoke-WebRequest $url -OutFile $tmp -UseBasicParsing
$h = (Get-FileHash $tmp -Algorithm SHA256).Hash
if ($h -ne $Sha256.ToUpper()) { Remove-Item $tmp; throw "Huella distinta: $h (esperada $Sha256). No se instaló nada." }
if (Test-Path $Destino) {
    $ant = Join-Path (Split-Path $Destino) 'anteriores'
    New-Item -ItemType Directory -Force $ant | Out-Null
    Copy-Item $Destino (Join-Path $ant ("AcadParalelo_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.dll'))
}
Move-Item $tmp $Destino -Force
Write-Host "Instalado $Destino ($($Commit.Substring(0,7)), $h)"
