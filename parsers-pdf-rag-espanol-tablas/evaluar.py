"""Compara el texto extraído con la referencia y resume tiempos y memoria.

Métricas de calidad (por parser y tipo de documento):
- parrafos_integros: % de párrafos de la referencia que aparecen enteros y seguidos en la salida.
- similitud: similitud de Levenshtein normalizada entre la referencia completa y la salida (0–100).
- orden: % de pares de párrafos consecutivos que salen en el orden correcto (si ambos aparecen).
- especiales: % de caracteres á é í ó ú ñ ü ¿ ¡ « » € de la referencia que conserva la salida
  en bruto (sin normalizar Unicode).
- celdas: % de celdas de concepto, precio unitario y total que aparecen en la salida.
- filas_completas: % de filas cuyo concepto, precio unitario y total salen en la misma línea y en orden.
- importes_juntos: % de filas cuyo precio unitario y total salen en la misma línea y en orden.
- pies_colados: % de pies de página («Página N») que aparecen en la salida y acaban dentro del texto
  que se trocea para el RAG.

Salida: resultados/calidad_por_documento.csv y resultados/resumen.json.
"""

import csv
import json
import os
import re
import statistics
import unicodedata

from pypdf import PdfReader
from rapidfuzz.distance import Levenshtein

AQUI = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(AQUI, "corpus")
SALIDAS = os.path.join(AQUI, "salidas")
RESULTADOS = os.path.join(AQUI, "resultados")
ESPECIALES = "áéíóúñüÁÉÍÓÚÑ¿¡«»€"


