"""Tamaño de chunk para RAG en español: recall de recuperación por tamaño, solapamiento y modelo de embeddings.

Corpus: XQuAD en español (google/xquad, xquad.es), agrupado por artículo con los títulos de SQuAD v1.1.
Se trocea cada artículo en chunks de 128, 256, 512 y 1024 tokens (o200k_base), con 0 % y 20 % de
solapamiento, se indexan con tres modelos de embeddings y se mide si el chunk que contiene la respuesta
sale entre los recuperados. 5 repeticiones por caso (tiempos y comprobación de determinismo).

    .venv/bin/python medir.py
"""

import csv
from decimal import ROUND_HALF_UP, Decimal
import json
import os
import platform
import re
import statistics
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import tiktoken
import torch
from huggingface_hub import HfApi, hf_hub_download
from sentence_transformers import SentenceTransformer

AQUI = Path(__file__).parent
RES = AQUI / "resultados"
RES.mkdir(exist_ok=True)

TAMANOS = [128, 256, 512, 1024]
SOLAPES = [0.0, 0.2]
PRESUPUESTOS = [1024, 2048]  # tokens de contexto que se mandarían al LLM
REPETICIONES = 5
BOOTSTRAP = 2000
MODELOS = {
    "multilingual-e5-small": {"id": "intfloat/multilingual-e5-small", "q": "query: ", "p": "passage: "},
    "paraphrase-multilingual-MiniLM-L12-v2": {"id": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "q": "", "p": ""},
    "bge-m3": {"id": "BAAI/bge-m3", "q": "", "p": ""},
}

enc = tiktoken.get_encoding("o200k_base")
ntok = lambda t: len(enc.encode_ordinary(t))  # noqa: E731
api = HfApi()


def reintentar(fn, *args, **kwargs):
    """La red del Hub a veces corta la conexión: hasta 6 intentos con espera creciente."""
    for intento in range(6):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            if intento == 5:
                raise
            print(f"Reintento {intento + 1} tras error de red: {type(e).__name__}")
            time.sleep(5 * (intento + 1))


def revision(repo: str, tipo: str | None = None) -> str:
    return reintentar(api.repo_info, repo, repo_type=tipo).sha


def cargar_corpus():
    rev_x = revision("google/xquad", "dataset")
    fichero = next(f for f in reintentar(api.list_repo_files, "google/xquad", repo_type="dataset", revision=rev_x)
                   if "xquad.es" in f and f.endswith(".parquet"))
    xq = pq.read_table(reintentar(hf_hub_download, "google/xquad", fichero, repo_type="dataset", revision=rev_x)).to_pylist()
    rev_s = revision("rajpurkar/squad", "dataset")
    fs = next(f for f in reintentar(api.list_repo_files, "rajpurkar/squad", repo_type="dataset", revision=rev_s)
              if "validation" in f and f.endswith(".parquet"))
    titulos = {r["id"]: r["title"] for r in pq.read_table(reintentar(hf_hub_download, "rajpurkar/squad", fs, repo_type="dataset", revision=rev_s), columns=["id", "title"]).to_pylist()}

    docs: dict[str, list[str]] = {}
    for r in xq:
        parrafos = docs.setdefault(titulos[r["id"]], [])
        if r["context"] not in parrafos:
            parrafos.append(r["context"])
    textos, desplaz = {}, {}
    for t, parrafos in docs.items():
        pos, partes = 0, []
        for p in parrafos:
            desplaz[(t, p)] = pos
            partes.append(p)
            pos += len(p) + 2
        textos[t] = "\n\n".join(partes)
    preguntas, corregidas, descartadas = [], 0, 0
    for r in xq:
        t = titulos[r["id"]]
        resp, ini_ctx = r["answers"]["text"][0], r["answers"]["answer_start"][0]
        if r["context"][ini_ctx:ini_ctx + len(resp)] != resp:
            # en la traducción, algunos answer_start no cuadran: se usa la aparición más cercana
            apariciones = [m.start() for m in re.finditer(re.escape(resp), r["context"])]
            if not apariciones:
                descartadas += 1
                continue
            ini_ctx = min(apariciones, key=lambda a: abs(a - ini_ctx))
            corregidas += 1
        ini = desplaz[(t, r["context"])] + ini_ctx
        preguntas.append({"id": r["id"], "doc": t, "pregunta": r["question"], "ini": ini, "fin": ini + len(resp)})
    print(f"answer_start corregidos: {corregidas}; preguntas descartadas: {descartadas}")
    return textos, preguntas, {"google/xquad": rev_x, "rajpurkar/squad": rev_s, "answer_start_corregidos": corregidas, "preguntas_descartadas": descartadas}


