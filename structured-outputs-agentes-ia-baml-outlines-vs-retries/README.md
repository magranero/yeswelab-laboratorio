# Structured outputs: reparar en local o reintentar

1000 salidas JSON sintéticas de un agente de extracción de pedidos, con los seis fallos sintácticos más habituales de los LLM (coma final, bloque markdown, comillas simples, respuesta cortada, claves sin comillas y comentarios). Se mide qué acepta `json.loads`, qué repara `json_repair` (parser tolerante) y si queda idéntico al original, cuánto tarda la reparación (5 repeticiones) y cuántos tokens cuesta un reintento (instrucciones + esquema + salida rota + error, con `o200k_base`).

```bash
uv run --with json-repair --with tiktoken python medir.py
```

Resultados en `resultados/resumen.json` y `resultados/tiempos_ms.csv`. No se mide BAML ni Outlines: ver el artículo.

## Licencias de terceros

json-repair (MIT) y tiktoken (MIT). Los datos son sintéticos, generados con semilla fija.
