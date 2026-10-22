# /// script
# requires-python = ">=3.10"
# dependencies = ["dnspython>=2.6", "tldextract>=5.1"]
# ///
"""Qué tecnología usa una web y quién está detrás de su dominio.

Lee un .txt con una URL por línea y escribe un CSV con, para cada URL:
  1. Tecnologías detectadas con las reglas de webappanalyzer (https://github.com/enthec/webappanalyzer),
     la continuación abierta de Wappalyzer: CMS, lenguaje, servidor, analítica, CDN, etc., con versión si se ve.
  2. Datos del dominio y de contacto por RDAP (el sucesor estándar de WHOIS) o, si el dominio no tiene RDAP,
     por WHOIS clásico (puerto 43): registrador, fechas, titular, correo, teléfono y correo de abuso.

    uv run analizar_webs.py webs.txt                       # resultados/webs.csv
    uv run analizar_webs.py webs.txt -o salida.csv --detalle salida.json
    uv run --with playwright analizar_webs.py webs.txt --navegador   # + reglas js, dom y xhr

La primera vez descarga las reglas de webappanalyzer (GPL-3.0) en .webappanalyzer/; no se redistribuyen aquí.
Cada URL recibe una sola visita a la portada (más robots.txt), como un navegador normal.
"""

import argparse
import csv
import fnmatch
import html as htmlmod
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from email.message import Message
from http.cookiejar import CookieJar

import dns.resolver
import tldextract

AQUI = os.path.dirname(os.path.abspath(__file__))
# Versión fija de las reglas para que el resultado sea repetible; --reglas master para usar las últimas.
REGLAS_COMMIT = "d91f7e510e93457041bea874e8a9ffb011e3e4fe"
RAW = "https://raw.githubusercontent.com/enthec/webappanalyzer/{ref}/src/{archivo}"
UA = "Mozilla/5.0 (compatible; yeswelab-analizar-webs/1.0; +https://yeswelab.com/guias/analizar-web-tecnologia-whois/)"
TIMEOUT = 20
MAX_HTML = 3_000_000

COLUMNAS = [
    "url", "url_final", "estado_http", "dominio", "tecnologias", "cms", "lenguajes", "servidor_web",
    "analitica", "cdn", "num_tecnologias", "servicios_dns", "registrador", "alta_dominio", "caducidad_dominio",
    "titular", "titular_pais", "emails_contacto", "telefonos_contacto", "email_abuso", "servidores_dns",
    "fuente_whois", "errores",
]


# ---------- Reglas de webappanalyzer ----------

def descargar_reglas(ref: str) -> tuple[dict, dict]:
    carpeta = os.path.join(AQUI, ".webappanalyzer", ref[:12])
    os.makedirs(carpeta, exist_ok=True)
    archivos = ["categories.json"] + [f"technologies/{c}.json" for c in "_abcdefghijklmnopqrstuvwxyz"]
    for a in archivos:
        destino = os.path.join(carpeta, a.replace("/", "_"))
        if not os.path.exists(destino) or ref == "master":
            with urllib.request.urlopen(RAW.format(ref=ref, archivo=a), timeout=60) as r:
                open(destino, "wb").write(r.read())
    categorias = json.load(open(os.path.join(carpeta, "categories.json")))
    tecnologias = {}
    for a in archivos[1:]:
        tecnologias.update(json.load(open(os.path.join(carpeta, a.replace("/", "_")))))
    return tecnologias, categorias


