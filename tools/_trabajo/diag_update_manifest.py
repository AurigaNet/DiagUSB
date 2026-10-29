import json
import hashlib
import urllib.request

# ============================================================
# LibreHardwareMonitor verification (already verified above)
# ============================================================
lhm_info = {
    "name": "LibreHardwareMonitor",
    "official_domain": "librehardwaremonitor.org",
    "url": "https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v0.9.6/LibreHardwareMonitor.zip",
    "version": "0.9.6",
    "sha256": "086d9f1b5a99e643edc2cfaaac16051685b551e4c5ac0b32a57c58c0e529c001",
    "license": "MPL-2.0",
    "file": "LibreHardwareMonitor.zip",
    "source": "https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/tag/v0.9.6",
    "checksum_url": "https://api.github.com/repos/LibreHardwareMonitor/LibreHardwareMonitor/releases/latest",
    "redistribuible": "yes: MPL-2.0 compatible with GPL-3.0-or-later",
    "estado": "verificado",
    "notes": "Windows 10/11 build without additional runtime requirements. SHA-256 verificado contra API de GitHub el 2026-10-29. Requiere instalacion del driver PawnIO para sensores CPU/ventilador."
}

# ============================================================
# PawnIO - excluded due to license
# ============================================================
pawnio_info = {
    "name": "PawnIO",
    "official_domain": "pawnio.eu",
    "url": None,
    "version": None,
    "sha256": None,
    "license": "GPL-2.0",
    "file": None,
    "source": "https://github.com/namazso/PawnIO",
    "checksum_url": None,
    "redistribuible": "no: GPL-2.0 incompatibles con inclusion en kit GPL-3.0-or-later",
    "estado": "excluido",
    "motivo": "La licencia GPL-2.0 requiere que el codigo fuente este disponible y que la obra derivada distribuya bajo los mismos terminos. Incluir el instalador dentro de un kit con licencia GPL-3.0-or-later generarria obligaciones legales conflictivas. Se incluye solo deteccion de driver y mensaje de UI explicando instalacion manual."
}

# Read current manifest
with open('tools/tools.manifest.json', 'r', encoding='utf-8') as f:
    manifest = json.load(f)

# Add LHM (before the closing bracket, after Npcap)
# Find the last existing tool and add LHM before the ]
tools_tools = manifest["tools"]

# Add LHM
tools_tools.append(lhm_info)
# Add PawnIO (excluded)
tools_tools.append(pawnio_info)

# Write back
with open('tools/tools.manifest.json', 'w', encoding='utf-8') as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)

print("Manifest updated successfully")
print(f"Total tools: {len(tools_tools)}")
for t in tools_tools:
    print(f"  {t['name']}: estado={t['estado']}")