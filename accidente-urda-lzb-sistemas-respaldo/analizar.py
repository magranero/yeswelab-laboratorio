"""Accidente de Urda (28/10/2026): análisis de las capas de protección, la cronología y los telefonemas.

Solo usa datos publicados (datos/hechos.json, datos/cronologia.csv) y el texto literal del Reglamento de
Circulación Ferroviaria (datos/telefonemas.json). No hay mediciones propias del tren: hay cálculos
reproducibles sobre esos datos, con cada hipótesis por separado cuando las fuentes no coinciden.

    uv run --with matplotlib python analizar.py
"""

import csv
import json
import os
import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(AQUI, "resultados")
GRAF = os.path.join(RES, "graficos")
os.makedirs(GRAF, exist_ok=True)

TINTA, TINTA2, LINEA, PAPEL, PAPEL2, GRIS = "#0a0b0a", "#181b18", "#343a34", "#ecebe4", "#b9b8ae", "#7e7e74"
ACIDO, ALERTA, FRIO = "#d4ff3a", "#ff5a36", "#8fb4ff"
plt.rcParams.update({"figure.facecolor": TINTA, "axes.facecolor": TINTA, "savefig.facecolor": TINTA,
                     "text.color": PAPEL, "axes.labelcolor": PAPEL2, "xtick.color": PAPEL2, "ytick.color": PAPEL2,
                     "axes.edgecolor": LINEA, "font.size": 10, "font.family": "DejaVu Sans"})


def r(x, d=1):
    """Redondeo único, a la mitad hacia arriba."""
    return float(Decimal(str(x)).quantize(Decimal(1).scaleb(-d), ROUND_HALF_UP))


