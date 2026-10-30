"""Convierte resultados/modelos.json y resultados/modelos_openclaw.json en tablas Markdown (resultados/resumen.md).

    python3 resumen.py
"""

import json
import statistics
import os
from decimal import ROUND_HALF_UP, Decimal

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultados")


def r(x, d=1):
    """Redondeo único, a la mitad hacia arriba, con coma decimal."""
    q = Decimal(1).scaleb(-d) if d else Decimal(1)
    return str(Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP)).replace(".", ",")


def tabla(datos, titulo, con_defecto):
    filas = [f"### {titulo}", "",
             "| Modelo | Memoria cargado | En GPU | Lectura (tok/s) | Hasta empezar a responder | Escritura (tok/s) | Herramientas | Respuesta con herramienta |"
             + (" Sin Modelfile |" if con_defecto else ""),
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |" + (" ---: |" if con_defecto else "")]
    for clave, m in datos.items():
        fila = (f"| {clave} | {r(m['memoria_gb'])} GB | {r(m['en_gpu_pct'], 0)} % | {r(m['lectura_tok_s_mediana'], 0)} | "
                f"{r(m['segundos_hasta_respuesta_mediana'])} s | {r(m['escritura_tok_s_mediana'])} | "
                f"{m['aciertos_herramientas']}/{m['pruebas_herramientas']} | "
                f"{r(statistics.median(h['segundos'] for h in m['herramientas']))} s |")
        if con_defecto:
            d = m.get("sin_modelfile")
            fila += f" {r(d['memoria_gb'])} GB ({d['contexto'] // 1024}K) |" if d else " — |"
        filas.append(fila)
    tokens = {m["tokens_prompt"] for m in datos.values()}
    filas += ["", f"Prompt de {', '.join(str(t) for t in sorted(tokens))} tokens; medianas de 3 repeticiones; "
                  "5 peticiones con herramientas por modelo.", ""]
    return filas


def main():
    salida = ["# Resumen de la medición", ""]
    entorno = os.path.join(RES, "entorno_medicion.json")
    if os.path.exists(entorno):
        e = json.load(open(entorno))
        salida += [f"Equipo: {e['equipo']}, {r(e['ram_gb'], 0)} GB de memoria unificada. {e['sistema']}. "
                   f"Ollama {e['ollama']}. {e['energia']}. Fecha: {e['fecha']}.", ""]
    for fichero, titulo, defecto in (("modelos.json", "Como Hermes: 64K de contexto, API compatible con OpenAI", True),
                                     ("modelos_openclaw.json", "Como OpenClaw: 32K de contexto, API nativa de Ollama", False)):
        p = os.path.join(RES, fichero)
        if os.path.exists(p):
            salida += tabla(json.load(open(p)), titulo, defecto)
    open(os.path.join(RES, "resumen.md"), "w").write("\n".join(salida))
    print("\n".join(salida))


if __name__ == "__main__":
    main()
