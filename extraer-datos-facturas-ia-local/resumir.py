"""Resume resultados/*.csv en resultados/resumen.json sin redondear.

Uso: python resumir.py resultados
"""
import csv
import json
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

LETRAS = "TRWAGMYFPDXBNJZSQVHLCKE"


def nif_valido(n):
    """Letra de control de DNI/NIE o dígito de control de CIF."""
    if re.fullmatch(r"[XYZ]?\d{7,8}[A-Z]", n or ""):
        num = int(str("XYZ".find(n[0])) + n[1:-1]) if n[0] in "XYZ" else int(n[:-1])
        return LETRAS[num % 23] == n[-1]
    m = re.fullmatch(r"([ABCDEFGHJNPQRSUVW])(\d{7})([0-9A-J])", n or "")
    if not m:
        return False
    d = [int(c) for c in m[2]]
    suma = d[1] + d[3] + d[5] + sum(sum(divmod(2 * d[i], 10)) for i in (0, 2, 4, 6))
    control = (10 - suma % 10) % 10
    return m[3] in (str(control), "JABCDEFGHI"[control])


res = Path(sys.argv[1] if len(sys.argv) > 1 else "resultados")
ext = list(csv.DictReader(open(res / "extracciones.csv")))
tie = list(csv.DictReader(open(res / "tiempos.csv")))
car = {r["detector"]: float(r["segundos_carga"]) for r in csv.DictReader(open(res / "carga.csv"))}

detectores = list(dict.fromkeys(r["detector"] for r in ext))
out = {"facturas": len({r["factura"] for r in ext}),
       "repeticiones": len({r["repeticion"] for r in ext}),
       "campos_por_factura": len({r["campo"] for r in ext}),
       "facturas_con_retencion_irpf": len({r["factura"] for r in ext if r["campo"] == "retencion_irpf"
                                           and r["esperado"] not in ("0.00", "0", "")}),
       "facturas_por_plantilla": {p: len({r["factura"] for r in ext if r["plantilla"] == p})
                                  for p in sorted({r["plantilla"] for r in ext})},
       "detectores": {}}

