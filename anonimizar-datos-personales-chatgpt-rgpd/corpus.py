"""Corpus sintético de documentos de pyme en español con datos personales etiquetados.

Todo es inventado con Faker (es_ES) y una semilla fija: no hay datos de personas reales.
El corpus no se guarda en el repositorio; se regenera igual en cada ejecución.

Cada documento: {"id", "tipo", "texto", "entidades": [(inicio, fin, tipo, formato)]}.
Tipos de entidad: PERSONA, EMAIL, TELEFONO, DNI_NIE, IBAN, DIRECCION.
"""

import random
import re
import unicodedata

from faker import Faker

SEMILLA = 20261107
LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"
N_DOCUMENTOS = 500


def _sin_tildes(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


class Generador:
    def __init__(self, semilla: int):
        self.r = random.Random(semilla)
        self.f = Faker("es_ES")
        self.f.seed_instance(semilla)

    # --- valores con varios formatos reales -------------------------------------------------
    def persona(self, minusculas=False):
        nombre = f"{self.f.first_name()} {self.f.last_name()}"
        if self.r.random() < 0.5:
            nombre += f" {self.f.last_name()}"
        if minusculas:
            return nombre.lower(), "minusculas"
        return nombre, "normal"

    def email(self, nombre: str):
        base = _sin_tildes(nombre.lower()).split()
        usuario = self.r.choice([base[0] + "." + base[1], base[0][0] + base[1], base[0] + str(self.r.randint(1, 99))])
        usuario = re.sub(r"[^a-z0-9.]", "", usuario)
        dominio = self.r.choice(["gmail.com", "hotmail.com", "yahoo.es", "outlook.es", self.f.free_email_domain()])
        return f"{usuario}@{dominio}", "normal"

    def telefono(self):
        movil = self.r.random() < 0.7
        if movil:
            d = self.r.choice("67") + "".join(str(self.r.randint(0, 9)) for _ in range(8))
        else:
            d = self.r.choice(["91", "93", "95", "96", "98"]) + "".join(str(self.r.randint(0, 9)) for _ in range(7))
        formato = self.r.choice(["espacios", "seguido", "prefijo", "guiones"])
        if formato == "espacios":
            t = f"{d[:3]} {d[3:5]} {d[5:7]} {d[7:]}" if movil else f"{d[:2]} {d[2:5]} {d[5:7]} {d[7:]}"
        elif formato == "seguido":
            t = d
        elif formato == "prefijo":
            t = f"+34 {d[:3]} {d[3:6]} {d[6:]}"
        else:
            t = f"{d[:3]}-{d[3:6]}-{d[6:]}"
        return t, formato

    def dni_nie(self):
        if self.r.random() < 0.75:
            n = self.r.randint(0, 99999999)
            v = f"{n:08d}{LETRAS_DNI[n % 23]}"  # 8 cifras + letra de control válida
            formato = self.r.choice(["dni_seguido", "dni_guion", "dni_puntos"])
            if formato == "dni_guion":
                v = f"{v[:8]}-{v[8]}"
            elif formato == "dni_puntos":
                v = f"{v[:2]}.{v[2:5]}.{v[5:8]}-{v[8]}"
            return v, formato
        pre = self.r.choice("XYZ")
        n = self.r.randint(0, 9999999)
        return f"{pre}{n:07d}{LETRAS_DNI[('XYZ'.index(pre) * 10000000 + n) % 23]}", "nie"

    def iban(self):
        bban = "".join(str(self.r.randint(0, 9)) for _ in range(20))
        control = 98 - int(bban + "142800") % 97  # E=14, S=28, «00» provisional (ISO 13616)
        v = f"ES{control:02d}{bban}"  # IBAN español con dígitos de control válidos
        if self.r.random() < 0.5:
            return " ".join(v[i:i + 4] for i in range(0, len(v), 4)), "espacios"
        return v, "seguido"

    def direccion(self):
        return f"{self.f.street_address().strip()}, {self.f.postcode()} {self.f.city()}", "normal"


# Plantillas: casos de pyme. {X} se rellena con una entidad; el resto es texto fijo.
PLANTILLAS = {
    "correo_gestoria": [
        "Hola, soy {PERSONA}. Os adjunto las facturas del trimestre. Para la declaración, mi DNI es {DNI_NIE} "
        "y la domiciliación va a la cuenta {IBAN}. Si necesitáis algo, llamadme al {TELEFONO} o escribidme a {EMAIL}.",
        "Buenos días: os escribe {PERSONA} desde {EMAIL}. He cambiado de banco; a partir de ahora el IBAN es {IBAN}. "
        "Mi NIF sigue siendo {DNI_NIE}. Gracias.",
        "Asunto: alta de autónomo. Nombre: {PERSONA}. Documento: {DNI_NIE}. Domicilio fiscal: {DIRECCION}. "
        "Teléfono de contacto {TELEFONO}.",
    ],
    "ticket_tienda": [
        "Pedido 48213: el cliente {PERSONA} ({EMAIL}) dice que el paquete no ha llegado a {DIRECCION}. "
        "Pide que le llamemos al {TELEFONO} antes de las 14:00.",
        "Devolución solicitada por {PERSONA}. Reembolsar 59,90 € en la cuenta {IBAN}. Dirección de recogida: {DIRECCION}.",
        "Reclamación de {PERSONA}, teléfono {TELEFONO}: la talla no corresponde. Responder a {EMAIL} con la etiqueta de envío.",
    ],
    "nota_rrhh": [
        "Incorporación el lunes de {PERSONA}, con DNI {DNI_NIE}. Nómina a la cuenta {IBAN}. Domicilio: {DIRECCION}. "
        "Contacto de emergencia: {PERSONA}, {TELEFONO}.",
        "Baja voluntaria de {PERSONA} ({DNI_NIE}). Enviar el finiquito a {EMAIL} y el certificado de empresa a {DIRECCION}.",
    ],
    "ficha_clinica": [
        "Paciente: {PERSONA}. DNI/NIE: {DNI_NIE}. Tel.: {TELEFONO}. Dirección: {DIRECCION}. "
        "Cita de revisión el próximo jueves; recordar por SMS.",
        "Aviso: {PERSONA} ha cancelado la cita. Volver a llamar al {TELEFONO}; prefiere que le escriban a {EMAIL}.",
    ],
    "whatsapp": [
        "hola soy {PERSONA_MIN}, os paso mi dni {DNI_NIE} y mi movil {TELEFONO} para lo del presupuesto",
        "buenas, el recibo me lo pasais a la cuenta {IBAN} q es la nueva. un saludo, {PERSONA_MIN}",
        "oye que la factura ponla a nombre de {PERSONA_MIN}, {DIRECCION}. mi correo es {EMAIL}",
    ],
}


def generar(n: int = N_DOCUMENTOS, semilla: int = SEMILLA) -> list[dict]:
    g = Generador(semilla)
    tipos = sorted(PLANTILLAS)
    docs = []
    for i in range(n):
        tipo = tipos[i % len(tipos)]
        plantilla = g.r.choice(PLANTILLAS[tipo])
        texto, entidades, pos = "", [], 0
        ultima_persona = "Ana García"
        for m in re.finditer(r"\{(\w+)\}", plantilla):
            texto += plantilla[pos:m.start()]
            clave = m.group(1)
            if clave in ("PERSONA", "PERSONA_MIN"):
                valor, formato = g.persona(minusculas=clave == "PERSONA_MIN")
                ultima_persona = valor
                etiqueta = "PERSONA"
            elif clave == "EMAIL":
                valor, formato = g.email(ultima_persona)
                etiqueta = "EMAIL"
            elif clave == "TELEFONO":
                valor, formato = g.telefono()
                etiqueta = "TELEFONO"
            elif clave == "DNI_NIE":
                valor, formato = g.dni_nie()
                etiqueta = "DNI_NIE"
            elif clave == "IBAN":
                valor, formato = g.iban()
                etiqueta = "IBAN"
            else:
                valor, formato = g.direccion()
                etiqueta = "DIRECCION"
            entidades.append((len(texto), len(texto) + len(valor), etiqueta, formato))
            texto += valor
            pos = m.end()
        texto += plantilla[pos:]
        docs.append({"id": i, "tipo": tipo, "texto": texto, "entidades": entidades})
    return docs


if __name__ == "__main__":
    for d in generar(6):
        print(d["tipo"], "|", d["texto"])
        for a, b, t, f in d["entidades"]:
            print("   ", t, f, repr(d["texto"][a:b]))
