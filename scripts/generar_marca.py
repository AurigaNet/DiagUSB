# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Genera los recursos de marca del instalador y del ejecutable."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "assets" / "branding"
ESCALA = 2

AZUL_CLARO = (53, 199, 255, 255)
AZUL = (34, 139, 246, 255)
AZUL_OSCURO = (10, 57, 150, 255)
FONDO = (10, 20, 36, 255)
TEXTO = (230, 238, 248, 255)
SECUNDARIO = (159, 179, 203, 255)

FUENTE_SEMIBOLD = Path(r"C:\Windows\Fonts\seguisb.ttf")
FUENTE_NORMAL = Path(r"C:\Windows\Fonts\segoeui.ttf")
FUENTE_MONO = Path(r"C:\Windows\Fonts\consola.ttf")


def fuente(ruta: Path, tamano: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(ruta), tamano)


def gradiente_vertical(tamano: tuple[int, int], arriba: tuple[int, int, int],
                       abajo: tuple[int, int, int]) -> Image.Image:
    ancho, alto = tamano
    img = Image.new("RGBA", tamano)
    px = img.load()
    for y in range(alto):
        t = y / max(1, alto - 1)
        color = tuple(round(arriba[i] + (abajo[i] - arriba[i]) * t) for i in range(3))
        for x in range(ancho):
            px[x, y] = (*color, 255)
    return img


def crear_icono() -> Image.Image:
    lado = 1024 * ESCALA
    icono = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))

    mascara = Image.new("L", (lado, lado), 0)
    ImageDraw.Draw(mascara).rounded_rectangle(
        (54 * ESCALA, 54 * ESCALA, lado - 54 * ESCALA, lado - 54 * ESCALA),
        radius=230 * ESCALA, fill=255)

    base = gradiente_vertical((lado, lado), (38, 143, 255), (9, 48, 133)).convert("RGBA")

    brillo = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    bd = ImageDraw.Draw(brillo)
    bd.ellipse((-260 * ESCALA, -330 * ESCALA, 900 * ESCALA, 660 * ESCALA),
               fill=(120, 205, 255, 60))
    brillo = brillo.filter(ImageFilter.GaussianBlur(150 * ESCALA))
    base = Image.alpha_composite(base, brillo)

    icono.paste(base, (0, 0), mascara)

    borde = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    ImageDraw.Draw(borde).rounded_rectangle(
        (56 * ESCALA, 56 * ESCALA, lado - 56 * ESCALA, lado - 56 * ESCALA),
        radius=228 * ESCALA, outline=(126, 202, 255, 120), width=4 * ESCALA)
    icono = Image.alpha_composite(icono, borde)

    usb = Image.new("RGBA", (1500, 1500), (0, 0, 0, 0))
    ud = ImageDraw.Draw(usb)

    ud.rounded_rectangle((525, 430, 975, 1180), radius=105,
                         fill=(255, 255, 255, 255),
                         outline=(163, 222, 255, 255), width=6)
    ud.rounded_rectangle((585, 1120, 915, 1290), radius=52,
                         fill=(228, 244, 255, 255))
    ud.rounded_rectangle((585, 1180, 915, 1290), radius=52,
                         fill=(12, 74, 173, 255))
    for x in (645, 735, 825):
        ud.rounded_rectangle((x, 1205, x + 44, 1262), radius=12,
                             fill=(122, 213, 255, 255))

    ud.line([(585, 845), (655, 845), (700, 760), (760, 955), (815, 845), (925, 845)],
            fill=(28, 140, 255, 255), width=30, joint="curve")
    ud.line([(585, 845), (655, 845), (700, 760), (760, 955), (815, 845), (925, 845)],
            fill=(87, 201, 255, 255), width=13, joint="curve")

    ud.rounded_rectangle((628, 500, 872, 590), radius=34,
                         fill=(232, 247, 255, 255))
    ud.rounded_rectangle((628, 500, 872, 528), radius=24,
                         fill=(255, 255, 255, 255))

    usb = usb.rotate(-31, resample=Image.Resampling.BICUBIC, expand=True)
    caja = usb.getbbox()
    if caja:
        usb = usb.crop(caja)
    objetivo = int(lado * 0.67)
    usb.thumbnail((objetivo, objetivo), Image.Resampling.LANCZOS)

    sombra = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    sx = (lado - usb.width) // 2
    sy = (lado - usb.height) // 2 + 18 * ESCALA
    sombra.paste((4, 18, 48, 170), (sx + 10 * ESCALA, sy + 14 * ESCALA), usb)
    sombra = sombra.filter(ImageFilter.GaussianBlur(28 * ESCALA))
    icono = Image.alpha_composite(icono, sombra)
    icono.alpha_composite(usb, (sx, sy))

    return icono.resize((1024, 1024), Image.Resampling.LANCZOS)


def texto_con_espaciado(draw: ImageDraw.ImageDraw, xy: tuple[int, int], texto: str,
                        font: ImageFont.FreeTypeFont, relleno, espacio: int) -> int:
    x, y = xy
    for ch in texto:
        draw.text((x, y), ch, font=font, fill=relleno)
        x += int(draw.textlength(ch, font=font)) + espacio
    return x


