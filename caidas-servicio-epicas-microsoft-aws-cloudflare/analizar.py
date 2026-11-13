"""Caídas épicas de servicios en la nube: qué las provoca, cuánto duran y cada cuánto falla lo que usa una pyme.

Dos fuentes:
  1. datos/caidas.json: las grandes caídas de 2021 a 2026 con las horas de su informe oficial.
  2. resultados/incidentes.csv (recolectar.py): incidentes publicados en las páginas de estado de 31 servicios.

    uv run --with matplotlib python analizar.py

Escribe resultados/resumen.json, resultados/top_caidas.csv, resultados/servicios.csv y los gráficos.
Redondeo: una sola vez, al final, a la mitad hacia arriba.
"""

import csv
import json
import os
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(AQUI, "resultados")
GRAF = os.path.join(RES, "graficos")
os.makedirs(GRAF, exist_ok=True)

TINTA, TINTA2, LINEA, PAPEL, PAPEL2, GRIS = "#0a0b0a", "#181b18", "#343a34", "#ecebe4", "#b9b8ae", "#7e7e74"
ACIDO, ALERTA, FRIO = "#d4ff3a", "#ff5a36", "#8fb4ff"
plt.rcParams.update({"figure.facecolor": TINTA, "axes.facecolor": TINTA, "savefig.facecolor": TINTA,
                     "text.color": PAPEL, "axes.labelcolor": PAPEL2, "xtick.color": PAPEL2, "ytick.color": PAPEL2,
                     "axes.edgecolor": LINEA, "font.family": "DejaVu Sans", "font.size": 11})

# Pila de ejemplo de una pyme de servicios: web, correo masivo, CRM, reuniones, archivos, tareas, automatización e IA
PILA_PYME = ["Wix", "HubSpot", "Zoom", "Dropbox", "Notion", "Asana", "Zapier", "OpenAI"]
# ClickUp devuelve incidentes importados con fecha de resolución anterior a la de creación: sus datos no son medibles
EXCLUIDOS = {"ClickUp": "incidentes importados con resolución anterior a la creación"}


def r(x, d=1):
    q = Decimal(1).scaleb(-d) if d else Decimal(1)
    return float(Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP))


def coma(x, d=1):
    return f"{r(x, d):.{d}f}".replace(".", ",")


def f(t):
    return datetime.fromisoformat(t) if t else None


def top_caidas():
    datos = json.load(open(os.path.join(AQUI, "datos", "caidas.json"), encoding="utf-8"))
    filas = []
    for c in datos["caidas"]:
        ini = f(c["inicio"])
        fin = f(c["fin"]) if c.get("fin") else f(c["ultima_consulta"])
        horas = (fin - ini).total_seconds() / 3600
        filas.append({**c, "horas": horas, "horas_completo": (f(c["fin_completo"]) - ini).total_seconds() / 3600 if c.get("fin_completo") else None,
                      "horas_parcial": (f(c["fin_parcial"]) - ini).total_seconds() / 3600 if c.get("fin_parcial") else None,
                      "anio": ini.year})
    return filas, datos["espana"]


def incidentes():
    filas = list(csv.DictReader(open(os.path.join(RES, "incidentes.csv"), encoding="utf-8")))
    fuentes = json.load(open(os.path.join(RES, "fuentes_estado.json"), encoding="utf-8"))
    consulta = max(datetime.fromisoformat(v["consultado"]) for v in fuentes.values() if "consultado" in v)
    por = defaultdict(list)
    for x in filas:
        if x["mantenimiento"] == "1" or not x["inicio"] or x["servicio"] in EXCLUIDOS:
            continue
        x["ini"], x["fin"] = f(x["inicio"]), f(x["resuelto"])
        por[x["servicio"]].append(x)
    return por, fuentes, consulta


def dias_con_incidente(lista, desde, hasta):
    """Días (UTC) con al menos un incidente activo, dentro de [desde, hasta)."""
    dias = set()
    for x in lista:
        a, b = max(x["ini"], desde), min(x["fin"] or hasta, hasta)
        d = a.date()
        while datetime.combine(d, datetime.min.time(), timezone.utc) < b:
            dias.add(d)
            d += timedelta(days=1)
    return dias


