# PHP 7, el Kit Digital y PHP2Shell

Qué se puede medir con datos públicos sobre las webs que siguen en PHP 7 el día que sale PHP2Shell (CVE-2026-109618 y CVE-2026-109619, 21 de octubre de 2026), y sobre el desfase entre el Kit Digital y el fin de soporte de PHP 7.4.

`medir.py` consulta solo fuentes públicas y oficiales:

- **php.net:** fechas de lanzamiento y de fin de soporte, versiones de seguridad publicadas y CVE citados en el ChangeLog de PHP 8 después del 28/11/2022 (fin de PHP 7.4).
- **NVD (NIST):** para cada CVE, si sus configuraciones vulnerables incluyen PHP 7.x.
- **BOE-A-2021-21873** (Orden ETD/1498/2021, bases del Kit Digital): requisitos de la solución «Sitio web y presencia en internet» y cuántas veces mencionan seguridad o actualizaciones.
- **W3Techs:** cuota de versiones de PHP en la web el día de la ejecución.

No sondea ninguna web ajena: no hay escaneo de versiones de PHP en webs del Kit Digital, ni se publica ninguna lista de sitios.

```bash
python3 medir.py
```

Tarda unos 10 minutos por el límite de peticiones de NVD sin clave.

## Resultados

- `resultados/resumen.json`: todas las cifras del artículo.
- `resultados/versiones_seguridad_php8.json`: cada versión de seguridad de PHP 8 desde el fin de PHP 7.4.
- `resultados/cve_desde_fin_php74.json`: cada CVE y aviso GHSA del ChangeLog, con lo que dice NVD.

## Limitaciones

- NVD no siempre lista las ramas sin soporte entre las afectadas: un CVE marcado como «no incluye PHP 7» puede afectarle igualmente. El recuento es un mínimo.
- W3Techs mide las webs que anuncian su versión de PHP; la cuota real puede ser distinta.
- Las fechas de apertura de las convocatorias del Kit Digital vienen de las notas de prensa del Gobierno y de Red.es.
