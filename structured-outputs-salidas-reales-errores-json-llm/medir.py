"""Structured outputs con salidas REALES: qué errores comete de verdad un LLM al devolver JSON,
cuántos se reparan en local y cuánto cuesta un reintento real.

Modelos abiertos ejecutados en local con Ollama. Cada modelo extrae pedidos de correos en español:

  A. Generación libre (sin restringir el formato), 5 semillas por correo. Se guarda cada salida tal cual.
  B. Reintento real: cuando la salida no se puede reparar en local, se le pide al modelo que la corrija
     (se registran tokens y tiempo que devuelve Ollama).
  C. Generación restringida al esquema (salida estructurada de Ollama, gramática JSON Schema; mismo
     principio que Outlines), 5 semillas por correo.

Los resultados se van guardando en resultados/*.jsonl y se puede reanudar. El análisis está en analizar.py.

    uv run --with json-repair python medir.py --modelos llama3.2 qwen2.5:3b gemma3:4b llama3.1 --correos 60
"""

import argparse
import json
import os
import random
import time
import urllib.request

from json_repair import repair_json

OLLAMA = "http://127.0.0.1:11434/api/chat"
INSTRUCCIONES = (
    "Eres un agente que extrae pedidos de correos de clientes. Devuelve SOLO un JSON válido que cumpla este esquema, "
    "sin texto antes ni después. Si un campo no aparece, usa null."
)
ESQUEMA = {
    "type": "object",
    "properties": {
        "cliente": {"type": "object", "properties": {"nombre": {"type": "string"}, "email": {"type": "string"}, "empresa": {"type": ["string", "null"]}}, "required": ["nombre", "email", "empresa"]},
        "lineas": {"type": "array", "items": {"type": "object", "properties": {"sku": {"type": "string"}, "descripcion": {"type": "string"}, "cantidad": {"type": "integer"}, "precio_unitario": {"type": ["number", "null"]}}, "required": ["sku", "descripcion", "cantidad", "precio_unitario"]}},
        "urgente": {"type": "boolean"},
        "entrega": {"type": "object", "properties": {"ciudad": {"type": "string"}, "fecha": {"type": ["string", "null"]}}, "required": ["ciudad", "fecha"]},
        "notas": {"type": ["string", "null"]},
    },
    "required": ["cliente", "lineas", "urgente", "entrega", "notas"],
}
SISTEMA = INSTRUCCIONES + "\n\nEsquema:\n" + json.dumps(ESQUEMA, ensure_ascii=False, indent=2)

NOMBRES = ["Ana Ruiz", "Luis Pérez", "Marta Gómez", "Jorge Díaz", "Lucía Fernández", "Carlos Méndez", "Sofía Herrera", "Diego Castro"]
EMPRESAS = [None, "Acme SL", "Talleres Norte", "Distribuciones Sur SA", "Ferretería La Unión"]
CIUDADES = ["Madrid", "Santander", "Ciudad de México", "Bogotá", "Lima", "Valencia", "Buenos Aires", "Sevilla", "Quito", "Monterrey"]
PRODUCTOS = ["tornillos M8", "placas base", "cables USB-C", "licencias anuales", "sensores de humedad", "cajas estancas", "fuentes de 24V", "bridas de nailon"]
SALUDOS = ["Hola,", "Buenos días:", "Buenas tardes,", "Estimados señores:", "Qué tal,"]
CIERRES = ["Gracias.", "Un saludo,", "Quedo atento.", "Saludos cordiales,", "Gracias de antemano."]


def correo(r: random.Random, i: int) -> tuple[str, dict]:
    nombre, empresa = r.choice(NOMBRES), r.choice(EMPRESAS)
    email = f"{nombre.split()[0].lower()}.{i}@ejemplo.com"
    lineas = []
    for _ in range(r.randint(1, 4)):
        lineas.append({"sku": f"SKU-{r.randint(1000, 9999)}", "descripcion": r.choice(PRODUCTOS), "cantidad": r.randint(1, 60), "precio_unitario": r.choice([None, round(r.uniform(0.5, 300), 2)])})
    urgente, ciudad = r.random() < 0.3, r.choice(CIUDADES)
    fecha = r.choice([None, "2026-11-03", "2026-11-20", "2026-12-15"])
    notas = r.choice([None, "Llamar antes de entregar", "Factura a nombre de la empresa", "Dejar en recepción"])
    partes = [r.choice(SALUDOS), ""]
    partes.append(f"Les escribe {nombre}" + (f" de {empresa}" if empresa else "") + ". Quería hacer el siguiente pedido:")
    for l in lineas:
        precio = f" a {str(l['precio_unitario']).replace('.', ',')} € la unidad" if l["precio_unitario"] else ""
        partes.append(f"- {l['cantidad']} {l['descripcion']} (ref. {l['sku']}){precio}")
    partes.append(f"La entrega sería en {ciudad}" + (f" el {fecha}" if fecha else "") + ".")
    if urgente:
        partes.append(r.choice(["Es urgente, lo necesitamos cuanto antes.", "Por favor, tratadlo con urgencia."]))
    if notas:
        partes.append(f"Nota: {notas.lower()}.")
    partes += ["", r.choice(CIERRES), nombre, email]
    verdad = {"cliente": {"nombre": nombre, "email": email, "empresa": empresa}, "lineas": lineas, "urgente": urgente, "entrega": {"ciudad": ciudad, "fecha": fecha}, "notas": notas}
    return "\n".join(partes), verdad


