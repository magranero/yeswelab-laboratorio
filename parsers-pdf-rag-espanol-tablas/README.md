# Parsers de PDF para RAG en español: texto, dos columnas y facturas

Convierte 36 PDF en español con 6 parsers de Python (pypdf, pdfplumber, PyMuPDF, PyMuPDF4LLM, MarkItDown y Docling) y compara el texto extraído con la referencia exacta con la que se generó cada PDF. Mide calidad (párrafos enteros, orden de lectura, tildes y símbolos, celdas y filas de tabla), tiempo, memoria y si la salida es idéntica entre ejecuciones.

## Corpus

Generado por `generar.py` con ReportLab y semilla fija, así que no hay datos de terceros: 12 informes a una columna, 12 a dos columnas y 12 facturas (la mitad con conceptos largos que ocupan varias líneas dentro de la celda). Textos con tildes, ñ, ¿ ¡, comillas latinas « » e importes en formato español (1.234,56 €). Cada PDF lleva un pie «Página N» que no forma parte de la referencia. Los PDF son digitales (no escaneados). Nota: las frases «con un coste de …» llevan el símbolo € duplicado por un error del generador; está igual en el PDF y en la referencia, así que no afecta a la comparación.

## Métricas

- `pies_colados`: % de pies de página («Página N») que aparecen en la salida, es decir, que acabarían dentro de los fragmentos del RAG.
- `parrafos_integros`: % de párrafos de la referencia que aparecen enteros y seguidos en la salida (tras normalizar espacios, saltos de línea y marcas de Markdown).
- `similitud`: similitud de Levenshtein normalizada entre todo el texto de referencia y la salida (0–100). Solo en informes.
- `orden`: % de pares de párrafos consecutivos que salen en el orden correcto. Solo en informes.
- `especiales`: % de caracteres á é í ó ú ñ ü ¿ ¡ « » € que conserva la salida en bruto, sin normalizar Unicode.
- `celdas`: % de celdas de concepto, precio unitario y total que aparecen en la salida. Solo en facturas.
- `filas_completas`: % de filas cuyo concepto, precio unitario y total salen en la misma línea y en orden.
- `importes_juntos`: % de filas cuyo precio unitario y total salen en la misma línea y en orden.

Cada parser se usa con su llamada más sencilla y su configuración por defecto (ver `cargar()` en `medir.py`). Cada repetición corre en un proceso nuevo, en orden intercalado entre parsers, tras una pasada de calentamiento que no cuenta.

## Cómo repetirlo

```bash
uv venv .venv -p 3.12
uv pip install -p .venv/bin/python reportlab pypdf pdfplumber pymupdf pymupdf4llm "markitdown[pdf]" docling rapidfuzz
.venv/bin/python generar.py
.venv/bin/python medir.py --reps 5
.venv/bin/python evaluar.py

# opcional: PyMuPDF en un entorno donde solo se instala PyMuPDF
uv venv .venv-pymupdf -p 3.12
uv pip install -p .venv-pymupdf/bin/python pymupdf
.venv/bin/python medir_aislado.py .venv-pymupdf/bin/python
```

Tarda menos de 10 minutos en un portátil Apple Silicon, sin contar la instalación; casi todo es Docling y PyMuPDF4LLM. La primera vez, Docling descarga sus modelos de Hugging Face (no hace falta cuenta). Versiones exactas en `entorno.txt`.

## Archivos

- `corpus/`: los 36 PDF y `referencia.json` con el texto y las filas exactas de cada uno.
- `salidas/<parser>/`: texto extraído por cada parser (primera repetición medida).
- `resultados/procesos.csv`: por parser y repetición, tiempo de importación, tiempo total del corpus y pico de memoria (RSS máxima del proceso).
- `resultados/tiempos.csv`: tiempo de cada documento en cada repetición.
- `resultados/determinismo.json`: si la salida fue idéntica (SHA-256) en las 5 repeticiones.
- `resultados/calidad_por_documento.csv`: métricas de calidad de cada parser en cada PDF.
- `resultados/pymupdf_aislado.csv`: la misma medida de PyMuPDF en un entorno donde solo se pidió instalar PyMuPDF (comprueba que su memoria no se debe a compartir entorno).
- `resultados/resumen.json`: medias por tipo de documento y mediana, cuartiles y desviación de tiempo y memoria.

## Licencias de terceros

Las librerías se instalan desde PyPI y no se incluyen aquí: pypdf (BSD), pdfplumber (MIT), MarkItDown (MIT), Docling (MIT), ReportLab (BSD) y rapidfuzz (MIT); PyMuPDF se distribuye con licencia AGPL 3.0 o comercial de Artifex, y PyMuPDF4LLM y pymupdf-layout dependen de él (consulta sus condiciones en PyPI). Docling descarga los modelos `docling-project/docling-layout-heron` y `docling-project/docling-models` de Hugging Face, cada uno con su propia licencia: consúltala en su ficha antes de reutilizarlos.
