"""Mide BM25, embeddings, fusión RRF y reranker en dos conjuntos en español.

    .venv/bin/python preparar.py   # datos y reranker (una vez)
    .venv/bin/python medir.py      # calidad y latencia -> resultados/

Recuperadores:
- bm25: bm25s con el lematizador Snowball de español y stopwords en español.
- e5-small: intfloat/multilingual-e5-small (los dos conjuntos).
- bge-m3: BAAI/bge-m3 denso, fp16 (solo MLQA: en MIRACL completo no cabe en el tiempo de cómputo).
- rrf: fusión por posición (k = 60) del top-100 de BM25 y de un denso.
- +rerank: bge-reranker-v2-m3 reordena el top-20 de BM25 o del híbrido, en una muestra fija de consultas.

Todo lo caro se guarda en datos/ (embeddings y puntuaciones del reranker), así que repetirlo es rápido.
"""

import csv
import json
import os
import random
import re
import statistics
import sys
import time

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import bm25s
import numpy as np
import Stemmer
import torch
from sentence_transformers import CrossEncoder, SentenceTransformer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preparar import DATOS, DENSOS, RES, SEMILLA, cargar  # noqa: E402

K_RRF = 60
TOP = 100
TOP_RERANK = 20
MUESTRA_RERANK = 300
MUESTRA_LATENCIA = 30
REPETICIONES = 5
BOOTSTRAP = 2000
DENSOS_POR_CONJUNTO = {"miracl": ["e5-small"], "mlqa": ["e5-small", "bge-m3"]}
PREFIJO_CONSULTA = {"e5-small": "query: ", "bge-m3": ""}
RERANKER = os.path.join(DATOS, "bge-reranker-v2-m3")
STEM = Stemmer.Stemmer("spanish")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ---------- recuperadores ----------

def tokenizar(textos):
    return bm25s.tokenize(textos, stopwords="es", stemmer=STEM, show_progress=False)


def indexar_bm25(textos):
    r = bm25s.BM25()
    r.index(tokenizar(textos), show_progress=False)
    return r


def buscar_bm25(indice, consultas, k=TOP):
    ids, _ = indice.retrieve(tokenizar(consultas), k=k, show_progress=False, n_threads=1)
    return ids.tolist()


def modelo_denso(clave):
    repo, rev, _ = DENSOS[clave]
    kw = {"model_kwargs": {"torch_dtype": torch.float16}} if clave == "bge-m3" else {}
    m = SentenceTransformer(repo, revision=rev, device="mps", **kw)
    m.max_seq_length = 512
    return m


def embeddings_corpus(clave, nombre, modelo, textos, tiempos):
    destino = os.path.join(DATOS, f"emb-{clave}-{nombre}.npy")
    if os.path.exists(destino):
        return np.load(destino)
    prefijo = DENSOS[clave][2]
    t = time.perf_counter()
    v = modelo.encode([prefijo + x for x in textos], batch_size=32, normalize_embeddings=True,
                      convert_to_numpy=True, show_progress_bar=False).astype(np.float32)
    tiempos[f"{clave}/{nombre}"] = {"segundos": time.perf_counter() - t, "pasajes": len(textos)}
    np.save(destino, v)
    return v


def codificar_consultas(clave, modelo, consultas):
    return modelo.encode([PREFIJO_CONSULTA[clave] + q for q in consultas], batch_size=64, normalize_embeddings=True,
                         convert_to_numpy=True, show_progress_bar=False).astype(np.float32)


def buscar_denso(matriz, vq, k=TOP):
    s = vq @ matriz.T
    top = np.argpartition(-s, k, axis=1)[:, :k]
    orden = np.take_along_axis(s, top, axis=1).argsort(axis=1)[:, ::-1]
    return np.take_along_axis(top, orden, axis=1).tolist()


