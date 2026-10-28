<#
Carga un CSV en la base de datos de ArchiMind (precios, materiales, programa de áreas o
partidas). Se ejecuta con doble clic en «Importar datos.bat», o soltando el CSV sobre él.

Pregunta qué tabla es y ejecuta el comando de siempre:
  uv run --package archimind-docs archimind-docs-importar <tabla> <archivo.csv>
Las columnas de cada tabla están en packages\docs\README.md y las plantillas vacías, en
packages\docs\plantillas.

Parámetros, para probarlo: -Archivo <csv> (también el primero sin nombre), -Tabla <nombre>
(unit_prices, materials, area_program o budget_items) y -SinPausa.
#>
param(
    [Parameter(Position = 0)][string]$Archivo = "",
    [string]$Tabla = "",
    [switch]$SinPausa
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
$Repo = Split-Path -Parent $PSScriptRoot
$Plantillas = Join-Path $Repo "packages\docs\plantillas"
$Tablas = [ordered]@{
    "1" = @("unit_prices", "Precios unitarios (APU)")
    "2" = @("materials", "Materiales")
    "3" = @("area_program", "Programa de áreas (reemplaza el anterior entero)")
    "4" = @("budget_items", "Partidas del presupuesto (partida → APU y material)")
}

function Exit-Importador([int]$Codigo) {
    if (-not $SinPausa) {
        Write-Host ""
        Read-Host "Pulsa Intro para cerrar esta ventana" | Out-Null
    }
    exit $Codigo
}

Write-Host "Importar datos a ArchiMind" -ForegroundColor Cyan
Write-Host "Plantillas con las columnas de cada tabla: $Plantillas"

if (-not $Tabla) {
    Write-Host ""
    Write-Host "¿Qué vas a cargar?"
    foreach ($opcion in $Tablas.Keys) {
        Write-Host "  $opcion. $($Tablas[$opcion][1])"
    }
    $elegida = (Read-Host "Escribe el número y pulsa Intro").Trim()
    if (-not $Tablas.Contains($elegida)) {
        Write-Host "«$elegida» no es una de las opciones (1 a 4)." -ForegroundColor Yellow
        Exit-Importador 1
    }
    $Tabla = $Tablas[$elegida][0]
}
$nombres = @($Tablas.Values | ForEach-Object { $_[0] })
if ($nombres -notcontains $Tabla) {
    Write-Host "«$Tabla» no es una tabla de ArchiMind: son $($nombres -join ', ')." `
        -ForegroundColor Yellow
    Exit-Importador 1
}

if (-not $Archivo) {
    $Archivo = Read-Host "Arrastra el archivo CSV a esta ventana y pulsa Intro"
}
$Archivo = $Archivo.Trim().Trim('"')
if (-not (Test-Path -LiteralPath $Archivo -PathType Leaf)) {
    Write-Host "No encuentro el archivo «$Archivo»." -ForegroundColor Yellow
    Exit-Importador 1
}

$uv = Get-Command uv -ErrorAction SilentlyContinue
$Uv = if ($uv) { $uv.Source } else { Join-Path $HOME ".local\bin\uv.exe" }
if (-not (Test-Path $Uv)) {
    Write-Host "ArchiMind no está instalado en este equipo: primero ejecuta «Instalar ArchiMind»." `
        -ForegroundColor Yellow
    Exit-Importador 1
}

Write-Host ""
Write-Host "Cargando $Archivo en $Tabla..."
Push-Location $Repo
$ErrorActionPreference = "Continue"
& $Uv run --package archimind-docs archimind-docs-importar $Tabla $Archivo 2>&1 |
    ForEach-Object { "$_" } | Out-Host
$codigo = $LASTEXITCODE
Pop-Location
if ($codigo -ne 0) {
    Write-Host ""
    Write-Host "No se cargó nada: corrige las filas indicadas arriba y vuelve a intentarlo." `
        -ForegroundColor Yellow
}
Exit-Importador $codigo
