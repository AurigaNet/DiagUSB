# SPDX-License-Identifier: GPL-3.0-or-later
"""Falla si alguna función tiene sentencias después de return/raise/continue/break."""
import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1] / "src" / "diagusb"
_TERMINALES = (ast.Return, ast.Raise, ast.Continue, ast.Break)


def _listas_de_sentencias(arbol):
    for nodo in ast.walk(arbol):
        for _, valor in ast.iter_fields(nodo):
            if (isinstance(valor, list) and valor
                    and all(isinstance(v, ast.stmt) for v in valor)):
                yield valor


def codigo_inalcanzable(ruta):
    arbol = ast.parse(Path(ruta).read_text(encoding="utf-8-sig"), filename=str(ruta))
    hallazgos = []
    for sentencias in _listas_de_sentencias(arbol):
        for anterior, siguiente in zip(sentencias, sentencias[1:]):
            if isinstance(anterior, _TERMINALES):
                hallazgos.append(f"{ruta}:{siguiente.lineno}")
                break
    return hallazgos


def test_no_hay_codigo_inalcanzable():
    hallazgos = []
    for ruta in sorted(RAIZ.rglob("*.py")):
        hallazgos += codigo_inalcanzable(ruta)
    assert not hallazgos, "Código después de return/raise:\n" + "\n".join(hallazgos)
