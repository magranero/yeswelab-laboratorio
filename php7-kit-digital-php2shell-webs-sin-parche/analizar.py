"""Cifras derivadas de resultados/cve_desde_fin_php74.json (sin volver a consultar NVD).

    python3 analizar.py
"""

import json

d = json.load(open("resultados/cve_desde_fin_php74.json"))
nvd = [x for x in d["nvd"] if x.get("en_nvd")]
criticos = sorted((x["cve"], x["cvss"]) for x in nvd if (x.get("cvss") or 0) >= 9)
altos = [x for x in nvd if 7 <= (x.get("cvss") or 0) < 9]
salida = {
    "cve_criticos_cvss_9_o_mas": len(criticos),
    "cve_altos_cvss_7_a_9": len(altos),
    "lista_criticos": criticos,
    "cve_que_nvd_marca_en_php7": [x["cve"] for x in nvd if x.get("nvd_incluye_php7")],
}
json.dump(salida, open("resultados/criticidad.json", "w"), indent=1)
print(json.dumps(salida, indent=1))
