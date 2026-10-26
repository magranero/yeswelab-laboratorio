"""Descarga y ordena tablas del INE (API JSON de INEbase, Tempus3).

Cada tabla se guarda en bruto la primera vez y se reutiliza después, para que el cuaderno se pueda
repetir sin conexión y con los mismos datos.
"""

import json
import os
import re
import time
import urllib.request

import pandas as pd

API = "https://servicios.ine.es/wstempus/jsCache/ES/DATOS_TABLA/{tabla}?tip=AM{extra}"
UA = {"User-Agent": "yeswelab-laboratorio/1.0 (+https://yeswelab.com)"}


def descargar(tabla: int, carpeta: str, extra: str = "") -> list:
    """JSON en bruto de una tabla del INE, con caché en disco."""
    ruta = os.path.join(carpeta, f"ine_{tabla}.json")
    if not os.path.exists(ruta):
        os.makedirs(carpeta, exist_ok=True)
        for intento in range(4):
            try:
                req = urllib.request.Request(API.format(tabla=tabla, extra=extra), headers=UA)
                with urllib.request.urlopen(req, timeout=300) as r:
                    open(ruta, "wb").write(r.read())
                break
            except OSError:
                if intento == 3:
                    raise
                time.sleep(10 * (intento + 1))
    return json.load(open(ruta, encoding="utf-8"))


def ordenar(series: list) -> pd.DataFrame:
    """Una fila por serie: una columna por dimensión de la tabla y el valor del último periodo."""
    filas = []
    for s in series:
        fila = {m["T3_Variable"]: m["Nombre"].strip() for m in s["MetaData"]}
        dato = s["Data"][-1] if s["Data"] else {}
        fila["valor"] = dato.get("Valor")
        fila["nombre_serie"] = s["Nombre"]
        filas.append(fila)
    return pd.DataFrame(filas)


def codigo(variable: str) -> str:
    """«D.1.A % de empresas que…» → «D.1.A»."""
    m = re.match(r"\s*([A-Z]\.\d+(?:\.[A-Z])?)", variable)
    return m.group(1) if m else variable


def etiqueta(variable: str) -> str:
    """Texto corto de una variable, sin código, sin «% de empresas que…» y sin la nota «(2)»."""
    t = re.sub(r"^\s*[A-Z]\.\d+(?:\.[A-Z])?\s*", "", variable)
    t = re.sub(r"\s*\(\d\)\s*$", "", t)
    for quitar in ("% de empresas que emplean tecnologías de IA para ", "% de empresas que emplean tecnología IA ",
                   "% de empresas con tecnología IA ", "% de empresas que emplean tecnologías de IA ",
                   "% de empresas que no utilizan ninguna de las tecnologías de IA de D.1 debido a ",
                   "% de empresas que no utilizan ninguna de las tecnologías de IA de D.1  debido a ",
                   "% de empresas que no utilizan ninguna de las tecnologías de IA de E.1 porque: "):
        t = t.replace(quitar, "")
    return t.strip()


def redondear(x, decimales: int = 1):
    """Redondeo a la mitad hacia arriba, como publica el INE (79,55 → 79,6). Se aplica una sola vez, al final."""
    from decimal import ROUND_HALF_UP, Decimal

    q = Decimal(1).scaleb(-decimales)
    uno = lambda v: float(Decimal(str(v)).quantize(q, ROUND_HALF_UP)) if isinstance(v, (int, float)) and v == v else v
    if isinstance(x, pd.DataFrame):
        return x.map(uno)
    if isinstance(x, pd.Series):
        return x.map(uno)
    return uno(x)
