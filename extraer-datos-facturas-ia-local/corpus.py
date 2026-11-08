"""Genera facturas españolas sintéticas en PDF con sus datos de referencia.

Tres plantillas (A, B y C) con formatos de fecha, NIF e importes distintos.
Todos los datos son inventados: nombres y direcciones de Faker y NIF/CIF
aleatorios con dígito o letra de control válidos. Semilla fija.

Uso: python corpus.py [carpeta_salida] [n_facturas]
"""
import json
import random
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from faker import Faker
from fpdf import FPDF

SEMILLA = 20261108
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"
CONCEPTOS = [
    "Asesoría fiscal mensual", "Mantenimiento web", "Diseño de folleto",
    "Licencia de software (1 año)", "Revisión de caldera", "Traducción de contrato",
    "Reparación de ordenador", "Sesión de fotografía", "Material de oficina",
    "Formación en Excel (4 h)", "Limpieza de oficina", "Transporte de mercancía",
    "Cartuchos de tinta", "Consultoría de marketing", "Hosting anual",
    "Instalación eléctrica", "Auditoría de protección de datos", "Gestión de nóminas",
]

C2 = Decimal("0.01")


def eur(x: Decimal) -> Decimal:
    return x.quantize(C2, rounding=ROUND_HALF_UP)


def nif_persona(r: random.Random) -> str:
    n = r.randint(10_000_000, 99_999_999)
    return f"{n}{LETRAS_DNI[n % 23]}"


def cif_sociedad(r: random.Random) -> str:
    letra = r.choice("AB")
    d = [r.randint(0, 9) for _ in range(7)]
    pares = d[1] + d[3] + d[5]
    impares = sum(sum(divmod(2 * d[i], 10)) for i in (0, 2, 4, 6))
    control = (10 - (pares + impares) % 10) % 10
    return letra + "".join(map(str, d)) + str(control)


def formato_nif(nif: str, r: random.Random) -> str:
    """Escribe el NIF como suele aparecer: seguido, con guion o con puntos."""
    estilo = r.choice(["seguido", "guion", "puntos"])
    if estilo == "seguido":
        return nif
    if nif[0].isalpha():  # CIF: B12345674
        return f"{nif[0]}-{nif[1:]}" if estilo == "guion" else f"{nif[0]}-{nif[1:3]}.{nif[3:6]}.{nif[6:]}"
    return f"{nif[:8]}-{nif[8]}" if estilo == "guion" else f"{nif[:2]}.{nif[2:5]}.{nif[5:8]}-{nif[8]}"


def importe_es(x: Decimal, estilo: str) -> str:
    entero, dec = f"{x:.2f}".split(".")
    miles = f"{int(entero):,}".replace(",", ".")
    if estilo == "euro_detras":
        return f"{miles},{dec} €"
    if estilo == "eur_sin_miles":
        return f"{entero},{dec} EUR"
    return f"€ {miles},{dec}"


def fecha_txt(f, estilo: str) -> str:
    if estilo == "barras":
        return f.strftime("%d/%m/%Y")
    if estilo == "guiones":
        return f.strftime("%d-%m-%Y")
    if estilo == "larga":
        return f"{f.day} de {MESES[f.month - 1]} de {f.year}"
    return f.isoformat()


def factura(i: int, r: random.Random, fk: Faker) -> dict:
    plantilla = "ABC"[i % 3]
    autonomo = r.random() < 0.45
    emisor = fk.name() if autonomo else fk.company()
    nif_e = nif_persona(r) if autonomo else cif_sociedad(r)
    cliente = fk.company()
    nif_c = cif_sociedad(r) if r.random() < 0.8 else nif_persona(r)
    tipo = r.choice([21, 21, 21, 10, 4])
    lineas = []
    for _ in range(r.randint(1, 6)):
        cant = r.randint(1, 12)
        precio = eur(Decimal(r.randint(500, 90000)) / 100)
        lineas.append((r.choice(CONCEPTOS), cant, precio, eur(cant * precio)))
    base = sum((l[3] for l in lineas), Decimal("0"))
    cuota = eur(base * tipo / 100)
    retencion = eur(base * Decimal("0.15")) if autonomo and r.random() < 0.7 else Decimal("0.00")
    total = base + cuota - retencion
    fecha = fk.date_between_dates(date_start=__import__("datetime").date(2026, 1, 1),
                                  date_end=__import__("datetime").date(2026, 10, 31))
    venc = fecha + __import__("datetime").timedelta(days=r.choice([15, 30, 60]))
    serie = r.choice(["F{y}-{n:04d}", "A/{y}/{n:03d}", "{yy}-{n:04d}", "FAC{y}{n:05d}"])
    numero = serie.format(y=fecha.year, yy=str(fecha.year)[2:], n=r.randint(1, 999))
    pedido = f"PED-{r.randint(1000, 9999)}"
    return {
        "id": f"factura_{i:03d}", "plantilla": plantilla,
        "verdad": {
            "numero": numero, "fecha": fecha.isoformat(),
            "nif_emisor": nif_e, "nif_cliente": nif_c,
            "base_imponible": str(base), "tipo_iva": tipo, "cuota_iva": str(cuota),
            "retencion_irpf": str(retencion), "total": str(total),
        },
        "render": {
            "emisor": emisor, "dir_emisor": fk.address().replace("\n", ", "),
            "tel_emisor": fk.phone_number(), "cliente": cliente,
            "dir_cliente": fk.address().replace("\n", ", "),
            "nif_e": formato_nif(nif_e, r), "nif_c": formato_nif(nif_c, r),
            "fecha": fecha_txt(fecha, r.choice(["barras", "guiones", "larga", "iso"])),
            "venc": fecha_txt(venc, "barras"), "pedido": pedido,
            "importe": r.choice(["euro_detras", "eur_sin_miles", "euro_delante"]),
            "iban": f"ES{r.randint(10, 99)} {r.randint(1000, 9999)} {r.randint(1000, 9999)} "
                    f"{r.randint(10, 99)}{r.randint(10, 99)} {r.randint(100000, 999999)}{r.randint(1000, 9999)}",
            "lineas": [(c, n, str(p), str(t)) for c, n, p, t in lineas],
        },
    }


