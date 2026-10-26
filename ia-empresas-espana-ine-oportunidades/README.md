# IA en las empresas españolas: oportunidades de negocio con los datos del INE

Artículo: https://yeswelab.com/experimentos/ia-empresas-espana-ine-oportunidades/

Cuaderno Jupyter (`analisis.ipynb`) que cruza la *Encuesta sobre el uso de TIC y del comercio electrónico en las empresas* del INE (ediciones 2025-2026 y 2024-2025) con el Directorio Central de Empresas (DIRCE) para responder: **qué productos y servicios de IA se pueden ofrecer a las empresas españolas, a cuántas y por qué no los tienen ya**.

```bash
uv sync
uv run jupyter lab analisis.ipynb                                     # abrirlo y explorarlo
uv run jupyter nbconvert --to notebook --execute --inplace analisis.ipynb   # o ejecutarlo de principio a fin
```

La primera vez descarga el DIRCE (70 MB) en `cache/`. Las tablas de la encuesta vienen en `datos/` tal como las devuelve la API del INE, para que el resultado sea repetible; si las borras, el cuaderno las vuelve a descargar.

## Fuentes

| Tabla del INE | Contenido |
| --- | --- |
| [82382](https://www.ine.es/jaxi/Tabla.htm?tpx=82382&L=0) | IA en empresas de 10 o más empleados, por actividad y tamaño (primer trimestre de 2026) |
| [82394](https://www.ine.es/jaxi/Tabla.htm?tpx=82394&L=0) | IA en empresas de menos de 10 empleados (2026) |
| [82404](https://www.ine.es/jaxi/Tabla.htm?tpx=82404&L=0) | IA por comunidades autónomas (2026) |
| [82415](https://www.ine.es/jaxi/Tabla.htm?tpx=82415&L=0) | Error estándar de la variable D.1.A por estratos (2026) |
| [76387](https://www.ine.es/jaxi/Tabla.htm?tpx=76387&L=0), [76397](https://www.ine.es/jaxi/Tabla.htm?tpx=76397&L=0) | Lo mismo en la edición anterior (primer trimestre de 2025) |
| [39372](https://www.ine.es/jaxiT3/Tabla.htm?t=39372) | DIRCE: empresas por actividad (CNAE-2009) y asalariados, 1 de enero de 2025 |

Datos del INE, reutilizables citando la fuente (INE, www.ine.es).

## Resultados

Todo en `resultados/`, en CSV y JSON:

| Fichero | Qué es |
| --- | --- |
| `panorama_uso_ia.csv` | Uso de IA por tamaño, 2025 y 2026 |
| `empresas_dirce_por_sector.csv` | Empresas de 10 o más asalariados por sector y tamaño (DIRCE) |
| `mercado_empresas.csv` | Empresas que usan IA, que la han considerado, que nunca se lo han planteado y que compran a un proveedor externo |
| `tecnologias_y_usos.csv` | Tecnologías y usos de IA sobre el total de empresas, 2025 y 2026 |
| `origen_de_la_ia.csv` | Cómo consiguen la IA: desarrollo propio, proveedor externo, código abierto o cerrado |
| `frenos_y_servicios.csv` | Motivos para no usarla y el servicio que responde a cada uno |
| `sectores.csv` | Demanda en espera, compra a proveedores y brecha de tamaño por sector |
| `crecimiento_por_sector.csv` | Cambio del uso de IA en los sectores con la misma definición en las dos ediciones |
| `comunidades.csv` | Uso de IA y frenos por comunidad autónoma |
| `error_estandar_d1a.csv` | Error estándar publicado por el INE y margen al 95 % |
| `oportunidades.csv` | Productos y servicios priorizados, con su dato de respaldo |
| `resumen.json` | Las cifras clave del artículo |
| `graficos/` | Los gráficos del cuaderno en PNG |

## Limitaciones

- **Porcentajes con distinta base:** el uso de IA y «la han considerado» van sobre todas las empresas con internet; las tecnologías, los usos y el origen, sobre las que ya usan IA; los frenos, sobre las que la han considerado y no la usan.
- **El número de empresas es un orden de magnitud:** porcentajes de la encuesta (2026) × empresas del DIRCE (1 de enero de 2025, CNAE-2009) en las divisiones que cubre la encuesta. Se redondea a centenas.
- **Comparación entre años:** solo para el total, el tamaño y los sectores que se definen igual en las dos ediciones; la encuesta pasó de la CNAE-2009 a la CNAE-25. Las preguntas sobre el origen de la IA cambiaron y no se comparan.
- **Incertidumbre:** el INE solo publica el error estándar por sector de una variable de IA (D.1.A). Su margen al 95 % va de 0,9 a 8,8 puntos según el estrato: las diferencias pequeñas entre sectores, y sobre todo entre comunidades pequeñas (Ceuta, Melilla, La Rioja, Cantabria), no son concluyentes.
- Las empresas de menos de 10 empleados no se desglosan por sector ni se convierten a número de empresas.