def main():
    top, espana = top_caidas()
    por, fuentes, consulta = incidentes()

    # --- 1. Grandes caídas ---
    confirmadas = [c for c in top if not c.get("en_curso")]
    tipos = Counter(c["causa_tipo"] for c in confirmadas)
    con_cambio = [c for c in confirmadas if c["causa_tipo"] != "Automatización + fallo latente"]
    latentes = [c for c in confirmadas if c["fallo_latente"]]
    ranking = sorted(top, key=lambda c: -c["horas"])

    # --- 2. Páginas de estado ---
    servicios, todas = [], []
    for nombre, lista in por.items():
        dur = [(x["fin"] - x["ini"]).total_seconds() / 3600 for x in lista if x["fin"] and x["fin"] >= x["ini"]]
        desde = min(x["ini"] for x in lista)
        ventana = (consulta - desde).total_seconds() / 86400
        dias_naturales = (consulta.date() - desde.date()).days + 1
        dias = dias_con_incidente(lista, desde, consulta)
        graves = [x for x in lista if x["impacto"] in ("major", "critical")]
        dias_graves = dias_con_incidente(graves, desde, consulta)
        servicios.append({
            "servicio": nombre, "categoria": lista[0]["categoria"], "incidentes": len(lista), "ventana_dias": ventana,
            "incidentes_30d": len(lista) / ventana * 30, "graves": len(graves), "pct_graves": 100 * len(graves) / len(lista),
            "duracion_mediana_h": statistics.median(dur) if dur else None,
            "pct_dias_con_incidente": 100 * len(dias) / dias_naturales,
            "pct_dias_con_grave": 100 * len(dias_graves) / dias_naturales,
        })
        todas += dur
    servicios.sort(key=lambda s: -s["incidentes_30d"])
    n_inc = sum(s["incidentes"] for s in servicios)
    pila = [s for s in servicios if s["servicio"] in PILA_PYME]
    prob_ningun = prob_ningun_grave = 1.0
    for s in pila:
        prob_ningun *= 1 - s["pct_dias_con_incidente"] / 100
        prob_ningun_grave *= 1 - s["pct_dias_con_grave"] / 100
    dias_mes_alguna = 30 * (1 - prob_ningun)
    dias_mes_grave = 30 * (1 - prob_ningun_grave)
    graves_total = sum(s["graves"] for s in servicios)

    resumen = {
        "grandes_caidas": {
            "n": len(top), "confirmadas": len(confirmadas), "en_curso": [c["id"] for c in top if c.get("en_curso")],
            "por_tipo_de_disparador": dict(tipos),
            "empezaron_con_un_cambio": len(con_cambio), "con_fallo_latente": len(latentes),
            "por_ataque": sum(c["ataque"] for c in confirmadas),
            "ranking_horas": [{"id": c["id"], "empresa": c["empresa"], "horas": r(c["horas"]), "dias": r(c["horas"] / 24),
                               "horas_completo": r(c["horas_completo"]) if c["horas_completo"] else None,
                               "horas_parcial": r(c["horas_parcial"]) if c["horas_parcial"] else None,
                               "en_curso": bool(c.get("en_curso"))} for c in ranking],
            "mediana_horas_confirmadas": r(statistics.median(c["horas"] for c in confirmadas)),
        },
        "paginas_de_estado": {
            "consultado": consulta.isoformat(timespec="minutes"), "servicios": len(servicios), "incidentes": n_inc,
            "duracion_mediana_h": r(statistics.median(todas), 2),
            "pct_resueltos_menos_1h": r(100 * sum(d < 1 for d in todas) / len(todas)),
            "pct_resueltos_menos_4h": r(100 * sum(d < 4 for d in todas) / len(todas)),
            "pct_mas_24h": r(100 * sum(d >= 24 for d in todas) / len(todas)),
            "pct_graves": r(100 * graves_total / n_inc),
            "mediana_incidentes_30d": r(statistics.median(s["incidentes_30d"] for s in servicios)),
            "mediana_pct_dias_con_incidente": r(statistics.median(s["pct_dias_con_incidente"] for s in servicios)),
            "excluidos": EXCLUIDOS,
            "mediana_pct_dias_con_grave": r(statistics.median(s["pct_dias_con_grave"] for s in servicios)),
            "pila_pyme": {"servicios": PILA_PYME, "dias_al_mes_con_alguna_incidencia": r(dias_mes_alguna),
                          "dias_al_mes_con_alguna_grave": r(dias_mes_grave),
                          "supuesto": "fallos independientes entre servicios; % de días con incidente medido en la ventana de cada uno"},
            "por_servicio": [{k: (r(v) if isinstance(v, float) else v) for k, v in s.items()} for s in servicios],
        },
    }
    json.dump(resumen, open(os.path.join(RES, "resumen.json"), "w"), ensure_ascii=False, indent=1)
    with open(os.path.join(RES, "top_caidas.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["puesto", "empresa", "servicio", "inicio", "horas", "disparador", "alcance", "fuente"])
        for i, c in enumerate(ranking, 1):
            w.writerow([i, c["empresa"], c["servicio"], c["inicio"], r(c["horas"]), c["causa_tipo"], c["alcance"], c["fuente"]])
    with open(os.path.join(RES, "servicios.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(servicios[0]))
        w.writeheader()
        w.writerows([{k: (r(v, 2) if isinstance(v, float) else v) for k, v in s.items()} for s in servicios])

    # --- Gráficos ---
    # 1. Duración de las grandes caídas (escala logarítmica)
    fig, ax = plt.subplots(figsize=(10, 5.6))
    orden = list(reversed(ranking))
    etiquetas = [f"{c['empresa']} ({c['anio']})" for c in orden]
    colores = [FRIO if c.get("en_curso") else (ALERTA if c["horas"] >= 24 else ACIDO) for c in orden]
    ax.barh(etiquetas, [c["horas"] for c in orden], color=colores, height=0.62)
    ax.set_xscale("log")
    for i, c in enumerate(orden):
        h = c["horas"]
        txt = (f"{coma(h / 24)} días" if h >= 48 else f"{coma(h)} h") + (" y sigue" if c.get("en_curso") else "")
        ax.text(h * 1.08, i, txt, va="center", fontsize=10, color=PAPEL)
    ax.set_xlabel("Horas hasta la recuperación según el informe oficial (escala logarítmica)")
    ax.set_xlim(0.5, 2000)
    ax.set_xticks([1, 10, 100, 1000])
    ax.set_xticklabels(["1 h", "10 h", "100 h", "1.000 h"])
    ax.grid(axis="x", color=LINEA, linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_title("Las grandes caídas de 2021 a 2026, por duración", loc="left", fontsize=14, color=PAPEL, pad=12)
    fig.tight_layout()
    fig.savefig(os.path.join(GRAF, "duracion_grandes_caidas.png"), dpi=160)
    plt.close(fig)

    # 2. Qué las disparó
    fig, ax = plt.subplots(figsize=(10, 4.2))
    t = tipos.most_common()
    ax.barh([k for k, _ in reversed(t)], [v for _, v in reversed(t)], color=ACIDO, height=0.6)
    for i, (_, v) in enumerate(reversed(t)):
        ax.text(v + 0.05, i, str(v), va="center", color=PAPEL)
    ax.set_xlabel(f"Grandes caídas con causa confirmada ({len(confirmadas)})")
    ax.xaxis.get_major_locator().set_params(integer=True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_title("Qué las disparó: ningún ataque, casi siempre un cambio propio", loc="left", fontsize=14, color=PAPEL, pad=12)
    fig.tight_layout()
    fig.savefig(os.path.join(GRAF, "disparadores.png"), dpi=160)
    plt.close(fig)

    # 3. % de días con alguna incidencia publicada, por servicio
    fig, ax = plt.subplots(figsize=(10, 9))
    orden = sorted(servicios, key=lambda s: s["pct_dias_con_incidente"])
    ax.barh([s["servicio"] for s in orden], [s["pct_dias_con_incidente"] for s in orden],
            color=[ALERTA if s["servicio"] in PILA_PYME else GRIS for s in orden], height=0.66)
    for i, s in enumerate(orden):
        ax.text(s["pct_dias_con_incidente"] + 0.8, i, f"{r(s['pct_dias_con_incidente'], 0):.0f} %", va="center", fontsize=9, color=PAPEL2)
    ax.set_xlabel("% de días con alguna incidencia publicada en su página de estado (en la ventana que cubre su API)")
    ax.set_xlim(0, 105)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.set_title("Cada cuánto avisa de problemas lo que usa una pyme", loc="left", fontsize=14, color=PAPEL, pad=12)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.text(0.01, 0.01, "En rojo, la pila de ejemplo de una pyme de servicios. Más avisos no es peor servicio: cada empresa publica con su criterio.",
             fontsize=9, color=GRIS)
    fig.savefig(os.path.join(GRAF, "dias_con_incidencia.png"), dpi=160)
    plt.close(fig)

    # 4. Distribución de la duración de los incidentes publicados
    fig, ax = plt.subplots(figsize=(10, 4.4))
    tramos = [(0, 0.5, "< 30 min"), (0.5, 1, "30–60 min"), (1, 2, "1–2 h"), (2, 4, "2–4 h"), (4, 8, "4–8 h"), (8, 24, "8–24 h"), (24, 1e9, "> 24 h")]
    cuenta = [sum(a <= d < b for d in todas) for a, b, _ in tramos]
    ax.bar([t[2] for t in tramos], [100 * c / len(todas) for c in cuenta], color=FRIO, width=0.66)
    for i, c in enumerate(cuenta):
        ax.text(i, 100 * c / len(todas) + 0.6, f"{coma(100 * c / len(todas))} %", ha="center", fontsize=9, color=PAPEL)
    ax.set_ylabel("% de incidentes")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.set_title(f"Cuánto duran los {len(todas):,} incidentes resueltos de las páginas de estado".replace(",", "."), loc="left", fontsize=14, color=PAPEL, pad=12)
    fig.tight_layout()
    fig.savefig(os.path.join(GRAF, "duracion_incidentes.png"), dpi=160)
    plt.close(fig)

    print(json.dumps({k: v for k, v in resumen["paginas_de_estado"].items() if k != "por_servicio"}, ensure_ascii=False, indent=1))
    print(json.dumps(resumen["grandes_caidas"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
