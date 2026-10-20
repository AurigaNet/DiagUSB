# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Rasterizador PNG minimo para los informes DiagUSB (solo biblioteca estandar).

No hay dependencias: los graficos se dibujan sobre un lienzo RGB en memoria con
supersampling (se dibuja en grande y se reduce) para lograr bordes suavizados, y
se empaquetan con el escritor PNG basado en ``zlib`` y ``struct`` (los mismos
que usa la biblioteca estandar). Las tortas, donas y barras comparten el mismo
calculo de angulos y la misma paleta que los informes vectoriales.
"""

import math
import struct
import zlib

from .graficos import rgb_de


def _color255(color) -> tuple:
    """RGB 0..255 a partir de un nombre de paleta, hex o tupla (0..1 o 0..255)."""
    if isinstance(color, tuple):
        if all(v <= 1.0 for v in color):
            return tuple(int(round(v * 255)) for v in color)
        return tuple(int(v) for v in color)
    r, g, b = rgb_de(color)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


def _chunk(tipo: bytes, datos: bytes) -> bytes:
    return (struct.pack(">I", len(datos)) + tipo + datos
            + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF))


def escribir_png(ancho: int, alto: int, pixeles) -> bytes:
    """Arma un PNG RGB (8 bits) a partir de un buffer ``bytearray`` de w*h*3."""
    filas = bytearray()
    paso = ancho * 3
    for y in range(alto):
        filas.append(0)
        filas += pixeles[y * paso:(y + 1) * paso]
    ihdr = struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(filas), 9))
            + _chunk(b"IEND", b""))


class Lienzo:
    """Lienzo RGB con supersampling. Coordenadas enteras en el lienzo reducido."""

    def __init__(self, ancho: int, alto: int, fondo=(255, 255, 255), escala: int = 4):
        self.ancho = ancho
        self.alto = alto
        self.escala = escala
        self._w = ancho * escala
        self._h = alto * escala
        self._buf = bytearray(fondo * (self._w * self._h))

    def _pinta(self, x: int, y: int, color) -> None:
        if 0 <= x < self._w and 0 <= y < self._h:
            i = (y * self._w + x) * 3
            self._buf[i] = color[0]
            self._buf[i + 1] = color[1]
            self._buf[i + 2] = color[2]

    def rectangulo(self, x: float, y: float, w: float, h: float, color) -> None:
        c = _color255(color)
        s = self.escala
        for yy in range(int(y * s), int((y + h) * s)):
            for xx in range(int(x * s), int((x + w) * s)):
                self._pinta(xx, yy, c)

    def sector(self, cx: float, cy: float, r: float, a0: float, a1: float,
               color, r_interno: float = 0.0) -> None:
        """Porcion de torta/dona. Angulos en grados: 0 = 12 en punto, horario."""
        c = _color255(color)
        s = self.escala
        completo = (a1 - a0) >= 359.9
        cx_s, cy_s, r_s = cx * s, cy * s, r * s
        r_in_s = r_interno * s
        x0 = max(0, int(cx_s - r_s) - 1)
        x1 = min(self._w, int(cx_s + r_s) + 2)
        y0 = max(0, int(cy_s - r_s) - 1)
        y1 = min(self._h, int(cy_s + r_s) + 2)
        for yy in range(y0, y1):
            dy = yy + 0.5 - cy_s
            for xx in range(x0, x1):
                dx = xx + 0.5 - cx_s
                rad = (dx * dx + dy * dy) ** 0.5
                if rad > r_s or rad < r_in_s:
                    continue
                if completo:
                    self._pinta(xx, yy, c)
                    continue
                ang = math.degrees(math.atan2(dx, -dy)) % 360.0
                if a0 <= ang < a1:
                    self._pinta(xx, yy, c)

    def a_png(self) -> bytes:
        e = self.escala
        salida = bytearray(self.ancho * self.alto * 3)
        for y in range(self.alto):
            for x in range(self.ancho):
                r = g = b = 0
                for dy in range(e):
                    base = ((y * e + dy) * self._w + x * e) * 3
                    for dx in range(e):
                        i = base + dx * 3
                        r += self._buf[i]
                        g += self._buf[i + 1]
                        b += self._buf[i + 2]
                n = e * e
                j = (y * self.ancho + x) * 3
                salida[j] = r // n
                salida[j + 1] = g // n
                salida[j + 2] = b // n
        return escribir_png(self.ancho, self.alto, salida)


def _porciones_graficables(porciones_):
    return [p for p in porciones_ if p["a1"] - p["a0"] > 0.01]


def imagen_torta(porciones_, tam: int = 220, fondo=(255, 255, 255)) -> bytes:
    """PNG cuadrado con la torta (contorno blanco entre porciones)."""
    l = Lienzo(tam, tam, fondo)
    cx = cy = tam / 2
    r = tam / 2 - 4
    for p in _porciones_graficables(porciones_):
        l.sector(cx, cy, r, p["a0"], p["a1"], p["color"])
    # separadores blancos: se rellenan por el borde de cada porcion
    return l.a_png()


def imagen_dona(porciones_, tam: int = 220, grosor: float = 0.34,
                fondo=(255, 255, 255), color_centro=(255, 255, 255)) -> bytes:
    """PNG cuadrado con la dona; el agujero central queda del color de fondo."""
    l = Lienzo(tam, tam, color_centro)
    cx = cy = tam / 2
    r = tam / 2 - 4
    r_in = r * (1 - grosor)
    for p in _porciones_graficables(porciones_):
        l.sector(cx, cy, r, p["a0"], p["a1"], p["color"], r_interno=r_in)
    return l.a_png()


def imagen_barra(pct: float, color, ancho: int = 560, alto: int = 26,
                 fondo=(224, 227, 231), pista=(224, 227, 231)) -> bytes:
    """PNG de una barra de progreso horizontal (0..100)."""
    l = Lienzo(ancho, alto, fondo)
    l.rectangulo(0, 0, ancho, alto, pista)
    pct = max(0.0, min(100.0, float(pct or 0)))
    l.rectangulo(0, 0, ancho * pct / 100.0, alto, color)
    return l.a_png()