def pdf(f: dict, ruta: Path) -> None:
    v, d = f["verdad"], f["render"]
    imp = lambda x: importe_es(Decimal(x), d["importe"])  # noqa: E731
    p = FPDF()
    p.add_page()
    p.core_fonts_encoding = "windows-1252"  # para el símbolo €
    p.set_font("Helvetica", size=10)

    def linea(txt, h=6, ln=True):
        p.cell(0, h, txt, new_x="LMARGIN", new_y="NEXT") if ln else p.cell(0, h, txt)

    pl = f["plantilla"]
    if pl == "A":
        p.set_font_size(14); linea(d["emisor"], 8); p.set_font_size(10)
        linea(d["dir_emisor"]); linea(f"NIF: {d['nif_e']}   Tel.: {d['tel_emisor']}")
        p.ln(4); p.set_font_size(16); linea("FACTURA", 9); p.set_font_size(10)
        linea(f"Nº de factura: {v['numero']}"); linea(f"Fecha de factura: {d['fecha']}")
        linea(f"Fecha de vencimiento: {d['venc']}"); linea(f"Su pedido: {d['pedido']}")
        p.ln(3); linea("Cliente:"); linea(d["cliente"]); linea(d["dir_cliente"])
        linea(f"NIF/CIF: {d['nif_c']}")
    elif pl == "B":
        linea(f"Factura {v['numero']}", 8); linea(f"Fecha: {d['fecha']}")
        p.ln(2); linea(f"De: {d['emisor']} - N.I.F. {d['nif_e']}"); linea(d["dir_emisor"])
        linea(f"Para: {d['cliente']} - N.I.F. {d['nif_c']}"); linea(d["dir_cliente"])
        linea(f"Vence el {d['venc']} · Ref. pedido {d['pedido']}")
    else:  # C: datos del cliente primero y etiquetas distintas
        p.set_font_size(12); linea("DATOS DEL DESTINATARIO", 7); p.set_font_size(10)
        linea(f"{d['cliente']} · CIF {d['nif_c']}"); linea(d["dir_cliente"])
        p.ln(3); p.set_font_size(12); linea("PROVEEDOR", 7); p.set_font_size(10)
        linea(d["emisor"]); linea(f"Identificación fiscal: {d['nif_e']}"); linea(d["dir_emisor"])
        p.ln(3); linea(f"Documento: factura ordinaria   Serie y número: {v['numero']}")
        linea(f"Emitida el {d['fecha']}   Pago antes del {d['venc']}")
    p.ln(4)
    p.cell(95, 6, "Concepto"); p.cell(20, 6, "Uds.", align="R")
    p.cell(35, 6, "Precio", align="R"); p.cell(35, 6, "Importe", align="R", new_x="LMARGIN", new_y="NEXT")
    for c, n, pr, t in d["lineas"]:
        p.cell(95, 6, c); p.cell(20, 6, str(n), align="R")
        p.cell(35, 6, imp(pr), align="R"); p.cell(35, 6, imp(t), align="R", new_x="LMARGIN", new_y="NEXT")
    p.ln(4)
    ret = Decimal(v["retencion_irpf"])
    etiquetas = {
        "A": ("Base imponible", f"IVA {v['tipo_iva']} %", "Retención IRPF 15 %", "TOTAL FACTURA"),
        "B": ("Subtotal", f"I.V.A. ({v['tipo_iva']}%)", "Retención I.R.P.F. (15%)", "TOTAL A PAGAR"),
        "C": ("Importe neto", f"Cuota de IVA al {v['tipo_iva']}%", "IRPF (-15%)", "Importe total"),
    }[pl]
    filas = [(etiquetas[0], v["base_imponible"]), (etiquetas[1], v["cuota_iva"])]
    if ret > 0:
        filas.append((etiquetas[2], "-" + v["retencion_irpf"] if pl != "C" else v["retencion_irpf"]))
    filas.append((etiquetas[3], v["total"]))
    for et, x in filas:
        neg = x.startswith("-")
        p.cell(150, 6, et, align="R")
        p.cell(35, 6, ("-" if neg else "") + imp(x.lstrip("-")), align="R", new_x="LMARGIN", new_y="NEXT")
    p.ln(6)
    linea(f"Forma de pago: transferencia a {d['iban']}")
    p.output(str(ruta))


def main():
    salida = Path(sys.argv[1] if len(sys.argv) > 1 else "datos")
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 27
    salida.mkdir(parents=True, exist_ok=True)
    r = random.Random(SEMILLA)
    fk = Faker("es_ES")
    fk.seed_instance(SEMILLA)
    verdad = []
    for i in range(n):
        f = factura(i, r, fk)
        pdf(f, salida / f"{f['id']}.pdf")
        verdad.append({"id": f["id"], "plantilla": f["plantilla"], **f["verdad"]})
    (salida / "verdad.json").write_text(json.dumps(verdad, ensure_ascii=False, indent=1))
    print(f"{n} facturas en {salida}")


if __name__ == "__main__":
    main()
