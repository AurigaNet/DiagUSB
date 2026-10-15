# Build

## Empaquetado con PyInstaller

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
