"""PHP 7, el Kit Digital y PHP2Shell: lo que se puede medir con datos públicos.

Recoge y guarda en resultados/:
  1. Fechas oficiales de PHP (php.net): lanzamiento y fin de soporte de cada rama 7.x, última 7.4.
  2. Versiones de seguridad publicadas para PHP 8 desde que PHP 7.4 dejó de recibir parches (php.net).
  3. CVE y avisos de seguridad corregidos en PHP 8 desde ese día (ChangeLog de php.net) y, para cada CVE,
     si la base de datos oficial NVD lista PHP 7.x como afectado.
  4. Calendario del Kit Digital (aperturas de convocatoria) frente al fin de soporte de PHP 7.4.
  5. Qué exigen las bases del BOE a una web del Kit Digital y cuántas veces mencionan seguridad o actualizaciones.
  6. Cuota de versiones de PHP en la web según W3Techs (día de la ejecución).

    uv run python medir.py
No hace ninguna petición a webs de terceros más allá de esas fuentes públicas.
"""

import datetime as dt
import html
import json
import re
import time
import urllib.request

UA = {"User-Agent": "yeswelab-laboratorio/1.0 (+https://yeswelab.com)"}
HOY = dt.date.today()
FIN_74 = dt.date(2022, 11, 28)


def get(url: str, decode=True):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data.decode("utf-8", "ignore") if decode else data


def texto(h: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)))


def fecha(s: str) -> dt.date:
    return dt.datetime.strptime(s.strip(), "%d %b %Y").date()


def php_eol() -> dict:
    t = texto(get("https://www.php.net/eol.php"))
    salida = {}
    for v in ["5.6", "7.0", "7.1", "7.2", "7.3", "7.4", "8.0", "8.1"]:
        m = re.search(r"\b" + re.escape(v) + r"\b\s+(\d{1,2} \w{3} \d{4})", t)
        if m:
            salida[v] = str(fecha(m.group(1)))
    return salida


def ultima(version: str) -> dict:
    d = json.loads(get(f"https://www.php.net/releases/index.php?json&version={version}&max=1"))
    k = next(iter(d))
    return {"version": k, "fecha": str(fecha(d[k]["date"]))}


def lanzamiento_70() -> str:
    d = json.loads(get("https://www.php.net/releases/index.php?json&version=7.0&max=100"))
    return str(fecha(d["7.0.0"]["date"])) if "7.0.0" in d else ""


def seguridad_desde(desde: dt.date) -> list[dict]:
    versiones = []
    for rama in ["8.0", "8.1", "8.2", "8.3", "8.4", "8.5"]:
        d = json.loads(get(f"https://www.php.net/releases/index.php?json&version={rama}&max=200"))
        for v, info in d.items():
            f = fecha(info["date"])
            if f > desde and "security" in (info.get("tags") or []):
                versiones.append({"version": v, "fecha": str(f)})
    return sorted(versiones, key=lambda x: (x["fecha"], x["version"]))


def changelog_desde(desde: dt.date) -> tuple[dict, dict]:
    """CVE y GHSA citados en el ChangeLog de PHP 8 en versiones publicadas después de `desde`."""
    t = texto(get("https://www.php.net/ChangeLog-8.php"))
    cves, ghsas = {}, {}
    partes = re.split(r"Version (8\.\d+\.\d+) (\d{1,2} \w{3} \d{4})", t)
    for i in range(1, len(partes) - 2, 3):
        version, f, cuerpo = partes[i], fecha(partes[i + 1]), partes[i + 2]
        if f <= desde:
            continue
        # Solo CVE de 2022 en adelante: los antiguos aparecen como referencia («bypass de CVE-2012-1823»).
        for c in {c for c in re.findall(r"CVE-(\d{4})-\d{4,}", cuerpo) and re.findall(r"CVE-\d{4}-\d{4,}", cuerpo) if int(c[4:8]) >= 2022}:
            cves.setdefault(c, {"primera_version": version, "fecha": str(f)})
            if str(f) < cves[c]["fecha"]:
                cves[c] = {"primera_version": version, "fecha": str(f)}
        for g in set(re.findall(r"GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}", cuerpo)):
            ghsas.setdefault(g, {"primera_version": version, "fecha": str(f)})
    return cves, ghsas


