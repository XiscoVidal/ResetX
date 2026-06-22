@echo off
REM Firma Authenticode opcional — requiere certificado de firma de codigo (OV/EV).
REM Configura antes de ejecutar BUILD_INSTALLER.bat:
REM   set RESETX_SIGN_PFX=C:\ruta\certificado.pfx
REM   set RESETX_SIGN_PASSWORD=tu_password

if not defined RESETX_SIGN_PFX (
    echo [sign] RESETX_SIGN_PFX no definido — omitiendo firma.
    exit /b 0
)

set "SIGNTOOL=%ProgramFiles(x86)%\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe"
if not exist "%SIGNTOOL%" set "SIGNTOOL=%ProgramFiles(x86)%\Windows Kits\10\bin\x64\signtool.exe"
if not exist "%SIGNTOOL%" (
    echo [sign] signtool.exe no encontrado. Instala Windows SDK.
    exit /b 1
)

set "TS=http://timestamp.digicert.com"
set "PASS="
if defined RESETX_SIGN_PASSWORD set "PASS=/p %RESETX_SIGN_PASSWORD%"

if /I "%~1"=="installer" (
    "%SIGNTOOL%" sign /f "%RESETX_SIGN_PFX%" %PASS% /fd sha256 /tr %TS% /td sha256 "dist\ResetX-Setup.exe"
    exit /b %ERRORLEVEL%
)

"%SIGNTOOL%" sign /f "%RESETX_SIGN_PFX%" %PASS% /fd sha256 /tr %TS% /td sha256 "dist\ResetX\ResetX.exe"
exit /b %ERRORLEVEL%
