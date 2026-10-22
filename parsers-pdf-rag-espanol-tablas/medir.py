"""Convierte el corpus con cada parser y mide tiempo y memoria.

Cada repetición de cada parser corre en un proceso nuevo (importación en frío incluida
aparte), en orden intercalado: repetición 1 de todos, repetición 2 de todos, etc.
Antes de medir hay una pasada de calentamiento por parser que no cuenta (descarga
de modelos y cachés del sistema).

    python medir.py            # 5 repeticiones
    python medir.py --reps 7

Salida:
- salidas/<parser>/<pdf>.txt  texto extraído en la primera repetición medida
- resultados/tiempos.csv      una fila por parser, repetición y documento
- resultados/procesos.csv     una fila por parser y repetición (importación, total, memoria)
"""

import argparse
import csv
import hashlib
import json
import os
import resource
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(AQUI, "corpus")
SALIDAS = os.path.join(AQUI, "salidas")
RESULTADOS = os.path.join(AQUI, "resultados")
PARSERS = ["pypdf", "pdfplumber", "pymupdf", "pymupdf4llm", "markitdown", "docling"]


def cargar(nombre: str):
    """Devuelve una función ruta -> texto. La importación va aquí para medirla."""
    if nombre == "pypdf":
        from pypdf import PdfReader
        return lambda r: "\n".join(p.extract_text() or "" for p in PdfReader(r).pages)
    if nombre == "pdfplumber":
        import pdfplumber

        def f(r):
            with pdfplumber.open(r) as pdf:
                return "\n".join(p.extract_text() or "" for p in pdf.pages)
        return f
    if nombre == "pymupdf":
        import pymupdf

        def f(r):
            with pymupdf.open(r) as d:
                return "\n".join(p.get_text() for p in d)
        return f
    if nombre == "pymupdf4llm":
        import pymupdf4llm
        return lambda r: pymupdf4llm.to_markdown(r)
    if nombre == "markitdown":
        from markitdown import MarkItDown
        md = MarkItDown()
        return lambda r: md.convert(r).text_content
    if nombre == "docling":
        from docling.document_converter import DocumentConverter
        conv = DocumentConverter()  # configuración por defecto
        return lambda r: conv.convert(r).document.export_to_markdown()
    raise ValueError(nombre)


def trabajador(nombre: str, guardar: bool) -> None:
    t0 = time.perf_counter()
    convertir = cargar(nombre)
    t_import = time.perf_counter() - t0
    filas = []
    huellas = {}
    pdfs = sorted(a for a in os.listdir(CORPUS) if a.endswith(".pdf"))
    t1 = time.perf_counter()
    for pdf in pdfs:
        a = time.perf_counter()
        texto = convertir(os.path.join(CORPUS, pdf))
        filas.append({"pdf": pdf, "segundos": time.perf_counter() - a})
        huellas[pdf] = hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]
        if guardar:
            os.makedirs(os.path.join(SALIDAS, nombre), exist_ok=True)
            with open(os.path.join(SALIDAS, nombre, pdf[:-4] + ".txt"), "w", encoding="utf-8") as f:
                f.write(texto)
    total = time.perf_counter() - t1
    pico = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # bytes en macOS
    print(json.dumps({"import_s": t_import, "total_s": total, "pico_mb": pico / 2**20,
                      "docs": filas, "huellas": huellas}))


def lanzar(nombre: str, guardar: bool) -> dict:
    cmd = [sys.executable, __file__, "--trabajador", nombre] + (["--guardar"] if guardar else [])
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{nombre} falló:\n{p.stderr[-2000:]}")
    return json.loads(p.stdout.strip().splitlines()[-1])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--trabajador")
    ap.add_argument("--guardar", action="store_true")
    ap.add_argument("--parsers", default=",".join(PARSERS))
    a = ap.parse_args()
    if a.trabajador:
        trabajador(a.trabajador, a.guardar)
        return

    parsers = a.parsers.split(",")
    os.makedirs(RESULTADOS, exist_ok=True)
    for n in parsers:
        print(f"calentamiento {n}", flush=True)
        lanzar(n, guardar=False)
    tiempos, procesos, huellas = [], [], {}
    for rep in range(1, a.reps + 1):
        for n in parsers:
            r = lanzar(n, guardar=rep == 1)
            print(f"rep {rep} {n}: {r['total_s']:.2f} s, {r['pico_mb']:.0f} MB", flush=True)
            procesos.append({"parser": n, "rep": rep, "import_s": round(r["import_s"], 4),
                             "total_s": round(r["total_s"], 4), "pico_mb": round(r["pico_mb"], 1)})
            tiempos += [{"parser": n, "rep": rep, "pdf": d["pdf"], "segundos": round(d["segundos"], 5)}
                        for d in r["docs"]]
            huellas.setdefault(n, []).append(r["huellas"])
    with open(os.path.join(RESULTADOS, "tiempos.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["parser", "rep", "pdf", "segundos"])
        w.writeheader()
        w.writerows(tiempos)
    with open(os.path.join(RESULTADOS, "procesos.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["parser", "rep", "import_s", "total_s", "pico_mb"])
        w.writeheader()
        w.writerows(procesos)
    deterministas = {n: all(h == hs[0] for h in hs) for n, hs in huellas.items()}
    with open(os.path.join(RESULTADOS, "determinismo.json"), "w") as f:
        json.dump(deterministas, f, indent=1)
    print("salida idéntica en todas las repeticiones:", deterministas)


if __name__ == "__main__":
    main()
