"""Resume resultados/medidas.jsonl: mediana, mínimo, máximo y desviación por motor y tamaño.

Escribe resultados/resumen.csv, resultados/resumen.json y resultados/derivados.json
(cocientes frente a la búsqueda exacta con numpy, calculados sin redondear).
"""

import csv
import json
import os
import statistics as st
from collections import defaultdict

AQUI = os.path.dirname(os.path.abspath(__file__))
RESULTADOS = os.path.join(AQUI, "resultados")
METRICAS = ["indexado_s", "vectores_por_s", "disco_mb", "reapertura_ms", "lat_p50_ms", "lat_p95_ms",
            "lat_media_ms", "consultas_por_s", "recall_10", "memoria_extra_mb"]


def main() -> None:
    grupos = defaultdict(list)
    for linea in open(os.path.join(RESULTADOS, "medidas.jsonl"), encoding="utf-8"):
        m = json.loads(linea)
        grupos[(m["motor"], m["n"])].append(m)

    resumen = []
    for (motor, n), medidas in sorted(grupos.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        fila = {"motor": motor, "n": n, "repeticiones": len(medidas)}
        for k in METRICAS:
            v = [m[k] for m in medidas]
            fila[f"{k}_mediana"] = st.median(v)
            fila[f"{k}_min"] = min(v)
            fila[f"{k}_max"] = max(v)
            fila[f"{k}_desv"] = st.stdev(v) if len(v) > 1 else 0.0
        resumen.append(fila)

    with open(os.path.join(RESULTADOS, "resumen.json"), "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=2)
    with open(os.path.join(RESULTADOS, "resumen.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(resumen[0].keys()))
        w.writeheader()
        w.writerows(resumen)

    por = {(r["motor"], r["n"]): r for r in resumen}
    derivados = {}
    for (motor, n), r in por.items():
        base = por.get(("numpy", n))
        if not base:
            continue
        derivados[f"{motor}_{n}"] = {
            "lat_p50_vs_numpy": r["lat_p50_ms_mediana"] / base["lat_p50_ms_mediana"],
            "disco_vs_numpy": r["disco_mb_mediana"] / base["disco_mb_mediana"],
            "indexado_vs_numpy": r["indexado_s_mediana"] / base["indexado_s_mediana"],
            "recall_perdido_puntos": (1 - r["recall_10_mediana"]) * 100,
        }
        otro = por.get((motor, 10_000 if n == 100_000 else 100_000))
        if n == 100_000 and otro:
            derivados[f"{motor}_{n}"]["lat_p50_100k_vs_10k"] = r["lat_p50_ms_mediana"] / otro["lat_p50_ms_mediana"]
    with open(os.path.join(RESULTADOS, "derivados.json"), "w", encoding="utf-8") as f:
        json.dump(derivados, f, ensure_ascii=False, indent=2)

    for r in resumen:
        print(f"{r['n']:>7d} {r['motor']:14s} idx {r['indexado_s_mediana']:8.2f}s  disco {r['disco_mb_mediana']:8.1f}MB  "
              f"reab {r['reapertura_ms_mediana']:8.1f}ms  p50 {r['lat_p50_ms_mediana']:8.3f}  p95 {r['lat_p95_ms_mediana']:8.3f}  "
              f"recall {r['recall_10_mediana']:.4f}  mem {r['memoria_extra_mb_mediana']:7.1f}MB")


if __name__ == "__main__":
    main()
