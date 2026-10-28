<#
Instalador de ArchiMind para Windows. Se ejecuta con doble clic en «Instalar ArchiMind.bat».

Instala uv y Git si faltan, prepara ArchiMind (uv sync) y deja que scripts/instalacion.py
conecte los servidores con Claude Desktop y lo compruebe todo. Volver a ejecutarlo es seguro:
sirve para actualizar y para reparar la configuración. Lo que pasa queda en instalacion.log.

Parámetros, para probarlo o casos especiales:
  -CarpetaProyectos <ruta>  dónde crear la carpeta de proyectos (por defecto, en Documentos)
  -Rhino                    conectar el puente con Rhino aunque no se detecte Rhino 8
  -SinPausa                 no esperar a que se pulse Intro al terminar
#>
param(
    [string]$CarpetaProyectos = "",
    [switch]$Rhino,
    [switch]$SinPausa
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
$Repo = Split-Path -Parent $PSScriptRoot

function Write-Paso([string]$Texto) {
    Write-Host ""
    Write-Host "== $Texto" -ForegroundColor Cyan
}

function Write-Falta([string]$Texto) {
    Write-Host ""
    Write-Host "[FALTA] $Texto" -ForegroundColor Yellow
}

function Exit-Instalador([int]$Codigo) {
    try { Stop-Transcript | Out-Null } catch { }
    if (-not $SinPausa) {
        Write-Host ""
        Read-Host "Pulsa Intro para cerrar esta ventana" | Out-Null
    }
    exit $Codigo
}

function Update-RutaSesion {
    # Lo que un instalador acaba de añadir al PATH no llega solo a esta ventana.
    $maquina = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $usuario = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$maquina;$usuario;$(Join-Path $HOME '.local\bin')"
}

function Invoke-Programa([string]$Programa, [string[]]$Argumentos) {
    # La salida de error de un programa no detiene el script: manda su código de salida. Todo
    # pasa por Out-Host para que quede en instalacion.log.
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $Programa @Argumentos 2>&1 | ForEach-Object { "$_" } | Out-Host
    $codigo = $LASTEXITCODE
    $ErrorActionPreference = $anterior
    return $codigo
}

function Find-Uv {
    $comando = Get-Command uv -ErrorAction SilentlyContinue
    if ($comando) { return $comando.Source }
    $local = Join-Path $HOME ".local\bin\uv.exe"
    if (Test-Path $local) { return $local }
    return $null
}

try { Start-Transcript -Path (Join-Path $Repo "instalacion.log") -Force | Out-Null } catch { }

Write-Host "Instalador de ArchiMind" -ForegroundColor Cyan
Write-Host "Carpeta de ArchiMind: $Repo"

# --- 1. La carpeta -----------------------------------------------------------------------------
if ($Repo -match '\.zip\\') {
    Write-Falta ("Estás ejecutando el instalador desde dentro del archivo ZIP. Primero " +
        "extráelo: clic derecho sobre el ZIP → «Extraer todo», elige una carpeta (por ejemplo " +
        "C:\ArchiMind) y ejecuta «Instalar ArchiMind» desde la carpeta extraída.")
    Exit-Instalador 1
}
if (-not (Test-Path (Join-Path $Repo "pyproject.toml"))) {
    Write-Falta ("No encuentro los archivos de ArchiMind junto al instalador. Ejecuta " +
        "«Instalar ArchiMind» desde la carpeta de ArchiMind, sin moverlo a otro sitio.")
    Exit-Instalador 1
}

# --- 2. uv -------------------------------------------------------------------------------------
Write-Paso "uv (descarga Python y lo que ArchiMind necesita)"
$Uv = Find-Uv
if (-not $Uv) {
    Write-Host "Instalando uv..."
    $codigo = Invoke-Programa "powershell" @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
        "irm https://astral.sh/uv/install.ps1 | iex")
    Update-RutaSesion
    $Uv = Find-Uv
    if (-not $Uv) {
        Write-Falta ("No se pudo instalar uv (código $codigo). Revisa la conexión a internet y " +
            "vuelve a ejecutar el instalador. Si sigue fallando, mira docs\problemas-frecuentes.md.")
        Exit-Instalador 1
    }
}
Write-Host "[OK] uv: $Uv" -ForegroundColor Green

# --- 3. Git ------------------------------------------------------------------------------------
Write-Paso "Git (guarda el historial de versiones de cada proyecto)"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Instalando Git... (si Windows pide permiso, pulsa Sí)"
        Invoke-Programa "winget" @(
            "install", "--id", "Git.Git", "-e", "--source", "winget",
            "--accept-package-agreements", "--accept-source-agreements") | Out-Null
        Update-RutaSesion
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Falta ("Falta Git. Se abre su página de descarga: instálalo pulsando Next en " +
            "todas las pantallas y vuelve a ejecutar «Instalar ArchiMind».")
        Start-Process "https://git-scm.com/downloads/win"
        Exit-Instalador 1
    }
}
Write-Host "[OK] Git: $((Get-Command git).Source)" -ForegroundColor Green

# --- 4. ArchiMind ------------------------------------------------------------------------------
Write-Paso "Preparando ArchiMind (la primera vez puede tardar unos minutos)"
Push-Location $Repo
$codigo = Invoke-Programa $Uv @("sync")
Pop-Location
if ($codigo -ne 0) {
    Write-Falta ("No se pudo preparar ArchiMind (uv sync, código $codigo). Revisa la conexión " +
        "a internet y vuelve a ejecutar el instalador; el detalle quedó en instalacion.log.")
    Exit-Instalador 1
}
Write-Host "[OK] ArchiMind preparado" -ForegroundColor Green

# --- 5. Claude Desktop, opcionales y comprobación ---------------------------------------------
Write-Paso "Conectando con Claude Desktop y comprobando"
if (-not $CarpetaProyectos) {
    $CarpetaProyectos = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "ArchiMind-proyectos"
}
$argumentos = @("run", "python", (Join-Path $Repo "scripts\instalacion.py"),
    "--uv", $Uv, "--proyectos", $CarpetaProyectos)
if ($Rhino) { $argumentos += "--rhino" }
Push-Location $Repo
$codigo = Invoke-Programa $Uv $argumentos
Pop-Location

if ($codigo -eq 0 -and (Get-Process -Name "claude" -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host ("Claude Desktop está abierto: para que vea ArchiMind hay que cerrarlo del todo " +
        "(clic derecho en su icono junto al reloj → Salir) y volver a abrirlo.") -ForegroundColor Yellow
}
Exit-Instalador $codigo
