"""Tests contra PostgreSQL real (docker compose up -d db), conectando con el usuario de permisos mínimos.

    DATABASE_URL=postgresql+psycopg://app_web:cambia-esto@localhost:55432/web uv run pytest
"""

import os
import uuid

import psycopg
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://app_web:cambia-esto@localhost:55432/web")
os.environ["CORS_ORIGINS"] = '["https://tudominio.es"]'
os.environ["TURNSTILE_SECRET"] = ""
os.environ["ORIGEN_SECRETO"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.config import ajustes  # noqa: E402

cliente = TestClient(main.app)
WEB = "https://tudominio.es"
VALIDO = {"nombre": "Ana", "email": "ana@example.com", "mensaje": "Quiero cambiar mi WordPress", "ms_en_formulario": 8000}


def cab(origen=WEB):
    # Una IP distinta por test para que el límite por IP no se cuele entre tests
    h = {"cf-connecting-ip": f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"}
    if origen:
        h["origin"] = origen
    return h


def total() -> int:
    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as c:
        return c.execute("SELECT count(id) FROM contactos").fetchone()[0]


def test_salud():
    assert cliente.get("/health").json() == {"ok": True}


def test_sin_documentacion_publica():
    for ruta in ("/docs", "/redoc", "/openapi.json"):
        assert cliente.get(ruta).status_code == 404


def test_cors_solo_para_la_web():
    pre = {"access-control-request-method": "POST", "access-control-request-headers": "content-type"}
    ok = cliente.options("/v1/contacto", headers={"origin": WEB, **pre})
    assert ok.headers.get("access-control-allow-origin") == WEB
    malo = cliente.options("/v1/contacto", headers={"origin": "https://otra-web.com", **pre})
    assert "access-control-allow-origin" not in malo.headers


def test_post_desde_otro_origen_o_sin_origen_se_rechaza():
    assert cliente.post("/v1/contacto", json=VALIDO, headers=cab("https://otra-web.com")).status_code == 403
    assert cliente.post("/v1/contacto", json=VALIDO, headers=cab(None)).status_code == 403


def test_envio_valido_se_guarda():
    antes = total()
    r = cliente.post("/v1/contacto", json=VALIDO, headers=cab())
    assert r.status_code == 201 and r.json()["id"] > 0
    assert total() == antes + 1


def test_bots_reciben_ok_pero_no_se_guarda():
    antes = total()
    assert cliente.post("/v1/contacto", json={**VALIDO, "web": "http://spam"}, headers=cab()).status_code == 201
    assert cliente.post("/v1/contacto", json={**VALIDO, "ms_en_formulario": 400}, headers=cab()).status_code == 201
    assert total() == antes


def test_validacion_estricta():
    assert cliente.post("/v1/contacto", json={**VALIDO, "email": "no-es-un-email"}, headers=cab()).status_code == 422
    assert cliente.post("/v1/contacto", json={**VALIDO, "mensaje": "x" * 5000}, headers=cab()).status_code == 422


def test_limite_por_ip():
    h = cab()
    codigos = [cliente.post("/v1/contacto", json=VALIDO, headers=h).status_code for _ in range(ajustes.max_envios_por_hora + 1)]
    assert codigos[:-1] == [201] * ajustes.max_envios_por_hora and codigos[-1] == 429


def test_origen_secreto(monkeypatch):
    monkeypatch.setattr(ajustes, "origen_secreto", "s3creto")
    assert cliente.post("/v1/contacto", json=VALIDO, headers=cab()).status_code == 403
    assert cliente.post("/v1/contacto", json=VALIDO, headers={**cab(), "x-origen-secreto": "s3creto"}).status_code == 201
    assert cliente.get("/health").status_code == 200


def test_turnstile_fallido(monkeypatch):
    monkeypatch.setattr(ajustes, "turnstile_secret", "2x0000000000000000000000000000000AA")  # clave de prueba: siempre falla
    assert cliente.post("/v1/contacto", json={**VALIDO, "turnstile": "XXXX.DUMMY.TOKEN.XXXX"}, headers=cab()).status_code == 400


def test_turnstile_valido(monkeypatch):
    monkeypatch.setattr(ajustes, "turnstile_secret", "1x0000000000000000000000000000000AA")  # clave de prueba: siempre aprueba
    assert cliente.post("/v1/contacto", json={**VALIDO, "turnstile": "XXXX.DUMMY.TOKEN.XXXX"}, headers=cab()).status_code == 201


@pytest.mark.parametrize("sql", ["SELECT mensaje FROM contactos", "SELECT email FROM contactos",
                                 "DELETE FROM contactos", "UPDATE contactos SET nombre = 'x'", "DROP TABLE contactos",
                                 "CREATE TABLE robo (x int)"])
def test_el_usuario_de_la_api_no_puede_leer_ni_destruir(sql):
    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute(sql)
