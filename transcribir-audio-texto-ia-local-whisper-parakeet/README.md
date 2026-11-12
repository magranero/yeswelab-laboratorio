# Transcribir audios en español con IA local: Whisper (3 tamaños) frente a Parakeet, en GPU y en CPU

Transcribe 90 mensajes de voz típicos de una pyme (pedidos, citas, presupuestos, reclamaciones, avisos internos) en tres condiciones de sonido y mide cuántas palabras falla cada modelo, cuántos datos clave (importes, teléfonos, horas, fechas, cantidades) copia bien y cuánto tarda.

| Modelo | Qué es | Dónde corre |
| --- | --- | --- |
| `mlx-whisper-base` | Whisper base (74 M parámetros), OpenAI | GPU del Mac (MLX) |
| `mlx-whisper-small` | Whisper small (244 M) | GPU del Mac (MLX) |
| `mlx-whisper-large-v3-turbo` | Whisper large-v3-turbo (809 M) | GPU del Mac (MLX) |
| `parakeet-tdt-0.6b-v3` | NVIDIA Parakeet TDT 0.6B v3 (600 M), multilingüe | GPU del Mac (MLX) |
| `faster-whisper-large-v3-turbo-cpu` | Whisper large-v3-turbo con faster-whisper (CTranslate2), int8 | Solo CPU |

El modelo en CPU representa un ordenador sin chip de Apple ni tarjeta gráfica; como es unas 4 veces más lento, se mide solo con la voz de Mónica (30 audios, las tres condiciones).

## Audios

`textos.py` contiene 10 mensajes escritos para este experimento (nombres genéricos, teléfonos inventados) y sus datos clave. `audios.py` los convierte en voz con las voces de macOS (`say`): **Mónica** y **Eddy** (español de España) y **Paulina** (español de México). Cada audio se genera en tres condiciones:

- `limpio`: la voz tal cual, 16 kHz mono.
- `whatsapp`: banda de teléfono (300–3.400 Hz), 8 kHz y compresión Opus a 16 kbit/s, como una nota de voz o una llamada.
- `ruido`: ruido rosa con semilla fija a 10 dB de relación señal/ruido (un bar, una tienda, una furgoneta).

Son 30 audios por condición (7,2 minutos), 90 en total. Los audios no se guardan en el repositorio: se regeneran iguales con `audios.py`.

## Métricas

- **WER** (tasa de error por palabra): (sustituciones + borrados + inserciones) / palabras de la referencia, sobre el total de cada grupo. Antes de comparar se normalizan igual la referencia y la transcripción: minúsculas, sin tildes ni puntuación, «5:30» = «cinco y media», «1.800 €» = «mil ochocientos euros», «8 %» = «ocho por ciento», teléfonos y números de pedido cifra a cifra, «un/una» = «uno» (ver `normalizar` en `resumir.py`).
- **Datos clave correctos**: % de los 39 datos clave por voz y condición (importes, teléfonos, número de pedido, horas, días, cantidades, un topónimo) que aparecen tal cual en la transcripción normalizada. Un teléfono con una cifra cambiada cuenta como fallo.
- **Veces tiempo real**: minutos de audio / minutos de cálculo (30 = transcribe 30 minutos de audio en 1 minuto). También en segundos por minuto de audio.
- **Memoria**: pico de memoria del proceso (RSS) y, en los modelos MLX, pico de memoria de MLX.

Decodificación voraz (temperatura 0, sin búsqueda en haz) en todos; idioma fijado en español en Whisper; Parakeet detecta el idioma solo. Cada modelo corre en su propio proceso, con una transcripción de calentamiento antes de medir, y hace 5 pasadas completas. `resumen.json` guarda medianas, mínimos y máximos sin redondear.

## Cómo repetirlo

```bash
uv venv .venv -p 3.12
uv pip install -p .venv/bin/python mlx-whisper faster-whisper parakeet-mlx jiwer num2words "av<16"
.venv/bin/python audios.py datos
caffeinate -dimsu sh medir.sh
.venv/bin/python resumir.py resultados
```

Necesita un Mac con Apple Silicon (MLX), `ffmpeg` y las voces Mónica, Eddy (Español (España)) y Paulina instaladas en Ajustes del Sistema → Accesibilidad → Contenido leído. La primera vez descarga los modelos de Hugging Face (unos 12 GB en total, sin cuenta). `av<16` hace falta porque faster-whisper 1.2.1 no funciona con PyAV 19. La medición tarda unos 25 minutos en un M1 Max. Versiones y revisiones exactas en `entorno.txt`.

Para probar con tus audios: pon tus ficheros y su transcripción correcta en `textos.py` (o adapta `indice.json`) y repite.

## Archivos

- `resultados/transcripciones.jsonl`: texto devuelto por cada modelo en cada pasada y segundos de cálculo de cada audio.
- `resultados/por_audio.csv`: por modelo, pasada y audio: WER, sustituciones, borrados, inserciones, datos clave correctos y cuáles fallaron.
- `resultados/carga.jsonl`: segundos de carga (modelo ya descargado) y picos de memoria.
- `resultados/resumen.json`: resumen total, por condición, por voz y solo con la voz de Mónica (para comparar con la CPU).
- `resultados/energia.txt`: fuente de alimentación antes y después de medir.

## Fuentes y licencias

- Whisper (OpenAI): MIT. Conversiones a MLX de [mlx-community/whisper-base-mlx](https://huggingface.co/mlx-community/whisper-base-mlx), [whisper-small-mlx](https://huggingface.co/mlx-community/whisper-small-mlx) y [whisper-large-v3-turbo](https://huggingface.co/mlx-community/whisper-large-v3-turbo): MIT.
- [mobiuslabsgmbh/faster-whisper-large-v3-turbo](https://huggingface.co/mobiuslabsgmbh/faster-whisper-large-v3-turbo): MIT.
- [mlx-community/parakeet-tdt-0.6b-v3](https://huggingface.co/mlx-community/parakeet-tdt-0.6b-v3), conversión de [nvidia/parakeet-tdt-0.6b-v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3): CC BY 4.0.
- Los modelos se descargan; no se redistribuyen. Las voces son las de macOS y los audios no se incluyen.
- [mlx-whisper](https://github.com/ml-explore/mlx-examples): MIT. [faster-whisper](https://github.com/SYSTRAN/faster-whisper): MIT. [parakeet-mlx](https://github.com/senstella/parakeet-mlx): Apache 2.0. [jiwer](https://github.com/jitsi/jiwer): Apache 2.0. [num2words](https://github.com/savoirfairelinux/num2words): LGPL-2.1. [FFmpeg](https://ffmpeg.org): LGPL/GPL.

Código de este experimento: MIT. Resultados: CC BY 4.0.
