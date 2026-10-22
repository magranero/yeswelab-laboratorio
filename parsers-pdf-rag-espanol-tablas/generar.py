"""Genera el corpus de PDFs en español con su verdad de referencia.

Tres tipos de documento, 12 de cada uno (semilla fija):
- texto: informe a una columna, párrafos justificados;
- columnas: el mismo tipo de texto maquetado a dos columnas;
- factura: tabla de conceptos con importes en formato español (1.234,56 €),
  la mitad con conceptos largos que ocupan varias líneas dentro de la celda.

Todos llevan pie de página («Página N»), que no forma parte de la referencia.
Salida: corpus/*.pdf y corpus/referencia.json.
"""

import json
import os
import random

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(AQUI, "corpus")
POR_TIPO = 12

SUJETOS = ["La dirección de operaciones", "El equipo de atención al cliente", "La auditoría interna",
           "El área de compras", "La oficina técnica", "El departamento jurídico", "La compañía",
           "El comité de seguridad", "La filial de Bogotá", "La sede de Valencia", "El almacén de Monterrey"]
VERBOS = ["revisó", "aprobó", "rechazó", "documentó", "automatizó", "migró", "auditó", "renegoció", "señaló"]
OBJETOS = ["el protocolo de reclamaciones", "la integración con el ERP", "el contrato de mantenimiento",
           "la política de contraseñas", "el flujo de facturación electrónica", "el inventario de licencias",
           "la conciliación bancaria", "el cuadro de mando de logística", "el plan de continuidad"]
COLETILLAS = ["tras la reunión del día {d} de {m}", "con un coste de {i} €", "según el informe nº {n}",
              "porque el año pasado falló en {p} % de los casos", "a petición de la señora Muñoz",
              "sin cambios en la jornada de mañana", "después de que el piloto ahorrara {h} horas al mes"]
PREGUNTAS = ["¿Quién valida los cambios?", "¿Cuánto cuesta mantenerlo?", "¿Qué ocurre si falla el proveedor?",
             "¿Está cubierto por la garantía?"]
EXCLAMACIONES = ["¡Atención al plazo!", "¡Revisión obligatoria!", "¡Cambio aprobado!"]
CITAS = ["«sin excepciones»", "«antes del cierre»", "«en pruebas»", "«con prioridad alta»"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]
CONCEPTOS_CORTOS = ["Licencia anual", "Soporte técnico", "Formación in situ", "Migración de datos",
                    "Auditoría de seguridad", "Consultoría", "Mantenimiento", "Diseño de flujos",
                    "Integración API", "Pruebas de carga", "Informe de riesgos", "Alojamiento"]
CONCEPTOS_LARGOS = ["Licencia anual del módulo de facturación electrónica con firma cualificada",
                    "Soporte técnico prioritario de lunes a viernes, incluidas las guardias de cierre",
                    "Migración de datos históricos del ERP antiguo con validación de saldos",
                    "Auditoría de seguridad de la red de almacenes y revisión de contraseñas",
                    "Diseño de flujos de aprobación de pedidos para compras y logística",
                    "Formación in situ para el equipo de atención al cliente en Guadalajara"]


def importe(x: float) -> str:
    entero, dec = f"{x:,.2f}".split(".")
    return entero.replace(",", ".") + "," + dec + " €"


def frase(r: random.Random) -> str:
    c = r.choice(COLETILLAS).format(d=r.randint(1, 28), m=r.choice(MESES), i=importe(r.uniform(150, 98000)),
                                    n=r.randint(10, 999), p=r.randint(3, 40), h=r.randint(5, 120))
    s = f"{r.choice(SUJETOS)} {r.choice(VERBOS)} {r.choice(OBJETOS)} {c}"
    if r.random() < 0.25:
        s += f" {r.choice(CITAS)}"
    return s + "."


def parrafo(r: random.Random) -> str:
    partes = [frase(r) for _ in range(r.randint(3, 5))]
    if r.random() < 0.4:
        partes.insert(r.randint(0, len(partes)), r.choice(PREGUNTAS))
    if r.random() < 0.2:
        partes.append(r.choice(EXCLAMACIONES))
    return " ".join(partes)


def pie(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(A4[0] / 2, 1.2 * cm, f"Página {doc.page}")
    canvas.restoreState()


ESTILO = ParagraphStyle("cuerpo", fontName="Helvetica", fontSize=10, leading=13, alignment=TA_JUSTIFY,
                        spaceAfter=8)
TITULO = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=15, leading=19, spaceAfter=12)
CELDA = ParagraphStyle("celda", fontName="Helvetica", fontSize=9, leading=11)