def rrf(*listas, k=K_RRF, top=TOP):
    puntos = {}
    for lista in listas:
        for pos, d in enumerate(lista):
            puntos[d] = puntos.get(d, 0.0) + 1.0 / (k + pos + 1)
    return sorted(puntos, key=lambda d: -puntos[d])[:top]


# ---------- reranker con caché por par ----------

class Reranker:
    def __init__(self):
        self.modelo = CrossEncoder(RERANKER, device="mps", max_length=512,
                                   model_kwargs={"torch_dtype": torch.float16})
        self.cache_ruta = os.path.join(DATOS, "cache-reranker.json")
        self.cache = json.load(open(self.cache_ruta)) if os.path.exists(self.cache_ruta) else {}

    def puntuar(self, pares):
        return [float(x) for x in self.modelo.predict(pares, batch_size=16, show_progress_bar=False)]

    def reordenar(self, nombre, qid, consulta, candidatos, textos):
        faltan = [d for d in candidatos if f"{nombre}|{qid}|{d}" not in self.cache]
        if faltan:
            for d, s in zip(faltan, self.puntuar([(consulta, textos[d]) for d in faltan])):
                self.cache[f"{nombre}|{qid}|{d}"] = s
        return sorted(candidatos, key=lambda d: -self.cache[f"{nombre}|{qid}|{d}"])

    def guardar(self):
        json.dump(self.cache, open(self.cache_ruta, "w"))


# ---------- métricas ----------

def metricas(ranking, relevantes):
    """nDCG@10 (relevancia binaria), Recall@10, Recall@100 y MRR@10 de una consulta."""
    dcg = sum(1 / np.log2(i + 2) for i, d in enumerate(ranking[:10]) if d in relevantes)
    idcg = sum(1 / np.log2(i + 2) for i in range(min(10, len(relevantes))))
    mrr = next((1 / (i + 1) for i, d in enumerate(ranking[:10]) if d in relevantes), 0.0)
    return {
        "ndcg@10": dcg / idcg,
        "recall@10": len(set(ranking[:10]) & relevantes) / len(relevantes),
        "recall@100": len(set(ranking[:100]) & relevantes) / len(relevantes),
        "mrr@10": mrr,
    }


def literal(consulta):
    """Consulta con cifras o nombres propios (mayúscula que no abre la frase)."""
    palabras = re.findall(r"\w+", consulta)
    return bool(re.search(r"\d", consulta)) or any(p[0].isupper() for p in palabras[1:])


def ic_bootstrap(a, b, semilla=SEMILLA):
    """Diferencia media b - a e IC 95 % por bootstrap pareado."""
    a, b = np.asarray(a), np.asarray(b)
    d = b - a
    rng = np.random.default_rng(semilla)
    medias = d[rng.integers(0, len(d), size=(BOOTSTRAP, len(d)))].mean(axis=1)
    return {"diferencia": float(d.mean()), "ic95_bajo": float(np.percentile(medias, 2.5)),
            "ic95_alto": float(np.percentile(medias, 97.5)), "consultas": int(len(d))}


# ---------- experimento ----------

