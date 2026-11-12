"""Calcula WER, datos clave y velocidad a partir de resultados/transcripciones.jsonl.

    python resumir.py resultados

Guarda resultados/por_audio.csv (una fila por modelo, repetición y audio) y resultados/resumen.json
(medianas, mínimos y máximos sin redondear). No redondea nada: el redondeo se hace al escribir el artículo.
"""
import csv
import json
import os
import re
import statistics
import sys
import unicodedata
from collections import defaultdict

import jiwer
from num2words import num2words

from textos import TEXTOS

DIGITOS = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"]
REF = {t["id"]: t for t in TEXTOS}


def normalizar(texto: str) -> str:
    """Misma normalización para la referencia y para la transcripción: así «5 y media», «5:30» y
    «cinco y media» cuentan igual, y solo se penaliza lo que cambia el significado."""
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\b(\d{1,2})[:.]30\b", r"\1 y media", t)
    t = re.sub(r"\b(\d{1,2})[:.]15\b", r"\1 y cuarto", t)
    t = re.sub(r"\b(\d{1,2})[:.]00\b", r"\1", t)
    t = re.sub(r"\b(\d+),(\d{2})\b", r"\1 con \2", t)       # 435,60 -> 435 con 60
    t = re.sub(r"(\d)\s*%", r"\1 por ciento", t)
    t = t.replace("€", " euros ")
    t = re.sub(r"(?<=\d)[\s.\-](?=\d)", "", t)               # 1.800 -> 1800; 612 34 56 78 -> 612345678

    def numero(m):
        cifras = m.group(2)
        if len(cifras) >= 7 or m.group(1):                   # teléfonos y números de pedido: cifra a cifra
            return (m.group(1) or "") + " ".join(DIGITOS[int(c)] for c in cifras)
        return num2words(int(cifras), lang="es")
    t = re.sub(r"(numero\s+)?(\d+)", numero, t)
    t = re.sub(r"[^a-z0-9ñ ]+", " ", t)
    t = re.sub(r"\b(un|una)\b", "uno", t)
    return re.sub(r"\s+", " ", t).strip()


def contiene(hip: str, clave: str) -> bool:
    return re.search(r"\b" + re.escape(normalizar(clave)) + r"\b", hip) is not None


def resumen(valores):
    return {"mediana": statistics.median(valores), "min": min(valores), "max": max(valores), "n": len(valores)}