class Patron:
    """Una regla de Wappalyzer: «regex\\;version:\\1\\;confidence:50»."""

    def __init__(self, texto: str):
        partes = str(texto).split("\\;")
        self.version = ""
        self.confianza = 100
        for p in partes[1:]:
            if p.startswith("version:"):
                self.version = p[8:]
            elif p.startswith("confidence:"):
                self.confianza = int(p[11:] or 100)
        fuente = partes[0].replace("(?<", "(?P<").replace("(?P<=", "(?<=").replace("(?P<!", "(?<!")
        try:
            # Algunas reglas son regex de JavaScript que Python no acepta: se saltan.
            self.regex = re.compile(fuente, re.I) if fuente else None
            self.valido = True
        except re.error:
            self.regex, self.valido = None, False

    def buscar(self, valor: str):
        """Devuelve la versión ('' si no hay) cuando coincide, o None."""
        if not self.valido:
            return None
        if self.regex is None:
            return ""
        m = self.regex.search(valor or "")
        if not m:
            return None
        return self._version(m)

    def _version(self, m: re.Match) -> str:
        if not self.version:
            return ""
        v = self.version
        grupos = [m.group(0)] + [g or "" for g in m.groups()]
        # Ternario de Wappalyzer: \1?si:no
        for i, g in enumerate(grupos):
            v = re.sub(rf"\\{i}\?([^:]*):(.*)", lambda t: t.group(1) if g else t.group(2), v)
            v = v.replace(f"\\{i}", g)
        return v.strip()


def lista(x) -> list:
    return x if isinstance(x, list) else [x]


def preparar(tecnologias: dict) -> dict:
    """Compila todas las regex una sola vez."""
    comp = {}
    for nombre, t in tecnologias.items():
        c = {}
        for k in ("html", "text", "scriptSrc", "scripts", "url", "robots", "xhr", "certIssuer"):
            if k in t:
                c[k] = [Patron(p) for p in lista(t[k])]
        for k in ("headers", "meta", "cookies", "js"):
            if k in t and isinstance(t[k], dict):
                c[k] = {n.lower() if k != "js" else n: [Patron(p) for p in lista(v)] for n, v in t[k].items()}
        if "dns" in t:
            c["dns"] = {n.upper(): [Patron(p) for p in lista(v)] for n, v in t["dns"].items()}
        if "dom" in t:
            c["dom"] = t["dom"]
        comp[nombre] = c
    return comp


# ---------- Recogida de datos de la página ----------

def descargar(url: str) -> dict:
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es,en;q=0.8"})
    try:
        r = opener.open(req, timeout=TIMEOUT)
    except urllib.error.HTTPError as e:  # Una 403 o 404 también trae cabeceras y HTML útiles
        r = e
    cuerpo = r.read(MAX_HTML)
    cab: Message = r.headers
    charset = cab.get_content_charset() or "utf-8"
    return {
        "url_final": r.geturl(),
        "estado": r.status if hasattr(r, "status") else r.code,
        "headers": {k.lower(): v for k, v in cab.items()},
        "cookies": {c.name.lower(): c.value for c in jar},
        "html": cuerpo.decode(charset, "ignore"),
    }


def extraer(html: str) -> dict:
    meta = {}
    for tag in re.findall(r"<meta\b[^>]*>", html, re.I):
        nombre = re.search(r"""(?:name|property|http-equiv)\s*=\s*["']([^"']+)""", tag, re.I)
        cont = re.search(r"""content\s*=\s*["']([^"']*)""", tag, re.I)
        if nombre and cont:
            meta.setdefault(nombre.group(1).lower(), []).append(htmlmod.unescape(cont.group(1)))
    scripts_src = re.findall(r"""<script\b[^>]*\bsrc\s*=\s*["']([^"']+)""", html, re.I)
    scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.I | re.S)
    texto = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.I | re.S)
    texto = re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", texto)))
    return {"meta": meta, "scriptSrc": scripts_src, "scripts": [s for s in scripts if s.strip()], "text": texto}


def robots(url_final: str) -> str:
    base = re.match(r"https?://[^/]+", url_final).group(0)
    try:
        req = urllib.request.Request(base + "/robots.txt", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read(200_000).decode("utf-8", "ignore")
    except (OSError, ValueError):
        return ""


def emisor_certificado(host: str) -> str:
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=TIMEOUT) as s, ctx.wrap_socket(s, server_hostname=host) as t:
            emisor = dict(x[0] for x in t.getpeercert().get("issuer", ()))
        return " ".join(v for k, v in emisor.items() if k in ("organizationName", "commonName"))
    except (OSError, ssl.SSLError, ValueError):
        return ""


def registros_dns(dominio: str) -> dict:
    res = {}
    for tipo in ("TXT", "SOA", "NS", "CNAME", "MX"):
        try:
            res[tipo] = [r.to_text().strip('"') for r in dns.resolver.resolve(dominio, tipo, lifetime=8)]
        except Exception:  # NXDOMAIN, sin respuesta, timeout: no hay registros de ese tipo
            res[tipo] = []
    return res


