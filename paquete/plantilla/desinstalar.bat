@echo off
rem Doble clic: quita el plugin de AutoCAD (de este usuario y de todos los usuarios).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1" -Desinstalar
pause
