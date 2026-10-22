# Tamaño de chunk para RAG en español

Mide cuánto acierta la recuperación de un RAG con textos en español según el tamaño del chunk (128, 256, 512 y 1024 tokens), el solapamiento (0 % y 20 %) y el modelo de embeddings (multilingual-e5-small, paraphrase-multilingual-MiniLM-L12-v2 y bge-m3).

- Corpus: [XQuAD](https://huggingface.co/datasets/google/xquad) en español (`xquad.es`, 1190 preguntas sobre 240 párrafos de 48 artículos de Wikipedia). Los párrafos se agrupan por artículo con los títulos de [SQuAD v1.1](https://huggingface.co/datasets/rajpurkar/squad) (mismos `id`), así que cada artículo es un documento largo que hay que trocear.
- Troceo: frases empaquetadas hasta el tamaño en tokens de `o200k_base` (tiktoken), sin partir frases salvo que una sola pase del tamaño. Con solapamiento, cada chunk repite las últimas frases del anterior hasta el 20 % del tamaño.
- Acierto: el chunk recuperado contiene entera la respuesta de referencia. Se mide recall@1, @3 y @5, y el recall con un presupuesto fijo de contexto (1024 y 2048 tokens que se mandarían al LLM: se cogen los mejores chunks mientras quepan; siempre al menos uno).
- Truncado: chunks que pasan del `max_seq_length` del modelo (el modelo solo ve el principio).
- Techo: porcentaje de preguntas cuya respuesta cabe entera en algún chunk; si el troceo la parte entre dos, ningún recuperador puede acertar.
- 5 repeticiones por configuración: tiempo de indexado (mediana, mínimo, máximo y desviación) y comprobación de que el recall no cambia entre repeticiones. Intervalo de confianza del 95 % por bootstrap sobre preguntas (2000 remuestreos, semilla fija).

## Cómo repetirlo

```bash
uv venv .venv -p 3.12
uv pip install -p .venv/bin/python sentence-transformers torch tiktoken pyarrow huggingface_hub numpy
.venv/bin/python medir.py
.venv/bin/python resumir.py
```

Descarga el corpus y los modelos del Hugging Face Hub (sin acceso restringido; no hace falta cuenta). Usa la GPU de Apple Silicon (MPS) si está disponible; en un M1 Max tarda unos 15 minutos, la mayor parte con bge-m3. Las revisiones exactas están en `resultados/resumen.json` y `entorno.txt`.

## Resultados

- `resultados/resumen.json`: recall por configuración con IC 95 %, chunks, tokens medios, truncados y tiempos.
- `resultados/resumen.csv`: lo mismo sin intervalos, en una tabla.
- `resultados/aciertos_por_pregunta.csv`: acierto de cada pregunta en cada configuración.
- `resultados/tiempos.csv`: cada repetición del indexado y de las consultas.
- `resultados/derivados.json`: diferencias en puntos entre 128 y 1024 tokens, efecto del solapamiento y tiempo de indexado relativo a multilingual-e5-small (lo calcula `resumir.py`).

## Licencias de terceros

El script descarga XQuAD (Google, CC BY-SA 4.0), SQuAD v1.1 (CC BY-SA 4.0) y los modelos multilingual-e5-small, paraphrase-multilingual-MiniLM-L12-v2 y bge-m3 desde Hugging Face; no se guardan en este repositorio. Consulta la licencia de cada uno en su ficha antes de reutilizarlos.
