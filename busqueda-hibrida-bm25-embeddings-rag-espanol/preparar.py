"""Descarga los datos y el reranker (revisiones fijadas) y describe los conjuntos.

    .venv/bin/python preparar.py

Deja en datos/ los parquet de MIRACL y MLQA en español y el reranker. Guarda en
resultados/datos.json qué se usó. Los embeddings los calcula medir.py.
"""

import json
import os
import platform
import time
import urllib.request

os.environ.setdefault("HF_HUB_OFFLINE", "0")
AQUI = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(AQUI, "datos")
RES = os.path.join(AQUI, "resultados")

MIRACL = ("mteb/MIRACLRetrievalHardNegatives", "332a9acb49f5e83d5397683f79d23e588f685916", "es-{p}/dev-00000-of-00001.parquet")
MLQA = ("mteb/MLQARetrieval", "cf59ddd8f4aaf39ce1869361e09252698c340945", "spa-spa-{p}/test-00000-of-00001.parquet")
RERANKER = ("BAAI/bge-reranker-v2-m3", "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
            ["config.json", "model.safetensors", "sentencepiece.bpe.model", "special_tokens_map.json",
             "tokenizer.json", "tokenizer_config.json"])
DENSOS = {
    "e5-small": ("intfloat/multilingual-e5-small", "614241f622f53c4eeff9890bdc4f31cfecc418b3", "passage: "),
    "bge-m3": ("BAAI/bge-m3", "5617a9f61b028005a4858fdac845db406aefb181", ""),
}
MLQA_CONSULTAS = 1000  # muestra fija de las 5.251 preguntas de MLQA (el reranker es lo caro)
SEMILLA = 20261025


def bajar(url: str, destino: str) -> None:
    if os.path.exists(destino) and os.path.getsize(destino) > 0:
        return
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    print("descargando", url)
    with urllib.request.urlopen(url, timeout=60) as r, open(destino + ".tmp", "wb") as f:
        while bloque := r.read(1 << 20):
            f.write(bloque)
    os.replace(destino + ".tmp", destino)


def descargar() -> None:
    for nombre, (repo, rev, patron) in {"miracl": MIRACL, "mlqa": MLQA}.items():
        for p in ("corpus", "qrels", "queries"):
            bajar(f"https://huggingface.co/datasets/{repo}/resolve/{rev}/{patron.format(p=p)}",
                  os.path.join(DATOS, f"{nombre}-es-{p}.parquet"))
    repo, rev, ficheros = RERANKER
    for f in ficheros:
        bajar(f"https://huggingface.co/{repo}/resolve/{rev}/{f}", os.path.join(DATOS, "bge-reranker-v2-m3", f))


def cargar(nombre: str):
    """Corpus, consultas y relevantes de un conjunto, ya filtrados y en orden fijo."""
    import pandas as pd

    corpus = pd.read_parquet(os.path.join(DATOS, f"{nombre}-es-corpus.parquet"))
    consultas = pd.read_parquet(os.path.join(DATOS, f"{nombre}-es-queries.parquet"))
    qrels = pd.read_parquet(os.path.join(DATOS, f"{nombre}-es-qrels.parquet"))
    qrels = qrels[qrels["score"] > 0]
    relevantes = qrels.groupby("query-id")["corpus-id"].apply(set).to_dict()
    consultas = consultas[consultas["id"].isin(relevantes)].sort_values("id").reset_index(drop=True)
    if nombre == "mlqa":
        consultas = consultas.sample(MLQA_CONSULTAS, random_state=SEMILLA).sort_values("id").reset_index(drop=True)
    corpus = corpus.sort_values("id").reset_index(drop=True)
    textos = (corpus["title"].fillna("") + ". " + corpus["text"].fillna("")).str.strip(". ").tolist()
    return corpus["id"].tolist(), textos, consultas["id"].tolist(), consultas["text"].tolist(), relevantes


def main() -> None:
    os.makedirs(RES, exist_ok=True)
    descargar()
    info = {
        "fecha": time.strftime("%Y-%m-%d"),
        "conjuntos": {
            "miracl": {"repo": MIRACL[0], "revision": MIRACL[1], "licencia": "CC BY-SA 4.0"},
            "mlqa": {"repo": MLQA[0], "revision": MLQA[1], "licencia": "CC BY-SA 3.0", "consultas_muestra": MLQA_CONSULTAS},
        },
        "modelos": {k: {"repo": v[0], "revision": v[1]} for k, v in DENSOS.items()}
        | {"reranker": {"repo": RERANKER[0], "revision": RERANKER[1]}},
        "python": platform.python_version(),
    }
    previo = os.path.join(RES, "datos.json")
    for nombre in ("miracl", "mlqa"):
        ids, _, qids, _, rel = cargar(nombre)
        n_rel = [len(rel[q]) for q in qids]
        info["conjuntos"][nombre] |= {"pasajes": len(ids), "consultas": len(qids),
                                      "relevantes_por_consulta_media": sum(n_rel) / len(n_rel)}
    json.dump(info, open(previo, "w"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
