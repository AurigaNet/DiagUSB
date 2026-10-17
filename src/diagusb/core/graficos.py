# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Graficos vectoriales para los informes DiagUSB.

Sin dependencias externas: calcula porciones, angulos, camina arcos en Bezier
y arma el SVG en linea. El mismo calculo de angulos alimenta al motor PDF, de
modo que ambos formatos dibujan exactamente los mismos datos.
"""

import math

# Paleta unica del documento. Cada entrada: (hex, rgb 0..1).
PALETA = {
    "critico": ("#C62839", (0.776, 0.157, 0.224)),
    "error": ("#E8590C", (0.910, 0.349, 0.047)),
    "advertencia": ("#F5A623", (0.961, 0.651, 0.137)),
    "ok": ("#2FBF71", (0.184, 0.749, 0.443)),
    "sin_datos": ("#8A99AD", (0.541, 0.600, 0.678)),
    "no_evaluado": ("#9FB3CB", (0.624, 0.702, 0.796)),
    "acento": ("#1769D2", (0.090, 0.412, 0.824)),
    "tinta": ("#0F1F35", (0.059, 0.122, 0.208)),
    "ambar": ("#F5A623", (0.961, 0.651, 0.137)),
    "rojo": ("#EF4B5B", (0.937, 0.294, 0.357)),
    "verde": ("#2FBF71", (0.184, 0.749, 0.443)),
    "gris": ("#8A99AD", (0.541, 0.600, 0.678)),
    "resto": ("#E3E7EC", (0.890, 0.906, 0.925)),
}

# Colores para porciones genericas (paquetes, discos, "Otros", etc.).
CAT_PALETA = ("#1769D2", "#2FBF71", "#F5A623", "#E8590C", "#8A99AD",
              "#9B59B6", "#0E9AA7", "#D6336C")

_SVG_ESC = {"&": "&amp;", "<": "&lt;", ">": "&gt;",
            '"': "&quot;", "'": "&#39;"}


def esc(texto) -> str:
    return "".join(_SVG_ESC.get(c, c) for c in str("" if texto is None else texto))


def rgb_de(color) -> tuple:
    """RGB 0..1 a partir de un nombre de PALETA o de un hex '#rrggbb'."""
    if isinstance(color, tuple):
        return color
    if color in PALETA:
        return PALETA[color][1]
    h = (color or "").lstrip("#")
    if len(h) == 6:
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (0.5, 0.5, 0.5)


def porciones(items, maximo: int = 6, etiqueta_otros: str = "Otros") -> list[dict]:
    """Convierte ``(etiqueta, valor, color)`` en porciones con % y angulos.

    - Se descartan valores <= 0.
    - Si hay mas de ``maximo`` porciones se conservan las mayores y el resto
      se agrega en una sola porcion ``etiqueta_otros``.
    - Los angulos se reparten en 360 grados empezando a las 12 en punto.
    """
    validos = [(str(e), float(v), c) for e, v, c in items
               if isinstance(v, (int, float)) and v > 0]
    if not validos:
        return []
    validos.sort(key=lambda x: x[1], reverse=True)
    if len(validos) > maximo:
        cabeza = validos[:maximo - 1]
        resto = sum(v for _, v, _ in validos[maximo - 1:])
        cabeza.append((etiqueta_otros, resto, PALETA["gris"][0]))
        validos = cabeza
    total = sum(v for _, v, _ in validos) or 1.0
    salida = []
    ang = 0.0
    for etiqueta, valor, color in validos:
        porcion_ang = valor / total * 360.0
        salida.append({
            "etiqueta": etiqueta,
            "valor": valor,
            "porcentaje": round(valor / total * 100.0, 1),
            "color": color,
            "a0": ang,
            "a1": ang + porcion_ang,
        })
        ang += porcion_ang
    return salida


def porciones_simples(items) -> list[dict]:
    """Porciones SIN reordenar ni agrupar (para 'usado vs libre' y similares).

    Conserva el orden y el color de cada item; solo calcula % y angulos.
    """
    validos = [(str(e), float(v), c) for e, v, c in items
               if isinstance(v, (int, float)) and v >= 0]
    total = sum(v for _, v, _ in validos) or 1.0
    salida = []
    ang = 0.0
    for etiqueta, valor, color in validos:
        porcion = valor / total * 360.0
        salida.append({
            "etiqueta": etiqueta,
            "valor": valor,
            "porcentaje": round(valor / total * 100.0, 1),
            "color": color,
            "a0": ang,
            "a1": ang + porcion,
        })
        ang += porcion
    return salida


def _punto(cx, cy, r, ang_grados):
    """Punto del circulo (SVG, y hacia abajo). 0 grados = 12 en punto."""
    rad = math.radians(ang_grados)
    return (cx + r * math.sin(rad), cy - r * math.cos(rad))


def _arco_svg(cx, cy, r, a0, a1):
    x0, y0 = _punto(cx, cy, r, a0)
    x1, y1 = _punto(cx, cy, r, a1)
    grande = 1 if (a1 - a0) > 180 else 0
    return f"A {r:.2f} {r:.2f} 0 {grande} 1 {x1:.2f} {y1:.2f}"


def camino_sector_svg(cx, cy, r, a0, a1, r_interno: float = 0.0) -> str:
    """Path SVG de una porcion de torta o de dona (angulos en grados)."""
    if a1 - a0 >= 359.99:
        if r_interno > 0:
            return (f"M {cx + r_interno:.2f} {cy:.2f} "
                    f"A {r_interno:.2f} {r_interno:.2f} 0 1 0 "
                    f"{cx - r_interno:.2f} {cy:.2f} "
                    f"A {r_interno:.2f} {r_interno:.2f} 0 1 0 "
                    f"{cx + r_interno:.2f} {cy:.2f} Z "
                    f"M {cx + r:.2f} {cy:.2f} "
                    f"A {r:.2f} {r:.2f} 0 1 0 {cx - r:.2f} {cy:.2f} "
                    f"A {r:.2f} {r:.2f} 0 1 0 {cx + r:.2f} {cy:.2f} Z")
        return (f"M {cx + r:.2f} {cy:.2f} "
                f"A {r:.2f} {r:.2f} 0 1 0 {cx - r:.2f} {cy:.2f} "
                f"A {r:.2f} {r:.2f} 0 1 0 {cx + r:.2f} {cy:.2f} Z")
    x0, y0 = _punto(cx, cy, r, a0)
    if r_interno > 0:
        xi1, yi1 = _punto(cx, cy, r_interno, a1)
        xi0, yi0 = _punto(cx, cy, r_interno, a0)
        grande = 1 if (a1 - a0) > 180 else 0
        return (f"M {x0:.2f} {y0:.2f} {_arco_svg(cx, cy, r, a0, a1)} "
                f"L {xi1:.2f} {yi1:.2f} "
                f"A {r_interno:.2f} {r_interno:.2f} 0 {grande} 0 "
                f"{xi0:.2f} {yi0:.2f} Z")
    return (f"M {cx:.2f} {cy:.2f} L {x0:.2f} {y0:.2f} "
            f"{_arco_svg(cx, cy, r, a0, a1)} Z")


def _leyenda_svg(porciones_, x, y, ancho: float, tam: float = 11.0) -> str:
    filas = []
    for i, p in enumerate(porciones_):
        fy = y + i * (tam + 6)
        filas.append(
            f"<rect x='{x:.1f}' y='{fy - tam + 1:.1f}' width='{tam:.1f}' "
            f"height='{tam:.1f}' rx='2' fill='{p['color']}'/>"
            f"<text x='{x + tam + 6:.1f}' y='{fy:.1f}' "
            f"font-family='Arial, sans-serif' font-size='11' fill='#333'>"
            f"{esc(p['etiqueta'])}: {p['valor']:g} ({p['porcentaje']:g}%)</text>")
    return "".join(filas)


def svg_torta(porciones_, diametro: float = 200, titulo: str = "",
              leyenda: bool = True) -> str:
    """SVG completo de una torta con leyenda (max 6 porciones)."""
    if not porciones_:
        return _svg_vacio(diametro, titulo, "Sin datos")
    ancho = diametro + (240 if leyenda else 16)
    alto = max(diametro + 24, len(porciones_) * 17 + 24)
    cx = 12 + diametro / 2
    cy = alto / 2
    r = diametro / 2
    partes = [f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 "
              f"{ancho:.0f} {alto:.0f}' width='100%' role='img'>"]
    if titulo:
        partes.append(f"<title>{esc(titulo)}</title>")
    for p in porciones_:
        partes.append(f"<path d='{camino_sector_svg(cx, cy, r, p['a0'], p['a1'])}' "
                      f"fill='{p['color']}' stroke='#ffffff' stroke-width='1.5'/>")
    if leyenda:
        partes.append(_leyenda_svg(porciones_, 12 + diametro + 12, 26, ancho))
    partes.append("</svg>")
    return "".join(partes)


def svg_dona(porciones_, diametro: float = 200, grosor: float = 46,
             titulo: str = "", leyenda: bool = True, centro: str = "") -> str:
    """SVG completo de una dona con leyenda y texto central opcional."""
    if not porciones_:
        return _svg_vacio(diametro, titulo, "Sin datos")
    ancho = diametro + (240 if leyenda else 16)
    alto = max(diametro + 24, len(porciones_) * 17 + 24)
    cx = 12 + diametro / 2
    cy = alto / 2
    r = diametro / 2
    r_in = max(0.0, r - grosor)
    partes = [f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 "
              f"{ancho:.0f} {alto:.0f}' width='100%' role='img'>"]
    if titulo:
        partes.append(f"<title>{esc(titulo)}</title>")
    for p in porciones_:
        partes.append(
            f"<path d='{camino_sector_svg(cx, cy, r, p['a0'], p['a1'], r_in)}' "
            f"fill='{p['color']}' stroke='#ffffff' stroke-width='1.5'/>")
    if centro:
        partes.append(f"<text x='{cx:.1f}' y='{cy + 5:.1f}' text-anchor='middle' "
                      f"font-family='Arial, sans-serif' font-size='18' "
                      f"font-weight='700' fill='#0F1F35'>{esc(centro)}</text>")
    if leyenda:
        partes.append(_leyenda_svg(porciones_, 12 + diametro + 12, 26, ancho))
    partes.append("</svg>")
    return "".join(partes)


def _svg_vacio(diametro, titulo, texto):
    ancho = diametro + 16
    alto = diametro + 24
    return (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {ancho:.0f} "
            f"{alto:.0f}' width='100%' role='img'>"
            f"<title>{esc(titulo)}</title>"
            f"<rect x='8' y='10' width='{diametro:.0f}' height='{diametro:.0f}' "
            f"rx='8' fill='#eef1f5'/>"
            f"<text x='{ancho / 2:.0f}' y='{alto / 2:.0f}' text-anchor='middle' "
            f"font-family='Arial, sans-serif' font-size='13' fill='#8A99AD'>"
            f"{esc(texto)}</text></svg>")


def arcos_bezier(cx, cy, r, a0, a1):
    """Segmentos Bezier cubicos que aproximan el arco (para el motor PDF).

    Usa la convencion del PDF (y hacia arriba, 0 grados = 12 en punto) y
    devuelve ``[(p0, c1, c2, p1), ...]`` con cada tramo <= 90 grados.
    """
    def punto_pdf(ang):
        rad = math.radians(ang)
        return (cx + r * math.sin(rad), cy + r * math.cos(rad))

    tramos = []
    total = a1 - a0
    if total <= 0:
        return tramos
    n = max(1, int(math.ceil(abs(total) / 90.0)))
    paso = total / n
    for i in range(n):
        b0 = a0 + i * paso
        b1 = b0 + paso
        p0 = punto_pdf(b0)
        p3 = punto_pdf(b1)
        k = 4.0 / 3.0 * math.tan(math.radians(paso) / 4.0) * r
        r0 = math.radians(b0)
        r1 = math.radians(b1)
        t0 = (math.cos(r0), -math.sin(r0))
        t1 = (math.cos(r1), -math.sin(r1))
        c1 = (p0[0] + k * t0[0], p0[1] + k * t0[1])
        c2 = (p3[0] - k * t1[0], p3[1] - k * t1[1])
        tramos.append((p0, c1, c2, p3))
    return tramos
