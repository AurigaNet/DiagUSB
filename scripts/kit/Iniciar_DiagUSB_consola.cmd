@echo off
chcp 65001 >nul
setlocal EnableExtensions
set "KIT=%~dp0"
title DiagUSB - Iniciar (consola)
cd /d "%KIT%"

echo ============================================================
echo  DiagUSB - Iniciar (menú de consola)
echo ============================================================
echo.

if not exist "%KIT%python\python.exe" (
    echo ERROR: no se encontró python\python.exe en el kit.
    goto :error
)

echo Verificando la firma digital de python\python.exe ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$f = Get-AuthenticodeSignature -LiteralPath '%KIT%python\python.exe'; if ($f.Status -eq 'HashMismatch' -or $f.Status -eq 'NotSigned') { Write-Host ('FIRMA INVALIDA (' + $f.Status + '). No se ejecutara nada.'); exit 2 } elseif ($f.Status -ne 'Valid') { Write-Host ('AVISO: no se pudo validar la firma (' + $f.Status + '); se continuara.'); exit 0 } else { Write-Host ('Firma valida: ' + $f.SignerCertificate.Subject); exit 0 }"
if errorlevel 2 goto :firma_mala
if errorlevel 1 goto :error

echo.
echo ------------------------------------------------------------
echo  Qué hace DiagUSB:
echo   - Ejecuta consultas de SOLO LECTURA con PowerShell sobre este equipo.
echo   - Solicita permisos de Administrador (UAC) para obtener datos completos.
echo   - NO modifica la configuración del equipo.
echo   - NO envía datos por red.
echo   - Guarda los informes en la carpeta del kit.
echo ------------------------------------------------------------
echo.
echo ¿Continuar? (S/N)
set /p "RESPUESTA=Opcion: "
if /i not "%RESPUESTA%"=="S" (
    echo Operación cancelada por el usuario.
    goto :fin
)

echo.
echo Iniciando DiagUSB (consola) ...
"%KIT%python\python.exe" -I -B -m diagusb %*
if errorlevel 1 goto :error
goto :fin

:error
echo.
echo ERROR: DiagUSB terminó con un error. Revise el mensaje anterior.
pause

:firma_mala
echo.
echo ERROR: la firma digital de python\python.exe no es válida. No se ejecutará DiagUSB.
pause

:fin
endlocal