def normalizar_linea(t: str) -> str:
    t = unicodedata.normalize("NFC", t)
    t = re.sub(r"<br\s*/?>", " ", t)
    t = t.replace("\\", "")
    t = re.sub(r"[*#|_`]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def normalizar(t: str) -> str:
    return normalizar_linea(t.replace("\n", " "))


def especiales(ref: str, salida: str) -> tuple[int, int]:
    total = conservados = 0
    for c in ESPECIALES:
        n = ref.count(c)
        total += n
        conservados += min(n, salida.count(c))
    return conservados, total


def evaluar_doc(ref: dict, salida: str, paginas: int) -> dict:
    plano = normalizar(salida)
    res = {}
    res["pies_colados"] = 100 * sum(f"Página {n}" in plano for n in range(1, paginas + 1)) / paginas
    textos = [ref["titulo"]] + ref["parrafos"]
    pars = [normalizar(p) for p in ref["parrafos"]]
    res["parrafos_integros"] = 100 * sum(p in plano for p in pars) / len(pars)
    if ref["tipo"] in ("texto", "columnas"):
        res["similitud"] = 100 * Levenshtein.normalized_similarity(normalizar(" ".join(textos)), plano)
        # el párrafo entero si está; si no, su comienzo (hay párrafos que empiezan igual)
        posiciones = [plano.find(p) if p in plano else plano.find(p[:60]) for p in pars]
        pares = [(a, b) for a, b in zip(posiciones, posiciones[1:]) if a >= 0 and b >= 0]
        res["orden"] = 100 * sum(a < b for a, b in pares) / len(pares) if pares else 0.0
    celdas_ref = " ".join(" ".join(f) for f in ref["filas"]) + " " + " ".join(ref.get("cabecera", []))
    c, t = especiales(" ".join(textos) + " " + celdas_ref, salida)
    res["especiales"] = 100 * c / t
    if ref["filas"]:
        lineas = [normalizar_linea(l) for l in salida.splitlines()]
        celdas = [normalizar(x) for f in ref["filas"] for x in (f[0], f[2], f[4])]
        res["celdas"] = 100 * sum(x in plano for x in celdas) / len(celdas)
        completas = juntos = 0
        for concepto, _, precio, _, total in ref["filas"]:
            patron_imp = re.escape(precio) + r".*" + re.escape(total)
            patron_fila = re.escape(normalizar(concepto)) + r".*" + patron_imp
            juntos += any(re.search(patron_imp, l) for l in lineas)
            completas += any(re.search(patron_fila, l) for l in lineas)
        res["filas_completas"] = 100 * completas / len(ref["filas"])
        res["importes_juntos"] = 100 * juntos / len(ref["filas"])
    return res


def cuartiles(v: list[float]) -> dict:
    q = statistics.quantiles(v, n=4) if len(v) > 1 else [v[0]] * 3
    return {"mediana": round(statistics.median(v), 4), "min": round(min(v), 4), "max": round(max(v), 4),
            "q1": round(q[0], 4), "q3": round(q[2], 4), "desv": round(statistics.pstdev(v), 4), "n": len(v)}


def main() -> None:
    referencia = json.load(open(os.path.join(CORPUS, "referencia.json"), encoding="utf-8"))
    paginas = {pdf: len(PdfReader(os.path.join(CORPUS, pdf)).pages) for pdf in referencia}
    parsers = sorted(os.listdir(SALIDAS))
    filas = []
    for p in parsers:
        for pdf, ref in referencia.items():
            salida = open(os.path.join(SALIDAS, p, pdf[:-4] + ".txt"), encoding="utf-8").read()
            m = evaluar_doc(ref, salida, paginas[pdf])
            filas.append({"parser": p, "pdf": pdf, "tipo": ref["tipo"], "paginas": paginas[pdf],
                          **m})  # sin redondear: se redondea una sola vez, al final
    claves = ["pies_colados", "parrafos_integros", "similitud", "orden", "especiales", "celdas", "filas_completas",
              "importes_juntos"]
    with open(os.path.join(RESULTADOS, "calidad_por_documento.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["parser", "pdf", "tipo", "paginas"] + claves)
        w.writeheader()
        w.writerows({k: round(v, 2) if isinstance(v, float) else v for k, v in f.items()} for f in filas)

    procesos = list(csv.DictReader(open(os.path.join(RESULTADOS, "procesos.csv"))))
    total_paginas = sum(paginas.values())
    resumen = {"documentos": len(referencia), "paginas": total_paginas,
               "documentos_por_tipo": {t: sum(r["tipo"] == t for r in referencia.values())
                                       for t in sorted({r["tipo"] for r in referencia.values()})},
               "parsers": {}}
    for p in parsers:
        mias = [f for f in filas if f["parser"] == p]
        calidad = {}
        for tipo in sorted({f["tipo"] for f in mias}):
            del_tipo = [f for f in mias if f["tipo"] == tipo]
            calidad[tipo] = {k: round(statistics.mean(f[k] for f in del_tipo), 2)
                             for k in claves if k in del_tipo[0]}
        calidad["todos"] = {"especiales": round(statistics.mean(f["especiales"] for f in mias), 2),
                            "pies_colados": round(statistics.mean(f["pies_colados"] for f in mias), 2),
                            "parrafos_integros": round(statistics.mean(f["parrafos_integros"] for f in mias), 2)}
        facturas = [f for f in mias if f["tipo"].startswith("factura")]
        calidad["facturas_todas"] = {k: round(statistics.mean(f[k] for f in facturas), 2)
                                     for k in ("celdas", "filas_completas", "importes_juntos")}
        pr = [r for r in procesos if r["parser"] == p]
        totales = [float(r["total_s"]) for r in pr]
        resumen["parsers"][p] = {
            "calidad": calidad,
            "total_s": cuartiles(totales),
            "ms_por_pagina": cuartiles([1000 * t / total_paginas for t in totales]),
            "import_s": cuartiles([float(r["import_s"]) for r in pr]),
            "pico_mb": cuartiles([float(r["pico_mb"]) for r in pr]),
        }
    with open(os.path.join(RESULTADOS, "resumen.json"), "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=1)
    for p, d in resumen["parsers"].items():
        print(p, json.dumps(d["calidad"], ensure_ascii=False))
        print("   ms/pág", d["ms_por_pagina"]["mediana"], "import", d["import_s"]["mediana"],
              "MB", d["pico_mb"]["mediana"])


if __name__ == "__main__":
    main()
