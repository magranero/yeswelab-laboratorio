"""Agentes de navegador: ¿cuántos tokens cuesta «ver» una página con capturas o con el Accessibility Tree?

Ejecuta una tarea de 10 pasos sobre una web servida en local (la propia yeswelab.com compilada) y, en cada paso,
genera las tres observaciones que puede recibir un agente:

  1. captura de pantalla (1280x800, a 1x y a 2x como una pantalla Retina);
  2. Accessibility Tree completo (todos los nodos, incluido el texto);
  3. Accessibility Tree filtrado: solo elementos interactivos y encabezados, con referencias [ref=eN];
  4. Accessibility Tree filtrado y limitado a lo que se ve en pantalla.

Mide los tokens de cada observación, el tiempo de captura y si el clic por referencia acierta.

    uv run --with playwright --with tiktoken python medir.py --sitio ../../dist --repeticiones 5

Tokens de imagen según la fórmula publicada por cada proveedor (ver README). Tokens de texto con el
tokenizador o200k_base (GPT-4o/GPT-5); el de Claude no es público.
"""

import argparse
import functools
import http.server
import json
import math
import os
import platform
import subprocess
import statistics
import threading
import time
from importlib.metadata import version

import tiktoken
from playwright.sync_api import sync_playwright

ANCHO, ALTO = 1280, 800
ENC = tiktoken.get_encoding("o200k_base")
INTERACTIVOS = {
    "link", "button", "textbox", "searchbox", "combobox", "checkbox", "radio",
    "menuitem", "tab", "option", "switch", "slider", "spinbutton",
}

# La tarea: (descripción, acción, rol, fragmento del nombre accesible, texto a escribir)
TAREA = [
    ("Abrir la portada", None, None, None, None),
    ("Ir a Experimentos", "clic", "link", "Experimentos", None),
    ("Buscar «tokens»", "escribir", "searchbox", "Buscar en los experimentos", "tokens"),
    ("Abrir el experimento de tokens", "clic", "link", "tokens más gasta el español", None),
    ("Bajar hasta el final del artículo", "scroll", None, None, None),
    ("Ir a Guías", "clic", "link", "Guías", None),
    ("Abrir la guía de harness de agentes", "clic", "link", "Harness de agentes", None),
    ("Ir al formulario de encargo", "clic", "link", "Encargar este experimento", None),
    ("Escribir la hipótesis", "escribir", "textbox", "hipotesis", "Queremos medir si un agente de navegador aguanta 500 tareas al día."),
    ("Elegir el tipo de decisión", "clic", "radio", "Elegir entre A y B", None),
]


def tokens_claude(w: int, h: int) -> int:
    """Anthropic: tokens ≈ ancho × alto / 750, tras reducir a ≤1568 px de lado largo y ~1,15 Mpx."""
    escala = min(1.0, 1568 / max(w, h), math.sqrt(1_150_000 / (w * h)))
    return round((w * escala) * (h * escala) / 750)


def tokens_gpt4o(w: int, h: int) -> int:
    """OpenAI GPT-4o, detalle alto: encajar en 2048x2048, lado corto a 768, 170 por tesela de 512 + 85."""
    escala = min(1.0, 2048 / max(w, h))
    w, h = w * escala, h * escala
    escala = min(1.0, 768 / min(w, h))
    w, h = w * escala, h * escala
    return 85 + 170 * math.ceil(w / 512) * math.ceil(h / 512)


def en_pantalla(cdp, nodo: int) -> bool:
    try:
        quads = cdp.send("DOM.getContentQuads", {"backendNodeId": nodo})["quads"]
    except Exception:
        return False
    for q in quads:
        xs, ys = q[0::2], q[1::2]
        if max(xs) > 0 and min(xs) < ANCHO and max(ys) > 0 and min(ys) < ALTO and (max(xs) - min(xs)) > 0:
            return True
    return False


def arbol(cdp, filtrado: bool, solo_pantalla: bool = False) -> tuple[str, dict[str, int]]:
    """Devuelve el árbol como texto (formato de los agentes de navegador) y el mapa ref -> backendDOMNodeId."""
    nodos = cdp.send("Accessibility.getFullAXTree")["nodes"]
    lineas, refs = [], {}
    for n in nodos:
        if n.get("ignored"):
            continue
        rol = (n.get("role") or {}).get("value", "")
        nombre = ((n.get("name") or {}).get("value") or "").strip()
        if not filtrado:
            # Árbol completo: todo nodo con nombre, incluido el texto de la página.
            if nombre and rol not in ("InlineTextBox", "LineBreak"):
                lineas.append(f'- {rol} "{nombre}"')
            continue
        if not nombre or rol in ("StaticText", "InlineTextBox", "RootWebArea", "LineBreak"):
            continue
        if solo_pantalla and not (n.get("backendDOMNodeId") and en_pantalla(cdp, n["backendDOMNodeId"])):
            continue
        if filtrado:
            if rol in INTERACTIVOS and n.get("backendDOMNodeId"):
                ref = f"e{len(refs) + 1}"
                refs[ref] = n["backendDOMNodeId"]
                lineas.append(f'- {rol} "{nombre[:100]}" [ref={ref}]')
            elif rol == "heading":
                lineas.append(f'- heading "{nombre[:100]}"')
    return "\n".join(lineas), refs


