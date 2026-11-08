# ¿Qué datos personales se escapan al anonimizar un texto antes de ChatGPT?

Experimento del cuaderno de [yeswelab.com](https://yeswelab.com/experimentos/anonimizar-datos-personales-chatgpt-rgpd/), medido el 7 de noviembre de 2026.

Compara cinco detectores locales de datos personales sobre 500 documentos de pyme en español (correos a una gestoría, tickets de una tienda online, notas de RRHH, fichas de una clínica y mensajes de WhatsApp) con 1.878 datos personales etiquetados: nombres, correos, teléfonos, DNI/NIE, IBAN y direcciones.

| Detector | Qué es |
| --- | --- |
| `regex` | Expresiones regulares propias para correo, teléfono, DNI/NIE e IBAN (sin nombres ni direcciones) |
| `presidio_defecto` | Microsoft Presidio con spaCy `es_core_news_lg`, configuración por defecto para español |
| `presidio_telefono_es` | Lo mismo, con el reconocedor de teléfonos limitado a la región ES |
| `gliner_multi_pii` | GLiNER multi PII v1, etiquetas en inglés, umbral 0,5 |
| `openai_privacy_filter` | OpenAI Privacy Filter (transformers), clase por token con argmax |

Además se calculan tres uniones (regex + cada modelo) a partir de las salidas guardadas.

## Métricas

- **Se escapa:** un dato personal con alguna letra o cifra sin tapar. Un IBAN con los cuatro últimos dígitos visibles cuenta como fuga.
- **Documentos con fuga:** documentos con al menos un dato que se escapa.
- **Tapado de más:** fracción del texto que no era dato personal y se tapó igualmente.
- **Tiempo:** milisegundos por documento, mediana de 5 pasadas completas por los 500 documentos, en CPU.

## Cómo repetirlo

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python presidio-analyzer spacy gliner transformers torch faker huggingface_hub pandas protobuf sentencepiece tiktoken
HF_HOME=./cache/hf caffeinate -dimsu .venv/bin/python medir.py
.venv/bin/python resumir.py
```

`medir.py` descarga de Hugging Face los tres modelos (unos 7 GB con la caché) en las revisiones de `entorno.txt`. No necesita cuentas ni claves. En un M1 Max, la medición tarda unos 20 minutos.

## Ficheros

- `corpus.py`: genera el corpus sintético con semilla fija. Los DNI, NIE e IBAN tienen dígitos de control válidos, pero son aleatorios; nombres, correos y direcciones salen de Faker (es_ES). **No hay datos de personas reales** y el corpus no se guarda en el repositorio.
- `medir.py`: ejecuta los detectores y guarda las posiciones tapadas.
- `resumir.py`: calcula el resumen.
- `resultados/por_entidad.csv`: cobertura de cada dato personal por detector (sin el texto).
- `resultados/por_documento.csv`: caracteres tapados de más por documento.
- `resultados/tiempos.csv` y `resultados/carga.csv`: tiempos en bruto.
- `resultados/resumen.json`: resumen sin redondear.

## Fuentes y licencias

- [openai/privacy-filter](https://huggingface.co/openai/privacy-filter): Apache 2.0.
- [urchade/gliner_multi_pii-v1](https://huggingface.co/urchade/gliner_multi_pii-v1): Apache 2.0 (base [microsoft/mdeberta-v3-base](https://huggingface.co/microsoft/mdeberta-v3-base), MIT).
- [spacy/es_core_news_lg](https://huggingface.co/spacy/es_core_news_lg): GPL-3.0. Se descarga; no se redistribuye.
- [Microsoft Presidio](https://github.com/microsoft/presidio): MIT. [Faker](https://github.com/joke2k/faker): MIT.

Código de este experimento: MIT. Resultados: CC BY 4.0.