def frases(texto: str, maximo: int):
    """Spans (ini, fin) de frases; las que pasan de `maximo` tokens se parten por palabras."""
    spans = []
    for m in re.finditer(r"[^\n]+", texto):
        base = m.start()
        trozos = re.split(r"(?<=[.!?…])\s+", m.group())
        pos = 0
        for tr in trozos:
            ini = m.group().index(tr, pos) + base
            fin = ini + len(tr)
            pos = fin - base
            if ntok(tr) <= maximo:
                spans.append((ini, fin))
                continue
            palabras = [w for w in re.finditer(r"\S+", tr)]
            a = 0
            while a < len(palabras):
                b = a + 1
                while b < len(palabras) and ntok(tr[palabras[a].start():palabras[b].end()]) <= maximo:
                    b += 1
                spans.append((ini + palabras[a].start(), ini + palabras[b - 1].end()))
                a = b
    return spans


def trocear(textos: dict, tamano: int, solape: float):
    chunks = []
    for doc, texto in textos.items():
        fs = frases(texto, tamano)
        toks = [ntok(texto[a:b]) for a, b in fs]
        i = 0
        while i < len(fs):
            j, total = i, 0
            while j < len(fs) and total + toks[j] <= tamano:
                total += toks[j]
                j += 1
            chunks.append({"doc": doc, "ini": fs[i][0], "fin": fs[j - 1][1]})
            if j >= len(fs):
                break
            # siguiente chunk: retrocede frases que quepan en el solapamiento
            k, atras = j, 0
            while solape and k - 1 > i and atras + toks[k - 1] <= solape * tamano:
                k -= 1
                atras += toks[k]
            i = k
    for c in chunks:
        c["texto"] = textos[c["doc"]][c["ini"]:c["fin"]]
        c["tokens"] = ntok(c["texto"])
    return chunks


def evaluar(sims: np.ndarray, chunks: list, preguntas: list):
    orden = np.argsort(-sims, axis=1)[:, :50]
    acierto = {f"recall@{k}": [] for k in (1, 3, 5)} | {f"recall_presupuesto_{p}": [] for p in PRESUPUESTOS}
    for qi, q in enumerate(preguntas):
        contiene = [chunks[c]["doc"] == q["doc"] and chunks[c]["ini"] <= q["ini"] and q["fin"] <= chunks[c]["fin"] for c in orden[qi]]
        for k in (1, 3, 5):
            acierto[f"recall@{k}"].append(int(any(contiene[:k])))
        for p in PRESUPUESTOS:
            usados, ok = 0, False
            for n, c in enumerate(orden[qi]):
                if usados + chunks[c]["tokens"] > p and n > 0:
                    break
                usados += chunks[c]["tokens"]
                ok = ok or contiene[n]
            acierto[f"recall_presupuesto_{p}"].append(int(ok))
    return {k: np.array(v) for k, v in acierto.items()}


def ic95(v: np.ndarray, rng) -> list[float]:
    medias = [v[rng.integers(0, len(v), len(v))].mean() for _ in range(BOOTSTRAP)]
    return [round(float(np.percentile(medias, 2.5)), 4), round(float(np.percentile(medias, 97.5)), 4)]


