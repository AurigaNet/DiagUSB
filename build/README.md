# Build

## Kit portable (distribución principal)

La distribución principal de DiagUSB es el kit con Python embebido (`DiagUSB-kit-<version>.zip`), que se arma con `scripts\armar_kit.ps1` y no requiere PyInstaller. Ver el `README.md` de la raíz. El resto de este documento describe la **variante opcional** basada en PyInstaller.

## Empaquetado con PyInstaller (variante opcional)

Este directorio contiene los archivos necesarios para crear un ejecutable portable de DiagUSB usando PyInstaller en modo `onedir`.

### Archivos

- `diagusb.spec` - Archivo de configuracion de PyInstaller

### Requisitos

- Python 3.10 o superior
- PyInstaller instalado: `pip install pyinstaller`

### Construccion

Ejecute el script de construccion:

```batch
scripts\build.cmd
```

O directamente con PyInstaller:

```batch
pyinstaller build\diagusb.spec --noconfirm
```

### Salida

El ejecutable se genera en: `dist\diagusb\diagusb.exe`

### Notas

- El modo `onedir` crea un directorio con el ejecutable y todas sus dependencias
- Los collectors de PowerShell se incluyen en el paquete bajo la carpeta `collectors/`
- Los paquetes de impresion e inventario se incluyen bajo `diagusb/packages/`
