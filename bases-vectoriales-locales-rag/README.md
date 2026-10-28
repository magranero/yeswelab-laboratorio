# Bases vectoriales locales para RAG

Compara las opciones embebidas (sin servidor) más citadas para guardar y buscar embeddings en local: búsqueda exacta con numpy, FAISS (plano y HNSW), sqlite-vec, DuckDB, Chroma y LanceDB (sin índice y con su índice IVF_PQ por defecto). Mide, con 10.000 y 100.000 párrafos de Wikipedia en español:

- **Indexado:** segundos hasta tener los vectores persistidos en disco y listos para consultar.
- **Disco:** tamaño de lo que queda guardado.
- **Reapertura:** abrir de nuevo lo guardado y hacer la primera consulta.
- **Latencia:** 1.000 consultas de una en una (k = 10) tras 20 de calentamiento; mediana (p50) y percentil 95 (p95).
- **Recall@10:** proporción de los 10 vecinos exactos (similitud coseno calculada con numpy) que devuelve cada motor.
- **Memoria extra:** pico de RSS del proceso menos el RSS tras importar la librería y cargar los vectores.

Cada motor usa su configuración por defecto. Se añaden dos variantes ajustadas solo en la consulta para ver cuánto se recupera: `faiss_hnsw_ef64` (efSearch = 64) y `lancedb_ivfpq_refine` (refine_factor = 10). Cada medida corre en un proceso nuevo y una carpeta temporal nueva; 5 repeticiones por caso, en orden aleatorio e intercalado (semilla fija).

## Datos

- Corpus: un fichero de [wikimedia/wikipedia](https://huggingface.co/datasets/wikimedia/wikipedia) (`20231101.es/train-00002-of-00013.parquet`, revisión fijada en `preparar.py`). Se cortan los artículos en párrafos de 300 a 1.500 caracteres, se barajan con semilla fija y se toman 100.000 para indexar (los primeros 10.000 forman el corpus pequeño) y 1.000 distintos para consultar; la consulta es la primera frase de cada uno de esos párrafos.
- Embeddings: [intfloat/multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small) (384 dimensiones, normalizados, prefijos `passage:` y `query:`).

## Cómo repetirlo

```bash
uv venv .venv -p 3.12 --managed-python   # hace falta un Python con carga de extensiones de SQLite
uv pip install -p .venv/bin/python numpy faiss-cpu sqlite-vec duckdb chromadb lancedb pyarrow psutil sentence-transformers torch huggingface_hub
.venv/bin/python preparar.py   # descarga corpus y modelo, calcula embeddings y vecinos exactos (unos 6 minutos en MPS)
.venv/bin/python medir.py      # 10 configuraciones × 2 tamaños × 5 repeticiones (unos 25 minutos)
.venv/bin/python resumir.py
```

Si la librería de Hugging Face no puede descargar el parquet, se puede bajar a mano a `datos/wiki-es.parquet` desde la URL `https://huggingface.co/datasets/wikimedia/wikipedia/resolve/<revisión>/<fichero>`; `preparar.py` la usa si existe. `datos/` no se sube al repositorio.

## Resultados

- `resultados/medidas.jsonl`: cada medida (motor, tamaño, repetición) sin redondear.
- `resultados/resumen.csv` y `resultados/resumen.json`: mediana, mínimo, máximo y desviación típica por motor y tamaño.
- `resultados/derivados.json`: cocientes frente a numpy y entre 100.000 y 10.000 vectores, calculados sin redondear.
- `resultados/datos.json`: corpus, modelo, revisiones y tiempo de cálculo de los embeddings.

## Licencias de terceros

El script descarga un fichero de Wikipedia en español (wikimedia/wikipedia, texto bajo CC BY-SA 4.0 y GFDL) y el modelo multilingual-e5-small (MIT) desde Hugging Face; no se guardan en este repositorio. Las librerías medidas tienen sus propias licencias (numpy BSD, FAISS MIT, sqlite-vec MIT/Apache 2.0, DuckDB MIT, Chroma Apache 2.0, LanceDB Apache 2.0).
