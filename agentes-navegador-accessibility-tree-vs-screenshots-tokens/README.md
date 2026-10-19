# Agentes de navegador: Accessibility Tree vs capturas de pantalla

Cuántos tokens cuesta que un agente «vea» una página en cada paso de una tarea de 10 pasos, según le pases:

1. una **captura de pantalla** (1280×800 a 1x y a 2x);
2. el **Accessibility Tree completo** (todos los nodos, incluido el texto);
3. el **Accessibility Tree filtrado**: solo elementos interactivos y encabezados, con referencias `[ref=eN]`;
4. el **Accessibility Tree filtrado y limitado a lo visible en pantalla**.

También mide el tiempo de captura de cada observación y si el clic por referencia acierta (el punto de clic cae en el elemento o en su etiqueta).

## Cómo repetirlo

Necesitas [uv](https://docs.astral.sh/uv/) y la web compilada (o cualquier carpeta con HTML estático) en `--sitio`.

```bash
uv run --with playwright --with tiktoken python -m playwright install chromium
uv run --with playwright --with tiktoken python medir.py --sitio /ruta/a/la/web/compilada --repeticiones 5
```

La tarea está definida en `TAREA` dentro de `medir.py` (pasos sobre yeswelab.com: portada, experimentos, búsqueda, artículo, guías, formulario). Para otra web, cambia esos pasos.

## Cómo se cuentan los tokens

- **Imágenes, Claude (Anthropic):** tokens ≈ ancho × alto / 750, tras reducir la imagen a un máximo de 1568 px de lado largo y unos 1,15 megapíxeles. Fórmula de la documentación de visión de Anthropic.
- **Imágenes, GPT-4o (OpenAI), detalle alto:** la imagen se encaja en 2048×2048, el lado corto se reduce a 768 px y se cobran 170 tokens por tesela de 512×512 más 85 fijos. Fórmula de la documentación de visión de OpenAI.
- **Texto:** tokenizador `o200k_base` de tiktoken (GPT-4o/GPT-5). El tokenizador de Claude no es público; es una aproximación.

Las fórmulas de imagen son las publicadas por cada proveedor en el momento de la medición y pueden cambiar; los modelos más recientes pueden contar imágenes de otra forma.

## Resultados

- `resultados/pasos.csv`: cada paso de cada repetición, con tokens de las cuatro observaciones, tiempos y acierto del clic.
- `resultados/resumen.json`: totales por tarea (solo la última observación y con historial completo), reducciones, medianas y dispersión.

## Licencias de terceros

Usa Playwright (Apache 2.0), el Chromium que descarga Playwright y tiktoken (MIT). La web medida es yeswelab.com, servida en local.
