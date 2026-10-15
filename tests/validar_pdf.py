# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Validador estructural de PDF (solo biblioteca estandar).

Comprueba, sin dependencias externas:
  - cabecera ``%PDF-`` y final ``%%EOF``;
  - cada offset de la tabla ``xref`` apunta exactamente al inicio de ``N G obj``;
  - ``startxref`` apunta a la tabla ``xref``;
  - el ``trailer`` tiene ``/Size`` y ``/Root`` correctos;
  - cada stream tiene ``/Length`` igual a su longitud real (sin bytes de mas);
  - los objetos referenciados (``N 0 R``) existen;
  - los objetos de pagina/catalogo tienen el tipo esperado.

Uso:
    python -X utf8 tests\\validar_pdf.py archivo.pdf
    from validar_pdf import validar_pdf
    errores = validar_pdf(data_bytes)
"""

import re
import sys

_OBJ = re.compile(rb"(?m)^(\d+) 0 obj\b")
_REF = re.compile(rb"(\d+) 0 R")


def _offsets_objetos(data: bytes) -> dict[int, int]:
    return {int(m.group(1)): m.start() for m in _OBJ.finditer(data)}


def _cuerpo_sin_stream(region: bytes) -> bytes:
    """Parte del objeto antes de ``stream`` (diccionario), para leer referencias."""
    p = region.find(b"stream")
    return region if p == -1 else region[:p]


def validar_pdf(data: bytes) -> list[str]:
    """Devuelve la lista de errores estructurales (vacia si el PDF es valido)."""
    errores: list[str] = []

    if not data.startswith(b"%PDF-"):
        return ["cabecera: el archivo no empieza con '%PDF-'"]
    if not data.rstrip().endswith(b"%%EOF"):
        errores.append("final: el archivo no termina con '%%EOF'")

    objs = _offsets_objetos(data)
    if not objs:
        return errores + ["objetos: no se encontro ningun objeto 'N 0 obj'"]

    # --- startxref -> tabla xref ---
    p = data.rfind(b"startxref")
    if p == -1:
        return errores + ["startxref: no encontrado"]
    mnum = re.match(rb"startxref\s+(\d+)\s+%%EOF", data[p:])
    if not mnum:
        return errores + ["startxref: formato invalido"]
    xref_pos = int(mnum.group(1))
    if data[xref_pos:xref_pos + 4] != b"xref":
        errores.append(
            f"startxref: apunta a {xref_pos}, pero alli no esta 'xref' "
            f"(se leyo {data[xref_pos:xref_pos + 8]!r})")

    # --- tabla xref ---
    pos = xref_pos
    count = 0
    entradas: list[tuple[int, int, bytes]] = []
    if data[pos:pos + 4] == b"xref":
        pos += 4
        while data[pos:pos + 1] in (b"\r", b"\n"):
            pos += 1
        fin_encabezado = data.find(b"\n", pos)
        encabezado = data[pos:fin_encabezado].strip()
        partes = encabezado.split()
        if len(partes) != 2 or not partes[1].isdigit():
            errores.append(f"xref: encabezado de subseccion invalido {encabezado!r}")
        else:
            count = int(partes[1])
            pos = fin_encabezado + 1
            for i in range(count):
                entrada = data[pos:pos + 20]
                pos += 20
                m = re.match(rb"^(\d{10}) (\d{5}) ([nf])\s\s$", entrada)
                if not m:
                    errores.append(f"xref: entrada {i} con formato invalido {entrada!r}")
                    entradas.append((0, 0, b"?"))
                    continue
                entradas.append((int(m.group(1)), int(m.group(2)), m.group(3)))
            # objeto libre 0
            if entradas and entradas[0][2] != b"f":
                errores.append("xref: la entrada 0 deberia ser libre ('f')")
            for i in range(1, count):
                off, gen, tipo = entradas[i]
                if tipo != b"n":
                    continue
                esperado = objs.get(i)
                if esperado is None:
                    errores.append(f"xref: la entrada {i} es 'n' pero el objeto no existe")
                elif off != esperado:
                    errores.append(
                        f"xref: la entrada {i} apunta a {off}, pero 'N G obj' esta en {esperado}")
                if data[off:off + 4] == b"" or not data[off:off + 16].startswith(f"{i} 0 obj".encode()):
                    errores.append(
                        f"xref: la entrada {i} (offset {off}) no apunta a '{i} 0 obj' "
                        f"(se leyo {data[off:off + 12]!r})")

    # --- trailer ---
    ptrailer = data.find(b"trailer", pos)
    trailer = b""
    if ptrailer == -1:
        errores.append("trailer: no encontrado")
    else:
        pfin = data.find(b"startxref", ptrailer)
        trailer = data[ptrailer:pfin if pfin != -1 else len(data)]
        msize = re.search(rb"/Size\s+(\d+)", trailer)
        mroot = re.search(rb"/Root\s+(\d+)\s+0\s+R", trailer)
        if not msize:
            errores.append("trailer: falta /Size")
        elif count and int(msize.group(1)) != count:
            errores.append(f"trailer: /Size={msize.group(1)} no coincide con el xref ({count})")
        if not mroot:
            errores.append("trailer: falta /Root")
        else:
            root = int(mroot.group(1))
            if root not in objs:
                errores.append(f"trailer: /Root apunta a objeto inexistente {root}")

    # --- streams: /Length real ---
    offs = sorted(objs.items(), key=lambda kv: kv[1])
    for idx, (num, off) in enumerate(offs):
        fin = offs[idx + 1][1] if idx + 1 < len(offs) else (xref_pos if xref_pos > off else len(data))
        region = data[off:fin]
        if b"stream" not in region:
            continue
        pstream = region.find(b"stream")
        # tras la palabra 'stream' debe venir CRLF o LF
        q = pstream + len(b"stream")
        if region[q:q + 2] == b"\r\n":
            q += 2
        elif region[q:q + 1] == b"\n":
            q += 1
        elif region[q:q + 1] == b"\r":
            q += 1
        else:
            errores.append(f"objeto {num}: 'stream' sin fin de linea")
            continue
        mlen = re.search(rb"/Length\s+(\d+)", region[:pstream])
        if not mlen:
            errores.append(f"objeto {num}: stream sin /Length")
            continue
        largo = int(mlen.group(1))
        datos_stream = region[q:q + largo]
        despues = region[q + largo:q + largo + 12]
        if not (despues.startswith(b"\nendstream") or despues.startswith(b"\r\nendstream")
                or despues.startswith(b"endstream")):
            errores.append(
                f"objeto {num}: /Length={largo} no coincide con el stream real "
                f"(despues de {largo} bytes hay {despues!r})")
        elif b"endstream" not in despues:
            errores.append(f"objeto {num}: falta 'endstream'")

    # --- referencias existentes ---
    for num, off in offs:
        region = _cuerpo_sin_stream(data[off:(offs and data.find(b"endobj", off) + 6) or len(data)])
        for m in _REF.finditer(region):
            ref = int(m.group(1))
            if ref not in objs:
                errores.append(f"objeto {num}: referencia a objeto inexistente {ref} 0 R")
    if trailer:
        for m in _REF.finditer(trailer):
            ref = int(m.group(1))
            if ref not in objs:
                errores.append(f"trailer: referencia a objeto inexistente {ref} 0 R")

    # --- tipos de objeto ---
    def cuerpo(num: int) -> bytes:
        off = objs[num]
        fin = data.find(b"endobj", off)
        return data[off:fin if fin != -1 else off + 500]

    if trailer:
        mroot = re.search(rb"/Root\s+(\d+)\s+0\s+R", trailer)
        if mroot and int(mroot.group(1)) in objs:
            root = int(mroot.group(1))
            if b"/Type /Catalog" not in cuerpo(root):
                errores.append(f"objeto {root} (/Root) no es /Type /Catalog")
            mpages = re.search(rb"/Pages\s+(\d+)\s+0\s+R", cuerpo(root))
            if mpages and int(mpages.group(1)) in objs:
                pages = int(mpages.group(1))
                cpages = cuerpo(pages)
                if b"/Type /Pages" not in cpages:
                    errores.append(f"objeto {pages} (/Pages) no es /Type /Pages")
                mkids = re.search(rb"/Kids\s*\[([^\]]*)\]", cpages)
                if not mkids:
                    errores.append(f"objeto {pages} (/Pages) sin /Kids")
                else:
                    for m in _REF.finditer(mkids.group(1)):
                        kid = int(m.group(1))
                        if kid not in objs:
                            errores.append(f"/Kids referencia objeto inexistente {kid} 0 R")
                        elif b"/Type /Page" not in cuerpo(kid):
                            errores.append(f"objeto {kid} en /Kids no es /Type /Page")
                        else:
                            mc = re.search(rb"/Contents\s+(\d+)\s+0\s+R", cuerpo(kid))
                            if not mc:
                                errores.append(f"objeto {kid} (/Page) sin /Contents")
                            elif int(mc.group(1)) not in objs:
                                errores.append(
                                    f"objeto {kid} (/Page): /Contents {mc.group(1).decode()} 0 R inexistente")
                            elif b"stream" not in cuerpo(int(mc.group(1))):
                                errores.append(
                                    f"objeto {kid} (/Page): /Contents {mc.group(1).decode()} no es un stream")
            else:
                errores.append("catalogo: /Pages ausente o inexistente")

    return errores


def validar_archivo(ruta: str) -> list[str]:
    with open(ruta, "rb") as fh:
        return validar_pdf(fh.read())


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("uso: python validar_pdf.py archivo.pdf [archivo2.pdf ...]")
        return 2
    fallo = 0
    for ruta in argv[1:]:
        errs = validar_archivo(ruta)
        if errs:
            fallo = 1
            print(f"[INVALIDO] {ruta}")
            for e in errs:
                print(f"    - {e}")
        else:
            print(f"[OK] {ruta}")
    return fallo


if __name__ == "__main__":
    sys.exit(main(sys.argv))