def con_navegador(url: str, comp: dict) -> dict:
    """Abre la página en Chromium para evaluar las reglas js, dom y xhr."""
    from playwright.sync_api import sync_playwright

    cadenas = sorted({j for c in comp.values() for j in c.get("js", {})})
    doms = []
    for nombre, c in comp.items():
        d = c.get("dom")
        if isinstance(d, (str, list)):
            doms += [[nombre, sel, None] for sel in lista(d)]
        elif isinstance(d, dict):
            doms += [[nombre, sel, spec] for sel, spec in d.items()]
    xhr = set()
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pagina = nav.new_page(user_agent=UA)
        pagina.on("request", lambda r: xhr.add(re.sub(r"^https?://([^/]+).*", r"\1", r.url)) if r.resource_type in ("xhr", "fetch") else None)
        resp = pagina.goto(url, wait_until="load", timeout=TIMEOUT * 1000)
        pagina.wait_for_timeout(2500)
        js = pagina.evaluate(
            """(cadenas) => { const r = {}; for (const c of cadenas) { try {
                 let v = window; for (const p of c.split('.')) { if (v == null) break; v = v[p]; }
                 if (v !== undefined && v !== null) r[c] = typeof v === 'object' || typeof v === 'function' ? '' : String(v);
               } catch (e) {} } return r; }""", cadenas)
        dom = pagina.evaluate(
            """(checks) => checks.map(([nombre, sel, spec]) => { try {
                 const els = [...document.querySelectorAll(sel)]; if (!els.length) return null;
                 const e = els[0]; const out = {exists: true, text: e.textContent || '', attributes: {}, properties: {}};
                 if (spec) { for (const a of Object.keys(spec.attributes || {})) out.attributes[a] = e.getAttribute(a);
                             for (const p of Object.keys(spec.properties || {})) { const v = e[p]; out.properties[p] = v === undefined ? null : String(v); } }
                 return out; } catch (err) { return null; } })""", doms)
        datos = {
            "url_final": pagina.url, "estado": resp.status if resp else 0,
            "headers": {k.lower(): v for k, v in (resp.all_headers() if resp else {}).items()},
            "cookies": {c["name"].lower(): c["value"] for c in pagina.context.cookies()},
            "html": pagina.content(), "js": js, "xhr": sorted(xhr),
            "dom": [(n, s, spec, r) for (n, s, spec), r in zip(doms, dom) if r],
        }
        nav.close()
    return datos


# ---------- Motor de detección ----------

