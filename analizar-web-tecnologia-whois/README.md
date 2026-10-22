# Qué tecnología usa una web y quién está detrás de su dominio

Guía: https://yeswelab.com/guias/analizar-web-tecnologia-whois/

`analizar_webs.py` lee un `.txt` con una URL por línea y escribe un CSV con:

- **Tecnología:** CMS, lenguaje, servidor, analítica, CDN y el resto de lo que detectan las reglas de [webappanalyzer](https://github.com/enthec/webappanalyzer) (la continuación abierta de Wappalyzer, 7647 tecnologías), con versión cuando la web la deja ver.
- **Dominio y contacto:** registrador, fechas de alta y caducidad, titular, correos y teléfonos de contacto, correo de abuso y servidores DNS, por RDAP (el sucesor estándar de WHOIS) y, si hace falta, por WHOIS clásico.

```bash
uv run analizar_webs.py webs.txt                                   # resultados/webs.csv
uv run analizar_webs.py webs.txt -o mis_webs.csv --detalle mis_webs.json
uv run --with playwright analizar_webs.py webs.txt --navegador     # también reglas js, dom y xhr
```

Con `--navegador` hace falta Chromium de Playwright una vez: `uv run --with playwright playwright install chromium`.

## Columnas del CSV

| Columna | Qué es |
| --- | --- |
| `url`, `url_final`, `estado_http`, `dominio` | La URL de entrada, adónde redirige, el código HTTP y el dominio registrable |
| `tecnologias` | Todo lo detectado en la web, con versión si se ve |
| `cms`, `lenguajes`, `servidor_web`, `analitica`, `cdn` | Lo mismo, filtrado por categoría |
| `num_tecnologias` | Cuántas tecnologías se detectaron en la web |
| `servicios_dns` | Servicios que solo aparecen en los DNS (registros TXT de verificación, MX, NS): los ha dado de alta el dominio, no tienen por qué estar en la web |
| `registrador`, `alta_dominio`, `caducidad_dominio`, `servidores_dns` | Datos del registro del dominio |
| `titular`, `titular_pais` | Titular del dominio; `(oculto)` si el registro lo protege y `(servicio de privacidad: …)` si figura un intermediario |
| `emails_contacto`, `telefonos_contacto` | Contacto del titular, administrativo o técnico cuando es público |
| `email_abuso` | Correo del registrador para denunciar abusos |
| `fuente_whois` | De dónde salen los datos: RDAP, WHOIS o los dos |
| `errores` | Lo que no se pudo obtener y por qué |

`--detalle` guarda además, por cada tecnología, su confianza y qué la delató (cabecera, cookie, meta, script, DNS…).

## Ejemplo

`webs.txt` trae 5 webs de organizaciones conocidas. Sus resultados del 22/10/2026 están en `resultados/`: `webs.csv` en modo rápido y `webs_navegador.csv` con `--navegador`.

## Cómo funciona

- Una sola visita a la portada (y a `robots.txt`) con un User-Agent que se identifica, más consultas DNS, el certificado TLS y RDAP/WHOIS. Pausa de 1 s entre webs (`--pausa`).
- Las reglas se descargan la primera vez en `.webappanalyzer/`, fijadas a un commit para que el resultado sea repetible (`--reglas master` para las últimas). webappanalyzer es GPL-3.0: este repo no las redistribuye.
- Sin `--navegador` no se pueden evaluar las reglas `js` (variables de JavaScript) ni `dom` (selectores CSS), que son casi la mitad: detecta menos.
- RDAP se consulta en el servidor oficial de cada registro (directorio de IANA) y, si el registro solo publica el registrador, en el RDAP del registrador.

## Limitaciones

- Solo se detecta lo que la web deja ver. Una web bastionada (sin cabecera `Server`, sin `generator`, con JavaScript propio) da muy poco.
- `.es` no tiene RDAP ni WHOIS público: Red.es solo lo da a IP autorizadas y en [dominios.es](https://www.dominios.es) con captcha.
- Desde el RGPD, los datos de titulares particulares están ocultos en casi todos los registros. Lo que devuelve el script es solo lo que el registro publica.
- Algunas versiones salen de comentarios o rutas de ficheros y pueden estar desfasadas.

## Uso responsable

Los datos de contacto de un WHOIS siguen siendo datos personales si identifican a una persona. Úsalos para lo que se publican: contactar por un problema con el dominio o la web. No los uses para enviar publicidad sin consentimiento (en España lo prohíbe el artículo 21 de la LSSI) ni para crear bases de datos de contactos.
