"""¿Cuántos tokens más gasta el español (y el portugués) que el inglés?

Cuenta tokens de las mismas frases traducidas (corpus paralelo OPUS-100, split de test)
con los tokenizadores públicos de varias familias de modelos y mide su velocidad.

    python medir.py            # escribe resultados/*.csv y resultados/resumen.json

Los conteos son deterministas; la velocidad se mide con REPETICIONES pasadas por caso.
"""

import csv
import json
import os
import platform
import random
import statistics
import time

import pyarrow.parquet as pq
import tiktoken
import tokenizers
from huggingface_hub import hf_hub_download

AQUI = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(AQUI, "resultados")
REPETICIONES = 7
BOOTSTRAP = 2000
random.seed(20261018)

# Pares del corpus: (repositorio, carpeta, idioma destino)
PARES = [("es", "en-es"), ("pt", "en-pt")]

# Tokenizadores sin acceso restringido. Nombre visible -> cómo cargarlo.
TOKENIZADORES = {
    "o200k_base (GPT-4o/GPT-5)": ("tiktoken", "o200k_base"),
    "cl100k_base (GPT-4/3.5)": ("tiktoken", "cl100k_base"),
    "Llama 3": ("hf", "unsloth/Llama-3.2-1B-Instruct"),
    "Gemma 3": ("hf", "unsloth/gemma-3-1b-it"),
    "Qwen3": ("hf", "Qwen/Qwen3-8B"),
    "DeepSeek-V3": ("hf", "deepseek-ai/DeepSeek-V3"),
    "Mistral Tekken (Nemo)": ("hf", "unsloth/Mistral-Nemo-Instruct-2407"),
}


def cargar_corpus():
    corpus = {}
    for lang, carpeta in PARES:
        ruta = hf_hub_download("Helsinki-NLP/opus-100", f"{carpeta}/test-00000-of-00001.parquet", repo_type="dataset")
        filas = pq.read_table(ruta).column("translation").to_pylist()
        pares = [(f["en"].strip(), f[lang].strip()) for f in filas if f["en"].strip() and f[lang].strip()]
        corpus[lang] = pares
    return corpus


def cargar_tokenizador(tipo, nombre):
    if tipo == "tiktoken":
        enc = tiktoken.get_encoding(nombre)
        return lambda t: len(enc.encode_ordinary(t)), nombre
    ruta = hf_hub_download(nombre, "tokenizer.json")
    tok = tokenizers.Tokenizer.from_file(ruta)
    return lambda t: len(tok.encode(t, add_special_tokens=False).ids), nombre


def bootstrap_ratio(en, xx):
    n = len(en)
    ratios = []
    for _ in range(BOOTSTRAP):
        idx = [random.randrange(n) for _ in range(n)]
        ratios.append(sum(xx[i] for i in idx) / sum(en[i] for i in idx))
    ratios.sort()
    return ratios[int(0.025 * BOOTSTRAP)], ratios[int(0.975 * BOOTSTRAP)]


