@echo off
rem Carga un CSV en la base de datos de ArchiMind: doble clic, o soltar el CSV encima.
rem Hace todo scripts\importar_datos.ps1.
if not exist "%~dp0scripts\importar_datos.ps1" (
  echo No encuentro los archivos de ArchiMind junto a este programa.
  echo Ejecutalo desde la carpeta de ArchiMind, ya extraida del ZIP.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\importar_datos.ps1" %*
