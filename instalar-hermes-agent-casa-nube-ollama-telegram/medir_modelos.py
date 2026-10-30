"""¿Qué equipo hace falta para mover Hermes Agent con un modelo local de Ollama?

Para cada modelo con soporte de herramientas, con el contexto de 64K que Hermes exige para trabajar como agente
(se crea una variante «<modelo>-64k» con un Modelfile, como indica la documentación de Hermes):
  0. Memoria que ocupa el modelo base sin Modelfile, llamado por la API compatible con OpenAI (Ollama elige el contexto).
  1. Memoria que ocupa cargado (y cuánta en GPU), según /api/ps de Ollama.
  2. Lectura de un prompt de unos 12.000 tokens (lo que pesa un agente con instrucciones y herramientas) y
     escritura de 200 tokens: tokens por segundo y segundos hasta la respuesta. 3 repeticiones.
  3. Llamadas a herramientas por la API compatible con OpenAI (la que usa Hermes): 5 peticiones de oficina; acierta
     si llama a la herramienta correcta con argumentos JSON válidos.

    python3 medir_modelos.py qwen3:4b qwen3:8b ...
    python3 medir_modelos.py --cpu 4 qwen3:4b    # sin GPU y con 4 hilos: aproxima un VPS de 4 vCPU
    python3 medir_modelos.py --openclaw qwen3:8b # como OpenClaw: 32K de contexto y API nativa de Ollama
Solo usa Ollama en local (http://localhost:11434). Sin claves ni servicios externos.
"""

import json
import os
import platform
import statistics
import subprocess
import sys
import time
import urllib.request

OLLAMA = "http://localhost:11434"
CONTEXTO = 65536
REPETICIONES = 3
PRUEBAS_HERRAMIENTAS = 5
AQUI = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(AQUI, "resultados")

PARRAFO = ("La empresa recibe cada mes facturas de proveedores por correo electrónico. El departamento de administración "
           "las descarga, revisa el importe, la fecha de vencimiento y el número de pedido, y las registra en una hoja de "
           "cálculo compartida antes de pasarlas a contabilidad. ")
PREGUNTA = "Resume en tres frases qué tareas repetitivas aparecen en el texto anterior y cuál automatizarías primero."

HERRAMIENTAS = [
    {"type": "function", "function": {
        "name": "consultar_factura", "description": "Devuelve el importe total y el vencimiento de una factura por su número",
        "parameters": {"type": "object", "properties": {"numero": {"type": "string", "description": "Número de factura, p. ej. F-2026-0042"}},
                       "required": ["numero"]}}},
    {"type": "function", "function": {
        "name": "crear_recordatorio", "description": "Crea un recordatorio en el calendario de la empresa",
        "parameters": {"type": "object", "properties": {"fecha": {"type": "string", "description": "Fecha en formato AAAA-MM-DD"},
                                                        "texto": {"type": "string"}}, "required": ["fecha", "texto"]}}},
]
PETICIONES = [
    ("¿Cuánto suma la factura F-2026-0042 y cuándo vence?", "consultar_factura", {"numero"}),
    ("Recuérdame el 2026-11-15 que tengo que pagar el alquiler de la oficina.", "crear_recordatorio", {"fecha", "texto"}),
    ("Dime el importe de la factura número F-2026-0107.", "consultar_factura", {"numero"}),
    ("Pon un recordatorio para el 2026-12-01: renovar el seguro de la furgoneta.", "crear_recordatorio", {"fecha", "texto"}),
    ("Necesito saber el vencimiento de la factura F-2026-0300.", "consultar_factura", {"numero"}),
]


