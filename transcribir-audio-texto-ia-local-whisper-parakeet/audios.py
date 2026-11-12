"""Genera los audios de prueba con las voces de macOS (`say`) y ffmpeg, en tres condiciones.

    python audios.py datos

- limpio: la voz sintética tal cual, 16 kHz mono.
- whatsapp: banda de teléfono (300–3.400 Hz) y compresión Opus a 16 kbit/s, como una nota de voz o una llamada.
- ruido: ruido rosa con semilla fija mezclado a 10 dB de relación señal/ruido (bar, tienda, furgoneta).

Todo es reproducible: mismas voces, mismo texto y misma semilla dan el mismo audio.
"""
import json
import os
import subprocess
import sys
import wave

import numpy as np

from textos import TEXTOS, VOCES, VOZ_ID

SNR_DB = 10


def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def duracion(ruta):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", ruta],
                         check=True, capture_output=True, text=True).stdout
    return float(out.strip())


def leer_wav(ruta):
    with wave.open(ruta) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64), w.getframerate()


def escribir_wav(ruta, x, sr):
    with wave.open(ruta, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(np.clip(np.round(x), -32768, 32767).astype(np.int16).tobytes())


def ruido_rosa(n, rng):
    """Ruido blanco filtrado a 1/f en potencia (espectro 1/sqrt(f) en amplitud)."""
    espectro = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n)
    f[0] = f[1]
    return np.fft.irfft(espectro / np.sqrt(f), n)


def mezclar_ruido(entrada, salida, semilla):
    voz, sr = leer_wav(entrada)
    rng = np.random.default_rng(20261112 + semilla)
    r = ruido_rosa(len(voz), rng)
    # Potencia de la voz solo donde hay voz (por encima de -40 dB del pico), para no contar silencios.
    activa = voz[np.abs(voz) > np.abs(voz).max() * 0.01]
    p_voz = np.mean(activa ** 2)
    r *= np.sqrt(p_voz / (10 ** (SNR_DB / 10)) / np.mean(r ** 2))
    mezcla = voz + r
    pico = np.abs(mezcla).max()
    if pico > 32767:
        mezcla *= 32767 / pico
    escribir_wav(salida, mezcla, sr)


def main(carpeta):
    os.makedirs(carpeta, exist_ok=True)
    indice = []
    for t in TEXTOS:
        for voz in VOCES:
            base = f"{t['id']}__{VOZ_ID[voz]}"
            aiff = os.path.join(carpeta, base + ".aiff")
            limpio = os.path.join(carpeta, base + "__limpio.wav")
            run(["say", "-v", voz, "-o", aiff, t["texto"]])
            run(["ffmpeg", "-y", "-i", aiff, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", limpio])
            os.remove(aiff)
            # WhatsApp / teléfono: filtro de banda, 8 kHz, Opus 16 kbit/s y vuelta a WAV de 16 kHz.
            ogg = os.path.join(carpeta, base + ".ogg")
            run(["ffmpeg", "-y", "-i", limpio, "-af", "highpass=f=300,lowpass=f=3400", "-ar", "8000",
                 "-c:a", "libopus", "-b:a", "16k", ogg])
            whatsapp = os.path.join(carpeta, base + "__whatsapp.wav")
            run(["ffmpeg", "-y", "-i", ogg, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", whatsapp])
            os.remove(ogg)
            # Ruido rosa a SNR fija (calculada sobre la potencia media de la voz), con semilla por audio.
            ruido = os.path.join(carpeta, base + "__ruido.wav")
            mezclar_ruido(limpio, ruido, semilla=len(indice))
            for cond, ruta in (("limpio", limpio), ("whatsapp", whatsapp), ("ruido", ruido)):
                indice.append({"audio": os.path.basename(ruta), "texto_id": t["id"], "voz": VOZ_ID[voz],
                               "condicion": cond, "segundos": duracion(ruta)})
    json.dump(indice, open(os.path.join(carpeta, "indice.json"), "w"), ensure_ascii=False, indent=1)
    print(len(indice), "audios,", sum(a["segundos"] for a in indice if a["condicion"] == "limpio"), "s por condición")


if __name__ == "__main__":
    main(sys.argv[1])
