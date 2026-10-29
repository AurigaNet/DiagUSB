import json, sys

manifest_path = "tools/tools.manifest.json"
with open(manifest_path, "r", encoding="utf-8") as f:
    manifest = json.load(f)

# --- Reemplazar PawnIO entry por el estado correcto (verificado) ---
for tool in manifest["tools"]:
    if tool["name"] == "PawnIO":
        tool["url"] = "https://github.com/namazso/PawnIO.Setup/releases/latest/download/PawnIO_setup.exe"
        tool["version"] = "2.2.0"
        tool["sha256"] = "1f519a22e47187f70a1379a48ca604981c4fcf694f4e65b734aaa74a9fba3032"
        tool["license"] = "GPL-2.0"
        tool["file"] = "PawnIO_setup.exe"
        tool["source"] = "https://github.com/namazso/PawnIO"
        tool["checksum_url"] = "https://api.github.com/repos/namazso/PawnIO.Setup/releases/latest"
        tool["redistribuible"] = "yes: binario independiente con licencia GPL-2.0, funcionalidad agregada en el kit (no codigo enlazado). Texto de licencia y fuente indicados."
        tool["estado"] = "verificado"
        tool["motivo"] = None  # Eliminar el motivo antiguo (excluido)
        tool["notes"] = "Instalador para Windows 10/11 con driver firmado Authenticode (2026-03-15 v2.2.0); GPL-2.0 de repositorio namazso. Solo como instalador de kernel con consentimiento."
        break

with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)
print("PawnIO actualizado a estado 'verificado'.")
