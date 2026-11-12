#!/bin/sh
# Medición completa: 5 repeticiones por modelo. Lanzar con: caffeinate -dimsu sh medir.sh
set -e
PY=.venv/bin/python
mkdir -p resultados
rm -f resultados/transcripciones.jsonl resultados/carga.jsonl
pmset -g batt | head -1 > resultados/energia.txt
for m in mlx-whisper-base mlx-whisper-small mlx-whisper-large-v3-turbo parakeet-tdt-0.6b-v3; do
  $PY transcribir.py $m datos resultados/transcripciones.jsonl 5
done
# En CPU (sin GPU) es unas 7 veces más lento: solo la voz de Mónica (30 audios, las 3 condiciones).
$PY transcribir.py faster-whisper-large-v3-turbo-cpu datos resultados/transcripciones.jsonl 5 monica_es
pmset -g batt | head -1 >> resultados/energia.txt
