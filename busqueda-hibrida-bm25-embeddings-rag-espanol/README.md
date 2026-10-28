# Búsqueda híbrida o vectorial para RAG en español

BM25, embeddings densos, fusión RRF y reranker medidos con dos conjuntos de preguntas en español. Artículo: [yeswelab.com/experimentos/busqueda-hibrida-bm25-embeddings-rag-espanol/](https://yeswelab.com/experimentos/busqueda-hibrida-bm25-embeddings-rag-espanol/).

## Qué se mide

| Método | Qué es |
| :--- | :--- |
| `bm25` | bm25s con el lematizador Snowball de español y stopwords en español |
| `e5-small` | intfloat/multilingual-e5-small, similitud coseno exacta |
| `bge-m3` | BAAI/bge-m3 (solo la parte densa, fp16); solo en MLQA |
| `rrf bm25+<denso>` | Reciprocal Rank Fusion (k = 60) del top-100 de BM25 y del denso |
| `<base> +rerank` | BAAI/bge-reranker-v2-m3 reordena el top-20 de la base, en una muestra fija de 300 consultas |

Métricas por consulta: nDCG@10 (relevancia binaria), Recall@10, Recall@100 y MRR@10. Diferencias de nDCG@10 con IC 95 % por bootstrap pareado (2.000 remuestreos). Latencia: una consulta cada vez, 30 consultas fijas × 5 repeticiones.

## Cómo repetirlo

```bash
python3 -m venv .venv
.venv/bin/pip install bm25s==0.3.15 PyStemmer==3.1.0 sentence-transformers==6.2.0 transformers==5.20.2 torch==2.14.1 numpy pandas pyarrow
.venv/bin/python preparar.py   # descarga datos y reranker (revisiones fijadas)
.venv/bin/python medir.py      # calidad y latencia; menos de 30 min en un M1 Max
.venv/bin/python resumir.py    # comparaciones extra a partir de por_consulta.csv
```

Los modelos e5-small y bge-m3 se descargan de Hugging Face la primera vez que `sentence-transformers` los carga (quita `HF_HUB_OFFLINE=1` de `medir.py` si no los tienes en caché). En otro equipo sin GPU de Apple, cambia `device="mps"` por `"cuda"` o `"cpu"`.

## Resultados (`resultados/`)

- `datos.json`: conjuntos, revisiones y licencias.
- `por_consulta.csv`: las cuatro métricas de cada consulta y método, y si la consulta tiene cifras o nombres propios (`literal`).
- `resumen.json`: medias por conjunto, por grupo (todas, muestra del reranker, literal y no literal), comparaciones con IC 95 %, tiempos de indexado de BM25 (5 repeticiones), tiempo de embeddings del corpus y latencias (mediana, p90 y rango de medianas entre repeticiones).
- `latencia.csv`: cada medición de latencia en milisegundos.
- `comparaciones_extra.json`: híbrido + reranker frente a los densos solos (IC 95 %) y cuántas consultas mejora o empeora el reranker.

## Fuentes y licencias

- MIRACL (español, dev) en la versión con negativos difíciles de MTEB: [mteb/MIRACLRetrievalHardNegatives](https://huggingface.co/datasets/mteb/MIRACLRetrievalHardNegatives), CC BY-SA 4.0. Zhang et al., «MIRACL: A Multilingual Retrieval Dataset Covering 18 Diverse Languages», TACL 2023.
- MLQA (español-español, test): [mteb/MLQARetrieval](https://huggingface.co/datasets/mteb/MLQARetrieval), CC BY-SA 3.0. Lewis et al., «MLQA: Evaluating Cross-lingual Extractive Question Answering», ACL 2020.
- [intfloat/multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small) (MIT), [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) (MIT) y [BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3) (Apache 2.0).

Los datos y modelos no se guardan en este repositorio: los descarga `preparar.py`. Código bajo MIT; resultados bajo CC BY 4.0.