def main():
    textos, preguntas, revs = cargar_corpus()
    print(f"{len(textos)} artículos, {len(preguntas)} preguntas, {sum(ntok(t) for t in textos.values())} tokens")
    disp = os.environ.get("DISPOSITIVO") or ("mps" if torch.backends.mps.is_available() else "cpu")
    filas, tiempos, por_pregunta = [], [], []
    for nombre, cfg in MODELOS.items():
        revs[cfg["id"]] = revision(cfg["id"])
        modelo = reintentar(SentenceTransformer, cfg["id"], device=disp, revision=revs[cfg["id"]])
        max_seq = modelo.max_seq_length
        tok_modelo = modelo.tokenizer
        qs = [cfg["q"] + q["pregunta"] for q in preguntas]
        for tamano in TAMANOS:
            for solape in SOLAPES:
                chunks = trocear(textos, tamano, solape)
                ps = [cfg["p"] + c["texto"] for c in chunks]
                # techo: preguntas cuya respuesta cabe entera en algún chunk (si se parte entre dos, ningún recuperador acierta)
                techo = sum(any(c["doc"] == q["doc"] and c["ini"] <= q["ini"] and q["fin"] <= c["fin"] for c in chunks) for q in preguntas)
                truncados = sum(len(tok_modelo(p)["input_ids"]) > max_seq for p in ps)
                modelo.encode(ps[:8], batch_size=8)  # calentamiento
                resultados_rep = []
                for rep in range(REPETICIONES):
                    t0 = time.perf_counter()
                    E = modelo.encode(ps, batch_size=16, normalize_embeddings=True, convert_to_numpy=True)
                    t1 = time.perf_counter()
                    Q = modelo.encode(qs, batch_size=64, normalize_embeddings=True, convert_to_numpy=True)
                    t2 = time.perf_counter()
                    met = evaluar(Q @ E.T, chunks, preguntas)
                    resultados_rep.append({k: float(v.mean()) for k, v in met.items()})
                    tiempos.append({"modelo": nombre, "tamano": tamano, "solape": solape, "repeticion": rep + 1,
                                    "indexar_s": round(t1 - t0, 4), "consultas_s": round(t2 - t1, 4)})
                    print(nombre, tamano, solape, rep + 1, round(t1 - t0, 2), resultados_rep[-1]["recall@5"])
                rng = np.random.default_rng(0)
                ts = [t["indexar_s"] for t in tiempos if t["modelo"] == nombre and t["tamano"] == tamano and t["solape"] == solape]
                fila = {
                    "modelo": nombre, "tamano": tamano, "solape": solape, "chunks": len(chunks),
                    "tokens_medios_chunk": round(statistics.mean(c["tokens"] for c in chunks), 1),
                    "techo_respuesta_entera_pct": round(100 * techo / len(preguntas), 1),
                    "max_seq_modelo": max_seq, "chunks_truncados": truncados,
                    "pct_truncados": round(100 * truncados / len(chunks), 1),
                    "indexar_mediana_s": round(statistics.median(ts), 3), "indexar_min_s": min(ts), "indexar_max_s": max(ts),
                    "indexar_desv_s": round(statistics.stdev(ts), 4),
                    "variacion_recall_entre_reps": round(max(abs(r["recall@5"] - resultados_rep[0]["recall@5"]) for r in resultados_rep), 6),
                }
                for k in met:
                    mediana = statistics.median(r[k] for r in resultados_rep)
                    fila[k] = round(mediana, 4)
                    fila[k + "_pct"] = float(Decimal(str(100 * mediana)).quantize(Decimal("0.1"), ROUND_HALF_UP))  # redondear una sola vez
                    fila[k + "_ic95"] = ic95(met[k], rng)
                filas.append(fila)
                for qi, q in enumerate(preguntas):
                    por_pregunta.append({"modelo": nombre, "tamano": tamano, "solape": solape, "id": q["id"],
                                         **{k: int(v[qi]) for k, v in met.items()}})
        del modelo
        if disp == "mps":
            torch.mps.empty_cache()

    with open(RES / "tiempos.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(tiempos[0]))
        w.writeheader()
        w.writerows(tiempos)
    with open(RES / "aciertos_por_pregunta.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(por_pregunta[0]))
        w.writeheader()
        w.writerows(por_pregunta)
    resumen = {
        "fecha": time.strftime("%Y-%m-%d"),
        "corpus": {"articulos": len(textos), "preguntas": len(preguntas), "tokens_o200k": sum(ntok(t) for t in textos.values()),
                   "parrafos": sum(t.count("\n\n") + 1 for t in textos.values())},
        "dispositivo": disp, "repeticiones": REPETICIONES, "bootstrap": BOOTSTRAP, "revisiones": revs,
        "configuraciones": filas,
    }
    (RES / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1))
    with open(RES / "resumen.csv", "w", newline="") as f:
        campos = [k for k in filas[0] if not k.endswith("_ic95")]
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)
    print("python", platform.python_version())


if __name__ == "__main__":
    main()
