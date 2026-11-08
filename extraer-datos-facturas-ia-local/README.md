# Extraer datos de facturas españolas con IA local: reglas frente a 4 modelos pequeños

Lee 27 facturas españolas en PDF y extrae 9 campos (número, fecha, NIF del emisor, NIF del cliente, base imponible, tipo de IVA, cuota de IVA, retención de IRPF y total) con:

| Detector | Qué es |
| --- | --- |
| `reglas` | Expresiones regulares escritas mirando solo las plantillas A y B |
| `qwen3-4b-instruct-2507` | Qwen3 4B Instruct 2507, 4 bits, MLX |
| `gemma-3-4b-it` | Gemma 3 4B IT, 4 bits, MLX |
| `llama-3.2-3b-instruct` | Llama 3.2 3B Instruct, 4 bits, MLX |
| `qwen3-1.7b` | Qwen3 1.7B, 4 bits, MLX, sin modo de razonamiento |

Todos reciben el mismo texto, extraído del PDF con PyMuPDF. Los modelos reciben la misma instrucción (ver `INSTRUCCIONES` en `medir.py`) y responden en JSON, con decodificación voraz (temperatura 0).

## Corpus

`corpus.py` genera las facturas con fpdf2 y semilla fija, así que no hay datos de terceros ni de personas reales: nombres y direcciones de Faker, NIF y CIF aleatorios con su letra o dígito de control válidos, IBAN inventados. Tres plantillas, 9 facturas de cada una:

- **A:** factura clásica con «Nº de factura», «Fecha de factura», «Base imponible», «IVA 21 %», «TOTAL FACTURA».
- **B:** etiquetas abreviadas: «Subtotal», «I.V.A. (21%)», «Retención I.R.P.F. (15%)», «TOTAL A PAGAR».
- **C:** el cliente aparece antes que el proveedor y las etiquetas cambian («Importe neto», «Cuota de IVA al 21%», «Serie y número», «Emitida el»). Las reglas no se escribieron para ella: simula la factura de un proveedor nuevo.

Trampas a propósito: fecha de vencimiento y número de pedido junto a la fecha y el número de factura; NIF con guiones o puntos; fechas en cuatro formatos; importes con «€» delante o detrás, con «EUR» y con o sin puntos de miles; tipos de IVA del 21, 10 y 4 %; retención de IRPF del 15 % en parte de las facturas de autónomos (el total es base + IVA − IRPF).

## Métricas

- `campos_correctos`: % de campos que coinciden exactamente con la referencia, tras normalizar formato (importes a céntimos, fechas a AAAA-MM-DD, NIF sin guiones ni puntos).
- `facturas_perfectas`: % de facturas con los 9 campos bien.
- `json_valido`: % de respuestas que se pueden leer como JSON.
- `cuadra`: si los importes extraídos cumplen base + IVA − IRPF = total y IVA = base × tipo (±1 céntimo). Es la comprobación automática que haría un programa antes de dar la factura por buena. `errores_detectados_por_cuadre_n` cuenta las facturas con algún error que no cuadran (se mandarían a revisión) y `errores_que_cuadran_n`, las que tienen algún error y cuadran igualmente (pasarían sin revisión).
- Tiempo por factura (desde que se envía la instrucción hasta el último token), tokens por segundo y pico de memoria de MLX.

Cada detector hace 5 pasadas completas por las 27 facturas. `resumen.json` guarda las medianas, mínimos, máximos y percentiles sin redondear.

## Cómo repetirlo

```bash
uv venv .venv -p 3.12
uv pip install -p .venv/bin/python mlx-lm pymupdf fpdf2 faker
.venv/bin/python corpus.py datos 27
.venv/bin/python medir.py datos resultados 5
.venv/bin/python resumir.py resultados
```

Necesita un Mac con Apple Silicon (MLX). La primera vez descarga los cuatro modelos de Hugging Face (unos 9 GB, sin cuenta). La medición tarda unos 25 minutos en un M1 Max. Versiones y revisiones exactas en `entorno.txt`.

## Archivos

- `resultados/extracciones.csv`: por detector, repetición, factura y campo: valor esperado, valor obtenido, si es correcto, si el JSON era válido y si los importes cuadran.
- `resultados/tiempos.csv`: segundos, tokens de entrada y salida, tokens por segundo y pico de memoria de cada factura.
- `resultados/carga.csv`: segundos de carga de cada modelo (ya descargado).
- `resultados/resumen.json`: resumen por detector, por campo y por plantilla.

## Fuentes y licencias

- [mlx-community/Qwen3-4B-Instruct-2507-4bit](https://huggingface.co/mlx-community/Qwen3-4B-Instruct-2507-4bit) y [mlx-community/Qwen3-1.7B-4bit](https://huggingface.co/mlx-community/Qwen3-1.7B-4bit): Apache 2.0 (modelos originales de Qwen).
- [mlx-community/gemma-3-4b-it-4bit](https://huggingface.co/mlx-community/gemma-3-4b-it-4bit): [Gemma Terms of Use](https://ai.google.dev/gemma/terms).
- [mlx-community/Llama-3.2-3B-Instruct-4bit](https://huggingface.co/mlx-community/Llama-3.2-3B-Instruct-4bit): [Llama 3.2 Community License](https://www.llama.com/llama3_2/license/).
- Los modelos se descargan; no se redistribuyen.
- [MLX](https://github.com/ml-explore/mlx) y [mlx-lm](https://github.com/ml-explore/mlx-lm): MIT. [PyMuPDF](https://github.com/pymupdf/PyMuPDF): AGPL-3.0. [fpdf2](https://github.com/py-pdf/fpdf2): LGPL-3.0. [Faker](https://github.com/joke2k/faker): MIT.

Código de este experimento: MIT. Resultados: CC BY 4.0.
