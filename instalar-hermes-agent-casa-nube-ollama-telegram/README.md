# ¿Qué equipo hace falta para un agente de IA con modelo local?

Guías:

- Hermes Agent: https://yeswelab.com/guias/instalar-hermes-agent-casa-nube-ollama-telegram/
- OpenClaw: https://yeswelab.com/guias/openclaw-instalacion-segura/

`medir_modelos.py` mide, con Ollama en local, cuánta memoria ocupa cada modelo con herramientas, cuánto tarda en leer el prompt de un agente (unos 10.000 tokens), a qué velocidad escribe y si usa bien las herramientas en 5 peticiones de oficina. Lo hace en las condiciones de cada agente:

| Modo | Contexto | API de Ollama | Fichero |
| --- | --- | --- | --- |
| Hermes Agent | 64K, con una variante `<modelo>-64k` creada por Modelfile | Compatible con OpenAI (`/v1/chat/completions`) | `resultados/modelos.json` |
| OpenClaw (`--openclaw`) | 32K | Nativa (`/api/chat`) | `resultados/modelos_openclaw.json` |
| Sin tarjeta gráfica (`--cpu 4`) | 64K | Nativa, con `num_gpu: 0` y 4 hilos | `resultados/modelos.json` |

```bash
ollama pull qwen3:4b qwen3:8b gpt-oss:20b qwen3:30b-a3b gemma4:31b   # uno por uno
python3 medir_modelos.py qwen3:4b qwen3:8b gpt-oss:20b qwen3:30b-a3b gemma4:31b
python3 medir_modelos.py --cpu 4 qwen3:4b qwen3:8b
python3 medir_modelos.py --openclaw qwen3:4b qwen3:8b gpt-oss:20b qwen3:30b-a3b gemma4:31b
python3 resumen.py   # tablas en resultados/resumen.md
```

Sin dependencias: solo Python 3 y Ollama. No usa claves ni servicios externos.

## Cómo mide

- **Memoria:** `size` y `size_vram` de `/api/ps` con el modelo cargado.
- **Lectura y escritura:** `prompt_eval_count / prompt_eval_duration` y `eval_count / eval_duration` de Ollama. Una carga de calentamiento y 3 repeticiones; se da la mediana. Cada repetición empieza con un identificador distinto para que Ollama no reutilice el prompt ya procesado (con el identificador al final, la lectura salía a decenas de miles de tokens por segundo, falsa).
- **Herramientas:** dos herramientas (`consultar_factura`, `crear_recordatorio`) y 5 peticiones. Acierta si llama a la herramienta correcta con argumentos JSON válidos y completos.
- **Sin Modelfile:** en modo Hermes se carga también el modelo base por la API compatible con OpenAI, sin indicar contexto, para ver qué contexto elige Ollama y cuánto ocupa.
- **Razonamiento:** `think: false` en qwen3 y gemma4, `think: "low"` en gpt-oss, para medir la respuesta y no el razonamiento.
- `resultados/modelos_ficha.json`: contexto de serie, tamaño y cuantización de cada modelo según `/api/show`.

## Resultados

En `resultados/resumen.md`. Medido el 30/10/2026 en un MacBook Pro M1 Max con 64 GB, macOS 26.6.2, Ollama 0.40.8, conectado a la corriente.

## Limitaciones

- Un solo equipo (Apple Silicon). Las recomendaciones para tarjetas NVIDIA de las guías son una estimación por la memoria medida, no una medición.
- El modo `--cpu` usa los núcleos del M1 Max: aproxima un VPS de 4 vCPU, pero un VPS real puede ser más lento.
- Las 5 peticiones con herramientas son sencillas y de un paso. No miden tareas largas de varios pasos, donde los modelos locales fallan más.
- Cuantizaciones por defecto de Ollama (Q4_K_M, MXFP4 y NVFP4 en gemma4:31b). Otras cuantizaciones cambian memoria y velocidad.