def main(carpeta):
    filas = [json.loads(l) for l in open(os.path.join(carpeta, "transcripciones.jsonl"))]
    por_audio = []
    for f in filas:
        ref = normalizar(REF[f["texto_id"]]["texto"])
        hip = normalizar(f["texto"])
        o = jiwer.process_words(ref, hip)
        errores = o.substitutions + o.deletions + o.insertions
        claves = REF[f["texto_id"]]["clave"]
        fallos = [c for c in claves if not contiene(hip, c)]
        por_audio.append({
            "modelo": f["modelo"], "rep": f["rep"], "audio": f["audio"], "texto_id": f["texto_id"], "voz": f["voz"],
            "condicion": f["condicion"], "segundos_audio": f["segundos"],
            "segundos_transcripcion": f["segundos_transcripcion"],
            "palabras_ref": len(ref.split()), "errores": errores, "sustituciones": o.substitutions,
            "borrados": o.deletions, "inserciones": o.insertions, "wer": errores / len(ref.split()),
            "claves_total": len(claves), "claves_ok": len(claves) - len(fallos), "claves_fallidas": "; ".join(fallos),
            "transcripcion": f["texto"],
        })
    with open(os.path.join(carpeta, "por_audio.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(por_audio[0].keys()))
        w.writeheader()
        w.writerows(por_audio)

    # Agregados por modelo, condición y repetición (WER de corpus: errores totales / palabras totales).
    grupos = defaultdict(list)
    for r in por_audio:
        grupos[(r["modelo"], r["condicion"], r["rep"], r["voz"])].append(r)

    def agregar(filtro):
        """filtro(modelo, condicion, voz) -> bool. Devuelve métricas por modelo con mediana sobre repeticiones."""
        por_modelo_rep = defaultdict(list)
        for (m, c, rep, v), rs in grupos.items():
            if filtro(m, c, v):
                por_modelo_rep[(m, rep)].extend(rs)
        salida = defaultdict(lambda: defaultdict(list))
        for (m, rep), rs in por_modelo_rep.items():
            err = sum(r["errores"] for r in rs)
            pal = sum(r["palabras_ref"] for r in rs)
            ok = sum(r["claves_ok"] for r in rs)
            tot = sum(r["claves_total"] for r in rs)
            seg_a = sum(r["segundos_audio"] for r in rs)
            seg_t = sum(r["segundos_transcripcion"] for r in rs)
            salida[m]["wer_pct"].append(100 * err / pal)
            salida[m]["claves_ok_pct"].append(100 * ok / tot)
            salida[m]["audios_todas_claves_ok_pct"].append(
                100 * sum(r["claves_ok"] == r["claves_total"] for r in rs) / len(rs))
            salida[m]["veces_tiempo_real"].append(seg_a / seg_t)
            salida[m]["segundos_por_minuto_audio"].append(60 * seg_t / seg_a)
            salida[m]["audios"].append(len(rs))
            salida[m]["minutos_audio"].append(seg_a / 60)
        return {m: {k: resumen(v) for k, v in d.items()} for m, d in salida.items()}

    conds = ["limpio", "whatsapp", "ruido"]
    res = {
        "total": agregar(lambda m, c, v: True),
        "por_condicion": {c: agregar(lambda m, cc, v, c=c: cc == c) for c in conds},
        "solo_voz_monica": agregar(lambda m, c, v: v == "monica_es"),
        "solo_voz_monica_por_condicion": {c: agregar(lambda m, cc, v, c=c: cc == c and v == "monica_es") for c in conds},
        "por_voz": {v: agregar(lambda m, c, vv, v=v: vv == v) for v in ["monica_es", "eddy_es", "paulina_mx"]},
    }
    # ¿Da el mismo texto en las 5 repeticiones? (decodificación voraz: debería)
    textos = defaultdict(set)
    for r in por_audio:
        textos[(r["modelo"], r["audio"])].add(r["transcripcion"])
    res["audios_con_texto_distinto_entre_repeticiones"] = {
        m: sum(1 for (mm, _), s in textos.items() if mm == m and len(s) > 1)
        for m in sorted({r["modelo"] for r in por_audio})}
    # Fallos de datos clave por clave (repetición 1), para ver qué se escapa.
    fallos = defaultdict(lambda: defaultdict(int))
    for r in por_audio:
        if r["rep"] == 1 and r["claves_fallidas"]:
            for c in r["claves_fallidas"].split("; "):
                fallos[r["modelo"]][f"{r['texto_id']}: {c}"] += 1
    res["claves_fallidas_rep1"] = {m: dict(sorted(d.items(), key=lambda x: -x[1])) for m, d in fallos.items()}
    carga = [json.loads(l) for l in open(os.path.join(carpeta, "carga.jsonl"))]
    res["carga_y_memoria"] = {c["modelo"]: {**c, "rss_pico_gb": c["rss_pico_bytes"] / 1e9,
                                            "mlx_pico_gb": (c["mlx_pico_bytes"] / 1e9) if c["mlx_pico_bytes"] else None}
                              for c in carga}
    # Comparaciones derivadas (de las medianas sin redondear).
    t, mo = res["total"], res["solo_voz_monica"]
    gpu, cpu = "mlx-whisper-large-v3-turbo", "faster-whisper-large-v3-turbo-cpu"
    res["comparaciones"] = {
        "parakeet_vs_turbo_gpu_veces_mas_rapido": t["parakeet-tdt-0.6b-v3"]["veces_tiempo_real"]["mediana"]
        / t[gpu]["veces_tiempo_real"]["mediana"],
        "turbo_gpu_vs_cpu_veces_mas_rapido_voz_monica": mo[gpu]["veces_tiempo_real"]["mediana"]
        / mo[cpu]["veces_tiempo_real"]["mediana"],
        "base_wer_ruido_menos_limpio_puntos": res["por_condicion"]["ruido"]["mlx-whisper-base"]["wer_pct"]["mediana"]
        - res["por_condicion"]["limpio"]["mlx-whisper-base"]["wer_pct"]["mediana"],
        "minutos_de_calculo_por_hora_de_audio": {m: v["segundos_por_minuto_audio"]["mediana"] for m, v in t.items()},
    }
    json.dump(res, open(os.path.join(carpeta, "resumen.json"), "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
