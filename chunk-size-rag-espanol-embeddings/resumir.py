"""Comparaciones derivadas de resultados/resumen.json (diferencias en puntos, coste del solapamiento, tiempos).

    .venv/bin/python resumir.py
"""

import json
from pathlib import Path

RES = Path(__file__).parent / "resultados"
d = json.loads((RES / "resumen.json").read_text())
cfg = {(c["modelo"], c["tamano"], c["solape"]): c for c in d["configuraciones"]}
modelos = list(dict.fromkeys(c["modelo"] for c in d["configuraciones"]))
tamanos = sorted({c["tamano"] for c in d["configuraciones"]})
metricas = ["recall@1_pct", "recall@3_pct", "recall@5_pct", "recall_presupuesto_1024_pct", "recall_presupuesto_2048_pct"]

salida = {"pequeno_vs_grande": [], "solapamiento": [], "mejor_por_modelo": {}, "tiempo_indexado_vs_e5_small": {}}
for m in modelos:
    for s in (0.0, 0.2):
        a, b = cfg[(m, tamanos[0], s)], cfg[(m, tamanos[-1], s)]
        salida["pequeno_vs_grande"].append({"modelo": m, "solape": s, "de": tamanos[0], "a": tamanos[-1],
                                            **{f"dif_puntos_{k}": round(a[k] - b[k], 1) for k in metricas}})
    for t in tamanos:
        a, b = cfg[(m, t, 0.0)], cfg[(m, t, 0.2)]
        salida["solapamiento"].append({"modelo": m, "tamano": t,
                                       "chunks_extra_pct": round(100 * (b["chunks"] / a["chunks"] - 1), 1),
                                       **{f"dif_puntos_{k}": round(b[k] - a[k], 1) for k in metricas}})
    for k in metricas:
        mejor = max((c for c in d["configuraciones"] if c["modelo"] == m), key=lambda c: c[k])
        salida["mejor_por_modelo"].setdefault(m, {})[k] = {"tamano": mejor["tamano"], "solape": mejor["solape"], "valor": mejor[k]}
base = "multilingual-e5-small"
for m in modelos:
    salida["tiempo_indexado_vs_e5_small"][m] = {
        str(t): round(cfg[(m, t, 0.0)]["indexar_mediana_s"] / cfg[(base, t, 0.0)]["indexar_mediana_s"], 1) for t in tamanos}
deltas = [abs(x[f"dif_puntos_recall@5_pct"]) for x in salida["solapamiento"]]
salida["solapamiento_max_efecto_recall@5_puntos"] = max(deltas)
(RES / "derivados.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1))
print(json.dumps(salida, ensure_ascii=False, indent=1))
