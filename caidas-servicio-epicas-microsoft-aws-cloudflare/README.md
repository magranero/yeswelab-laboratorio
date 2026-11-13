# Caídas épicas de la nube y cada cuánto falla lo que usa una pyme

Artículo: https://yeswelab.com/experimentos/caidas-servicio-epicas-microsoft-aws-cloudflare/

Dos partes:

1. **Top de grandes caídas (2021-2026)** con las horas y la causa de su informe oficial: `datos/caidas.json`, con el enlace a la fuente de cada dato.
2. **Incidentes de páginas de estado** de 31 servicios que usan las pymes, leídos de su API pública (Statuspage, `/api/v2/incidents.json`).

```bash
python3 recolectar.py                          # resultados/incidentes.csv y resultados/fuentes_estado.json
uv run --with matplotlib python analizar.py    # resumen, tablas y gráficos
```

## Resultados

| Fichero | Qué es |
| --- | --- |
| `resultados/resumen.json` | Cifras del artículo: ranking, disparadores, duraciones, % de días con incidencia y la pila de ejemplo |
| `resultados/top_caidas.csv` | El top 10 ordenado por duración, con alcance, disparador y fuente |
| `resultados/servicios.csv` | Por servicio: incidentes, ventana, incidentes cada 30 días, duración mediana, % de días con incidencia y con incidencia grave |
| `resultados/incidentes.csv` | Un incidente por fila: servicio, fechas, impacto declarado y nº de componentes (sin textos) |
| `resultados/graficos/` | Los cuatro gráficos del artículo |

## Cómo se mide

- **Duración de las grandes caídas:** de la hora de inicio a la de recuperación que da cada informe, en su zona horaria. Si la fuente solo da el día (Atlassian), se cuenta hasta el inicio de ese día.
- **Incidentes por 30 días:** incidentes devueltos / días desde el más antiguo hasta la consulta × 30.
- **% de días con incidencia:** días naturales (UTC) con algún incidente abierto / días naturales de la ventana.
- **Grave:** impacto `major` o `critical`, tal como lo marca cada empresa.
- **Pila de ejemplo:** 30 × (1 − ∏(1 − pᵢ)), suponiendo fallos independientes.
- Redondeo una sola vez, al final, a la mitad hacia arriba.

## Limitaciones

- Diez caídas no son una muestra estadística; la clasificación del disparador es nuestra.
- La caída de Microsoft 365 de noviembre de 2026 seguía abierta al publicar: la duración es hasta la última actualización consultada.
- Las páginas de estado miden lo que cada empresa publica, no la disponibilidad real.
- La API devuelve solo los últimos 25 o 50 incidentes: cada servicio tiene una ventana distinta.
- ClickUp queda fuera: devuelve incidentes con resolución anterior a la creación.
