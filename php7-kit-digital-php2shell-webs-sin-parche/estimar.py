"""Estimación de cuántas webs del Kit Digital siguen en una versión de PHP sin parche de PHP2Shell.

Solo usa datos públicos agregados; no consulta ninguna web de pymes:
  1. Contadores oficiales del Kit Digital (kitdigital.red.es): soluciones «Sitio Web y Presencia en Internet».
  2. W3Techs: cuota de PHP en la web y reparto de versiones (PHP 8.x, PHP 7, PHP 5).

PHP2Shell se corrigió en PHP 8.2 a 8.5. Sin parche quedan PHP 8.1, 8.0, 7.x y anteriores.

    python3 estimar.py
"""

import datetime as dt
import html
import json
import re
import time
import urllib.request

UA = {"User-Agent": "yeswelab-laboratorio/1.0 (+https://yeswelab.com)"}


def texto(url: str) -> str:
    for intento in range(4):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                h = r.read().decode("utf-8", "ignore")
            break
        except OSError:
            if intento == 3:
                raise
            time.sleep(10 * (intento + 1))
    h = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)))


def numero(s: str) -> int:
    return int(s.replace(".", ""))


def kit_digital() -> dict:
    t = texto("https://www.kitdigital.red.es/")
    categorias = {m.group(2).strip(): numero(m.group(1))
                  for m in re.finditer(r"([\d.]{4,}) ((?:Sitio Web y Presencia en Internet|Comercio electrónico|Presencia Avanzada en Internet))", t)}
    act = re.search(r"última actualización de datos es el (\d{2}/\d{2}/\d{4})", t)
    ayudas = re.search(r"\+([\d.]+) Ayudas concedidas", t)
    return {"fuente": "https://www.kitdigital.red.es/", "actualizacion": act.group(1) if act else None,
            "ayudas_concedidas": numero(ayudas.group(1)) if ayudas else None, "soluciones": categorias}


def w3techs() -> dict:
    t = texto("https://w3techs.com/technologies/details/pl-php")
    t8 = texto("https://w3techs.com/technologies/details/pl-php/8")
    cuota = re.search(r"PHP is used by ([\d.]+)% of all the websites whose server-side programming language we know", t)
    return {"php_en_webs_con_lenguaje_conocido_pct": float(cuota.group(1)),
            "por_version_principal_pct": {m.group(1): float(m.group(2)) for m in re.finditer(r"Version (\d)\s+([\d.]+)%", t)},
            "dentro_de_php8_pct": {m.group(1): float(m.group(2)) for m in re.finditer(r"Version (8\.\d)\s+([\d.]+)%", t8)}}


def main() -> None:
    kd, w3 = kit_digital(), w3techs()
    webs = kd["soluciones"]["Sitio Web y Presencia en Internet"]
    v, v8 = w3["por_version_principal_pct"], w3["dentro_de_php8_pct"]
    # Sin parche de PHP2Shell, en % de las webs con PHP (sin redondear hasta el final)
    php8_sin = v.get("8", 0) * (v8.get("8.0", 0) + v8.get("8.1", 0)) / 100
    php_antiguo = v.get("7", 0) + v.get("5", 0) + v.get("4", 0)
    sin_parche = php8_sin + php_antiguo
    php = w3["php_en_webs_con_lenguaje_conocido_pct"] / 100
    escenarios = {
        # Mezcla de la web mundial: 69,3 % con PHP y su reparto de versiones
        "central": webs * php * sin_parche / 100,
        # Solo PHP 7 o anterior (sin contar 8.0 y 8.1)
        "bajo_solo_php7_o_anterior": webs * php * php_antiguo / 100,
        # Todas las webs del Kit Digital en PHP (p. ej., todas en WordPress)
        "alto_todas_en_php": webs * sin_parche / 100,
    }
    salida = {
        "fecha": str(dt.date.today()),
        "kit_digital": kd,
        "w3techs": w3,
        "sin_parche_php2shell_pct_de_webs_php": round(sin_parche, 1),
        "php8_0_y_8_1_pct_de_webs_php": round(php8_sin, 1),
        "php7_o_anterior_pct_de_webs_php": round(php_antiguo, 1),
        "webs_kit_digital": webs,
        "estimacion_webs_sin_parche": {k: int(round(x, -2)) for k, x in escenarios.items()},
        "supuestos": [
            "Todas las webs pagadas siguen en línea (no hay dato público de cuántas se han dado de baja).",
            "Las webs del Kit Digital reparten lenguaje y versiones de PHP como la web mundial según W3Techs.",
            "Una solución «Sitio Web y Presencia en Internet» es una web.",
        ],
    }
    with open("resultados/estimacion.json", "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1)
    print(json.dumps(salida, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
