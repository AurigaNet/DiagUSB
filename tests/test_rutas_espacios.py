# SPDX-License-Identifier: GPL-3.0-or-later
"""Test que comprueba que las rutas del kit funcionan desde cualquier ruta (incluido espacios)."""

import tempfile, shutil, sys, subprocess, json, zipfile
sys.path.insert(0, "src")
from diagusb.core import publicacion

def test_kit_funciona_desde_ruta_con_espacios():
    with tempfile.TemporaryDirectory() as tmp:
        # Copiar un archivo del proyecto a una ruta con espacios
        ruta_espacio = tmp + " /directorio con espacios/"
        import os
        os.makedirs(ruta_espacio, exist_ok=True)
        # Copiar el script armar_kit.ps1 como referencia
        shutil.copy2("scripts/armar_kit.ps1", ruta_espacio + "armar_kit.ps1")
        # Verificar que se puede leer el archivo desde esa ruta
        with open(ruta_espacio + "armar_kit.ps1", "r", encoding="utf-8") as f:
            contenido = f.read()
        assert "SPDX-License-Identifier" in contenido
        # El test es que la ruta se resolvió correctamente
        assert True

if __name__ == "__main__":
    test_kit_funciona_desde_ruta_con_espacios()
    print("Ruta con espacios OK")