def tupla(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def nvd_afecta_7(cve: str) -> dict:
    """Consulta NVD y dice si alguna configuración vulnerable incluye una versión 7.x de PHP."""
    url = f"https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={cve}"
    for intento in range(4):
        try:
            d = json.loads(get(url))
            break
        except Exception:
            time.sleep(10 * (intento + 1))
    else:
        return {"cve": cve, "en_nvd": None}
    vulns = d.get("vulnerabilities") or []
    if not vulns:
        return {"cve": cve, "en_nvd": False}
    c = vulns[0]["cve"]
    afecta7 = False
    cvss = None
    for m in (c.get("metrics") or {}).values():
        if m:
            cvss = m[0].get("cvssData", {}).get("baseScore")
            break
    for conf in c.get("configurations") or []:
        for nodo in conf.get("nodes") or []:
            for cm in nodo.get("cpeMatch") or []:
                if not cm.get("vulnerable") or ":php:php:" not in cm.get("criteria", ""):
                    continue
                exacta = cm["criteria"].split(":")[5]
                ini = cm.get("versionStartIncluding") or cm.get("versionStartExcluding")
                fin_ex, fin_in = cm.get("versionEndExcluding"), cm.get("versionEndIncluding")
                if exacta not in ("*", "-") and exacta.startswith("7."):
                    afecta7 = True
                elif exacta == "*":
                    desde_ok = ini is None or tupla(ini) <= (7, 4, 33)
                    hasta_ok = (fin_ex and tupla(fin_ex) > (7, 4, 33)) or (fin_in and tupla(fin_in) >= (7, 4, 33)) or (not fin_ex and not fin_in)
                    if desde_ok and hasta_ok:
                        afecta7 = True
    return {"cve": cve, "en_nvd": True, "cvss": cvss, "nvd_incluye_php7": afecta7}


def boe_kit_digital() -> dict:
    t = texto(get("https://www.boe.es/diario_boe/txt.php?id=BOE-A-2021-21873"))
    i = t.find("Sitio web y presencia en internet Objetivo")
    j = t.find("Categoría de solución de digitalización II", i)
    bloque = t[i:j]
    terminos = ["seguridad", "actualiz", "mantenimiento", "parche", "PHP", "versión"]
    return {
        "fuente": "BOE-A-2021-21873 (Orden ETD/1498/2021), anexo IV, Sitio web y presencia en internet",
        "importe_euros": 2000,
        "doce_meses_dominio": "Dominio: alta de nuevo dominio para la pyme beneficiaria durante un plazo mínimo de doce meses" in bloque,
        "doce_meses_hosting": "alojamiento de la página web desarrollada durante un plazo mínimo de doce meses" in bloque,
        "exige_wcag_aa": "nivel AA" in bloque,
        "palabras_del_requisito": len(bloque.split()),
        "menciones": {k: len(re.findall(k, bloque, re.I)) for k in terminos},
    }


def w3techs() -> dict:
    t = texto(get("https://w3techs.com/technologies/details/pl-php"))
    t7 = texto(get("https://w3techs.com/technologies/details/pl-php/7"))
    cuota = re.search(r"PHP is used by ([\d.]+)% of all the websites", t)
    return {
        "fecha_consulta": str(HOY),
        "php_en_webs_pct": float(cuota.group(1)) if cuota else None,
        "por_version_principal_pct": {m.group(1): float(m.group(2)) for m in re.finditer(r"Version (\d)\s+([\d.]+)%", t)},
        "dentro_de_php7_pct": {m.group(1): float(m.group(2)) for m in re.finditer(r"Version (7\.\d)\s+([\d.]+)%", t7)},
    }


def main() -> None:
    eol = php_eol()
    kit = {"segmento_I": "2022-03-15", "segmento_II": "2022-09-02", "segmento_III": "2022-10-20"}
    calendario = {
        s: {"apertura": f, "dias_de_soporte_que_le_quedaban_a_php74": (FIN_74 - dt.date.fromisoformat(f)).days}
        for s, f in kit.items()
    }
    seg = seguridad_desde(FIN_74)
    cves, ghsas = changelog_desde(FIN_74)
    nvd = []
    for c in sorted(cves):
        nvd.append(nvd_afecta_7(c))
        time.sleep(7)  # NVD sin clave: 5 peticiones cada 30 s
    w3 = w3techs()
    sin_parche = round(w3["php_en_webs_pct"] * (w3["por_version_principal_pct"].get("7", 0) + w3["por_version_principal_pct"].get("5", 0)) / 100, 1) if w3["php_en_webs_pct"] else None
    resumen = {
        "fecha": str(HOY),
        "php": {
            "lanzamiento_7_0": lanzamiento_70(),
            "fin_de_soporte": eol,
            "ultima_7_4": ultima("7.4"),
            "dias_desde_fin_7_4": (HOY - FIN_74).days,
            "ultimas_versiones_8": {r: ultima(r) for r in ["8.2", "8.3", "8.4", "8.5"]},
        },
        "desde_fin_7_4": {
            "versiones_de_seguridad_php8": len(seg),
            "cve_corregidos_en_php8": len(cves),
            "cve_en_nvd": sum(1 for x in nvd if x.get("en_nvd")),
            "cve_que_nvd_marca_en_php7": sum(1 for x in nvd if x.get("nvd_incluye_php7")),
            "avisos_ghsa_en_changelog": len(ghsas),
        },
        "kit_digital": {"calendario": calendario, "requisitos_web": boe_kit_digital()},
        "w3techs": w3,
        "webs_con_php_5_o_7_sobre_el_total_pct": sin_parche,
    }
    with open("resultados/versiones_seguridad_php8.json", "w", encoding="utf-8") as f:
        json.dump(seg, f, indent=1)
    with open("resultados/cve_desde_fin_php74.json", "w", encoding="utf-8") as f:
        json.dump({"cves": cves, "nvd": nvd, "ghsa": ghsas}, f, indent=1)
    with open("resultados/resumen.json", "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=1)
    print(json.dumps(resumen, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
