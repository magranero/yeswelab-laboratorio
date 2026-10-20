"""Structured outputs: ¿reparar en local el JSON roto de un LLM o pedirle que lo repita?

Genera 1000 salidas JSON de un agente (esquema realista de extracción de pedidos) y les aplica los seis
fallos sintácticos más habituales de los LLM. Mide, con 5 repeticiones:
  - cuántas acepta json.loads tal cual;
  - cuántas repara json_repair (parser tolerante en Python) y si el resultado es idéntico al original;
  - cuánto tarda cada reparación;
  - cuántos tokens cuesta un reintento: reenviar instrucciones + esquema + salida rota + error (o200k_base).

    uv run --with json-repair --with tiktoken python medir.py
"""

import json
import platform
import random
import statistics
import subprocess
import time
from importlib.metadata import version

import tiktoken
from json_repair import repair_json

ENC = tiktoken.get_encoding("o200k_base")
N, REPS = 1000, 5
INSTRUCCIONES = (
    "Eres un agente que extrae pedidos de correos de clientes. Devuelve SOLO un JSON válido que cumpla este esquema, "
    "sin texto antes ni después. Si un campo no aparece, usa null."
)
ESQUEMA = json.dumps({
    "type": "object",
    "properties": {
        "cliente": {"type": "object", "properties": {"nombre": {"type": "string"}, "email": {"type": "string"}, "empresa": {"type": ["string", "null"]}}},
        "lineas": {"type": "array", "items": {"type": "object", "properties": {"sku": {"type": "string"}, "descripcion": {"type": "string"}, "cantidad": {"type": "integer"}, "precio_unitario": {"type": "number"}}}},
        "urgente": {"type": "boolean"},
        "entrega": {"type": "object", "properties": {"ciudad": {"type": "string"}, "fecha": {"type": ["string", "null"]}}},
        "notas": {"type": ["string", "null"]},
    },
    "required": ["cliente", "lineas", "urgente", "entrega"],
}, ensure_ascii=False, indent=2)

CIUDADES = ["Madrid", "Santander", "Ciudad de México", "Bogotá", "Lima", "Valencia", "Buenos Aires", "Sevilla"]
PRODUCTOS = ["Tornillo M8", "Placa base", "Cable USB-C", "Licencia anual", "Sensor de humedad", "Caja estanca", "Fuente 24V"]


def pedido(r: random.Random) -> dict:
    return {
        "cliente": {"nombre": r.choice(["Ana Ruiz", "Luis Pérez", "Marta Gómez", "Jorge Díaz"]), "email": f"cliente{r.randint(1, 999)}@ejemplo.com", "empresa": r.choice([None, "Acme SL", "Talleres Norte"])},
        "lineas": [{"sku": f"SKU-{r.randint(1000, 9999)}", "descripcion": r.choice(PRODUCTOS), "cantidad": r.randint(1, 50), "precio_unitario": round(r.uniform(0.5, 300), 2)} for _ in range(r.randint(1, 4))],
        "urgente": r.random() < 0.3,
        "entrega": {"ciudad": r.choice(CIUDADES), "fecha": r.choice([None, "2026-11-03", "2026-12-15"])},
        "notas": r.choice([None, "Llamar antes de entregar", "Factura a nombre de la empresa"]),
    }


# Los seis fallos habituales de un LLM al devolver JSON
def coma_final(s, r):  # coma colgante antes de cerrar
    return s.replace("\n  }", ",\n  }", 1) if "\n  }" in s else s[:-1] + ",}"

def bloque_markdown(s, r):  # envuelto en ```json ... ``` con frase
    return "Aquí tienes el pedido:\n```json\n" + s + "\n```"

def comillas_simples(s, r):
    return s.replace('"', "'")

def cortado(s, r):  # respuesta truncada por max_tokens
    return s[: int(len(s) * r.uniform(0.85, 0.97))]

def sin_comillas_claves(s, r):
    import re
    return re.sub(r'"(\w+)":', r"\1:", s)

def comentario(s, r):  # comentario tipo JS
    return s.replace("{", "{ // pedido extraído", 1)