def crear_logo(icono: Image.Image) -> Image.Image:
    logo = Image.new("RGBA", (1800, 520), (0, 0, 0, 0))
    icono_logo = icono.resize((360, 360), Image.Resampling.LANCZOS)
    logo.alpha_composite(icono_logo, (58, 80))

    d = ImageDraw.Draw(logo)
    f_word = fuente(FUENTE_SEMIBOLD, 154)
    f_sub = fuente(FUENTE_SEMIBOLD, 35)
    f_tag = fuente(FUENTE_NORMAL, 30)

    x = 470
    y = 82
    d.text((x, y), "Diag", font=f_word, fill=TEXTO)
    x += int(d.textlength("Diag", font=f_word)) - 4
    d.text((x, y), "USB", font=f_word, fill=AZUL_CLARO)

    texto_con_espaciado(d, (478, 278), "DIAGNÓSTICO TÉCNICO", f_sub, SECUNDARIO, 6)

    d.rounded_rectangle((478, 342, 1110, 349), radius=4, fill=(34, 139, 246, 180))
    d.ellipse((1118, 338, 1132, 352), fill=AZUL_CLARO)
    d.text((478, 378), "Herramienta portable para soporte informático", font=f_tag,
           fill=(122, 164, 207, 255))
    return logo


def crear_wizard(icono: Image.Image) -> None:
    ancho, alto = 164 * ESCALA, 314 * ESCALA
    img = gradiente_vertical((ancho, alto), (7, 17, 32), (11, 41, 76)).convert("RGBA")

    glow = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-110 * ESCALA, -130 * ESCALA, 230 * ESCALA, 180 * ESCALA),
               fill=(23, 105, 210, 125))
    gd.ellipse((40 * ESCALA, 210 * ESCALA, 260 * ESCALA, 430 * ESCALA),
               fill=(34, 184, 240, 35))
    glow = glow.filter(ImageFilter.GaussianBlur(55 * ESCALA))
    img = Image.alpha_composite(img, glow)

    d = ImageDraw.Draw(img)
    d.line((0, 0, 0, alto), fill=(8, 23, 43, 255), width=3 * ESCALA)

    tam_icono = 210
    ic = icono.resize((tam_icono, tam_icono), Image.Resampling.LANCZOS)
    ix = (ancho - tam_icono) // 2
    iy = 46 * ESCALA
    img.alpha_composite(ic, (ix, iy))

    f_titulo = fuente(FUENTE_SEMIBOLD, 45)
    f_sub = fuente(FUENTE_SEMIBOLD, 19)
    f_peq = fuente(FUENTE_NORMAL, 17)
    f_version = fuente(FUENTE_MONO, 16)

    titulo = "DiagUSB"
    tx = (ancho - d.textlength(titulo, font=f_titulo)) // 2
    d.text((tx, 154 * ESCALA), titulo, font=f_titulo, fill=(242, 248, 255, 255))

    sub = "DIAGNÓSTICO"
    sx = (ancho - int(d.textlength(sub, font=f_sub) + 5 * (len(sub) - 1))) // 2
    texto_con_espaciado(d, (sx, 204 * ESCALA), sub, f_sub, (83, 199, 255, 255), 5)

    d.rounded_rectangle((38 * ESCALA, 236 * ESCALA, 126 * ESCALA, 238 * ESCALA),
                        radius=2, fill=(34, 139, 246, 130))

    lineas = ["Soporte técnico", "Windows 10 / 11"]
    for i, linea in enumerate(lineas):
        lx = (ancho - d.textlength(linea, font=f_peq)) // 2
        d.text((lx, (250 + i * 19) * ESCALA), linea, font=f_peq, fill=(159, 179, 203, 255))

    ver = "v0.1.0"
    vx = (ancho - d.textlength(ver, font=f_version)) // 2
    d.text((vx, 292 * ESCALA - 8), ver, font=f_version, fill=(91, 132, 174, 255))

    img.convert("RGB").resize((164, 314), Image.Resampling.LANCZOS).save(
        SALIDA / "wizard.bmp", format="BMP")

    pequeno = Image.new("RGB", (110, 110), (10, 20, 36))
    ic = icono.resize((96, 96), Image.Resampling.LANCZOS)
    pequeno.paste(ic, (7, 7), ic)
    pequeno.resize((55, 55), Image.Resampling.LANCZOS).save(
        SALIDA / "wizard-small.bmp", format="BMP")


def main() -> int:
    SALIDA.mkdir(parents=True, exist_ok=True)
    icono = crear_icono()
    icono.save(SALIDA / "icono.png", format="PNG")
    icono.save(SALIDA / "diagusb.ico", format="ICO",
               sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                      (128, 128), (256, 256)])
    logo = crear_logo(icono)
    logo.save(SALIDA / "logo_horizontal.png", format="PNG")
    crear_wizard(icono)

    for nombre in ("icono.png", "logo_horizontal.png", "diagusb.ico",
                   "wizard.bmp", "wizard-small.bmp"):
        ruta = SALIDA / nombre
        print(f"{nombre}: {ruta.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