def minutos(a: str, b: str) -> int:
    f = "%H:%M"
    return int((datetime.strptime(b, f) - datetime.strptime(a, f)).total_seconds() // 60)


hechos = json.load(open(os.path.join(AQUI, "datos", "hechos.json"), encoding="utf-8"))
tel = json.load(open(os.path.join(AQUI, "datos", "telefonemas.json"), encoding="utf-8"))
crono = list(csv.DictReader(open(os.path.join(AQUI, "datos", "cronologia.csv"), encoding="utf-8")))

# ---------- 1. Ventanas de tiempo y velocidades implícitas, por hipótesis de hora del impacto ----------
impactos = [(v["valor"], v["fuente"]) for v in hechos["hora_impacto"]["valores"]]
dist_km = hechos["distancia_entre_trenes_km"]["valor"]
CAIDA, ORDEN_AVE, AVISO_IRYO, SEGUNDO_AVISO = "08:30", "08:36", "08:41", "08:48"
ventanas = []
for hora, fuente in impactos:
    m_orden = minutos(ORDEN_AVE, hora)
    ventanas.append({
        "hipotesis_impacto": hora, "fuente": fuente,
        "min_desde_caida_lzb": minutos(CAIDA, hora),
        "min_desde_orden_marcha_normal": m_orden,
        "min_desde_primer_aviso_iryo": minutos(AVISO_IRYO, hora),
        "min_desde_segundo_aviso_iryo": minutos(SEGUNDO_AVISO, hora),
        "velocidad_media_implicita_kmh": r(dist_km / (m_orden / 60)) if m_orden else None,
    })
# Referencia: cuánto se tarda en recorrer esa distancia a velocidades de referencia
recorridos = [{"velocidad_kmh": v, "minutos_para_25_km": r(dist_km / v * 60)} for v in (40, 130, 200, 300)]

# Distancia de frenado ilustrativa d = v² / (2a). NO son valores normativos: deceleraciones supuestas.
frenado = []
for v in (40, 80, 130, 200):
    for a in (0.5, 0.7, 1.0):
        ms = v / 3.6
        frenado.append({"velocidad_kmh": v, "deceleracion_supuesta_ms2": a, "distancia_m": round(ms * ms / (2 * a))})

# ---------- 2. Los telefonemas: cuánto se parecen y a cuál se parece la orden dada ----------
def palabras(t):
    t = re.sub(r"\(.*?\)|_+|«|»|\"", " ", t.lower())
    return [w for w in re.findall(r"[a-záéíóúñ0-9]+", t)]


def jaccard(a, b):
    A, B = set(palabras(a)), set(palabras(b))
    return len(A & B) / len(A | B)


def prefijo_comun(a, b):
    n = 0
    for x, y in zip(palabras(a), palabras(b)):
        if x != y:
            break
        n += 1
    return n


t52, t53, t53b, orden = tel["5ET3.2"]["texto"], tel["5ET3.3"]["texto"], tel["5ET3.3_bis"]["texto"], tel["orden_dada"]["texto"]
telefonemas = {
    "similitud_5ET3.2_vs_5ET3.3": r(100 * jaccard(t52, t53)),
    "similitud_5ET3.3_vs_5ET3.3_bis": r(100 * jaccard(t53, t53b)),
    "orden_dada_vs_5ET3.2": r(100 * jaccard(orden, t52)),
    "orden_dada_vs_5ET3.3": r(100 * jaccard(orden, t53)),
    "palabras_iniciales_identicas_5ET3.3_vs_5ET3.3_bis": prefijo_comun(t53, t53b),
    "codigos_5ET3.3_distintos_en_la_misma_pagina": 2,
    "paginas_boe": [tel["5ET3.2"]["pagina_boe"], tel["5ET3.3"]["pagina_boe"]],
    "velocidad_5ET3.2": tel["5ET3.2"]["velocidad"], "velocidad_5ET3.3": tel["5ET3.3"]["velocidad"],
    "palabras_5ET3.2": len(palabras(t52)), "palabras_5ET3.3": len(palabras(t53)),
}

# ---------- 3. Capas de protección: qué hizo cada una ----------
capas = [
    {"capa": "LZB (control continuo en cabina)", "funcion": "Supervisa velocidad y distancia al tren de delante y frena solo",
     "estado": "caído", "detalle": "La central de Urda pierde la comunicación hacia las 8:30; el AVE informa de meta 0 (vía ocupada)"},
    {"capa": "BSL + señales laterales", "funcion": "Bloqueo con señales al lado de la vía cuando no hay LZB",
     "estado": "activo", "detalle": "La señal de entrada de Urda protegía al Iryo detenido; no se sabe si el AVE rebasó alguna en rojo"},
    {"capa": "ASFA", "funcion": "Frena en puntos concretos (balizas) si se ignora una señal",
     "estado": "sin datos", "detalle": "Su actuación solo se sabrá con las cajas negras"},
    {"capa": "Procedimiento (telefonema)", "funcion": "Fija cómo se reanuda la marcha con el sistema degradado",
     "estado": "fallo", "detalle": "Con meta 000 tocaba el 5ET3.2 (marcha a la vista); se usó el 5ET3.3 con «marcha normal»"},
    {"capa": "Supervisión de la sala", "funcion": "Segunda persona que detecta y corrige la orden",
     "estado": "fallo", "detalle": "La orden no se rectificó entre las 8:36 y el impacto"},
    {"capa": "Comunicación tren a tren", "funcion": "Avisar al AVE de que el Iryo seguía parado",
     "estado": "fallo", "detalle": "El Iryo comunica a las 8:41 y a las 8:48 que sigue detenido; no consta aviso al AVE"},
]

identificadores = {"pk_impacto": 118, "trenes": {"AVE": 2080, "Iryo": 6076, "mencionado_en_la_sala": 2061}}
json.dump({"identificadores": identificadores, "ventanas": ventanas, "recorridos_25_km": recorridos, "frenado_ilustrativo": frenado,
           "telefonemas": telefonemas, "capas": capas,
           "fuentes_discrepantes": {k: hechos[k] for k in ("trenes_detenidos", "km_sin_lzb", "hora_impacto")}},
          open(os.path.join(RES, "resumen.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
with open(os.path.join(RES, "ventanas.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(ventanas[0]))
    w.writeheader(); w.writerows(ventanas)
with open(os.path.join(RES, "frenado_ilustrativo.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(frenado[0]))
    w.writeheader(); w.writerows(frenado)


# ---------- 4. Diagramas ----------
def guardar(fig, nombre):
    fig.savefig(os.path.join(GRAF, nombre), dpi=150, bbox_inches="tight")
    plt.close(fig)


# 4.1 Capas de protección (queso suizo)
COLOR = {"caído": ALERTA, "fallo": ALERTA, "activo": ACIDO, "sin datos": GRIS}
CORTO = ["LZB\n(control continuo)", "BSL +\nseñales laterales", "ASFA\n(balizas)", "Procedimiento\n(telefonema)", "Supervisión\nde la sala", "Aviso\nal AVE"]
fig, ax = plt.subplots(figsize=(11, 5.6))
ax.set_xlim(0, 12); ax.set_ylim(-0.6, 6.4); ax.axis("off")
for i, c in enumerate(capas):
    x = 0.4 + i * 1.95
    ax.add_patch(FancyBboxPatch((x, 0.6), 1.5, 4.6, boxstyle="round,pad=0.02,rounding_size=0.08",
                                facecolor=TINTA2, edgecolor=COLOR[c["estado"]], lw=2))
    if c["estado"] in ("caído", "fallo"):
        ax.add_patch(plt.Circle((x + 0.75, 2.9), 0.32, facecolor=TINTA, edgecolor=ALERTA, lw=2))
    ax.text(x + 0.75, 5.4, CORTO[i], ha="center", va="bottom", fontsize=8.6, color=PAPEL, linespacing=1.3)
    ax.text(x + 0.75, 0.35, c["estado"].upper(), ha="center", va="top", fontsize=8.5, color=COLOR[c["estado"]], fontweight="bold")
ax.add_patch(FancyArrowPatch((0.05, 2.9), (11.95, 2.9), arrowstyle="-|>", mutation_scale=18, color=ALERTA, lw=1.6, ls="--"))
ax.text(6, -0.45, "Defensa en profundidad: el alcance se produce cuando la secuencia atraviesa todas las capas que fallaron",
        ha="center", fontsize=9, color=PAPEL2)
guardar(fig, "capas_de_proteccion.png")

# 4.2 Cronología con las tres hipótesis de impacto
fig, ax = plt.subplots(figsize=(11, 4.4))
base = datetime.strptime("08:28", "%H:%M")
mx = lambda h: (datetime.strptime(h, "%H:%M") - base).total_seconds() / 60
filas = {"Central LZB": 3, "AVE 2080": 2, "Iryo 6076": 1, "Sala Atocha": 0}
eventos = [("08:30", "Central LZB", "Cae el LZB", ALERTA), ("08:31", "AVE 2080", "Meta 0", PAPEL2),
           ("08:36", "AVE 2080", "Orden «marcha normal»", ALERTA), ("08:41", "Iryo 6076", "Parada ante señal", PAPEL2),
           ("08:48", "Iryo 6076", "Sigue parada", PAPEL2), ("08:48", "Sala Atocha", "«¿No estamos haciendo eso?»", PAPEL2)]
for h, quien, txt, col in eventos:
    ax.scatter(mx(h), filas[quien], s=60, color=col, zorder=3)
    ax.annotate(txt, (mx(h), filas[quien]), xytext=(4, 9), textcoords="offset points", fontsize=8, color=PAPEL)
ax.hlines(1, mx("08:30"), mx("08:54"), color=FRIO, lw=6, alpha=0.35)
ax.text(mx("08:30"), 0.62, "Iryo detenido", fontsize=7.5, color=FRIO)
ax.hlines(2, mx("08:36"), mx("08:53"), color=ALERTA, lw=6, alpha=0.35)
ax.text(mx("08:36") + 0.2, 1.62, "AVE en marcha normal hacia el Iryo", fontsize=7.5, color=ALERTA)
for (h, fuente), alto in zip(impactos, (3.55, 3.55, 2.95)):
    ax.axvline(mx(h), color=ALERTA, lw=1, ls=":")
    ax.text(mx(h) + (0.15 if alto < 3.5 else 0), alto, f"impacto {h}\n({fuente.split(' (')[0]})", fontsize=7, color=ALERTA,
            ha="left" if alto < 3.5 else "center")
ax.set_yticks(list(filas.values())); ax.set_yticklabels(list(filas.keys()))
ax.set_xticks([mx(f"08:{m:02d}") for m in range(30, 56, 5)]); ax.set_xticklabels([f"8:{m:02d}" for m in range(30, 56, 5)])
ax.set_ylim(-0.6, 4.2); ax.set_xlim(0, mx("08:56"))
ax.spines[["top", "right", "left"]].set_visible(False)
guardar(fig, "cronologia.png")

# 4.3 Grafo de información: quién sabía qué y qué no llegó
fig, ax = plt.subplots(figsize=(10, 5.4))
ax.set_xlim(0, 10); ax.set_ylim(0, 6); ax.axis("off")
nodos = {"central": (5, 5.3, "Central LZB Urda\n(caída 8:30)"), "atocha": (5, 3.0, "CTC Atocha\n(operador + sala)"),
         "ave": (1.4, 1.0, "AVE 2080"), "iryo": (8.6, 1.0, "Iryo 6076\n(detenido PK 118)")}
for k, (x, y, t) in nodos.items():
    ax.add_patch(FancyBboxPatch((x - 1.15, y - 0.45), 2.3, 0.9, boxstyle="round,pad=0.02,rounding_size=0.1",
                                facecolor=TINTA2, edgecolor=ALERTA if k == "central" else LINEA, lw=1.5))
    ax.text(x, y, t, ha="center", va="center", fontsize=8.6)


def flecha(a, b, txt, col, estilo="-", desv=0.0, rad=0.0):
    (x1, y1, _), (x2, y2, _) = nodos[a], nodos[b]
    ax.add_patch(FancyArrowPatch((x1, y1 - 0.5 if y1 > y2 else y1 + 0.5), (x2, y2 + 0.5 if y1 > y2 else y2 - 0.5),
                                 arrowstyle="-|>", mutation_scale=14, color=col, lw=1.4, ls=estilo,
                                 connectionstyle=f"arc3,rad={rad}"))
    ax.text((x1 + x2) / 2 + desv, (y1 + y2) / 2, txt, fontsize=7.6, color=col, ha="center")


flecha("central", "atocha", "control pasa a Atocha", PAPEL2)


def recta(p1, p2, txt, col, pos, estilo="-", ha="center"):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=14, color=col, lw=1.5, ls=estilo))
    ax.text(*pos, txt, fontsize=7.8, color=col, ha=ha, va="center", bbox=dict(facecolor=TINTA, edgecolor="none", pad=1.5))


recta((0.9, 1.5), (3.85, 2.75), "8:31 · meta 0\n(vía ocupada)", PAPEL2, (0.25, 2.9), ha="left")
recta((4.3, 2.5), (1.95, 1.5), "8:36 · «marcha normal»", ALERTA, (3.05, 2.05), ha="center")
recta((9.0, 1.5), (6.15, 2.75), "8:41 y 8:48 ·\nsigo detenida", PAPEL2, (8.85, 2.35), ha="right")
recta((5.0, 2.5), (2.6, 1.15), "", ALERTA, (0, 0), estilo="--")
ax.text(4.55, 1.35, "aviso que no consta:\n«el Iryo sigue parado delante»", fontsize=7.8, color=ALERTA, ha="left", va="center")
ax.add_patch(FancyArrowPatch((2.55, 0.75), (7.45, 0.75), arrowstyle="-", color=GRIS, lw=1, ls=":"))
ax.text(5, 0.42, "misma vía, mismo sentido · unos 25 km de separación (según la prensa)", fontsize=7.6, color=GRIS, ha="center")
guardar(fig, "grafo_informacion.png")

# 4.4 Velocidad media implícita por hipótesis frente a velocidades de referencia
fig, ax = plt.subplots(figsize=(8, 3.6))
etq = [f"Impacto {v['hipotesis_impacto']}" for v in ventanas]
vals = [v["velocidad_media_implicita_kmh"] for v in ventanas]
ax.barh(etq, vals, color=ALERTA, alpha=0.8)
for y, v in enumerate(vals):
    ax.text(v + 2, y, f"{str(v).replace('.', ',')} km/h", va="center", fontsize=8.5)
ax.axvline(200, color=GRIS, ls=":"); ax.text(200, 2.45, "200 km/h", fontsize=7.5, color=GRIS, ha="center")
ax.set_xlabel(f"Velocidad media implícita para {dist_km} km desde la orden de las 8:36 (km/h)")
ax.invert_yaxis(); ax.spines[["top", "right"]].set_visible(False)
guardar(fig, "velocidad_implicita.png")

print(json.dumps({"ventanas": ventanas, "telefonemas": telefonemas}, ensure_ascii=False, indent=1))
