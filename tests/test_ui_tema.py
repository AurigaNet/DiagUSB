# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Pruebas del tema visual: barra lateral azul marino y tarjetas blancas."""

from pathlib import Path

import diagusb.web_server as ws

STATIC = Path(ws.__file__).parent / "static"


def _css() -> str:
    return (STATIC / "app.css").read_text(encoding="utf-8", errors="replace")


def _html() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8", errors="replace")


def _js() -> str:
    return (STATIC / "app.js").read_text(encoding="utf-8", errors="replace")


def test_paleta_clara_con_barra_lateral_marino():
    css = _css()
    assert "--fondo: #EDF2F7" in css
    assert "--sidebar: #0B1F3A" in css
    assert "--panel: #FFFFFF" in css
    assert "--texto: #172A44" in css
    assert "linear-gradient(180deg, var(--sidebar)" in css


def test_tarjetas_y_paneles_blancos():
    css = _css()
    assert ".panel {" in css
    assert "background: var(--panel);" in css
    assert ".diag-card {" in css
    assert "box-shadow: var(--sombra);" in css
    assert ".results-section { border-top: 3px solid var(--acento); }" in css


def test_resultados_compartidos_en_inicio_e_historial():
    html = _html()
    assert 'id="panelUltimo"' in html
    assert html.count('class="panel results-section"') >= 2
    assert "renderUltimoAnalisis" in _js()
    assert "renderUltimoAnalisis(regEntradas);" in _js()


def test_graficos_svg_legibles_sobre_blanco():
    js = _js()
    assert 'fill="#172A44"' in js
    assert 'stroke="#E3EAF2"' in js
    assert "#E6EEF8" not in js
    assert "#1C3250" not in js
    assert "#157F45" in js and "#2FBF71" not in js


def test_pagina_incluye_el_css_y_el_panel_nuevo():
    pagina = ws._cargar_pagina()
    assert "--sidebar: #0B1F3A" in pagina
    assert 'id="panelUltimo"' in pagina
    assert "Último análisis" in pagina