def clic_por_ref(page, cdp, nodo: int) -> bool:
    """Lleva el elemento a pantalla, hace clic en su centro y comprueba que el punto cae en él (o en su etiqueta)."""
    cdp.send("DOM.scrollIntoViewIfNeeded", {"backendNodeId": nodo})
    obj = cdp.send("DOM.resolveNode", {"backendNodeId": nodo})["object"]["objectId"]
    caja = cdp.send("Runtime.callFunctionOn", {
        "objectId": obj,
        "returnByValue": True,
        "functionDeclaration": """function() {
            const r = this.getBoundingClientRect();
            const x = r.x + r.width / 2, y = r.y + r.height / 2;
            const e = document.elementFromPoint(x, y);
            const etiqueta = this.closest('label') || (this.id && document.querySelector('label[for="' + this.id + '"]'));
            const acierta = !!e && (e === this || this.contains(e) || e.contains(this) || (etiqueta && etiqueta.contains(e)));
            return {x, y, acierta};
        }""",
    })["result"]["value"]
    page.mouse.click(caja["x"], caja["y"])
    return bool(caja["acierta"])


def servir(carpeta: str, puerto: int) -> http.server.ThreadingHTTPServer:
    manejador = functools.partial(http.server.SimpleHTTPRequestHandler, directory=carpeta)
    manejador.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", puerto), manejador)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def ejecutar(navegador, base: str, escala: int) -> list[dict]:
    ctx = navegador.new_context(viewport={"width": ANCHO, "height": ALTO}, device_scale_factor=escala, reduced_motion="reduce")
    page = ctx.new_page()
    cdp = ctx.new_cdp_session(page)
    cdp.send("Accessibility.enable")
    cdp.send("DOM.enable")
    page.goto(base + "/", wait_until="networkidle")
    pasos = []
    for i, (desc, accion, rol, nombre, texto) in enumerate(TAREA, start=1):
        page.wait_for_load_state("networkidle")
        t0 = time.perf_counter()
        png = page.screenshot()
        t_captura = (time.perf_counter() - t0) * 1000
        w, h = ANCHO * escala, ALTO * escala
        t0 = time.perf_counter()
        filtrado, refs = arbol(cdp, filtrado=True)
        t_arbol = (time.perf_counter() - t0) * 1000
        completo, _ = arbol(cdp, filtrado=False)
        visible, _ = arbol(cdp, filtrado=True, solo_pantalla=True)
        paso = {
            "paso": i,
            "descripcion": desc,
            "url": page.url.replace(base, ""),
            "escala": escala,
            "captura_px": f"{w}x{h}",
            "captura_bytes": len(png),
            "tokens_captura_claude": tokens_claude(w, h),
            "tokens_captura_gpt4o": tokens_gpt4o(w, h),
            "tokens_arbol_completo": len(ENC.encode(completo)),
            "tokens_arbol_filtrado": len(ENC.encode(filtrado)),
            "tokens_arbol_filtrado_pantalla": len(ENC.encode(visible)),
            "elementos_con_ref": len(refs),
            "ms_captura": round(t_captura, 2),
            "ms_arbol_filtrado": round(t_arbol, 2),
            "clic_acierta": None,
        }
        if accion in ("clic", "escribir"):
            ref = next((r for r, n in refs.items() if f'"' in filtrado and _coincide(filtrado, r, rol, nombre)), None)
            if ref is None:
                paso["clic_acierta"] = False
            else:
                paso["clic_acierta"] = clic_por_ref(page, cdp, refs[ref])
                if accion == "escribir":
                    page.keyboard.type(texto)
        elif accion == "scroll":
            page.keyboard.press("End")
            time.sleep(0.3)
        pasos.append(paso)
        page.wait_for_timeout(400)
    ctx.close()
    return pasos


def _coincide(texto_arbol: str, ref: str, rol: str, nombre: str) -> bool:
    for linea in texto_arbol.splitlines():
        if linea.endswith(f"[ref={ref}]"):
            return linea.startswith(f"- {rol} ") and nombre.lower() in linea.lower()
    return False


