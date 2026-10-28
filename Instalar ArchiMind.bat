@echo off
rem Instalador de ArchiMind: doble clic para instalar, actualizar o reparar.
rem Hace todo scripts\instalar.ps1; aqui solo se abre sin cambiar la politica de PowerShell.
if not exist "%~dp0scripts\instalar.ps1" (
  echo No encuentro los archivos de ArchiMind junto a este instalador.
  echo Si lo abriste desde dentro del ZIP, primero extraelo: clic derecho sobre el ZIP,
  echo "Extraer todo", y ejecuta "Instalar ArchiMind" desde la carpeta extraida.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\instalar.ps1" %*
