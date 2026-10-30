# Resumen de la medición

Equipo: Apple M1 Max, 64 GB de memoria unificada. macOS-26.6.2-arm64-arm-64bit-Mach-O. Ollama 0.40.8. Now drawing from 'AC Power'. Fecha: 2026-10-30.

### Como Hermes: 64K de contexto, API compatible con OpenAI

| Modelo | Memoria cargado | En GPU | Lectura (tok/s) | Hasta empezar a responder | Escritura (tok/s) | Herramientas | Respuesta con herramienta | Sin Modelfile |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| qwen3:4b | 12,9 GB | 100 % | 308 | 33,4 s | 28,5 | 5/5 | 8,8 s | 43,5 GB (256K) |
| qwen3:8b | 11,0 GB | 100 % | 212 | 48,6 s | 22,0 | 5/5 | 7,4 s | 11,0 GB (40K) |
| gpt-oss:20b | 13,3 GB | 100 % | 472 | 18,5 s | 36,7 | 5/5 | 1,8 s | 13,7 GB (128K) |
| qwen3:30b-a3b | 25,5 GB | 100 % | 324 | 31,8 s | 30,8 | 5/5 | 4,3 s | 45,4 GB (256K) |
| gemma4:31b | 22,6 GB | 100 % | 61 | 143,0 s | 8,5 | 5/5 | 13,1 s | 19,6 GB (256K) |
| qwen3:4b (CPU, 4 hilos) | 13,1 GB | 0 % | 44 | 233,4 s | 4,0 | 5/5 | 13,6 s | — |
| qwen3:8b (CPU, 4 hilos) | 11,9 GB | 0 % | 33 | 310,9 s | 3,8 | 5/5 | 3,4 s | — |

Prompt de 8702, 8741, 10300, 10306 tokens; medianas de 3 repeticiones; 5 peticiones con herramientas por modelo.

### Como OpenClaw: 32K de contexto, API nativa de Ollama

| Modelo | Memoria cargado | En GPU | Lectura (tok/s) | Hasta empezar a responder | Escritura (tok/s) | Herramientas | Respuesta con herramienta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| qwen3:4b | 7,6 GB | 100 % | 399 | 25,8 s | 36,0 | 5/5 | 6,9 s |
| qwen3:8b | 9,5 GB | 100 % | 261 | 39,5 s | 25,0 | 5/5 | 1,7 s |
| gpt-oss:20b | 12,9 GB | 100 % | 541 | 16,2 s | 43,5 | 5/5 | 1,3 s |
| qwen3:30b-a3b | 21,9 GB | 100 % | 393 | 26,2 s | 37,9 | 5/5 | 3,3 s |
| gemma4:31b | 19,4 GB | 100 % | 64 | 136,6 s | 8,3 | 5/5 | 5,2 s |

Prompt de 8702, 8741, 10300, 10306 tokens; medianas de 3 repeticiones; 5 peticiones con herramientas por modelo.