def detectar(datos: dict, comp: dict, tecnologias: dict) -> dict:
    hallado: dict[str, dict] = {}

    def anotar(nombre, version, confianza, prueba):
        h = hallado.setdefault(nombre, {"version": "", "confianza": 0, "pruebas": []})
        h["confianza"] = min(100, h["confianza"] + confianza)
        if version and len(version) > len(h["version"]):
            h["version"] = version
        if len(h["pruebas"]) < 5:
            h["pruebas"].append(prueba)

    def probar(nombre, patrones, valores, tipo):
        for pat in patrones:
            for v in valores:
                ver = pat.buscar(v)
                if ver is not None:
                    anotar(nombre, ver, pat.confianza, tipo)
                    break

    for nombre, c in comp.items():
        probar(nombre, c.get("html", []), [datos["html"]], "html")
        probar(nombre, c.get("text", []), [datos["text"]], "texto")
        probar(nombre, c.get("scriptSrc", []), datos["scriptSrc"], "script")
        probar(nombre, c.get("scripts", []), datos["scripts"], "script en línea")
        probar(nombre, c.get("url", []), [datos["url_final"]], "url")
        probar(nombre, c.get("robots", []), [datos["robots"]], "robots.txt")
        probar(nombre, c.get("certIssuer", []), [datos["cert"]], "certificado")
        probar(nombre, c.get("xhr", []), datos.get("xhr", []), "xhr")
        for k, fuente in (("headers", datos["headers"]), ("cookies", datos["cookies"])):
            for clave, patrones in c.get(k, {}).items():
                valores = [v for n, v in fuente.items() if fnmatch.fnmatch(n, clave)]
                if valores:
                    probar(nombre, patrones, valores, f"{k[:-1]} {clave}")
        for clave, patrones in c.get("meta", {}).items():
            if clave in datos["meta"]:
                probar(nombre, patrones, datos["meta"][clave], f"meta {clave}")
        for tipo, patrones in c.get("dns", {}).items():
            probar(nombre, patrones, datos["dns"].get(tipo, []), f"dns {tipo}")
        for cadena, patrones in c.get("js", {}).items():
            if cadena in datos.get("js", {}):
                probar(nombre, patrones, [datos["js"][cadena]], f"js {cadena}")

    for nombre, sel, spec, r in datos.get("dom", []):
        if not spec:
            anotar(nombre, "", 100, f"dom {sel}")
            continue
        for parte in ("attributes", "properties"):
            for k, p in (spec.get(parte) or {}).items():
                ver = Patron(p).buscar(r[parte].get(k)) if r[parte].get(k) is not None else None
                if ver is not None:
                    anotar(nombre, ver, 100, f"dom {sel}")
        if "text" in spec and Patron(spec["text"]).buscar(r["text"]) is not None:
            anotar(nombre, "", 100, f"dom {sel}")
        if "exists" in spec:
            anotar(nombre, "", 100, f"dom {sel}")

    # implies (con su confianza), requires, requiresCategory y excludes, hasta que no cambie nada
    cambio = True
    while cambio:
        cambio = False
        for nombre in list(hallado):
            for imp in lista(tecnologias.get(nombre, {}).get("implies", [])):
                p = Patron(imp)
                destino = str(imp).split("\\;")[0]
                if destino in tecnologias and destino not in hallado:
                    anotar(destino, "", p.confianza, f"implícito por {nombre}")
                    cambio = True
    for nombre in list(hallado):
        t = tecnologias.get(nombre, {})
        req = lista(t.get("requires", []))
        if req and not any(r in hallado for r in req):
            del hallado[nombre]
            continue
        cats = lista(t.get("requiresCategory", []))
        if cats and not any(set(tecnologias[o]["cats"]) & set(cats) for o in hallado if o != nombre):
            del hallado[nombre]
    for nombre in list(hallado):
        for ex in lista(tecnologias.get(nombre, {}).get("excludes", [])):
            hallado.pop(ex, None)
    return hallado


# ---------- RDAP / WHOIS ----------

def get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rdap+json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def vcard(entidad: dict) -> dict:
    out = {"nombre": "", "org": "", "emails": [], "telefonos": [], "pais": ""}
    for campo in (entidad.get("vcardArray") or [None, []])[1]:
        clave, _, _, valor = campo[0], campo[1], campo[2], campo[3]
        if clave == "fn":
            out["nombre"] = str(valor)
        elif clave == "org":
            out["org"] = str(valor if not isinstance(valor, list) else valor[0])
        elif clave == "email":
            out["emails"].append(str(valor))
        elif clave == "tel":
            out["telefonos"].append(str(valor).replace("tel:", ""))
        elif clave == "adr":
            pais = campo[1].get("cc") or (valor[-1] if isinstance(valor, list) else "")
            out["pais"] = str(pais or "")
    return out


_BOOTSTRAP = {}


def servidor_rdap(tld: str) -> str | None:
    """Servidor RDAP oficial del TLD según el directorio de IANA."""
    if not _BOOTSTRAP:
        for tlds, urls in get_json("https://data.iana.org/rdap/dns.json")["services"]:
            for x in tlds:
                _BOOTSTRAP[x.lower()] = urls[0].rstrip("/") + "/"
    return _BOOTSTRAP.get(tld.lower())


