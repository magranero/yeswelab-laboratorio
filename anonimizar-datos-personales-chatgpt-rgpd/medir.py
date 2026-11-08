"""Mide qué datos personales se escapan con cada detector local y cuánto tarda.

    HF_HOME=./cache/hf .venv/bin/python medir.py

Salida en resultados/ (sin texto de los documentos, solo posiciones y métricas):
- por_entidad.csv: cobertura de cada dato personal por cada detector.
- por_documento.csv: caracteres marcados que no eran datos personales.
- tiempos.csv: segundos para procesar el corpus entero, por repetición.
- carga.csv: segundos para cargar cada detector.
"""

import csv
import glob
import os
import re
import time

import torch

from corpus import generar

REPETICIONES = 5
AQUI = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(AQUI, "resultados")
HF = os.environ.get("HF_HOME", os.path.join(AQUI, "cache", "hf"))
REV = {
    "openai/privacy-filter": "7ffa9a043d54d1be65afb281eddf0ffbe629385b",
    "urchade/gliner_multi_pii-v1": "1fcf13e85f4eef5394e1fcd406cf2ca9ea82351d",
    "spacy/es_core_news_lg": "b2fdfe5a44949fb000827919be03237c078a0e87",
}


def snapshot(repo: str) -> str:
    from huggingface_hub import snapshot_download
    return snapshot_download(repo, revision=REV[repo], ignore_patterns=["onnx/*", "*.whl"])


# ---------------------------------------------------------------------------------------------
# 1. Expresiones regulares: lo que se programa en una tarde (sin nombres ni direcciones).
# ---------------------------------------------------------------------------------------------
REGEX = [
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    re.compile(r"\bES\d{2}(?:\s?\d{4}){5}\b", re.I),
    re.compile(r"\b[XYZ]\d{7}[A-Z]\b", re.I),
    re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}[-\s]?[A-Z]\b", re.I),
    re.compile(r"(?:\+34\s?)?\b[6789]\d{2}[\s-]?\d{2,3}[\s-]?\d{2,3}[\s-]?\d{0,3}\b"),
]


def detector_regex():
    def f(texto):
        return [(m.start(), m.end()) for p in REGEX for m in p.finditer(texto)]
    return f


# ---------------------------------------------------------------------------------------------
# 2 y 3. Presidio con spaCy es_core_news_lg: tal cual y con el reconocedor de teléfonos de España.
# ---------------------------------------------------------------------------------------------
def detector_presidio(ajustado: bool):
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_analyzer.predefined_recognizers import PhoneRecognizer

    nlp = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "es", "model_name": snapshot("spacy/es_core_news_lg")}],
    }).create_engine()
    motor = AnalyzerEngine(nlp_engine=nlp, supported_languages=["es"])
    if ajustado:
        motor.registry.remove_recognizer("PhoneRecognizer", language="es")
        motor.registry.add_recognizer(PhoneRecognizer(supported_language="es", supported_regions=["ES"]))

    def f(texto):
        return [(r.start, r.end) for r in motor.analyze(texto, language="es")]
    return f


# ---------------------------------------------------------------------------------------------
# 4. GLiNER multi PII v1 (umbral 0,5 por defecto).
# ---------------------------------------------------------------------------------------------
ETIQUETAS_GLINER = ["person", "email", "phone number", "address", "national id number", "iban"]


def detector_gliner():
    from gliner import GLiNER
    modelo = GLiNER.from_pretrained(snapshot("urchade/gliner_multi_pii-v1"))
    modelo.eval()

    def f(texto):
        return [(e["start"], e["end"]) for e in modelo.predict_entities(texto, ETIQUETAS_GLINER, threshold=0.5)]
    return f


# ---------------------------------------------------------------------------------------------
# 5. OpenAI Privacy Filter: clase por token (argmax, como en su ficha) y unión de tokens contiguos.
# ---------------------------------------------------------------------------------------------
def detector_privacy_filter(dispositivo: str):
    from transformers import AutoModelForTokenClassification, AutoTokenizer
    ruta = snapshot("openai/privacy-filter")
    tok = AutoTokenizer.from_pretrained(ruta)
    modelo = AutoModelForTokenClassification.from_pretrained(ruta, dtype=torch.float32).to(dispositivo).eval()
    id2label = modelo.config.id2label

    def f(texto):
        enc = tok(texto, return_tensors="pt", return_offsets_mapping=True)
        offsets = enc.pop("offset_mapping")[0].tolist()
        with torch.no_grad():
            pred = modelo(**{k: v.to(dispositivo) for k, v in enc.items()}).logits.argmax(-1)[0].tolist()
        spans, actual = [], None
        for (a, b), p in zip(offsets, pred):
            etiqueta = id2label[p]
            if etiqueta == "O" or a == b:
                actual = None
                continue
            cat = etiqueta.split("-", 1)[1]
            if actual and actual[2] == cat and not etiqueta.startswith(("B-", "S-")):
                actual[1] = b
            else:
                actual = [a, b, cat]
                spans.append(actual)
        return [(a, b) for a, b, _ in spans]
    return f