def calidad(nombre, info):
    ids, textos, qids, consultas, rel_ids = cargar(nombre)
    pos = {d: i for i, d in enumerate(ids)}
    relevantes = [{pos[d] for d in rel_ids[q] if d in pos} for q in qids]
    log(nombre, len(ids), "pasajes,", len(qids), "consultas")

    # BM25: índice 5 veces (tiempo) y búsqueda en lote.
    t_ind = []
    for _ in range(REPETICIONES):
        t = time.perf_counter()
        indice = indexar_bm25(textos)
        t_ind.append(time.perf_counter() - t)
    info["indexado_bm25_s"][nombre] = t_ind
    rankings = {"bm25": buscar_bm25(indice, consultas)}
    log(nombre, "bm25 listo", round(statistics.median(t_ind), 1), "s de índice")

    modelos, matrices = {}, {}
    for clave in DENSOS_POR_CONJUNTO[nombre]:
        modelos[clave] = modelo_denso(clave)
        matrices[clave] = embeddings_corpus(clave, nombre, modelos[clave], textos, info["embeddings_s"])
        rankings[clave] = buscar_denso(matrices[clave], codificar_consultas(clave, modelos[clave], consultas))
        rankings[f"rrf bm25+{clave}"] = [rrf(a, b) for a, b in zip(rankings["bm25"], rankings[clave])]
        log(nombre, clave, "listo")

    # Reranker sobre el top-20 de BM25 y del híbrido con e5-small, en una muestra fija.
    rng = random.Random(SEMILLA)
    muestra = sorted(rng.sample(range(len(qids)), min(MUESTRA_RERANK, len(qids))))
    rr = Reranker()
    t = time.perf_counter()
    for base in ("bm25", "rrf bm25+e5-small"):
        rankings[f"{base} +rerank"] = {}
        for i in muestra:
            cand = rankings[base][i][:TOP_RERANK]
            rankings[f"{base} +rerank"][i] = rr.reordenar(nombre, qids[i], consultas[i], cand, textos) + rankings[base][i][TOP_RERANK:]
    rr.guardar()
    log(nombre, "reranker listo", round(time.perf_counter() - t), "s")

    # Métricas por consulta.
    filas = []
    for metodo, rk in rankings.items():
        indices = muestra if isinstance(rk, dict) else range(len(qids))
        for i in indices:
            filas.append({"conjunto": nombre, "metodo": metodo, "query_id": qids[i], "literal": int(literal(consultas[i])),
                          "en_muestra_rerank": int(i in set(muestra)), "relevantes": len(relevantes[i]),
                          **metricas(rk[i], relevantes[i])})
    return filas, muestra, (indice, modelos, matrices, rr, textos, consultas, qids)


def agregados(filas):
    salida = {}
    grupos = {}
    for f in filas:
        claves = [("todas", f["metodo"])]
        if f["en_muestra_rerank"]:
            claves.append(("muestra_rerank", f["metodo"]))
        claves.append(("literal" if f["literal"] else "no_literal", f["metodo"]))
        for c in claves:
            grupos.setdefault(c, []).append(f)
    for (grupo, metodo), fs in grupos.items():
        if grupo == "todas" and "+rerank" in metodo:
            continue  # el reranker solo se aplicó a la muestra
        salida.setdefault(grupo, {})[metodo] = {m: float(np.mean([f[m] for f in fs]))
                                                for m in ("ndcg@10", "recall@10", "recall@100", "mrr@10")} | {"consultas": len(fs)}
    return salida


def comparaciones(filas):
    por = {}
    for f in filas:
        por.setdefault(f["metodo"], {})[f["query_id"]] = f["ndcg@10"]
    pares = [("bm25", "e5-small"), ("bm25", "rrf bm25+e5-small"), ("e5-small", "rrf bm25+e5-small"),
             ("bm25", "bge-m3"), ("bge-m3", "rrf bm25+bge-m3"),
             ("bm25", "bm25 +rerank"), ("rrf bm25+e5-small", "rrf bm25+e5-small +rerank"),
             ("bm25 +rerank", "rrf bm25+e5-small +rerank")]
    salida = {}
    for a, b in pares:
        if a in por and b in por:
            comunes = sorted(set(por[a]) & set(por[b]))
            salida[f"{b} vs {a}"] = ic_bootstrap([por[a][q] for q in comunes], [por[b][q] for q in comunes])
    return salida