def rdap(dominio: str) -> dict:
    base = servidor_rdap(dominio.rsplit(".", 1)[-1])
    if not base:
        raise LookupError("su registro no tiene RDAP")
    d = get_json(f"{base}domain/{dominio}")
    info = {"fuente_whois": "RDAP", "registrador": "", "titular": "", "titular_pais": "", "emails": [],
            "telefonos": [], "email_abuso": "", "alta": "", "caducidad": ""}
    for ev in d.get("events", []):
        if ev.get("eventAction") == "registration":
            info["alta"] = ev.get("eventDate", "")[:10]
        elif ev.get("eventAction") == "expiration":
            info["caducidad"] = ev.get("eventDate", "")[:10]
    info["dns"] = [n.get("ldhName", "").lower() for n in d.get("nameservers", [])]

    def recorrer(entidades):
        for e in entidades:
            yield e
            yield from recorrer(e.get("entities", []))

    entidades = list(recorrer(d.get("entities", [])))
    # En muchos TLD (.com, .org) el registro solo publica el registrador; el titular está en el RDAP del registrador.
    for enlace in d.get("links", []):
        if enlace.get("rel") == "related" and "rdap" in enlace.get("type", "") and enlace.get("href"):
            try:
                entidades += list(recorrer(get_json(enlace["href"]).get("entities", [])))
            except (OSError, ValueError):
                pass
            break
    for e in entidades:
        v, roles = vcard(e), e.get("roles", [])
        if "registrar" in roles:
            info["registrador"] = v["nombre"] or v["org"]
        if "abuse" in roles and v["emails"]:
            info["email_abuso"] = v["emails"][0]
        if {"registrant", "administrative", "technical"} & set(roles):
            if "registrant" in roles:
                info["titular"] = v["org"] or v["nombre"]
                info["titular_pais"] = v["pais"]
            info["emails"] += [x for x in v["emails"] if x not in info["emails"]]
            info["telefonos"] += [x for x in v["telefonos"] if x not in info["telefonos"]]
    return info


def whois_43(servidor: str, consulta: str) -> str:
    with socket.create_connection((servidor, 43), timeout=TIMEOUT) as s:
        s.sendall((consulta + "\r\n").encode())
        datos = b""
        while chunk := s.recv(4096):
            datos += chunk
    return datos.decode("utf-8", "ignore")


def whois(dominio: str) -> dict:
    tld = dominio.rsplit(".", 1)[-1]
    iana = whois_43("whois.iana.org", tld)
    m = re.search(r"^whois:\s*(\S+)", iana, re.M)
    if not m:
        raise LookupError(f"el registro de .{tld} no publica WHOIS")
    texto = whois_43(m.group(1), dominio)
    ref = re.search(r"Registrar WHOIS Server:\s*(\S+)", texto, re.I)
    if ref and ref.group(1).lower() != m.group(1).lower():
        try:
            texto += "\n" + whois_43(ref.group(1), dominio)
        except OSError:
            pass

    def campo(*nombres):
        for n in nombres:
            r = re.search(rf"^[ \t]*{n}:[ \t]*(.+)$", texto, re.I | re.M)
            if r and r.group(1).strip():
                return r.group(1).strip()
        return ""

    emails = []
    for n in ("Registrant Email", "Admin Email", "Tech Email"):
        for x in re.findall(rf"^[ \t]*{n}:[ \t]*(\S+@\S+)", texto, re.I | re.M):
            if x not in emails:
                emails.append(x)
    telefonos = []
    for n in ("Registrant Phone", "Admin Phone", "Tech Phone"):
        for x in re.findall(rf"^[ \t]*{n}:[ \t]*(\+?[\d.\- ]{{6,}})", texto, re.I | re.M):
            if x.strip() not in telefonos:
                telefonos.append(x.strip())
    return {
        "fuente_whois": f"WHOIS {m.group(1)}", "registrador": campo("Registrar", "Sponsoring Registrar"),
        "titular": campo("Registrant Organization", "Registrant Name", "Registrant"),
        "titular_pais": campo("Registrant Country"), "emails": emails, "telefonos": telefonos,
        "email_abuso": campo("Registrar Abuse Contact Email"),
        "alta": campo("Creation Date", "Created", "Registered on")[:10],
        "caducidad": campo("Registry Expiry Date", "Registrar Registration Expiration Date", "Expiry Date", "Expires")[:10],
        "dns": sorted({x.lower() for x in re.findall(r"^[ \t]*Name Server:[ \t]*(\S+)", texto, re.I | re.M)}),
    }


