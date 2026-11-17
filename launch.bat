@echo off
setlocal enabledelayedexpansion

REM Ir al directorio donde esta este .bat
cd /d "%~dp0"

echo ========================================
echo   Cliente Multimedia - NUC
echo ========================================
echo.

REM ---------------------------------------------------------------
REM [1/4] Verificar UV
REM ---------------------------------------------------------------
echo [1/4] Verificando UV...
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo       UV no encontrado. Instalando UV...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri https://astral.sh/uv/install.ps1 -UseBasicParsing | powershell -command -"
    if %errorlevel% neq 0 (
        echo       ERROR: No se pudo instalar UV.
        echo       Instalalo manualmente desde https://github.com/astral-sh/uv
        pause
        exit /b 1
    )
    echo       UV instalado correctamente.
    REM Recargar PATH de usuario para que 'uv' sea visible en esta sesion
    set "PATH=%PATH%;%USERPROFILE%\.local\bin"
) else (
    echo       UV encontrado.
)

REM ---------------------------------------------------------------
REM [2/4] Verificar VLC (requisito del sistema, no se instala por pip)
REM ---------------------------------------------------------------
echo [2/4] Verificando VLC...

set "VLC_FOUND=0"

REM 1) Buscar vlc.exe en rutas comunes de instalacion
if exist "%ProgramFiles%\VideoLAN\VLC\vlc.exe" set "VLC_FOUND=1"
if exist "%ProgramFiles(x86)%\VideoLAN\VLC\vlc.exe" set "VLC_FOUND=1"
if exist "%LOCALAPPDATA%\VideoLAN\VLC\vlc.exe" set "VLC_FOUND=1"

REM 2) Buscar vlc.exe en el PATH
if %VLC_FOUND%==0 (
    where vlc >nul 2>&1
    if %errorlevel%==0 set "VLC_FOUND=1"
)

if %VLC_FOUND%==1 (
    echo       VLC encontrado.
) else (
    echo       VLC NO encontrado. Instalando silenciosamente...
    REM Intentar con winget (disponible en Windows 10/11 modernos)
    where winget >nul 2>&1
    if %errorlevel%==0 (
        winget install --id VideoLAN.VLC -e --silent --accept-package-agreements --accept-source-agreements
        if %errorlevel% neq 0 (
            echo       ERROR: winget no pudo instalar VLC.
            echo       Instalalo manualmente desde https://www.videolan.org/vlc/
            pause
            exit /b 1
        )
        echo       VLC instalado correctamente.
    ) else (
        echo       winget no disponible en este sistema.
        echo       Instalando VLC por descarga directa...
        set "VLC_INSTALLER=%TEMP%\vlc-installer.exe"
        powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://get.videolan.org/vlc/3.0.21/win64/vlc-3.0.21-win64.exe' -OutFile '%VLC_INSTALLER%'" -UseBasicParsing
        if not exist "%VLC_INSTALLER%" (
            echo       ERROR: No se pudo descargar el instalador de VLC.
            echo       Instalalo manualmente desde https://www.videolan.org/vlc/
            pause
            exit /b 1
        )
        "%VLC_INSTALLER%" /S
        del "%VLC_INSTALLER%" >nul 2>&1
        echo       VLC instalado correctamente.
    )
)

REM ---------------------------------------------------------------
REM [3/4] Sincronizar dependencias Python con UV
REM ---------------------------------------------------------------
echo [3/4] Sincronizando dependencias con UV...
uv sync
if %errorlevel% neq 0 (
    echo       ERROR: Fallo al sincronizar dependencias.
    pause
    exit /b 1
)
echo       Dependencias listas.

REM ---------------------------------------------------------------
REM [4/4] Iniciar la aplicacion
REM ---------------------------------------------------------------
echo [4/4] Iniciando cliente multimedia...
echo.
uv run python src/main.py

endlocal