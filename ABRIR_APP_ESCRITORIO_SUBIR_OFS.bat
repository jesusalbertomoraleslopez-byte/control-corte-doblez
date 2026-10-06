@echo off
chcp 65001 > nul
title SIGRAMA METALES - Sincronizador de Ordenes de Fabricacion a Google Cloud

cd /d "%~dp0"

if exist "venv\Scripts\pythonw.exe" (
    start "" "venv\Scripts\pythonw.exe" "tools\gui_sincronizador_ofs.py"
    exit /b 0
)

if exist "venv\Scripts\python.exe" (
    start "" "venv\Scripts\python.exe" "tools\gui_sincronizador_ofs.py"
    exit /b 0
)

pause