def chat(modelo: str, mensajes: list, semilla: int, formato=None) -> dict:
    cuerpo = {"model": modelo, "messages": mensajes, "stream": False, "options": {"temperature": 0.7, "seed": semilla, "num_predict": 600}}
    if formato is not None:
        cuerpo["format"] = formato
    req = urllib.request.Request(OLLAMA, data=json.dumps(cuerpo).encode(), headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=300) as resp:
        d = json.loads(resp.read())
    return {
        "texto": d["message"]["content"],
        "fin": d.get("done_reason"),
        "tokens_entrada": d.get("prompt_eval_count", 0),
        "tokens_salida": d.get("eval_count", 0),
        "ms": round((time.perf_counter() - t0) * 1000, 1),
    }


def valida(obj) -> bool:
    """Validación mínima contra el esquema (tipos y campos obligatorios)."""
    try:
        c, e = obj["cliente"], obj["entrega"]
        assert isinstance(c["nombre"], str) and isinstance(c["email"], str)
        assert isinstance(obj["urgente"], bool) and isinstance(e["ciudad"], str)
        assert isinstance(obj["lineas"], list) and obj["lineas"]
        for l in obj["lineas"]:
            assert isinstance(l["sku"], str) and isinstance(l["cantidad"], int)
        return True
    except Exception:
        return False


def hechos(modelo, archivo):
    if not os.path.exists(archivo):
        return set()
    with open(archivo, encoding="utf-8") as f:
        return {(json.loads(l)["modelo"], json.loads(l)["correo"], json.loads(l)["semilla"]) for l in f if l.strip()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelos", nargs="+", required=True)
    ap.add_argument("--correos", type=int, default=60)
    ap.add_argument("--semillas", type=int, default=5)
    ap.add_argument("--fase", choices=["libre", "restringida", "todas"], default="todas")
    a = ap.parse_args()
    r = random.Random(2026)
    corpus = [correo(r, i) for i in range(a.correos)]
    os.makedirs("resultados", exist_ok=True)
    with open("resultados/corpus.jsonl", "w", encoding="utf-8") as f:
        for i, (texto, verdad) in enumerate(corpus):
            f.write(json.dumps({"correo": i, "texto": texto, "verdad": verdad}, ensure_ascii=False) + "\n")

    for modelo in a.modelos:
        if a.fase in ("libre", "todas"):
            archivo = "resultados/libre.jsonl"
            ya = hechos(modelo, archivo)
            with open(archivo, "a", encoding="utf-8") as f:
                for i, (texto, verdad) in enumerate(corpus):
                    for s in range(1, a.semillas + 1):
                        if (modelo, i, s) in ya:
                            continue
                        mensajes = [{"role": "system", "content": SISTEMA}, {"role": "user", "content": texto}]
                        out = chat(modelo, mensajes, s)
                        fila = {"modelo": modelo, "correo": i, "semilla": s, **out}
                        # Reintento real solo si la reparación local no deja un objeto válido según el esquema
                        reparado = repair_json(out["texto"], return_objects=True)
                        if out["fin"] == "length" or not valida(reparado):
                            mensajes += [{"role": "assistant", "content": out["texto"]},
                                         {"role": "user", "content": "Tu respuesta no es un JSON válido según el esquema. Devuelve solo el JSON corregido."}]
                            fila["reintento"] = chat(modelo, mensajes, s + 100)
                        f.write(json.dumps(fila, ensure_ascii=False) + "\n")
                        f.flush()
                    print(f"{modelo} libre: correo {i + 1}/{a.correos}", flush=True)
        if a.fase in ("restringida", "todas"):
            archivo = "resultados/restringida.jsonl"
            ya = hechos(modelo, archivo)
            with open(archivo, "a", encoding="utf-8") as f:
                for i, (texto, verdad) in enumerate(corpus):
                    for s in range(1, a.semillas + 1):
                        if (modelo, i, s) in ya:
                            continue
                        out = chat(modelo, [{"role": "system", "content": SISTEMA}, {"role": "user", "content": texto}], s, formato=ESQUEMA)
                        f.write(json.dumps({"modelo": modelo, "correo": i, "semilla": s, **out}, ensure_ascii=False) + "\n")
                        f.flush()
                    print(f"{modelo} restringida: correo {i + 1}/{a.correos}", flush=True)


if __name__ == "__main__":
    main()