def resumen(filas: list[dict]) -> dict:
    def med(xs):
        return {"mediana": round(statistics.median(xs), 2), "min": round(min(xs), 2), "max": round(max(xs), 2),
                "desviacion": round(statistics.pstdev(xs), 2) if len(xs) > 1 else 0.0}

    salida = {}
    for escala in sorted({f["escala"] for f in filas}):
        sub = [f for f in filas if f["escala"] == escala]
        runs = sorted({f["repeticion"] for f in sub})
        primera = [f for f in sub if f["repeticion"] == runs[0]]
        por_paso = {k: [f[k] for f in primera] for k in ("tokens_captura_claude", "tokens_captura_gpt4o", "tokens_arbol_completo", "tokens_arbol_filtrado", "tokens_arbol_filtrado_pantalla")}
        # Contexto acumulado: un agente que reenvía todas las observaciones anteriores en cada paso.
        acumulado = {k: sum(sum(v[: i + 1]) for i in range(len(v))) for k, v in por_paso.items()}
        ultimo = {k: sum(v) for k, v in por_paso.items()}
        clics = [f["clic_acierta"] for f in sub if f["clic_acierta"] is not None]
        salida[f"escala_{escala}x"] = {
            "captura_px": primera[0]["captura_px"],
            "tokens_tarea_solo_ultima_observacion": ultimo,
            "tokens_tarea_historial_completo": acumulado,
            "reduccion_filtrado_vs_captura_claude_pct": round(100 * (1 - ultimo["tokens_arbol_filtrado"] / ultimo["tokens_captura_claude"]), 1),
            "reduccion_filtrado_vs_captura_gpt4o_pct": round(100 * (1 - ultimo["tokens_arbol_filtrado"] / ultimo["tokens_captura_gpt4o"]), 1),
            "reduccion_filtrado_vs_completo_pct": round(100 * (1 - ultimo["tokens_arbol_filtrado"] / ultimo["tokens_arbol_completo"]), 1),
            "reduccion_pantalla_vs_captura_claude_pct": round(100 * (1 - ultimo["tokens_arbol_filtrado_pantalla"] / ultimo["tokens_captura_claude"]), 1),
            "reduccion_pantalla_vs_captura_gpt4o_pct": round(100 * (1 - ultimo["tokens_arbol_filtrado_pantalla"] / ultimo["tokens_captura_gpt4o"]), 1),
            "reduccion_historial_capturas_claude_vs_pantalla_pct": round(100 * (1 - acumulado["tokens_arbol_filtrado_pantalla"] / acumulado["tokens_captura_claude"]), 1),
            "tokens_arbol_filtrado_por_paso": med(por_paso["tokens_arbol_filtrado"]),
            "tokens_arbol_completo_por_paso": med(por_paso["tokens_arbol_completo"]),
            "tokens_arbol_filtrado_pantalla_por_paso": med(por_paso["tokens_arbol_filtrado_pantalla"]),
            "ms_captura_por_paso": med([f["ms_captura"] for f in sub]),
            "ms_arbol_filtrado_por_paso": med([f["ms_arbol_filtrado"] for f in sub]),
            "clics_por_ref": {"intentos": len(clics), "aciertos": sum(clics), "fallos": len(clics) - sum(clics)},
            "repeticiones": len(runs),
        }
    return salida


def _equipo() -> str:
    try:
        chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
        memoria = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout) // 2**30
        macos = subprocess.run(["sw_vers", "-productVersion"], capture_output=True, text=True).stdout.strip()
        return f"{chip}, {memoria} GB, macOS {macos} (portátil con otras apps abiertas)"
    except Exception:
        return f"{platform.machine()} {platform.system()} {platform.release()}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sitio", default="../../dist")
    ap.add_argument("--repeticiones", type=int, default=5)
    ap.add_argument("--puerto", type=int, default=4399)
    a = ap.parse_args()
    carpeta = os.path.abspath(a.sitio)
    srv = servir(carpeta, a.puerto)
    base = f"http://127.0.0.1:{a.puerto}"
    filas = []
    with sync_playwright() as p:
        nav = p.chromium.launch()
        navegador_version = nav.version
        for escala in (1, 2):
            for rep in range(1, a.repeticiones + 1):
                for paso in ejecutar(nav, base, escala):
                    paso["repeticion"] = rep
                    filas.append(paso)
        nav.close()
    srv.shutdown()

    os.makedirs("resultados", exist_ok=True)
    claves = list(filas[0].keys())
    with open("resultados/pasos.csv", "w", encoding="utf-8") as f:
        f.write(",".join(claves) + "\n")
        for fila in filas:
            f.write(",".join('"' + str(fila[k]).replace('"', "'") + '"' if isinstance(fila[k], str) else str(fila[k]) for k in claves) + "\n")
    with open("resultados/resumen.json", "w", encoding="utf-8") as f:
        json.dump(resumen(filas), f, ensure_ascii=False, indent=1)
    with open("entorno.txt", "w", encoding="utf-8") as f:
        f.write(
            f"Fecha de ejecución: {time.strftime('%Y-%m-%d')}\n"
            f"Equipo: {_equipo()}\n"
            f"Python: {platform.python_version()}\n"
            f"playwright {version('playwright')} · Chromium {navegador_version} (headless)\n"
            f"tiktoken {version('tiktoken')} (o200k_base)\n"
            f"Viewport: {ANCHO}x{ALTO} a 1x y 2x · {a.repeticiones} repeticiones de la tarea de {len(TAREA)} pasos por escala\n"
            "Sitio: yeswelab.com compilado con Astro y servido en local (127.0.0.1)\n"
        )
    print(json.dumps(resumen(filas), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