def latencia(nombre, estado, filas_lat):
    """Una consulta cada vez, 5 repeticiones sobre una muestra fija de consultas."""
    indice, modelos, matrices, rr, textos, consultas, qids = estado
    rng = random.Random(SEMILLA + 1)
    muestra = rng.sample(range(len(qids)), MUESTRA_LATENCIA)
    for i in muestra[:3]:  # calentamiento
        buscar_bm25(indice, [consultas[i]])
        for c in modelos:
            codificar_consultas(c, modelos[c], [consultas[i]])
        rr.puntuar([(consultas[i], textos[0])] * TOP_RERANK)
    for rep in range(REPETICIONES):
        for i in muestra:
            q = consultas[i]
            t = time.perf_counter(); b = buscar_bm25(indice, [q])[0]; t_bm25 = time.perf_counter() - t
            fila = {"conjunto": nombre, "repeticion": rep + 1, "query_id": qids[i], "bm25_ms": t_bm25 * 1000}
            for c in modelos:
                t = time.perf_counter()
                d = buscar_denso(matrices[c], codificar_consultas(c, modelos[c], [q]))[0]
                fila[f"{c}_ms"] = (time.perf_counter() - t) * 1000
                t = time.perf_counter(); h = rrf(b, d); fila[f"rrf_{c}_ms"] = (time.perf_counter() - t) * 1000
            t = time.perf_counter()
            if torch.backends.mps.is_available():
                torch.mps.synchronize()
            rr.puntuar([(q, textos[x]) for x in h[:TOP_RERANK]])
            fila["rerank20_ms"] = (time.perf_counter() - t) * 1000
            filas_lat.append(fila)
    log(nombre, "latencia lista")


def resumen_latencia(filas_lat):
    salida = {}
    for nombre in sorted({f["conjunto"] for f in filas_lat}):
        fs = [f for f in filas_lat if f["conjunto"] == nombre]
        for col in [c for c in fs[0] if c.endswith("_ms")]:
            vals = [f[col] for f in fs]
            por_rep = [statistics.median([f[col] for f in fs if f["repeticion"] == r]) for r in range(1, REPETICIONES + 1)]
            salida.setdefault(nombre, {})[col] = {
                "mediana": statistics.median(vals), "p90": float(np.percentile(vals, 90)),
                "mediana_por_repeticion_min": min(por_rep), "mediana_por_repeticion_max": max(por_rep),
                "mediciones": len(vals)}
    return salida


def guardar_csv(ruta, filas):
    with open(ruta, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


def main():
    os.makedirs(RES, exist_ok=True)
    info = {"fecha": time.strftime("%Y-%m-%d"), "indexado_bm25_s": {}, "embeddings_s": {},
            "parametros": {"k_rrf": K_RRF, "top": TOP, "top_rerank": TOP_RERANK, "muestra_rerank": MUESTRA_RERANK,
                           "muestra_latencia": MUESTRA_LATENCIA, "repeticiones": REPETICIONES, "bootstrap": BOOTSTRAP,
                           "semilla": SEMILLA}}
    previo = os.path.join(RES, "resumen.json")
    if os.path.exists(previo):
        info["embeddings_s"] = json.load(open(previo)).get("embeddings_s", {})
    filas, filas_lat = [], []
    info["calidad"], info["comparaciones_ndcg@10"] = {}, {}
    for nombre in ("mlqa", "miracl"):
        f, _, estado = calidad(nombre, info)
        filas += f
        info["calidad"][nombre] = agregados(f)
        info["comparaciones_ndcg@10"][nombre] = comparaciones(f)
        latencia(nombre, estado, filas_lat)
        del estado
    info["latencia_ms"] = resumen_latencia(filas_lat)
    info["indexado_bm25_s"] = {n: {"mediana": statistics.median(v), "min": min(v), "max": max(v), "valores": v}
                               for n, v in info["indexado_bm25_s"].items()}
    guardar_csv(os.path.join(RES, "por_consulta.csv"), filas)
    guardar_csv(os.path.join(RES, "latencia.csv"), filas_lat)
    json.dump(info, open(previo, "w"), indent=2, ensure_ascii=False)
    log("hecho")


if __name__ == "__main__":
    main()
