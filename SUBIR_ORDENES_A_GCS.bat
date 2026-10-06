@echo off
chcp 65001 >nul
title SIGRAMA - Sincronizador de Ordenes de Fabricacion Z: a Google Cloud Storage
color 0C

echo ===============================================================================
echo       INDUSTRIA SIGRAMA S.A. DE C.V. - PROTOCOLO GOOGLE CLOUD STORAGE
echo       Sincronizacion de Ordenes de Fabricacion (Z:\14 - ORDENES DE FABRICACION)
echo ===============================================================================
echo.

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] No se encontro el entorno virtual en venv\Scripts\python.exe
    pause
    exit /b 1
)

echo Iniciando sincronizacion hacia gs://sigrama-corte-doblez-storage...
echo.

venv\Scripts\python.exe tools\sync_z_to_gcs.py

echo.
echo ===============================================================================
echo Proceso finalizado. Puede cerrar esta ventana.
echo ===============================================================================
pause
