@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo   ResetX - Generar instalador
echo ========================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo Creando entorno virtual...
    python -m venv venv
    if errorlevel 1 goto :error
)

echo Instalando dependencias...
call venv\Scripts\activate.bat
pip install -r requirements.txt -q
if errorlevel 1 goto :error

echo.
echo Compilando ejecutable con PyInstaller...
pyinstaller resetx.spec --noconfirm --clean
if errorlevel 1 goto :error

echo.
echo Ejecutable listo: dist\ResetX\ResetX.exe

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" (
    echo.
    echo Generando instalador...
    "%ISCC%" installer.iss
    if errorlevel 1 goto :error
    echo.
    echo Instalador listo: dist\ResetX-Setup.exe
) else (
    echo.
    echo Inno Setup no encontrado.
    echo Instala Inno Setup 6 y vuelve a ejecutar este script para crear ResetX-Setup.exe
    echo https://jrsoftware.org/isinfo.php
    echo.
    echo Puedes distribuir la carpeta dist\ResetX\ como version portable.
)

echo.
echo Listo.
pause
exit /b 0

:error
echo.
echo ERROR en la compilacion.
pause
exit /b 1