# ---------------------------------------------------------------------------------------------
def cobertura(texto: str, inicio: int, fin: int, marcados: set[int]) -> float:
    """Fracción de letras y cifras del dato que quedan tapadas."""
    pos = [i for i in range(inicio, fin) if texto[i].isalnum()]
    return sum(1 for i in pos if i in marcados) / len(pos)


def marcar(spans) -> set[int]:
    s = set()
    for a, b in spans:
        s.update(range(a, b))
    return s


def main():
    os.makedirs(RES, exist_ok=True)
    docs = generar()
    # En CPU con fp32 fue más rápido que en la GPU (MPS) en una prueba previa con 20 documentos.
    dispositivo = "cpu"

    fabricas = {
        "regex": detector_regex,
        "presidio_defecto": lambda: detector_presidio(False),
        "presidio_telefono_es": lambda: detector_presidio(True),
        "gliner_multi_pii": detector_gliner,
        "openai_privacy_filter": lambda: detector_privacy_filter(dispositivo),
    }
    detectores, carga = {}, []
    for nombre, fab in fabricas.items():
        t0 = time.perf_counter()
        detectores[nombre] = fab()
        detectores[nombre](docs[0]["texto"])  # calentamiento
        carga.append({"detector": nombre, "segundos_carga": time.perf_counter() - t0})
        print("cargado", nombre, carga[-1]["segundos_carga"], flush=True)
    filas_ent, filas_doc, tiempos, salidas = [], [], [], {}
    for nombre, det in detectores.items():
        salida_previa = None
        for rep in range(1, REPETICIONES + 1):
            t0 = time.perf_counter()
            salida = [det(d["texto"]) for d in docs]
            seg = time.perf_counter() - t0
            tiempos.append({"detector": nombre, "repeticion": rep, "segundos_total": seg,
                            "ms_por_documento": seg * 1000 / len(docs), "documentos": len(docs)})
            print(nombre, rep, seg, flush=True)
            if salida_previa is not None and [sorted(s) for s in salida] != [sorted(s) for s in salida_previa]:
                print("AVISO: salida distinta entre repeticiones en", nombre)
            salida_previa = salida
        salidas[nombre] = salida

    # Combinaciones: unión de lo que marcan dos detectores (sin tiempo propio: es la suma de ambos).
    salidas["regex+openai_privacy_filter"] = [a + b for a, b in zip(salidas["regex"], salidas["openai_privacy_filter"])]
    salidas["regex+presidio_telefono_es"] = [a + b for a, b in zip(salidas["regex"], salidas["presidio_telefono_es"])]
    salidas["regex+gliner_multi_pii"] = [a + b for a, b in zip(salidas["regex"], salidas["gliner_multi_pii"])]

    for nombre, salida in salidas.items():
        for d, spans in zip(docs, salida):
            m = marcar(spans)
            oro = set()
            for a, b, tipo, formato in d["entidades"]:
                oro.update(range(a, b))
                filas_ent.append({"detector": nombre, "doc": d["id"], "tipo_doc": d["tipo"], "entidad": tipo,
                                  "formato": formato, "cobertura": cobertura(d["texto"], a, b, m)})
            alnum_marcados = [i for i in m if i < len(d["texto"]) and d["texto"][i].isalnum()]
            de_mas = [i for i in alnum_marcados if i not in oro]
            filas_doc.append({"detector": nombre, "doc": d["id"], "tipo_doc": d["tipo"],
                              "caracteres_marcados": len(alnum_marcados), "caracteres_de_mas": len(de_mas),
                              "caracteres_no_personales": sum(1 for i, c in enumerate(d["texto"]) if c.isalnum() and i not in oro)})

    for nombre, filas in (("por_entidad.csv", filas_ent), ("por_documento.csv", filas_doc),
                          ("tiempos.csv", tiempos), ("carga.csv", carga)):
        with open(os.path.join(RES, nombre), "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(filas[0]))
            w.writeheader()
            w.writerows(filas)
    print("dispositivo", dispositivo)


if __name__ == "__main__":
    main()