OCULTO = re.compile(r"redacted|privacy|private|data protected|not disclosed|withheld|gdpr|contact.*(form|registrar)", re.I)


PROXY = re.compile(r"dnstination|domains by proxy|withheld for privacy|contact privacy|whoisguard|privacy ?protect|"
                   r"identity protection service|perfect privacy|super privacy|proxy", re.I)


def limpiar(info: dict) -> dict:
    """Desde el RGPD casi todos los registros ocultan al titular particular: se marca como oculto, no se inventa."""
    for k in ("titular", "titular_pais"):
        if OCULTO.search(info.get(k, "")):
            info[k] = "(oculto)"
    if PROXY.search(info.get("titular", "")):  # Servicio de privacidad: no es el dueño real
        info["titular"] = f"(servicio de privacidad: {info['titular']})"
    info["emails"] = [e for e in info.get("emails", []) if re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", e, re.I) and not OCULTO.search(e)]
    info["telefonos"] = [x for x in info.get("telefonos", []) if not OCULTO.search(x) and re.search(r"\d{6,}", re.sub(r"\D", "", x))]
    return info


def contacto(dominio: str) -> dict:
    try:
        info = limpiar(rdap(dominio))
        if info["titular"] in ("", "(oculto)") and not info["emails"]:
            try:  # Algunos registradores solo dan el contacto por WHOIS
                w = limpiar(whois(dominio))
                if w["titular"] not in ("", "(oculto)") or w["emails"]:
                    for k in ("titular", "titular_pais", "emails", "telefonos"):
                        info[k] = w[k]
                    info["fuente_whois"] = f"RDAP + {w['fuente_whois']}"
            except (OSError, LookupError):
                pass
        return info
    except (OSError, ValueError, KeyError, LookupError) as e_rdap:
        try:
            return limpiar(whois(dominio))
        except (OSError, LookupError) as e_whois:
            if dominio.endswith(".es"):
                # Red.es solo da WHOIS a IP autorizadas; la consulta pública es la web de dominios.es (con captcha).
                return {"fuente_whois": "", "error": ".es no tiene RDAP ni WHOIS público: consulta https://www.dominios.es"}
            return {"fuente_whois": "", "error": f"RDAP: {e_rdap}; WHOIS: {e_whois}"}


# ---------- Programa ----------

def normalizar(linea: str) -> str:
    u = linea.strip()
    return u if re.match(r"https?://", u, re.I) else "https://" + u


def analizar(url: str, comp: dict, tecnologias: dict, categorias: dict, navegador: bool) -> tuple[dict, dict]:
    errores = []
    fila = {c: "" for c in COLUMNAS}
    fila["url"] = url
    host = re.sub(r"^https?://([^/:]+).*", r"\1", url, flags=re.I).lower()
    ext = tldextract.extract(host)
    dominio = ext.top_domain_under_public_suffix if hasattr(ext, "top_domain_under_public_suffix") else ext.registered_domain
    fila["dominio"] = dominio
    hallado = {}
    try:
        datos = con_navegador(url, comp) if navegador else descargar(url)
        datos.update(extraer(datos["html"]))
        datos["robots"] = robots(datos["url_final"])
        datos["cert"] = emisor_certificado(re.sub(r"^https?://([^/:]+).*", r"\1", datos["url_final"])) if datos["url_final"].startswith("https") else ""
        datos["dns"] = registros_dns(dominio)
        fila["url_final"], fila["estado_http"] = datos["url_final"], datos["estado"]
        hallado = detectar(datos, comp, tecnologias)
    except (OSError, ValueError) as e:
        errores.append(f"web: {e}")
    except Exception as e:  # Playwright lanza sus propios errores (timeout, DNS)
        errores.append(f"web: {type(e).__name__}: {e}")

    def de_categoria(*nombres):
        ids = {k for k, v in categorias.items() if v["name"] in nombres}
        return " | ".join(n for n in sorted(hallado_web) if ids & {str(c) for c in tecnologias[n]["cats"]})

    # Lo que solo aparece en los DNS (p. ej., un TXT de verificación de OpenAI o Zoom) no es tecnología de la web:
    # dice qué servicios ha dado de alta el dominio. Va en su propia columna.
    solo_dns = {n for n, h in hallado.items() if all(p.startswith("dns") for p in h["pruebas"])}
    cambio = True
    while cambio:  # Lo implícito solo es «de DNS» si todo lo que lo implica también lo es
        cambio = False
        for n, h in hallado.items():
            origen = [p[13:] for p in h["pruebas"] if p.startswith("implícito por ")]
            if n not in solo_dns and origen and len(origen) == len(h["pruebas"]) and all(o in solo_dns for o in origen):
                solo_dns.add(n)
                cambio = True
    fila["servicios_dns"] = " | ".join(sorted(solo_dns))
    hallado_web = {n: h for n, h in hallado.items() if n not in solo_dns}
    fila["tecnologias"] = " | ".join(f"{n} {h['version']}".strip() for n, h in sorted(hallado_web.items()))
    fila["cms"] = de_categoria("CMS", "Ecommerce", "Blogs")
    fila["lenguajes"] = de_categoria("Programming languages")
    fila["servidor_web"] = de_categoria("Web servers", "Reverse proxies")
    fila["analitica"] = de_categoria("Analytics", "Tag managers")
    fila["cdn"] = de_categoria("CDN", "PaaS", "Hosting")
    fila["num_tecnologias"] = len(hallado_web)

    w = contacto(dominio) if dominio else {"error": "sin dominio"}
    if w.get("error"):
        errores.append(f"whois: {w['error']}")
    fila.update({
        "registrador": w.get("registrador", ""), "alta_dominio": w.get("alta", ""),
        "caducidad_dominio": w.get("caducidad", ""), "titular": w.get("titular", ""),
        "titular_pais": w.get("titular_pais", ""), "emails_contacto": " | ".join(w.get("emails", [])),
        "telefonos_contacto": " | ".join(w.get("telefonos", [])), "email_abuso": w.get("email_abuso", ""),
        "servidores_dns": " | ".join(w.get("dns", [])), "fuente_whois": w.get("fuente_whois", ""),
        "errores": " ; ".join(errores),
    })
    detalle = {"url": url, "tecnologias": hallado, "whois": w}
    return fila, detalle


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("entrada", help="fichero .txt con una URL por línea")
    ap.add_argument("-o", "--salida", default=os.path.join(AQUI, "resultados", "webs.csv"))
    ap.add_argument("--detalle", help="JSON con la confianza y la prueba de cada tecnología")
    ap.add_argument("--navegador", action="store_true", help="renderiza con Playwright (reglas js, dom y xhr)")
    ap.add_argument("--reglas", default=REGLAS_COMMIT, help="commit o rama de webappanalyzer")
    ap.add_argument("--pausa", type=float, default=1.0, help="segundos entre webs")
    a = ap.parse_args()

    urls = [normalizar(l) for l in open(a.entrada, encoding="utf-8") if l.strip() and not l.lstrip().startswith("#")]
    tecnologias, categorias = descargar_reglas(a.reglas)
    comp = preparar(tecnologias)
    saltadas = sum(1 for c in comp.values() for v in c.values() if isinstance(v, list) for p in v if isinstance(p, Patron) and not p.valido)
    print(f"{len(tecnologias)} tecnologías cargadas ({saltadas} regex de JavaScript no compatibles se saltan)", file=sys.stderr)

    os.makedirs(os.path.dirname(os.path.abspath(a.salida)), exist_ok=True)
    detalles = []
    with open(a.salida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        w.writeheader()
        for i, url in enumerate(urls):
            fila, detalle = analizar(url, comp, tecnologias, categorias, a.navegador)
            w.writerow(fila)
            f.flush()
            detalles.append(detalle)
            print(f"[{i + 1}/{len(urls)}] {url}: {fila['num_tecnologias']} tecnologías, whois {fila['fuente_whois'] or 'no'}", file=sys.stderr)
            if i < len(urls) - 1:
                time.sleep(a.pausa)
    if a.detalle:
        json.dump(detalles, open(a.detalle, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"CSV: {a.salida}", file=sys.stderr)


if __name__ == "__main__":
    main()