for det in detectores:
    filas = [r for r in ext if r["detector"] == det]
    # Por factura y repetición
    porfac = defaultdict(list)
    for r in filas:
        porfac[(r["repeticion"], r["factura"], r["plantilla"])].append(r)
    fac_ok = {k: all(x["correcto"] == "1" for x in v) for k, v in porfac.items()}
    json_ok = {k: v[0]["json_valido"] == "1" for k, v in porfac.items()}
    cuadra = {k: v[0]["cuadra"] == "1" for k, v in porfac.items()}
    # Comprobación aritmética: de las facturas con algún error, cuántas no cuadran (se detectan)
    con_error = [k for k, ok in fac_ok.items() if not ok]
    detectadas = [k for k in con_error if not cuadra[k]]
    # Errores importantes que pasan la comprobación: factura mal leída que cuadra igualmente
    cuadra_y_mal = [k for k in con_error if cuadra[k]]
    # Segunda comprobación: los dos NIF tienen letra o dígito de control válido
    # y son distintos entre sí (emisor y cliente no pueden ser la misma empresa)
    def nifs_bien(v):
        n = {x["campo"]: x["obtenido"] for x in v if x["campo"] in ("nif_emisor", "nif_cliente")}
        return all(nif_valido(x) for x in n.values()) and n["nif_emisor"] != n["nif_cliente"]
    nifs_ok = {k: nifs_bien(v) for k, v in porfac.items()}
    detectadas2 = [k for k in con_error if not cuadra[k] or not nifs_ok[k]]
    # Errores que consisten solo en intercambiar el NIF del emisor y el del cliente
    def solo_intercambio(v):
        mal = {x["campo"]: x for x in v if x["correcto"] != "1"}
        return (set(mal) == {"nif_emisor", "nif_cliente"} and mal["nif_emisor"]["obtenido"] == mal["nif_cliente"]["esperado"]
                and mal["nif_cliente"]["obtenido"] == mal["nif_emisor"]["esperado"])
    intercambios = [k for k in con_error if solo_intercambio(porfac[k])]
    falsas_alarmas = [k for k, ok in fac_ok.items() if ok and (not cuadra[k] or not nifs_ok[k])]
    d = {
        "campos_correctos": sum(r["correcto"] == "1" for r in filas) / len(filas),
        "campos_correctos_n": sum(r["correcto"] == "1" for r in filas),
        "campos_total": len(filas),
        "facturas_perfectas": sum(fac_ok.values()) / len(fac_ok),
        "facturas_perfectas_n": sum(fac_ok.values()),
        "facturas_total": len(fac_ok),
        "json_valido": sum(json_ok.values()) / len(json_ok),
        "facturas_con_error_n": len(con_error),
        "errores_detectados_por_cuadre_n": len(detectadas),
        "errores_que_cuadran_n": len(cuadra_y_mal),
        "errores_que_cuadran_facturas": sorted({k[1] for k in cuadra_y_mal}),
        "errores_detectados_por_cuadre_o_nif_n": len(detectadas2),
        "errores_no_detectados_n": len(con_error) - len(detectadas2),
        "errores_no_detectados_facturas": sorted({k[1] for k in con_error if k not in detectadas2}),
        "errores_solo_intercambio_nif_n": len(intercambios),
        "facturas_perfectas_con_alarma_n": len(falsas_alarmas),
        "facturas_con_nif_sin_letra_n": len({k for k, v in porfac.items() if any(
            x["campo"].startswith("nif") and x["correcto"] != "1" and x["obtenido"] and x["esperado"][:-1] == x["obtenido"]
            for x in v)}),
        "facturas_con_importe_mal_n": len({k for k, v in porfac.items() if any(
            x["campo"] in ("base_imponible", "cuota_iva", "retencion_irpf", "total") and x["correcto"] != "1" for x in v)}),
        "por_campo": {}, "por_plantilla": {}, "por_plantilla_facturas_perfectas": {},
    }
    for c in dict.fromkeys(r["campo"] for r in filas):
        v = [r["correcto"] == "1" for r in filas if r["campo"] == c]
        d["por_campo"][c] = sum(v) / len(v)
    for p in sorted({r["plantilla"] for r in filas}):
        v = [r["correcto"] == "1" for r in filas if r["plantilla"] == p]
        d["por_plantilla"][p] = sum(v) / len(v)
        vf = [ok for k, ok in fac_ok.items() if k[2] == p]
        d["por_plantilla_facturas_perfectas"][p] = sum(vf) / len(vf)
    # Lo mismo contado por factura en la primera repetición (las salidas fueron idénticas en las 5)
    r1 = [k for k in porfac if k[0] == "1"]
    err1 = [k for k in r1 if not fac_ok[k]]
    d["rep1_facturas"] = {
        "facturas": len(r1),
        "perfectas": sum(fac_ok[k] for k in r1),
        "con_error": len(err1),
        "detectadas_por_cuadre": sum(not cuadra[k] for k in err1),
        "detectadas_por_cuadre_o_nif": sum(k in detectadas2 for k in err1),
        "no_detectadas": sum(k not in detectadas2 for k in err1),
        "solo_intercambio_nif": sum(k in intercambios for k in err1),
        "nif_sin_letra": sum(any(x["campo"].startswith("nif") and x["correcto"] != "1" and x["obtenido"]
                                 and x["esperado"][:-1] == x["obtenido"] for x in porfac[k]) for k in r1),
        "importe_mal": sum(any(x["campo"] in ("base_imponible", "cuota_iva", "retencion_irpf", "total")
                               and x["correcto"] != "1" for x in porfac[k]) for k in r1),
        "perfectas_por_plantilla": {p: sum(fac_ok[k] for k in r1 if k[2] == p) for p in sorted({k[2] for k in r1})},
    }
    # Estabilidad entre repeticiones: ¿la salida de cada campo es idéntica en todas?
    salidas = defaultdict(set)
    for r in filas:
        salidas[(r["factura"], r["campo"])].add(r["obtenido"])
    d["campos_con_salida_distinta_entre_repeticiones"] = sum(len(s) > 1 for s in salidas.values())
    # Ejemplos de errores (primera repetición)
    d["errores_rep1"] = [{"factura": r["factura"], "plantilla": r["plantilla"], "campo": r["campo"],
                          "esperado": r["esperado"], "obtenido": r["obtenido"]}
                         for r in filas if r["repeticion"] == "1" and r["correcto"] == "0"]
    # Tiempos
    t = [r for r in tie if r["detector"] == det]
    seg = [float(r["segundos"]) for r in t]
    total_rep = defaultdict(float)
    for r in t:
        total_rep[r["repeticion"]] += float(r["segundos"])
    d["segundos_por_factura"] = {"mediana": st.median(seg), "p10": st.quantiles(seg, n=10)[0],
                                 "p90": st.quantiles(seg, n=10)[-1], "min": min(seg), "max": max(seg),
                                 "n": len(seg)}
    d["minutos_300_facturas"] = st.median(seg) * 300 / 60
    d["segundos_por_pasada"] = {"mediana": st.median(total_rep.values()), "min": min(total_rep.values()),
                                "max": max(total_rep.values()), "n": len(total_rep)}
    if det != "reglas":
        d["generacion_tps_mediana"] = st.median(float(r["generacion_tps"]) for r in t)
        d["prompt_tps_mediana"] = st.median(float(r["prompt_tps"]) for r in t)
        d["tokens_prompt_mediana"] = st.median(int(r["tokens_prompt"]) for r in t)
        d["memoria_pico_gb_max"] = max(float(r["memoria_pico_gb"]) for r in t)
    d["segundos_carga"] = car.get(det)
    out["detectores"][det] = d

(res / "resumen.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
for det, d in out["detectores"].items():
    print(f"{det:24s} campos {d['campos_correctos']:.4f} facturas {d['facturas_perfectas']:.4f} "
          f"json {d['json_valido']:.4f} s/fac {d['segundos_por_factura']['mediana']:.4f} "
          f"errores {d['facturas_con_error_n']} cuadre {d['errores_detectados_por_cuadre_n']} "
          f"cuadre+nif {d['errores_detectados_por_cuadre_o_nif_n']} sin detectar {d['errores_no_detectados_n']} "
          f"intercambio {d['errores_solo_intercambio_nif_n']} alarmas {d['facturas_perfectas_con_alarma_n']}")