def doc_texto(ruta: str, r: random.Random, columnas: bool) -> dict:
    area = r.choice(["operaciones", "compras", "logística", "seguridad", "facturación"])
    titulo = f"Informe trimestral de {area} nº {r.randint(100, 999)}"
    parrafos = [parrafo(r) for _ in range(r.randint(12, 16))]
    historia = [Paragraph(titulo, TITULO)] + [Paragraph(p, ESTILO) for p in parrafos]
    if columnas:
        d = BaseDocTemplate(ruta, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm,
                            bottomMargin=2 * cm)
        ancho = (d.width - 1 * cm) / 2
        marcos = [Frame(d.leftMargin, d.bottomMargin, ancho, d.height, id="izq"),
                  Frame(d.leftMargin + ancho + 1 * cm, d.bottomMargin, ancho, d.height, id="der")]
        d.addPageTemplates([PageTemplate(id="dos", frames=marcos, onPage=pie)])
        d.build(historia)
    else:
        d = SimpleDocTemplate(ruta, pagesize=A4, leftMargin=2.5 * cm, rightMargin=2.5 * cm,
                              topMargin=2 * cm, bottomMargin=2 * cm)
        d.build(historia, onFirstPage=pie, onLaterPages=pie)
    return {"tipo": "columnas" if columnas else "texto", "titulo": titulo, "parrafos": parrafos, "filas": []}


def doc_factura(ruta: str, r: random.Random, largos: bool) -> dict:
    numero = f"F-2026-{r.randint(1000, 9999)}"
    titulo = f"Factura {numero}"
    intro = (f"Cliente: Distribuciones Peña y Núñez, S. L. Fecha de emisión: {r.randint(1, 28)} de "
             f"{r.choice(MESES)} de 2026. Forma de pago: transferencia a 30 días.")
    filas = []
    for i in range(r.randint(8, 14)):
        concepto = r.choice(CONCEPTOS_LARGOS if largos and i % 2 == 0 else CONCEPTOS_CORTOS)
        cantidad = r.randint(1, 40)
        precio = round(r.uniform(12, 4800), 2)
        filas.append([concepto, str(cantidad), importe(precio), "21 %", importe(cantidad * precio)])
    base = sum(float(f[4][:-2].replace(".", "").replace(",", ".")) for f in filas)
    cabecera = ["Concepto", "Cantidad", "Precio unitario", "IVA", "Total"]
    datos = [cabecera] + [[Paragraph(f[0], CELDA)] + f[1:] for f in filas]
    t = Table(datos, colWidths=[7.2 * cm, 1.8 * cm, 3 * cm, 1.4 * cm, 3 * cm], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                           ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                           ("FONTSIZE", (0, 0), (-1, -1), 9),
                           ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    cierre = (f"Base imponible: {importe(base)}. IVA (21 %): {importe(base * 0.21)}. "
              f"Total a pagar: {importe(base * 1.21)}.")
    d = SimpleDocTemplate(ruta, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=2 * cm,
                          bottomMargin=2 * cm)
    d.build([Paragraph(titulo, TITULO), Paragraph(intro, ESTILO), Spacer(1, 6), t, Spacer(1, 10),
             Paragraph(cierre, ESTILO)], onFirstPage=pie, onLaterPages=pie)
    return {"tipo": "factura_larga" if largos else "factura", "titulo": titulo, "parrafos": [intro, cierre],
            "cabecera": cabecera, "filas": filas}


def main() -> None:
    os.makedirs(SALIDA, exist_ok=True)
    r = random.Random(20261021)
    referencia = {}
    for i in range(POR_TIPO):
        for tipo in ("texto", "columnas", "factura"):
            nombre = f"{tipo}_{i:02d}.pdf"
            ruta = os.path.join(SALIDA, nombre)
            if tipo == "factura":
                referencia[nombre] = doc_factura(ruta, r, largos=i % 2 == 1)
            else:
                referencia[nombre] = doc_texto(ruta, r, columnas=tipo == "columnas")
    with open(os.path.join(SALIDA, "referencia.json"), "w", encoding="utf-8") as f:
        json.dump(referencia, f, ensure_ascii=False, indent=1)
    print(f"{len(referencia)} PDF generados en corpus/")


if __name__ == "__main__":
    main()
