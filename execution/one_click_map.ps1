param(
  [Parameter(Mandatory=$true)][string]$Story,   # ruta al story-spec JSON
  [string]$Name = "mapa"
)

# =====================================================================
# one_click_map.ps1 — mapa animado GeoLayers de un clic.
#
# REQUISITOS (sin esto no renderiza):
#   1. GEOlayers 3 instalado y su PANEL ABIERTO en After Effects.
#   2. Un Mapcomp base ya creado y seleccionado en el panel (setup one-time,
#      ver directives/animate_map.md).
#   3. Token de MapTiler/Mapbox cargado en el panel.
#   4. Correr ESTE script en una TERMINAL INTERACTIVA (no como tarea de fondo):
#      AfterFX -r solo se acopla a AE desde una sesion interactiva. AE sin dialogos.
# =====================================================================

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$afx  = "C:\Program Files\Adobe\Adobe After Effects 2026\Support Files\AfterFX.exe"
$aer  = "C:\Program Files\Adobe\Adobe After Effects 2026\Support Files\aerender.exe"

# Salida en D: (disco de trabajo) para no llenar C:. Cae a Documentos si D: no existe.
$outDir = "D:\IA - PROYECTS 2026\After Effects\Julio"
if (-not (Test-Path "D:\")) { $outDir = Join-Path $env:USERPROFILE "Documents\MacroWise_Maps" }
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$date = Get-Date -Format "yyyy-MM-dd"
$comp = "MWMAP_" + ($Name -replace '[^a-zA-Z0-9]','_')
$jsx  = Join-Path $outDir "$comp.jsx"
$mp4  = Join-Path $outDir ("{0}_{1}.mp4" -f $date,$Name)

Write-Host "==> 1/3 Generando .jsx desde el story-spec..." -ForegroundColor Cyan
& python (Join-Path $here "build_map.py") $Story --out $jsx
if ($LASTEXITCODE -ne 0) { Write-Error "build_map.py fallo"; exit 1 }

Write-Host "==> 2/3 GEOlayers construye + anima + finalize (AfterFX -r)..." -ForegroundColor Cyan
Write-Host "    (el panel de GEOlayers debe estar ABIERTO con un Mapcomp base)" -ForegroundColor DarkYellow
& $afx -r $jsx
Start-Sleep -Seconds 20   # GEOlayers descarga tiles + arma capas; dale tiempo

Write-Host "==> 3/3 Render final (aerender -reuse)..." -ForegroundColor Cyan
Write-Host "    Ajusta -comp al nombre del Mapcomp que finalize dejo en la cola." -ForegroundColor DarkYellow
if (Test-Path $mp4) { Remove-Item $mp4 -Force }
& $aer -reuse -comp $comp -output $mp4
if (-not (Test-Path $mp4)) {
  Write-Warning "No aparecio el MP4. Revisa: panel GEOlayers abierto? Mapcomp base? log en $env:TEMP\mw_map_log.txt"
  Write-Warning "Quiza el Mapcomp se llama distinto: corre 'aerender -reuse' con el nombre real del comp."
  exit 1
}
Write-Host "==> MP4: $mp4 ($([math]::Round((Get-Item $mp4).Length/1MB,1)) MB)" -ForegroundColor Green
