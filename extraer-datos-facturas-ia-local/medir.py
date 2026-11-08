"""Extrae 9 campos de facturas españolas con reglas y con modelos locales (MLX).

Uso: python medir.py datos resultados [repeticiones]
Guarda en bruto, sin redondear:
  resultados/extracciones.csv  una fila por detector, repetición, factura y campo
  resultados/tiempos.csv       segundos por factura, tokens y memoria
  resultados/carga.csv         segundos de carga de cada modelo
"""
import csv
import gc
import json
import re
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pymupdf

CAMPOS = ["numero", "fecha", "nif_emisor", "nif_cliente", "base_imponible",
          "tipo_iva", "cuota_iva", "retencion_irpf", "total"]

MODELOS = {
    "qwen3-4b-instruct-2507": ("mlx-community/Qwen3-4B-Instruct-2507-4bit", "50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b"),
    "gemma-3-4b-it": ("mlx-community/gemma-3-4b-it-4bit", "93724907d4ed1745d2fe50baadf3b0b01a65abf2"),
    "llama-3.2-3b-instruct": ("mlx-community/Llama-3.2-3B-Instruct-4bit", "7f0dc925e0d0afb0322d96f9255cfddf2ba5636e"),
    "qwen3-1.7b": ("mlx-community/Qwen3-1.7B-4bit", "3b1b1768f8f8cf8351c712464f906e86c2b8269e"),
}

INSTRUCCIONES = """Extrae los datos de esta factura española. Responde SOLO con un objeto JSON con estas claves:
- "numero": número de factura (serie incluida), tal como aparece
- "fecha": fecha de emisión de la factura en formato AAAA-MM-DD (no la de vencimiento)
- "nif_emisor": NIF o CIF de quien emite la factura (el proveedor), sin espacios, puntos ni guiones
- "nif_cliente": NIF o CIF del cliente (el destinatario), sin espacios, puntos ni guiones
- "base_imponible": base imponible, número con punto decimal
- "tipo_iva": porcentaje de IVA, número entero
- "cuota_iva": cuota de IVA en euros, número con punto decimal
- "retencion_irpf": retención de IRPF en euros como número positivo (0 si no hay)
- "total": total de la factura en euros, número con punto decimal

Factura:
"""

MESES = {m: i + 1 for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                                          "agosto", "septiembre", "octubre", "noviembre", "diciembre"])}


# ---------- Normalización y comparación ----------

def norm_importe(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        try:
            return abs(Decimal(str(x))).quantize(Decimal("0.01"))  # el signo no cuenta, igual que en texto
        except InvalidOperation:
            return None
    s = str(x).replace("€", "").replace("EUR", "").replace(" ", "").strip().lstrip("-")
    if "," in s:  # formato español 1.234,56
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def norm_fecha(x):
    if x is None:
        return None
    s = str(x).strip().lower()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}"
    m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)
    if m:
        return f"{int(m[3]):04d}-{int(m[2]):02d}-{int(m[1]):02d}"
    m = re.fullmatch(r"(\d{1,2}) de ([a-z]+) de (\d{4})", s)
    if m and m[2] in MESES:
        return f"{int(m[3]):04d}-{MESES[m[2]]:02d}-{int(m[1]):02d}"
    return s


def norm_nif(x):
    return None if x is None else re.sub(r"[\s.\-]", "", str(x)).upper()


def norm_numero(x):
    return None if x is None else re.sub(r"\s", "", str(x)).upper()


def norm_tipo(x):
    try:
        return int(Decimal(str(x).replace("%", "").replace(",", ".").strip()))
    except (InvalidOperation, ValueError):
        return None


NORM = {"numero": norm_numero, "fecha": norm_fecha, "nif_emisor": norm_nif, "nif_cliente": norm_nif,
        "base_imponible": norm_importe, "tipo_iva": norm_tipo, "cuota_iva": norm_importe,
        "retencion_irpf": norm_importe, "total": norm_importe}


def cuadra(d):
    """Comprobación aritmética que haría un programa: base + IVA - IRPF = total y IVA = base x tipo."""
    try:
        b, c, r, t, k = (NORM[f](d.get(f)) for f in
                         ["base_imponible", "cuota_iva", "retencion_irpf", "total", "tipo_iva"])
        if None in (b, c, t, k):
            return False
        r = r or Decimal("0")
        return abs(b + c - r - t) <= Decimal("0.01") and abs(b * k / 100 - c) <= Decimal("0.01")
    except Exception:
        return False


# ---------- Reglas (escritas mirando solo las plantillas A y B) ----------

IMPORTE = r"-?(?:€\s*)?(\d[\d.]*,\d{2})"
RE_NIF = re.compile(r"\b([ABJ]-?\d{2}\.?\d{3}\.?\d{3}|\d{2}\.?\d{3}\.?\d{3}-?[A-Z])\b")


