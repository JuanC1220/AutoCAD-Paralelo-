@echo off
rem Doble clic: pide la carpeta y deja los DWG limpios en <carpeta>_limpios (los originales no se tocan).
rem Tambien acepta los mismos parametros que limpiar_lotes.ps1, p. ej.: limpiar_lotes.bat -Entrada C:\planos -Recursivo
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0limpiar_lotes.ps1" %*
pause
