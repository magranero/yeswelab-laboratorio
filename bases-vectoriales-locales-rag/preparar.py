"""Prepara los vectores del experimento: párrafos de Wikipedia en español -> embeddings.

Descarga un fichero parquet de wikimedia/wikipedia (20231101.es, revisión fijada), corta los
artículos en párrafos, elige 100.000 párrafos para indexar y 1.000 distintos para consultar,
los pasa por multilingual-e5-small y calcula los 10 vecinos exactos de cada consulta
(producto escalar sobre vectores normalizados = similitud coseno) para 10.000 y 100.000 vectores.

Todo se guarda en datos/ (no se sube al repositorio).
"""

import json
import os
import random
import time

import numpy as np
import pyarrow.parquet as pq
import torch
from huggingface_hub import hf_hub_download
from sentence_transformers import SentenceTransformer

AQUI = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(AQUI, "datos")
RESULTADOS = os.path.join(AQUI, "resultados")

WIKI_REPO = "wikimedia/wikipedia"
WIKI_FICHERO = "20231101.es/train-00002-of-00013.parquet"
WIKI_REVISION = "b04c8d1ceb2f5cd4588862100d08de323dccfbaa"
MODELO = "intfloat/multilingual-e5-small"
MODELO_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
N_CORPUS = 100_000
N_CONSULTAS = 1_000
TAMANOS = [10_000, 100_000]
K = 10
SEMILLA = 20261024


def parrafos(textos):
    for t in textos:
        for p in t.split("\n"):
            p = p.strip()
            if 300 <= len(p) <= 1500:
                yield p


def primera_frase(p: str) -> str:
    corte = p.find(". ")
    frase = p if corte == -1 else p[: corte + 1]
    return frase[:300]


def main() -> None:
    os.makedirs(DATOS, exist_ok=True)
    os.makedirs(RESULTADOS, exist_ok=True)
    # Si ya se descargó a mano (curl de la URL resolve/<revisión>/<fichero>), se usa esa copia.
    ruta = os.path.join(DATOS, "wiki-es.parquet")
    if not os.path.exists(ruta):
        ruta = hf_hub_download(WIKI_REPO, WIKI_FICHERO, repo_type="dataset", revision=WIKI_REVISION)
    textos = pq.read_table(ruta, columns=["text"]).column("text").to_pylist()
    todos = list(dict.fromkeys(parrafos(textos)))  # sin duplicados, en orden
    random.Random(SEMILLA).shuffle(todos)
    corpus = todos[:N_CORPUS]
    consultas = [primera_frase(p) for p in todos[N_CORPUS : N_CORPUS + N_CONSULTAS]]

    dispositivo = "mps" if torch.backends.mps.is_available() else "cpu"
    modelo = SentenceTransformer(MODELO, revision=MODELO_REVISION, device=dispositivo)
    t0 = time.perf_counter()
    X = modelo.encode(["passage: " + p for p in corpus], batch_size=128, normalize_embeddings=True,
                      convert_to_numpy=True, show_progress_bar=True).astype(np.float32)
    t_corpus = time.perf_counter() - t0
    Q = modelo.encode(["query: " + q for q in consultas], batch_size=128, normalize_embeddings=True,
                      convert_to_numpy=True).astype(np.float32)
    np.save(os.path.join(DATOS, "corpus.npy"), X)
    np.save(os.path.join(DATOS, "consultas.npy"), Q)

    # Vecinos exactos (la verdad contra la que se mide el recall).
    for n in TAMANOS:
        S = Q @ X[:n].T
        top = np.argsort(-S, axis=1, kind="stable")[:, :K]
        np.save(os.path.join(DATOS, f"vecinos_{n}.npy"), top.astype(np.int64))

    info = {
        "corpus": {"repo": WIKI_REPO, "fichero": WIKI_FICHERO, "revision": WIKI_REVISION,
                   "parrafos_candidatos": len(todos), "parrafos_indexados": len(corpus),
                   "consultas": len(consultas),
                   "caracteres_medios_parrafo": float(np.mean([len(p) for p in corpus])),
                   "caracteres_medios_consulta": float(np.mean([len(q) for q in consultas]))},
        "modelo": {"nombre": MODELO, "revision": MODELO_REVISION, "dimensiones": int(X.shape[1]),
                   "dispositivo": dispositivo, "segundos_embeddings_corpus": t_corpus},
        "tamanos": TAMANOS, "k": K, "semilla": SEMILLA,
    }
    with open(os.path.join(RESULTADOS, "datos.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