FALLOS = [coma_final, bloque_markdown, comillas_simples, cortado, sin_comillas_claves, comentario]


def main() -> None:
    r = random.Random(42)
    casos = []
    for i in range(N):
        original = pedido(r)
        texto = json.dumps(original, ensure_ascii=False, indent=2)
        fallo = FALLOS[i % len(FALLOS)]
        casos.append((original, fallo.__name__, fallo(texto, r)))

    estricto_ok = sum(1 for o, f, t in casos if _carga(t) == o)
    por_fallo = {f.__name__: {"casos": 0, "reparados_identicos": 0, "parseables": 0} for f in FALLOS}
    tiempos = []
    for rep in range(REPS):
        t_rep = []
        for o, f, t in casos:
            t0 = time.perf_counter()
            arreglado = repair_json(t, return_objects=True)
            t_rep.append((time.perf_counter() - t0) * 1000)
            if rep == 0:
                por_fallo[f]["casos"] += 1
                por_fallo[f]["parseables"] += isinstance(arreglado, dict)
                por_fallo[f]["reparados_identicos"] += arreglado == o
        tiempos.append(t_rep)
    planos = [x for rep in tiempos for x in rep]
    identicos = sum(v["reparados_identicos"] for v in por_fallo.values())
    parseables = sum(v["parseables"] for v in por_fallo.values())

    # Coste de un reintento: se reenvía instrucciones + esquema + salida rota + mensaje de error, y se genera de nuevo.
    entrada_reintento = [len(ENC.encode(INSTRUCCIONES + "\n" + ESQUEMA + "\n" + t + "\nError: JSON inválido. Devuelve solo el JSON corregido.")) for o, f, t in casos]
    salida_reintento = [len(ENC.encode(json.dumps(o, ensure_ascii=False, indent=2))) for o, f, t in casos]
    llamada_normal = [len(ENC.encode(INSTRUCCIONES + "\n" + ESQUEMA)) + s for s in salida_reintento]

    resumen = {
        "casos": N,
        "repeticiones": REPS,
        "json_loads_estricto_ok": estricto_ok,
        "json_repair": {
            "parseables": parseables,
            "parseables_pct": round(100 * parseables / N, 1),
            "identicos_al_original": identicos,
            "identicos_pct": round(100 * identicos / N, 1),
            "ms_por_reparacion": {"mediana": round(statistics.median(planos), 3), "p95": round(sorted(planos)[int(0.95 * len(planos))], 3), "max": round(max(planos), 3)},
            "por_fallo": por_fallo,
        },
        "tokens_reintento": {
            "entrada_mediana": statistics.median(entrada_reintento),
            "salida_mediana": statistics.median(salida_reintento),
            "total_mediana": statistics.median([a + b for a, b in zip(entrada_reintento, salida_reintento)]),
            "llamada_original_mediana": statistics.median(llamada_normal),
            "reintento_vs_llamada_original_pct": round(100 * statistics.median([(a + b) / c for a, b, c in zip(entrada_reintento, salida_reintento, llamada_normal)]), 1),
        },
    }
    with open("resultados/resumen.json", "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=1)
    with open("resultados/tiempos_ms.csv", "w", encoding="utf-8") as f:
        f.write("repeticion,caso,fallo,ms\n")
        for rep, fila in enumerate(tiempos, 1):
            for i, ms in enumerate(fila):
                f.write(f"{rep},{i},{casos[i][1]},{ms:.4f}\n")
    chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
    with open("entorno.txt", "w", encoding="utf-8") as f:
        f.write(f"Fecha: {time.strftime('%Y-%m-%d')}\nEquipo: {chip}, macOS {platform.mac_ver()[0]}\nPython {platform.python_version()} · json-repair {version('json-repair')} · tiktoken {version('tiktoken')} (o200k_base)\n{N} casos sintéticos con semilla 42, {REPS} repeticiones de la reparación\n")
    print(json.dumps(resumen, ensure_ascii=False, indent=1))


def _carga(t):
    try:
        return json.loads(t)
    except Exception:
        return None


if __name__ == "__main__":
    main()
