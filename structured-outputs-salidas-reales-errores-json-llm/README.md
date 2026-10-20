# Structured outputs con salidas reales: qué errores comete un LLM al devolver JSON

Segunda parte de [structured-outputs-agentes-ia-baml-outlines-vs-retries](../structured-outputs-agentes-ia-baml-outlines-vs-retries). Aquí los errores no son sintéticos: cuatro modelos abiertos ejecutados en local con Ollama extraen pedidos de 30 correos en español, 5 veces cada uno.

- **Generación libre:** se guarda cada salida tal cual, se clasifica el fallo, se repara con `json_repair` y, si no queda válida según el esquema, se hace un **reintento real** con el modelo (tokens y tiempo que devuelve Ollama).
- **Generación restringida:** el mismo correo con el JSON Schema en el parámetro `format` de Ollama (decodificación restringida por gramática, el mismo principio que Outlines).
- Cada pedido se compara campo a campo con el correo original (email, empresa, ciudad, fecha, urgencia, SKU y cantidades).

## Cómo repetirlo

Necesitas [Ollama](https://ollama.com) con los modelos `llama3.2`, `llama3.1`, `qwen2.5:3b` y `gemma3:4b`, y [uv](https://docs.astral.sh/uv/).

```bash
uv run --with json-repair python medir.py --modelos llama3.2 qwen2.5:3b llama3.1 gemma3:4b --correos 30 --semillas 5
uv run --with json-repair python analizar.py
```

`medir.py` va guardando en `resultados/*.jsonl` y se puede reanudar. Tarda unas cuatro horas en un M1 Max.

## Resultados

- `resultados/corpus.jsonl`: los 30 correos y la verdad de cada pedido (datos sintéticos).
- `resultados/libre.jsonl` y `resultados/restringida.jsonl`: cada salida en bruto, con tokens, tiempo, motivo de fin y, si lo hubo, el reintento.
- `resultados/resumen.json`: el análisis.

## Licencias de terceros

Los modelos (Llama 3.1 y 3.2 de Meta, Qwen 2.5 de Alibaba, Gemma 3 de Google) tienen sus propias licencias; se descargan con Ollama y no se incluyen aquí. json-repair es MIT.
