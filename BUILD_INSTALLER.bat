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

call venv\Scripts\activate.bat
echo Instalando dependencias...
pip install -r requirements.txt -q
if errorlevel 1 goto :error

echo.
echo Generando iconos y metadatos...
python scripts\generate_icons.py
python scripts\generate_version_info.py
if errorlevel 1 goto :error

echo.
echo Compilando ejecutable con PyInstaller...
pyinstaller resetx.spec --noconfirm --clean
if errorlevel 1 goto :error

echo.
echo Ejecutable listo: dist\ResetX\ResetX.exe

if defined RESETX_SIGN_PFX (
    echo.
    echo Firmando ejecutable e instalador...
    call scripts\sign_release.bat
)

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" (
    echo.
    echo Generando instalador...
    "%ISCC%" installer.iss
    if errorlevel 1 goto :error
    if defined RESETX_SIGN_PFX call scripts\sign_release.bat installer
    echo.
    echo Instalador listo: dist\ResetX-Setup.exe
) else (
    echo.
    echo Inno Setup no encontrado — instala Inno Setup 6 para crear ResetX-Setup.exe
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
