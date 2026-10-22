"""API de formularios para una web estática.

Defensas, de fuera a dentro:
  1. Cloudflare (WAF y límite de peticiones) delante; con ORIGEN_SECRETO, la API rechaza lo que no pase por él.
  2. CORS cerrado a los dominios de la web: un navegador no puede llamarla desde otra web.
  3. Comprobación del Origin en el servidor: CORS solo lo aplican los navegadores; un script no lo respeta.
  4. Turnstile: el envío necesita un token válido de Cloudflare, emitido para nuestro dominio.
  5. Honeypot, tiempo mínimo de relleno y límite de envíos por IP (guardada como hash).
  6. Validación estricta de cada campo y usuario de base de datos con permisos mínimos.
"""

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from app.config import ajustes
from app.db import Contacto, Sesion

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")

TURNSTILE_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

# Sin documentación pública: no hay por qué enseñar el mapa de la API.
app = FastAPI(title="API de la web", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ajustes.cors_origins,
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
    max_age=600,
)


@app.middleware("http")
async def filtros(request: Request, siguiente):
    # Si hay ORIGEN_SECRETO, toda petición (salvo /health) tiene que traer la cabecera que añade Cloudflare.
    if ajustes.origen_secreto and request.url.path != "/health":
        recibido = request.headers.get("x-origen-secreto", "")
        if not hmac.compare_digest(recibido, ajustes.origen_secreto):
            return JSONResponse({"detail": "prohibido"}, status_code=403)
    # Antes de leer el cuerpo: un POST que no viene de nuestra web no llega ni a validarse.
    if request.method == "POST" and not _origen_permitido(request):
        return JSONResponse({"detail": "origen no permitido"}, status_code=403)
    respuesta = await siguiente(request)
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


class ContactoEntrada(BaseModel):
    nombre: str = Field(min_length=2, max_length=200)
    email: EmailStr
    mensaje: str = Field(min_length=10, max_length=4000)
    turnstile: str = Field(default="", max_length=2048)
    # Antispam: campo oculto que una persona deja vacío y milisegundos que tardó en rellenar
    web: str = Field(default="", max_length=200)
    ms_en_formulario: int = 0


def _ip(request: Request) -> str:
    # Detrás de Cloudflare la IP real llega en CF-Connecting-IP; detrás de un balanceador, en X-Forwarded-For.
    return (
        request.headers.get("cf-connecting-ip", "").strip()
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "")
    )


def _hash(ip: str) -> str:
    return hashlib.sha256(f"{ajustes.ip_salt}:{ip}".encode()).hexdigest()


def _origen_permitido(request: Request) -> bool:
    origen = request.headers.get("origin") or request.headers.get("referer", "")
    if not origen:
        return False
    p = urlparse(origen)
    return f"{p.scheme}://{p.netloc}" in ajustes.cors_origins


def _turnstile_valido(token: str, ip: str) -> bool:
    if not ajustes.turnstile_secret:
        return True
    try:
        r = httpx.post(TURNSTILE_URL, data={"secret": ajustes.turnstile_secret, "response": token, "remoteip": ip}, timeout=8)
        d = r.json()
    except (httpx.HTTPError, ValueError):
        log.warning("Turnstile no responde: se rechaza el envío")
        return False
    if not d.get("success"):
        return False
    # El token tiene que haberse emitido para uno de nuestros dominios (las claves de prueba devuelven «example.com»).
    host = d.get("hostname", "")
    permitidos = {urlparse(o).hostname for o in ajustes.cors_origins}
    es_clave_de_prueba = ajustes.turnstile_secret.startswith(("1x0000", "2x0000", "3x0000"))
    return host in permitidos or (es_clave_de_prueba and host == "example.com")


def _avisar(contacto_id: int, nombre: str, email: str, mensaje: str) -> None:
    # Recibe los datos en vez de leerlos: el usuario de la base de datos no puede leer los mensajes.
    if not (ajustes.telegram_bot_token and ajustes.telegram_chat_id):
        return
    texto = f"Nuevo contacto #{contacto_id}\n{nombre} <{email}>\n\n{mensaje[:1500]}"
    try:
        httpx.post(f"https://api.telegram.org/bot{ajustes.telegram_bot_token}/sendMessage",
                   json={"chat_id": ajustes.telegram_chat_id, "text": texto}, timeout=10)
    except httpx.HTTPError:
        log.warning("No se pudo avisar por Telegram del contacto %s", contacto_id)


@app.get("/health")
def salud() -> dict:
    return {"ok": True}


@app.post("/v1/contacto", status_code=201)
def crear_contacto(datos: ContactoEntrada, request: Request, tareas: BackgroundTasks) -> dict:
    if not _origen_permitido(request):
        raise HTTPException(403, "origen no permitido")
    # Bots: respuesta normal para no darles pistas, pero no se guarda nada.
    if datos.web or datos.ms_en_formulario < ajustes.ms_minimo_formulario:
        return {"ok": True}
    ip = _ip(request)
    if not _turnstile_valido(datos.turnstile, ip):
        raise HTTPException(400, "verificación anti-bots fallida, recarga la página")
    ip_hash = _hash(ip)
    with Sesion() as s:
        hace_una_hora = datetime.now(timezone.utc) - timedelta(hours=1)
        n = s.scalar(select(func.count()).select_from(Contacto).where(Contacto.ip_hash == ip_hash, Contacto.creado >= hace_una_hora))
        if n and n >= ajustes.max_envios_por_hora:
            raise HTTPException(429, "demasiados envíos seguidos, prueba en un rato")
        c = Contacto(nombre=datos.nombre.strip(), email=datos.email.lower(), mensaje=datos.mensaje.strip(), ip_hash=ip_hash)
        s.add(c)
        s.flush()  # INSERT … RETURNING id: solo necesita permiso de lectura sobre «id»
        contacto_id = c.id
        s.commit()
    tareas.add_task(_avisar, contacto_id, datos.nombre.strip(), datos.email.lower(), datos.mensaje.strip())
    return {"ok": True, "id": contacto_id}
