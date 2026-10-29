# Accidente de Urda: capas de protección, cronología y telefonemas

Artículo: https://yeswelab.com/experimentos/accidente-urda-lzb-sistemas-respaldo/

Análisis del alcance entre un AVE de Renfe y un Iryo detenido en el PK 118 de la línea de alta velocidad Madrid-Sevilla, junto a Urda (Toledo), el 28 de octubre de 2026, tras la caída de la central LZB. Se hace con datos publicados y con el texto literal del Reglamento de Circulación Ferroviaria; no sustituye a la investigación de la CIAF ni a la judicial.

```bash
uv run --with matplotlib python analizar.py
```

## Datos

| Fichero | Contenido |
| --- | --- |
| `datos/hechos.json` | Cada dato con su fuente y su estado: oficial, prensa, discrepante o sin confirmar |
| `datos/cronologia.csv` | Secuencia minuto a minuto con fuente, incluidas las tres horas publicadas del impacto |
| `datos/telefonemas.json` | Transcripción literal de los telefonemas 5ET3.2 y 5ET3.3 del BOE y de la orden que recogen los audios |

## Resultados

| Fichero | Qué es |
| --- | --- |
| `resultados/resumen.json` | Ventanas de tiempo, velocidades implícitas, comparación de telefonemas, capas de protección y fuentes discrepantes |
| `resultados/ventanas.csv` | Minutos desde la caída del LZB, desde la orden y desde cada aviso del Iryo, para cada hora del impacto |
| `resultados/frenado_ilustrativo.csv` | Distancia de frenado d = v²/2a con deceleraciones supuestas (no normativas) |
| `resultados/graficos/` | Capas de protección, cronología, grafo de información y velocidad implícita |

## Fuentes

- Reglamento de Circulación Ferroviaria (RD 664/2015), texto consolidado del BOE: arts. 1.5.1.4, 5ET3.3.1.4, 5ET3.4.3.4, 5ET3.4.3.5, 5ET3.4.3.6 y 5AN1.1.5.1.
- Real Decreto 606/2023 (BOE-A-2023-16156).
- Referencia del Consejo de Ministros de 27 de octubre de 2026 (La Moncloa).
- Declaraciones del ministro de Transportes y del 112 de Castilla-La Mancha, recogidas por Castilla-La Mancha Media.
- Audios del centro de control publicados por la Cadena SER y recogidos por Infobae y El Español.

## Limitaciones

- Ninguna cifra procede de los registradores de los trenes ni del enclavamiento: no son públicos.
- La distancia entre trenes (unos 25 km) y varias horas proceden de la prensa.
- Las distancias de frenado son ilustrativas: dependen del tren, la pendiente y el estado del carril.
