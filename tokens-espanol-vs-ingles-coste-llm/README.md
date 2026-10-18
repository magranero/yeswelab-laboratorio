# Tokens en español y portugués frente a inglés

Cuenta cuántos tokens gastan las mismas frases en inglés, español y portugués con 7 tokenizadores públicos (o200k_base, cl100k_base, Llama 3, Gemma 3, Qwen3, DeepSeek-V3 y Mistral Tekken) y mide cuánto tarda cada uno en tokenizar el corpus.

- Corpus: [OPUS-100](https://huggingface.co/datasets/Helsinki-NLP/opus-100), split de test, pares `en-es` y `en-pt` (2000 frases paralelas cada uno).
- Conteo sin tokens especiales (`encode_ordinary` en tiktoken, `add_special_tokens=False` en tokenizers).
- Sobrecoste = tokens del idioma / tokens del inglés − 1, sobre el total del corpus. Intervalo de confianza del 95 % por bootstrap (2000 remuestreos de frases, semilla fija).
- Velocidad: 7 pasadas por tokenizador sobre las 2000 frases en español, una llamada por frase, con calentamiento previo. Mediana, mínimo, máximo y desviación.

## Cómo repetirlo

```bash
uv venv .venv -p 3.12
uv pip install -p .venv/bin/python tiktoken tokenizers huggingface_hub pyarrow
.venv/bin/python medir.py
```

Descarga el corpus y los `tokenizer.json` del Hugging Face Hub (todos sin acceso restringido; no hace falta cuenta). Tarda menos de un minuto en un portátil Apple Silicon. Las revisiones exactas usadas están en `entorno.txt`.

## Resultados

- `resultados/resumen.json`: totales, sobrecoste, intervalos, tokens por palabra, caracteres por token y velocidad.
- `resultados/conteos_por_frase.csv`: tokens de cada frase en cada idioma y tokenizador.
- `resultados/tiempos.csv`: cada repetición de la medida de velocidad.

## Licencias de terceros

El script descarga el corpus OPUS-100 (Helsinki-NLP) y los `tokenizer.json` de cada modelo desde Hugging Face; no se guardan en este repositorio. Cada uno tiene su propia licencia: consúltala en su ficha antes de reutilizarlos.
