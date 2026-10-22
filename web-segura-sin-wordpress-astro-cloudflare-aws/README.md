# Web segura sin WordPress: Astro + API + PostgreSQL, con Cloudflare y AWS

Guía: https://yeswelab.com/guias/web-segura-sin-wordpress-astro-cloudflare-aws/

Plantilla para sustituir una web de WordPress (o de cualquier PHP) por una web estática, rápida y sin nada que parchear en el frontal, con una API propia para los formularios:

| Carpeta | Qué es |
| --- | --- |
| `web/` | Astro 7: HTML estático, cabeceras de seguridad (`public/_headers`) y despliegue en Cloudflare (`wrangler.jsonc`) |
| `api/` | FastAPI: valida, guarda en PostgreSQL y avisa por Telegram (opcional). CORS cerrado, Turnstile, honeypot y límite por IP |
| `sql/esquema.sql` | La tabla y un usuario `app_web` que solo puede insertar: si alguien compromete la API, no puede leer ni borrar nada |
| `aws/` | Despliegue de la API en ECS Express Mode, PostgreSQL en RDS sin IP pública, secretos en Secrets Manager y AWS WAF |
| `docker-compose.yml` | PostgreSQL 18 y la API en local |

## Probarlo en local

```bash
docker compose up -d --build          # PostgreSQL en 127.0.0.1:55432 y API en 127.0.0.1:8000
cd api && uv run pytest               # 17 tests contra PostgreSQL real
cd ../web && npm install && npm run dev   # http://localhost:4321
```

En local, Turnstile usa las claves de prueba públicas de Cloudflare, que siempre aprueban.

## Qué protege cada capa

| Capa | Defensa |
| --- | --- |
| Cloudflare | DNS, CDN, WAF gestionado gratuito, reglas propias, límite de peticiones, Turnstile |
| Web | Solo ficheros estáticos; CSP estricta (sin scripts ni estilos en línea), HSTS, sin iframes ajenos |
| AWS WAF | Solo rutas de la API, límite por IP, IP con mala reputación, reglas OWASP y exploits conocidos |
| API | CORS cerrado a tu dominio, comprobación del `Origin`, Turnstile, honeypot, tiempo mínimo, límite por IP, validación estricta, sin `/docs` |
| Base de datos | Sin IP pública, cifrada, copias de 7 días, solo acepta conexiones de la API, usuario con permisos mínimos, conexión TLS |

**CORS no es un cortafuegos.** Solo lo respetan los navegadores: impide que otra web use tu API desde el navegador de sus visitas, pero un script puede llamarla igual. Por eso la API también comprueba el origen, pide Turnstile y limita por IP, y el WAF filtra antes.

## Cloudflare: el frontal

1. Da de alta el dominio en Cloudflare y cambia los DNS en tu registrador.
2. `cd web && npm run deploy` y, en Workers → tu proyecto → Dominios, añade `tudominio.es` y `www.tudominio.es`.
3. **SSL/TLS:** «Always Use HTTPS» y TLS mínimo 1.2. Activa **DNSSEC**.
4. **Security → WAF:** el conjunto gestionado gratuito ya está activo. Añade estas reglas propias (el plan gratuito permite 5):
   - Bloquear métodos que una web estática no usa: `(http.request.method ne "GET" and http.request.method ne "HEAD")`
   - Bloquear a quien busca un WordPress: `(http.request.uri.path contains "/wp-" or http.request.uri.path contains ".php" or http.request.uri.path contains "/.env" or http.request.uri.path contains "/.git")`
5. **Límite de peticiones** (1 regla en el plan gratuito, contada por IP en 10 s): por ejemplo, más de 100 peticiones en 10 s → bloquear 10 s.
6. **Bot Fight Mode** activado.
7. **Turnstile:** crea un widget para tu dominio. La clave de sitio va en `PUBLIC_TURNSTILE_SITEKEY`; el secreto, solo en la API.

## AWS: la API y PostgreSQL

Paso a paso en [`aws/README.md`](aws/README.md).

## Licencia

Código MIT.
