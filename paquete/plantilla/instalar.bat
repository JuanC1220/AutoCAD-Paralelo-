@echo off
rem Doble clic: instala el plugin para este usuario. Para todos los usuarios: instalar.bat -TodosLosUsuarios
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1" %*
pause