def api(ruta, datos=None, timeout=1800):
    req = urllib.request.Request(OLLAMA + ruta, data=json.dumps(datos).encode() if datos is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def opciones_pensar(modelo):
    # Desactiva el razonamiento visible cuando el modelo lo permite, para medir respuesta y no razonamiento
    if modelo.startswith("gpt-oss"):
        return {"think": "low"}
    if modelo.startswith(("qwen3", "gemma4")):
        return {"think": False}
    return {}


def descargar_todo():
    for m in api("/api/ps").get("models", []):
        api("/api/generate", {"model": m["name"], "keep_alive": 0})
    time.sleep(3)


def cargado(nombre):
    return next((m for m in api("/api/ps").get("models", []) if nombre in (m["name"], m["model"], m["name"].removesuffix(":latest"))), {})


def sin_modelfile(modelo):
    """Lo que pasa si conectas Hermes al modelo tal cual: Ollama decide el contexto."""
    descargar_todo()
    api("/v1/chat/completions", {"model": modelo, "messages": [{"role": "user", "content": "Hola"}], "max_tokens": 5})
    ps = cargado(modelo)
    descargar_todo()
    return {"memoria_gb": ps.get("size", 0) / 1e9, "contexto": ps.get("context_length")}


def variante_64k(modelo):
    nombre = modelo.replace(":", "-") + f"-{CONTEXTO // 1024}k"
    api("/api/create", {"model": nombre, "from": modelo, "parameters": {"num_ctx": CONTEXTO}, "stream": False})
    return nombre


def medir(modelo, cpu_hilos=None, nativa=False):
    extra = {"num_gpu": 0, "num_thread": cpu_hilos} if cpu_hilos else {}
    base, modelo = modelo, variante_64k(modelo)
    por_defecto = None if cpu_hilos or nativa else sin_modelfile(base)
    descargar_todo()
    prompt = PARRAFO * 160 + "\n\n" + PREGUNTA
    reps = []
    # El identificador va al principio: si solo cambiara el final, Ollama reutilizaría el prompt ya procesado
    for rep in range(REPETICIONES + 1):  # la primera es calentamiento (carga en memoria)
        r = api("/api/chat", {"model": modelo, "stream": False, "keep_alive": "10m",
                              "messages": [{"role": "user", "content": f"Documento {rep}-{time.time_ns()}.\n\n" + prompt}],
                              "options": {"num_predict": 200, "temperature": 0, **extra}, **opciones_pensar(modelo)})
        if rep == 0:
            carga_s = r.get("load_duration", 0) / 1e9
            ps = cargado(modelo)
            continue
        reps.append({
            "rep": rep,
            "tokens_prompt": r.get("prompt_eval_count", 0),
            "lectura_tok_s": r["prompt_eval_count"] / (r["prompt_eval_duration"] / 1e9) if r.get("prompt_eval_duration") else None,
            "tokens_respuesta": r.get("eval_count", 0),
            "escritura_tok_s": r["eval_count"] / (r["eval_duration"] / 1e9) if r.get("eval_duration") else None,
            "segundos_hasta_respuesta": r.get("prompt_eval_duration", 0) / 1e9,
            "segundos_total": r.get("total_duration", 0) / 1e9,
        })
    herramientas = []
    for texto, esperada, args_req in PETICIONES:
        t0 = time.perf_counter()
        # La API compatible con OpenAI no deja apagar la GPU, y OpenClaw usa la nativa: mismas herramientas por /api/chat
        if cpu_hilos or nativa:
            r = api("/api/chat", {"model": modelo, "stream": False, "tools": HERRAMIENTAS, "messages": [{"role": "user", "content": texto}],
                                  "options": {"temperature": 0, **extra}, **opciones_pensar(modelo)})
            llamadas = [{"function": {"name": c["function"]["name"], "arguments": json.dumps(c["function"]["arguments"])}}
                        for c in r["message"].get("tool_calls") or []]
        else:
            r = api("/v1/chat/completions", {"model": modelo, "temperature": 0, "tools": HERRAMIENTAS,
                                              "messages": [{"role": "user", "content": texto}], **opciones_pensar(modelo)})
            llamadas = (r["choices"][0]["message"].get("tool_calls") or [])
        nombre = llamadas[0]["function"]["name"] if llamadas else None
        try:
            args = json.loads(llamadas[0]["function"]["arguments"]) if llamadas else {}
            json_ok = isinstance(args, dict)
        except (ValueError, TypeError):
            args, json_ok = {}, False
        herramientas.append({"peticion": texto, "esperada": esperada, "llamada": nombre, "json_valido": json_ok,
                             "argumentos_completos": args_req.issubset(args.keys()),
                             "acierto": nombre == esperada and json_ok and args_req.issubset(args.keys()),
                             "segundos": time.perf_counter() - t0})
    ps_tras_herramientas = cargado(modelo)
    descargar_todo()
    med = lambda k: statistics.median(x[k] for x in reps if x[k] is not None)
    return {
        "modelo": base, "variante": modelo, "contexto": CONTEXTO, "solo_cpu_hilos": cpu_hilos, "api": "nativa" if cpu_hilos or nativa else "openai",
        "sin_modelfile": por_defecto,
        "contexto_en_herramientas": ps_tras_herramientas.get("context_length"),
        "memoria_gb": ps.get("size", 0) / 1e9, "memoria_gpu_gb": ps.get("size_vram", 0) / 1e9,
        "en_gpu_pct": 100 * ps.get("size_vram", 0) / ps["size"] if ps.get("size") else None,
        "contexto_cargado": ps.get("context_length"), "carga_s": carga_s,
        "lectura_tok_s_mediana": med("lectura_tok_s"), "escritura_tok_s_mediana": med("escritura_tok_s"),
        "segundos_hasta_respuesta_mediana": med("segundos_hasta_respuesta"), "tokens_prompt": reps[0]["tokens_prompt"],
        "aciertos_herramientas": sum(h["acierto"] for h in herramientas), "pruebas_herramientas": len(herramientas),
        "repeticiones": reps, "herramientas": herramientas,
    }


def main():
    os.makedirs(RES, exist_ok=True)
    args = sys.argv[1:]
    global CONTEXTO
    cpu = int(args[args.index("--cpu") + 1]) if "--cpu" in args else None
    openclaw = "--openclaw" in args
    if openclaw:
        CONTEXTO = 32768
    modelos = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] != "--cpu")]
    salida = os.path.join(RES, "modelos_openclaw.json" if openclaw else "modelos.json")
    previos = json.load(open(salida)) if os.path.exists(salida) else {}
    for m in modelos:
        clave = f"{m} (CPU, {cpu} hilos)" if cpu else m
        print("midiendo", clave, flush=True)
        previos[clave] = medir(m, cpu, openclaw)
        json.dump(previos, open(salida, "w"), ensure_ascii=False, indent=1)
        r = previos[clave]
        print(f"  {r['memoria_gb']:.1f} GB ({r['en_gpu_pct']:.0f} % en GPU) · lectura {r['lectura_tok_s_mediana']:.0f} tok/s · "
              f"escritura {r['escritura_tok_s_mediana']:.1f} tok/s · herramientas {r['aciertos_herramientas']}/{r['pruebas_herramientas']}", flush=True)
    entorno = {"fecha": time.strftime("%Y-%m-%d"), "equipo": subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip(),
               "ram_gb": int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout) / 2**30,
               "sistema": platform.platform(), "ollama": api("/api/version")["version"],
               "energia": subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True).stdout.splitlines()[0]}
    json.dump(entorno, open(os.path.join(RES, "entorno_medicion.json"), "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
