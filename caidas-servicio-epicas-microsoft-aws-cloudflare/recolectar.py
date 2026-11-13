"""¿Cada cuánto falla una herramienta en la nube que usa una pyme, y cuánto tarda en volver?

Lee la API pública de las páginas de estado (Atlassian Statuspage: /api/v2/incidents.json) de 30 servicios
habituales en pymes y guarda, por incidente, solo lo necesario para medir: fechas, impacto declarado y nº de
componentes afectados. No guarda textos de los incidentes.

    python3 recolectar.py      # escribe resultados/incidentes.csv y resultados/fuentes_estado.json

La API devuelve los últimos 50 incidentes (25 en algunos planes): la ventana que cubre cada servicio es distinta
y se registra. Una petición por servicio, con pausa de 1 s.
"""

import csv
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(AQUI, "resultados")
AGENTE = "yeswelab-laboratorio (+https://yeswelab.com)"

# Servicio: (categoría para una pyme, dominio de su página de estado)
SERVICIOS = {
    "GitHub": ("Desarrollo y web", "www.githubstatus.com"),
    "Cloudflare": ("Desarrollo y web", "www.cloudflarestatus.com"),
    "Netlify": ("Desarrollo y web", "www.netlifystatus.com"),
    "Vercel": ("Desarrollo y web", "www.vercel-status.com"),
    "DigitalOcean": ("Desarrollo y web", "status.digitalocean.com"),
    "GoDaddy": ("Desarrollo y web", "status.godaddy.com"),
    "Shopify": ("Tienda y web", "www.shopifystatus.com"),
    "Wix": ("Tienda y web", "status.wix.com"),
    "Squarespace": ("Tienda y web", "status.squarespace.com"),
    "Webflow": ("Tienda y web", "status.webflow.com"),
    "HubSpot": ("Ventas y marketing", "status.hubspot.com"),
    "Klaviyo": ("Ventas y marketing", "status.klaviyo.com"),
    "Twilio": ("Ventas y marketing", "status.twilio.com"),
    "Typeform": ("Ventas y marketing", "status.typeform.com"),
    "Zoom": ("Comunicación", "status.zoom.us"),
    "Notion": ("Trabajo en equipo", "www.notion-status.com"),
    "Asana": ("Trabajo en equipo", "status.asana.com"),
    "monday.com": ("Trabajo en equipo", "status.monday.com"),
    "Trello": ("Trabajo en equipo", "trello.status.atlassian.com"),
    "Jira": ("Trabajo en equipo", "jira-software.status.atlassian.com"),
    "ClickUp": ("Trabajo en equipo", "status.clickup.com"),
    "Miro": ("Trabajo en equipo", "status.miro.com"),
    "Figma": ("Trabajo en equipo", "status.figma.com"),
    "Airtable": ("Trabajo en equipo", "status.airtable.com"),
    "Dropbox": ("Archivos", "status.dropbox.com"),
    "Box": ("Archivos", "status.box.com"),
    "Factorial": ("Gestión", "status.factorialhr.com"),
    "Zapier": ("Automatización e IA", "status.zapier.com"),
    "Make": ("Automatización e IA", "status.make.com"),
    "OpenAI": ("Automatización e IA", "status.openai.com"),
    "Claude": ("Automatización e IA", "status.anthropic.com"),
}


def fecha(t):
    return datetime.fromisoformat(t.replace("Z", "+00:00")) if t else None


def main():
    os.makedirs(RES, exist_ok=True)
    ahora = datetime.now(timezone.utc)
    filas, fuentes = [], {}
    for nombre, (cat, dominio) in SERVICIOS.items():
        url = f"https://{dominio}/api/v2/incidents.json"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": AGENTE}), timeout=20) as r:
                datos = json.load(r)
        except Exception as e:  # noqa: BLE001 - un servicio caído no debe parar la recogida
            fuentes[nombre] = {"url": url, "error": type(e).__name__}
            print(f"{nombre}: error {type(e).__name__}")
            continue
        inc = datos.get("incidents", [])
        fuentes[nombre] = {"url": url, "categoria": cat, "incidentes": len(inc), "consultado": ahora.isoformat(timespec="seconds")}
        for i in inc:
            ini, fin = fecha(i.get("started_at") or i.get("created_at")), fecha(i.get("resolved_at"))
            filas.append({
                "servicio": nombre, "categoria": cat, "id": i["id"],
                "inicio": ini.isoformat(timespec="seconds") if ini else "",
                "resuelto": fin.isoformat(timespec="seconds") if fin else "",
                "estado": i.get("status", ""), "impacto": i.get("impact", ""),
                "componentes": len(i.get("components") or []),
                "mantenimiento": "1" if i.get("scheduled_for") else "0",
            })
        print(f"{nombre}: {len(inc)} incidentes")
        time.sleep(1)
    with open(os.path.join(RES, "incidentes.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    json.dump(fuentes, open(os.path.join(RES, "fuentes_estado.json"), "w"), ensure_ascii=False, indent=1)
    print(f"{len(filas)} incidentes de {sum('error' not in v for v in fuentes.values())} servicios")


if __name__ == "__main__":
    main()
