@echo off
chcp 65001 >nul
title SIGRAMA - Despliegue en Google Cloud Run (Control Corte y Doblez)
color 0B

echo ===============================================================================
echo       INDUSTRIA SIGRAMA S.A. DE C.V. - PROTOCOLO OFICIAL GOOGLE CLOUD
echo       Despliegue de Aplicacion: Control de Corte y Doblez
echo       Servicio: sigrama-corte-doblez
echo       Region:   us-central1
echo       Proyecto: sigrama-cloud-calidad
echo       Bucket:   gs://sigrama-corte-doblez-storage
echo ===============================================================================
echo.

cd /d "%~dp0"

echo 1. Verificando configuracion de GCP...
call gcloud config set project sigrama-cloud-calidad
call gcloud config set run/region us-central1

echo.
echo 2. Construyendo imagen con Google Cloud Build...
call gcloud builds submit --tag gcr.io/sigrama-cloud-calidad/sigrama-corte-doblez:latest

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Fallo la construccion de la imagen Docker en Cloud Build.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo 3. Desplegando en Google Cloud Run...
call gcloud run deploy sigrama-corte-doblez ^
    --image gcr.io/sigrama-cloud-calidad/sigrama-corte-doblez:latest ^
    --region us-central1 ^
    --platform managed ^
    --allow-unauthenticated ^
    --memory 2Gi ^
    --cpu 2 ^
    --set-env-vars GCS_BUCKET=sigrama-corte-doblez-storage,PYTHONUNBUFFERED=1

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Fallo el despliegue del servicio en Cloud Run.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ===============================================================================
echo [EXITO] Despliegue completado con exito.
echo Servicio disponible en Google Cloud Run.
echo ===============================================================================
pause