def reglas(texto):
    t = texto
    out = {}
    m = re.search(r"(?:Nº de factura:|^Factura)\s*(\S+)", t, re.M)
    out["numero"] = m[1] if m else None
    m = re.search(r"^Fecha(?: de factura)?:\s*(.+)$", t, re.M)
    out["fecha"] = m[1].strip() if m else None
    nifs = RE_NIF.findall(t)
    out["nif_emisor"] = nifs[0] if len(nifs) > 0 else None
    out["nif_cliente"] = nifs[1] if len(nifs) > 1 else None

    def tras(etiqueta):
        m = re.search(etiqueta + r"[^\n]*\n" + IMPORTE, t, re.M)
        return m[1] if m else None
    out["base_imponible"] = tras(r"^(?:Base imponible|Subtotal)")
    m = re.search(r"^(?:IVA|I\.V\.A\.) \(?(\d+) ?%", t, re.M)
    out["tipo_iva"] = m[1] if m else None
    out["cuota_iva"] = tras(r"^(?:IVA|I\.V\.A\.) \(?\d+ ?%")
    out["retencion_irpf"] = tras(r"^Retención") or "0"
    out["total"] = tras(r"^TOTAL")
    return out


# ---------- Modelos locales ----------

def extraer_json(s):
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.S)
    m = re.search(r"\{.*\}", s, re.S)
    if not m:
        return None
    try:
        d = json.loads(m[0])
        return d if isinstance(d, dict) else None
    except json.JSONDecodeError:
        return None


def main():
    datos, res = Path(sys.argv[1]), Path(sys.argv[2])
    reps = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    solo = sys.argv[4].split(",") if len(sys.argv) > 4 else None
    res.mkdir(parents=True, exist_ok=True)
    verdad = json.loads((datos / "verdad.json").read_text())
    textos = {v["id"]: pymupdf.open(datos / f"{v['id']}.pdf")[0].get_text() for v in verdad}

    f_ext = open(res / "extracciones.csv", "a", newline="")
    f_tie = open(res / "tiempos.csv", "a", newline="")
    f_car = open(res / "carga.csv", "a", newline="")
    w_ext, w_tie, w_car = csv.writer(f_ext), csv.writer(f_tie), csv.writer(f_car)
    if f_ext.tell() == 0:
        w_ext.writerow(["detector", "repeticion", "factura", "plantilla", "campo", "esperado", "obtenido",
                        "correcto", "json_valido", "cuadra"])
        w_tie.writerow(["detector", "repeticion", "factura", "segundos", "tokens_prompt", "tokens_salida",
                        "prompt_tps", "generacion_tps", "memoria_pico_gb"])
        w_car.writerow(["detector", "segundos_carga"])

    def anotar(det, rep, v, d, valido, seg, tp=0, ts=0, ptps=0.0, gtps=0.0, mem=0.0):
        ok_cuadra = cuadra(d or {})
        for c in CAMPOS:
            esp = NORM[c](v[c])
            obt = NORM[c]((d or {}).get(c))
            if c == "retencion_irpf" and obt is None and valido:
                obt = Decimal("0.00")
            w_ext.writerow([det, rep, v["id"], v["plantilla"], c, esp, obt, int(esp == obt), int(valido),
                            int(ok_cuadra)])
        w_tie.writerow([det, rep, v["id"], seg, tp, ts, ptps, gtps, mem])

    detectores = ["reglas"] + list(MODELOS)
    if solo:
        detectores = [d for d in detectores if d in solo]

    for det in detectores:
        if det == "reglas":
            w_car.writerow([det, 0.0])
            for rep in range(1, reps + 1):
                for v in verdad:
                    t0 = time.perf_counter()
                    d = reglas(textos[v["id"]])
                    anotar(det, rep, v, d, True, time.perf_counter() - t0)
            f_ext.flush(); f_tie.flush()
            print("reglas hecho", flush=True)
            continue

        import mlx.core as mx
        from mlx_lm import load, stream_generate
        repo, rev = MODELOS[det]
        t0 = time.perf_counter()
        modelo, tok = load(repo, revision=rev) if "revision" in load.__code__.co_varnames else load(repo)
        w_car.writerow([det, time.perf_counter() - t0])
        f_car.flush()
        for rep in range(1, reps + 1):
            for v in verdad:
                msgs = [{"role": "user", "content": INSTRUCCIONES + textos[v["id"]]}]
                kw = {"enable_thinking": False} if det.startswith("qwen3-1.7b") else {}
                prompt = tok.apply_chat_template(msgs, add_generation_prompt=True, **kw)
                mx.reset_peak_memory()
                t0 = time.perf_counter()
                salida, ultimo = "", None
                for r in stream_generate(modelo, tok, prompt, max_tokens=400):  # greedy (temperatura 0)
                    salida += r.text
                    ultimo = r
                seg = time.perf_counter() - t0
                d = extraer_json(salida)
                anotar(det, rep, v, d, d is not None, seg, ultimo.prompt_tokens, ultimo.generation_tokens,
                       ultimo.prompt_tps, ultimo.generation_tps, ultimo.peak_memory)
            f_ext.flush(); f_tie.flush()
            print(det, "repetición", rep, "hecha", flush=True)
        del modelo, tok
        gc.collect()
        mx.clear_cache()


if __name__ == "__main__":
    main()
