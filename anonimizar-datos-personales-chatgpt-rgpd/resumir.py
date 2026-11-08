"""Resume resultados/*.csv en resultados/resumen.json (valores sin redondear).

    .venv/bin/python resumir.py

- escapan: fracción de datos personales que no quedan tapados del todo (alguna letra o cifra visible).
- escapan_enteros: fracción que no queda tapada en absoluto (cobertura 0).
- docs_con_fuga: fracción de documentos con al menos un dato que no queda tapado del todo.
- de_mas: fracción del texto que no era dato personal y se tapó igualmente (sobreanonimización).
- cobertura_media_por_tipo: fracción media de letras y cifras tapadas de cada dato.
- ms_por_documento: mediana, mínimo y máximo de las 5 repeticiones.
"""

import json
import os

import pandas as pd

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultados")


def main():
    ent = pd.read_csv(os.path.join(RES, "por_entidad.csv"))
    doc = pd.read_csv(os.path.join(RES, "por_documento.csv"))
    tiem = pd.read_csv(os.path.join(RES, "tiempos.csv"))
    carga = pd.read_csv(os.path.join(RES, "carga.csv"))

    ent["fuga"] = ent["cobertura"] < 1.0
    ent["fuga_entera"] = ent["cobertura"] == 0.0
    resumen = {"documentos": int(doc["doc"].nunique()), "datos_personales": int(len(ent) / ent["detector"].nunique()),
               "datos_por_tipo": ent[ent["detector"] == "regex"]["entidad"].value_counts().to_dict(),
               "detectores": {}}
    for det, g in ent.groupby("detector"):
        d = doc[doc["detector"] == det]
        r = {
            "escapan": g["fuga"].mean(),
            "escapan_n": int(g["fuga"].sum()),
            "escapan_enteros": g["fuga_entera"].mean(),
            "docs_con_fuga": g.groupby("doc")["fuga"].any().mean(),
            "docs_con_fuga_n": int(g.groupby("doc")["fuga"].any().sum()),
            "de_mas": d["caracteres_de_mas"].sum() / d["caracteres_no_personales"].sum(),
            "escapan_por_tipo": g.groupby("entidad")["fuga"].mean().to_dict(),
            "escapan_por_tipo_n": g.groupby("entidad")["fuga"].sum().astype(int).to_dict(),
            "cobertura_media_por_tipo": g.groupby("entidad")["cobertura"].mean().to_dict(),
            "escapan_por_formato": {f"{e}/{f}": v for (e, f), v in g.groupby(["entidad", "formato"])["fuga"].mean().items()},
            "escapan_por_tipo_doc": g.groupby("tipo_doc")["fuga"].mean().to_dict(),
        }
        t = tiem[tiem["detector"] == det]["ms_por_documento"]
        if len(t):
            r["ms_por_documento"] = {"mediana": t.median(), "min": t.min(), "max": t.max(), "n": int(len(t))}
            r["segundos_total_mediana"] = tiem[tiem["detector"] == det]["segundos_total"].median()
        c = carga[carga["detector"] == det]["segundos_carga"]
        if len(c):
            r["segundos_carga"] = float(c.iloc[0])
        resumen["detectores"][det] = r

    with open(os.path.join(RES, "resumen.json"), "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=2)
    filas = []
    for det, r in resumen["detectores"].items():
        filas.append((det, r["escapan"], r["docs_con_fuga"], r["de_mas"], r.get("ms_por_documento", {}).get("mediana")))
    for f in sorted(filas, key=lambda x: x[1]):
        print(*f)


if __name__ == "__main__":
    main()
