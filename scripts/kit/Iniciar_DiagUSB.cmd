@echo off
chcp 65001 >nul
setlocal EnableExtensions
set "KIT=%~dp0"
title DiagUSB - Iniciar (interfaz web)
cd /d "%KIT%"

echo ============================================================
echo  DiagUSB - Iniciar (interfaz web)
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
echo   - Funciona sin permisos de Administrador (modo estándar).
echo   - Pide permisos de Administrador (UAC) solo si usted usa el botón
echo     "Dar permisos de administrador" de la interfaz web.
echo   - NO modifica la configuración del equipo.
echo   - NO envía datos a servidores de DiagUSB ni telemetría.
echo   - El colector de red puede probar conectividad (ping a
echo     8.8.8.8/1.1.1.1, puerta de enlace y DNS google.com) sin
echo     enviar el diagnóstico.
echo   - Abre la interfaz web local en 127.0.0.1 (solo en este equipo).
echo   - Guarda los informes en la carpeta del kit.
echo.
echo  Datos que puede guardar (solo en este equipo):
echo   - Equipo y Windows: nombre, usuario, dominio, versión.
echo   - Hardware, discos, memoria, impresoras y drivers.
echo   - Red: IP, MAC, DNS, puerta de enlace y perfiles Wi-Fi
echo     (SSID, autenticación y cifrado; SIN contraseñas ni claves).
echo   - Programas, servicios, eventos, actualizaciones y seguridad.
echo   - Hallazgos, acciones e informes en config\ y reports\.
echo.
echo  Se requiere autorización para analizar el equipo. Al continuar,
echo  usted confirma que cuenta con esa autorización. Puede borrar los
echo  datos locales desde Configuración en la interfaz.
echo ------------------------------------------------------------
echo.
echo ¿Continuar? (S/N)
set /p "RESPUESTA=Opcion: "
if /i not "%RESPUESTA%"=="S" (
    echo Operación cancelada por el usuario.
    goto :fin
)

echo.
echo Iniciando DiagUSB ...
"%KIT%python\python.exe" -I -B -m diagusb --open web %*
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
