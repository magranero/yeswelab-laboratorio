"""Comparaciones extra a partir de resultados/por_consulta.csv (no recalcula nada caro).

    .venv/bin/python resumir.py

Escribe resultados/comparaciones_extra.json: diferencias de nDCG@10 con IC 95 % (bootstrap pareado)
entre el mejor flujo con reranker y los densos solos, en la muestra del reranker.
"""

import json
import os

import numpy as np
import pandas as pd

from preparar import RES, SEMILLA

BOOTSTRAP = 2000
PARES = {
    "miracl": [("e5-small", "rrf bm25+e5-small +rerank"), ("e5-small", "bm25 +rerank")],
    "mlqa": [("e5-small", "rrf bm25+e5-small +rerank"), ("bge-m3", "rrf bm25+e5-small +rerank"),
             ("rrf bm25+bge-m3", "rrf bm25+e5-small +rerank"), ("e5-small", "bm25 +rerank")],
}


def ic(a, b):
    d = np.asarray(b) - np.asarray(a)
    rng = np.random.default_rng(SEMILLA)
    medias = d[rng.integers(0, len(d), size=(BOOTSTRAP, len(d)))].mean(axis=1)
    return {"diferencia": float(d.mean()), "ic95_bajo": float(np.percentile(medias, 2.5)),
            "ic95_alto": float(np.percentile(medias, 97.5)), "consultas": int(len(d))}


def main():
    df = pd.read_csv(os.path.join(RES, "por_consulta.csv"))
    salida = {}
    for nombre, pares in PARES.items():
        d = df[(df.conjunto == nombre) & (df.en_muestra_rerank == 1)]
        tabla = d.pivot(index="query_id", columns="metodo", values="ndcg@10")
        for a, b in pares:
            salida.setdefault(nombre, {})[f"{b} vs {a}"] = ic(tabla[a].values, tabla[b].values)
        # Consultas que el reranker empeora frente a su base.
        base = tabla["rrf bm25+e5-small"]
        rr = tabla["rrf bm25+e5-small +rerank"]
        salida[nombre]["rerank_sobre_rrf_consultas"] = {
            "mejora": int((rr > base).sum()), "igual": int((rr == base).sum()), "empeora": int((rr < base).sum())}
    json.dump(salida, open(os.path.join(RES, "comparaciones_extra.json"), "w"), indent=2, ensure_ascii=False)
    print(json.dumps(salida, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
