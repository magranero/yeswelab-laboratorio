"""Analiza las salidas reales de medir.py y escribe resultados/resumen.json.

    uv run --with json-repair python analizar.py
"""

import json
import re
import statistics
from collections import Counter, defaultdict

from json_repair import repair_json

from medir import valida

TIPOS = ["sin_json", "cortado", "cierre_equivocado", "markdown", "texto_extra", "coma_final", "comillas_simples", "comentario", "otro_sintaxis", "devuelve_esquema", "no_cumple_esquema"]


def leer(archivo):
    try:
        with open(archivo, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError:
        return []


def estricto(texto):
    try:
        return json.loads(texto)
    except Exception:
        return None


def tipo_error(fila) -> str:
    """Clasifica por qué json.loads rechaza la salida (el primer motivo que encaja, en este orden)."""
    t = fila["texto"]
    if fila.get("fin") == "length":
        return "cortado"
    if "{" not in t:
        return "sin_json"  # negativas («no puedo cumplir con esa solicitud») u otra respuesta sin JSON
    if "```" in t:
        return "markdown"
    limpio = t.strip()
    if limpio and (limpio[0] not in "{[" or limpio[-1] not in "}]"):
        return "texto_extra"
    aperturas, cierres = limpio.count("{") + limpio.count("["), limpio.count("}") + limpio.count("]")
    if aperturas > cierres:
        return "cortado"
    if limpio.count("{") != limpio.count("}") or limpio.count("[") != limpio.count("]"):
        return "cierre_equivocado"  # p. ej. cierra una lista con } en vez de ]
    if re.search(r",\s*[}\]]", t):
        return "coma_final"
    if re.search(r"'\w+'\s*:", t):
        return "comillas_simples"
    if re.search(r"//|/\*", t):
        return "comentario"
    return "otro_sintaxis"


def clasifica(fila, obj, reparado) -> str | None:
    """None si la salida vale tal cual (json.loads + esquema). Si no, el tipo de fallo."""
    if obj is not None and fila.get("fin") != "length" and valida(obj):
        return None
    if es_esquema(reparado) and not (isinstance(reparado, dict) and isinstance(reparado.get("cliente"), dict)):
        return "devuelve_esquema"
    if obj is not None and fila.get("fin") != "length":
        return "no_cumple_esquema"
    return tipo_error(fila)


def correcto(obj, verdad) -> bool:
    """Pedido correcto si coinciden email, empresa, ciudad, fecha, urgencia y las líneas (sku y cantidad)."""
    try:
        if obj["cliente"]["email"] != verdad["cliente"]["email"]:
            return False
        if (obj["cliente"].get("empresa") or None) != verdad["cliente"]["empresa"] and not (obj["cliente"].get("empresa") is None and verdad["cliente"]["empresa"] is None):
            return False
        if obj["entrega"]["ciudad"] != verdad["entrega"]["ciudad"] or (obj["entrega"].get("fecha") or None) != verdad["entrega"]["fecha"]:
            return False
        if bool(obj["urgente"]) != verdad["urgente"]:
            return False
        lin = sorted((l["sku"], int(l["cantidad"])) for l in obj["lineas"])
        return lin == sorted((l["sku"], l["cantidad"]) for l in verdad["lineas"])
    except Exception:
        return False


def es_esquema(obj) -> bool:
    """El modelo copia el esquema en vez de (o además de) devolver los datos."""
    if isinstance(obj, list):
        return any(es_esquema(x) for x in obj)
    return isinstance(obj, dict) and ("properties" in obj or obj.get("type") == "object")


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def main() -> None:
    verdad = {d["correo"]: d["verdad"] for d in leer("resultados/corpus.jsonl")}
    libre, restringida = leer("resultados/libre.jsonl"), leer("resultados/restringida.jsonl")
    salida = {"modelos": {}}
    global_tipos, global_reparados = Counter(), Counter()

    for modelo in sorted({f["modelo"] for f in libre}):
        filas = [f for f in libre if f["modelo"] == modelo]
        n = len(filas)
        ok_estricto, tipos, rep_tipo = 0, Counter(), Counter()
        validos_local, correctos_local, esquema_devuelto = 0, 0, 0
        reintentos, ok_tras_reintento, correctos_tras_reintento = [], 0, 0
        for f in filas:
            v = verdad[f["correo"]]
            obj = estricto(f["texto"])
            reparado = repair_json(f["texto"], return_objects=True)
            t = clasifica(f, obj, reparado)
            vale = f.get("fin") != "length" and valida(reparado)
            if t is None:
                ok_estricto += 1
            else:
                tipos[t] += 1
                rep_tipo[t] += vale
                esquema_devuelto += t == "devuelve_esquema"
            if vale:
                validos_local += 1
                correctos_local += correcto(reparado, v)
            if "reintento" in f:
                r = f["reintento"]
                reintentos.append(r)
                r_obj = repair_json(r["texto"], return_objects=True)
                if r.get("fin") != "length" and valida(r_obj):
                    ok_tras_reintento += 1
                    correctos_tras_reintento += correcto(r_obj, v)
        fallos = n - ok_estricto
        global_tipos.update(tipos)
        global_reparados.update(rep_tipo)
        llamada = [f["tokens_entrada"] + f["tokens_salida"] for f in filas]
        coste_reintento = [r["tokens_entrada"] + r["tokens_salida"] for r in reintentos]
        # Coste estimado de reintentar una salida concreta: se reenvía lo de la llamada original más la salida rota y
        # un mensaje de error (~25 tokens), y el modelo genera de nuevo una salida de longitud parecida.
        estimado = {id(f): f["tokens_entrada"] + f["tokens_salida"] + 25 + f["tokens_salida"] for f in filas}
        reales_vs_estimados = [(f["reintento"]["tokens_entrada"] + f["reintento"]["tokens_salida"]) / estimado[id(f)] for f in filas if "reintento" in f]
        mediana_reintento = statistics.median(coste_reintento) if coste_reintento else None
        tokens_llamadas = sum(llamada)
        # Pipeline A: reintentar ante cualquier salida que no valga tal cual. Coste real si hubo reintento real; si no
        # (porque se reparó en local), el coste estimado de esa misma salida.
        extra_a = 0
        for f in filas:
            if clasifica(f, estricto(f["texto"]), repair_json(f["texto"], return_objects=True)) is None:
                continue
            extra_a += (f["reintento"]["tokens_entrada"] + f["reintento"]["tokens_salida"]) if "reintento" in f else estimado[id(f)]
        # Pipeline B: reparar en local y reintentar solo lo que no se repara (reintentos reales).
        extra_b = sum(coste_reintento)
        salida["modelos"][modelo] = {
            "salidas": n,
            "validas_sin_reparar": ok_estricto,
            "validas_sin_reparar_pct": round(100 * ok_estricto / n, 1),
            "fallos": fallos,
            "fallos_pct": round(100 * fallos / n, 1),
            "fallos_por_tipo": dict(tipos),
            "reparados_por_tipo": dict(rep_tipo),
            "devuelve_el_esquema": esquema_devuelto,
            "validos_tras_reparar_local": validos_local,
            "validos_tras_reparar_local_pct": round(100 * validos_local / n, 1),
            "pedidos_correctos_tras_reparar_local": correctos_local,
            "pedidos_correctos_tras_reparar_local_pct": round(100 * correctos_local / n, 1),
            "reintentos_reales": len(reintentos),
            "reintentos_que_arreglan": ok_tras_reintento,
            "reintentos_con_pedido_correcto": correctos_tras_reintento,
            "tokens_llamada_mediana": med(llamada),
            "tokens_reintento_mediana": med(coste_reintento),
            "reintento_real_vs_estimado_mediana": round(statistics.median(reales_vs_estimados), 3) if reales_vs_estimados else None,
            "ms_llamada_mediana": med([f["ms"] for f in filas]),
            "ms_reintento_mediana": med([r["ms"] for r in reintentos]),
            "tokens_extra_reintentar_siempre_por_1000": round(1000 * extra_a / n) if n else None,
            "tokens_extra_reparar_primero_por_1000": round(1000 * extra_b / n) if n else None,
            "tokens_totales_reintentar_siempre_por_1000": round(1000 * (tokens_llamadas + extra_a) / n),
            "tokens_totales_reparar_primero_por_1000": round(1000 * (tokens_llamadas + extra_b) / n),
            "ahorro_tokens_totales_pct": round(100 * (1 - (tokens_llamadas + extra_b) / (tokens_llamadas + extra_a)), 1) if extra_a else 0.0,
            "reintentos_evitados_pct": round(100 * (1 - len(reintentos) / fallos), 1) if fallos else None,
        }

    for modelo in sorted({f["modelo"] for f in restringida}):
        filas = [f for f in restringida if f["modelo"] == modelo]
        n = len(filas)
        validos = [f for f in filas if f.get("fin") != "length" and valida(estricto(f["texto"]) or {})]
        correctos = sum(correcto(estricto(f["texto"]), verdad[f["correo"]]) for f in validos)
        salida["modelos"].setdefault(modelo, {})["restringida"] = {
            "salidas": n,
            "json_valido": sum(1 for f in filas if estricto(f["texto"]) is not None),
            "valido_segun_esquema": len(validos),
            "pedidos_correctos": correctos,
            "pedidos_correctos_pct": round(100 * correctos / n, 1) if n else None,
            "tokens_mediana": med([f["tokens_entrada"] + f["tokens_salida"] for f in filas]),
            "ms_mediana": med([f["ms"] for f in filas]),
        }

    # Sensibilidad: el ahorro en tokens extra de «reparar primero» frente a «reintentar siempre» es la parte de
    # los fallos que se repara en local. Se calcula con la tasa de reparación medida para cada tipo.
    tasa = {t: (global_reparados[t] / global_tipos[t]) for t in TIPOS if global_tipos[t]}
    total_fallos = sum(global_tipos.values())
    mezcla_real = {t: global_tipos[t] / total_fallos for t in global_tipos} if total_fallos else {}
    def ahorro(mezcla):
        return round(100 * sum(p * tasa.get(t, 0) for t, p in mezcla.items()), 1)
    escenarios = {"mezcla_real": ahorro(mezcla_real)}
    for t in tasa:
        escenarios[f"todo_{t}"] = ahorro({t: 1.0})
    if "cortado" in tasa:
        resto = {t: p for t, p in mezcla_real.items() if t != "cortado"}
        total_resto = sum(resto.values()) or 1
        for parte in (0.25, 0.5, 0.75):
            mezcla = {"cortado": parte, **{t: (1 - parte) * p / total_resto for t, p in resto.items()}}
            escenarios[f"cortados_{int(parte * 100)}pct"] = ahorro(mezcla)
    salida["errores_globales"] = {
        "fallos": total_fallos,
        "por_tipo": dict(global_tipos),
        "reparados_por_tipo": dict(global_reparados),
        "tasa_reparacion_por_tipo_pct": {t: round(100 * v, 1) for t, v in tasa.items()},
        "mezcla_real_pct": {t: round(100 * v, 1) for t, v in mezcla_real.items()},
    }
    salida["sensibilidad_ahorro_tokens_extra_pct"] = escenarios
    with open("resultados/resumen.json", "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1)
    print(json.dumps(salida, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
