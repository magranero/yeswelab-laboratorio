"""PyMuPDF en un entorno donde solo se pide instalar PyMuPDF.

En el entorno común, `import pymupdf` carga también pymupdf-layout y onnxruntime. Este script
comprueba si eso se debe a compartir entorno con los demás parsers o a PyMuPDF en sí (PyMuPDF 2.0
declara pymupdf-layout, onnxruntime y pymupdf4llm como dependencias). Repite la medida de
`medir.py` para PyMuPDF con otro intérprete:

    uv venv .venv-pymupdf -p 3.12 && uv pip install -p .venv-pymupdf/bin/python pymupdf
    .venv/bin/python medir_aislado.py .venv-pymupdf/bin/python

Salida: resultados/pymupdf_aislado.csv (una fila por repetición).
"""

import csv
import json
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
REPS = 5


def main() -> None:
    python = sys.argv[1]
    cmd = [python, os.path.join(AQUI, "medir.py"), "--trabajador", "pymupdf"]
    subprocess.run(cmd, capture_output=True, check=True)  # calentamiento
    filas = []
    for rep in range(1, REPS + 1):
        p = subprocess.run(cmd, capture_output=True, text=True, check=True)
        r = json.loads(p.stdout.strip().splitlines()[-1])
        filas.append({"parser": "pymupdf_aislado", "rep": rep, "import_s": round(r["import_s"], 4),
                      "total_s": round(r["total_s"], 4), "pico_mb": round(r["pico_mb"], 1)})
        print(filas[-1])
    with open(os.path.join(AQUI, "resultados", "pymupdf_aislado.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


if __name__ == "__main__":
    main()