def main():
    os.makedirs(RES, exist_ok=True)
    corpus = cargar_corpus()
    filas_conteo, filas_tiempo, resumen = [], [], {"corpus": {}, "tokenizadores": {}}

    for lang, pares in corpus.items():
        en = [p[0] for p in pares]
        xx = [p[1] for p in pares]
        resumen["corpus"][lang] = {
            "frases": len(pares),
            "caracteres_en": sum(map(len, en)),
            f"caracteres_{lang}": sum(map(len, xx)),
            "palabras_en": sum(len(t.split()) for t in en),
            f"palabras_{lang}": sum(len(t.split()) for t in xx),
        }
        c = resumen["corpus"][lang]
        c["ratio_caracteres"] = round(c[f"caracteres_{lang}"] / c["caracteres_en"], 4)
        c["ratio_palabras"] = round(c[f"palabras_{lang}"] / c["palabras_en"], 4)

    for visible, (tipo, nombre) in TOKENIZADORES.items():
        contar, ident = cargar_tokenizador(tipo, nombre)
        r = {"id": ident}
        for lang, pares in corpus.items():
            en_tok = [contar(a) for a, _ in pares]
            xx_tok = [contar(b) for _, b in pares]
            for i, ((a, b), ta, tb) in enumerate(zip(pares, en_tok, xx_tok)):
                filas_conteo.append([visible, lang, i, len(a), len(b), ta, tb])
            total_en, total_xx = sum(en_tok), sum(xx_tok)
            lo, hi = bootstrap_ratio(en_tok, xx_tok)
            por_frase = [b / a for a, b in zip(en_tok, xx_tok) if a > 0]
            pal_en = resumen["corpus"][lang]["palabras_en"]
            pal_xx = resumen["corpus"][lang][f"palabras_{lang}"]
            r[lang] = {
                "tokens_en": total_en,
                f"tokens_{lang}": total_xx,
                "ratio_total": round(total_xx / total_en, 4),
                "sobrecoste_pct": round((total_xx / total_en - 1) * 100, 2),
                "ic95_ratio": [round(lo, 4), round(hi, 4)],
                "mediana_ratio_por_frase": round(statistics.median(por_frase), 4),
                "tokens_por_palabra_en": round(total_en / pal_en, 4),
                f"tokens_por_palabra_{lang}": round(total_xx / pal_xx, 4),
                "caracteres_por_token_en": round(resumen["corpus"][lang]["caracteres_en"] / total_en, 4),
                f"caracteres_por_token_{lang}": round(resumen["corpus"][lang][f"caracteres_{lang}"] / total_xx, 4),
            }

        # Velocidad: tokenizar todas las frases en español, una a una.
        textos = [b for _, b in corpus["es"]]
        caracteres = sum(map(len, textos))
        contar(textos[0])  # calentamiento
        tiempos = []
        for rep in range(REPETICIONES):
            t0 = time.perf_counter()
            for t in textos:
                contar(t)
            dt = time.perf_counter() - t0
            tiempos.append(dt)
            filas_tiempo.append([visible, rep, round(dt * 1000, 3), round(caracteres / dt / 1e6, 4)])
        med = statistics.median(tiempos)
        r["velocidad_es"] = {
            "repeticiones": REPETICIONES,
            "mediana_ms": round(med * 1000, 2),
            "min_ms": round(min(tiempos) * 1000, 2),
            "max_ms": round(max(tiempos) * 1000, 2),
            "desviacion_ms": round(statistics.stdev(tiempos) * 1000, 2),
            "mcaracteres_por_s": round(caracteres / med / 1e6, 3),
        }
        resumen["tokenizadores"][visible] = r
        print(f"{visible}: es {r['es']['sobrecoste_pct']} % · pt {r['pt']['sobrecoste_pct']} % · {r['velocidad_es']['mediana_ms']} ms")

    with open(os.path.join(RES, "conteos_por_frase.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tokenizador", "idioma", "frase", "caracteres_en", "caracteres_destino", "tokens_en", "tokens_destino"])
        w.writerows(filas_conteo)
    with open(os.path.join(RES, "tiempos.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tokenizador", "repeticion", "ms", "mcaracteres_por_s"])
        w.writerows(filas_tiempo)

    sob = [v["es"]["sobrecoste_pct"] for v in resumen["tokenizadores"].values()]
    sob_pt = [v["pt"]["sobrecoste_pct"] for v in resumen["tokenizadores"].values()]
    resumen["agregado"] = {
        "es_sobrecoste_min_pct": min(sob),
        "es_sobrecoste_max_pct": max(sob),
        "es_sobrecoste_mediana_pct": round(statistics.median(sob), 2),
        "pt_sobrecoste_min_pct": min(sob_pt),
        "pt_sobrecoste_max_pct": max(sob_pt),
        "pt_sobrecoste_mediana_pct": round(statistics.median(sob_pt), 2),
    }
    resumen["python"] = platform.python_version()
    with open(os.path.join(RES, "resumen.json"), "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
