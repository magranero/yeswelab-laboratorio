"""Transcribe todos los audios con un modelo y guarda texto y tiempos (una línea JSON por audio).

    python transcribir.py <modelo> <carpeta_audios> <salida.jsonl> <repeticiones> [voz]

Con [voz] solo se transcriben los audios de esa voz (se usa para el modelo en CPU, que es lento).

Cada modelo corre en su propio proceso para medir su memoria por separado. Antes de medir se hace
una transcripción de calentamiento que no se guarda. Decodificación voraz (temperatura 0) e idioma
fijado en español en los modelos Whisper; Parakeet detecta el idioma solo (no admite fijarlo).
"""
import json
import os
import resource
import sys
import time

MODELOS = {
    "mlx-whisper-base": ("mlx_whisper", "mlx-community/whisper-base-mlx"),
    "mlx-whisper-small": ("mlx_whisper", "mlx-community/whisper-small-mlx"),
    "mlx-whisper-large-v3-turbo": ("mlx_whisper", "mlx-community/whisper-large-v3-turbo"),
    "parakeet-tdt-0.6b-v3": ("parakeet", "mlx-community/parakeet-tdt-0.6b-v3"),
    "faster-whisper-large-v3-turbo-cpu": ("faster_whisper", "large-v3-turbo"),
}


def cargar(nombre):
    motor, repo = MODELOS[nombre]
    if motor == "mlx_whisper":
        import mlx_whisper
        from mlx_whisper.load_models import load_model
        import mlx.core as mx
        load_model(repo)  # descarga y deja en caché; mlx_whisper reutiliza el modelo cargado

        def tx(ruta):
            r = mlx_whisper.transcribe(ruta, path_or_hf_repo=repo, language="es", temperature=0.0, verbose=None)
            return r["text"]

        def memoria():
            return mx.get_peak_memory()
        return tx, memoria
    if motor == "parakeet":
        from parakeet_mlx import from_pretrained
        import mlx.core as mx
        modelo = from_pretrained(repo)

        def tx(ruta):
            return modelo.transcribe(ruta).text

        def memoria():
            return mx.get_peak_memory()
        return tx, memoria
    if motor == "faster_whisper":
        from faster_whisper import WhisperModel
        modelo = WhisperModel(repo, device="cpu", compute_type="int8", cpu_threads=os.cpu_count())

        def tx(ruta):
            segmentos, _ = modelo.transcribe(ruta, language="es", beam_size=1, temperature=0.0)
            return " ".join(s.text.strip() for s in segmentos)

        def memoria():
            return None
        return tx, memoria
    raise ValueError(nombre)


def main(nombre, carpeta, salida, reps, voz=None):
    indice = json.load(open(os.path.join(carpeta, "indice.json")))
    if voz:
        indice = [a for a in indice if a["voz"] == voz]
    t0 = time.perf_counter()
    tx, memoria = cargar(nombre)
    carga_s = time.perf_counter() - t0
    tx(os.path.join(carpeta, indice[0]["audio"]))  # calentamiento
    with open(salida, "a") as f:
        for rep in range(1, reps + 1):
            for a in indice:
                t = time.perf_counter()
                texto = tx(os.path.join(carpeta, a["audio"]))
                seg = time.perf_counter() - t
                f.write(json.dumps({"modelo": nombre, "rep": rep, **a, "texto": texto.strip(),
                                    "segundos_transcripcion": seg}, ensure_ascii=False) + "\n")
            f.flush()
            print(nombre, "repetición", rep, "hecha", flush=True)
    maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # bytes en macOS
    pico = memoria()
    with open(os.path.join(os.path.dirname(salida), "carga.jsonl"), "a") as f:
        f.write(json.dumps({"modelo": nombre, "carga_segundos": carga_s, "rss_pico_bytes": maxrss,
                            "mlx_pico_bytes": pico}) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5] if len(sys.argv) > 5 else None)
