"""Diez mensajes de voz típicos de una pyme, escritos para este experimento (sin datos reales).

Cada texto lleva sus «datos clave»: las cifras que una persona copiaría del audio a mano
(importes, teléfonos, horas, fechas, cantidades). Se comprueban por separado del WER porque
un error en una cifra cuesta más que un error en una palabra.
Los teléfonos usan el rango 600 000 0xx y similares, inventados; los nombres son genéricos.
"""

TEXTOS = [
    {
        "id": "pedido_bar",
        "tipo": "pedido de un cliente",
        "texto": "Hola, buenos días, soy Carmen del bar La Esquina. Quería hacer el pedido de esta semana: "
                 "veinticuatro cajas de agua, doce barriles de cerveza y seis cajas de refrescos de limón. "
                 "Si puede ser, que llegue el jueves antes de las diez de la mañana. Gracias.",
        "clave": ["veinticuatro cajas", "doce barriles", "seis cajas", "jueves", "diez"],
    },
    {
        "id": "cita_clinica",
        "tipo": "cambio de cita",
        "texto": "Buenas tardes, llamo de parte de Javier Moreno. Tenía cita con la doctora el martes a las cinco y media "
                 "y no voy a poder ir. ¿Me la podrían cambiar al miércoles por la tarde? Mi teléfono es el "
                 "seis uno dos, tres cuatro cinco, seis siete ocho. Muchas gracias.",
        "clave": ["martes", "cinco y media", "miércoles", "seis uno dos tres cuatro cinco seis siete ocho"],
    },
    {
        "id": "presupuesto_obra",
        "tipo": "presupuesto",
        "texto": "Te paso el presupuesto de la reforma del baño. La mano de obra son mil ochocientos euros, "
                 "los materiales unos novecientos cincuenta y el plato de ducha va aparte, doscientos cuarenta. "
                 "Calculamos dos semanas de trabajo y podríamos empezar el día quince.",
        "clave": ["mil ochocientos", "novecientos cincuenta", "doscientos cuarenta", "dos semanas", "quince"],
    },
    {
        "id": "reclamacion_tienda",
        "tipo": "reclamación",
        "texto": "Hola, os escribo por el pedido número cuatro siete ocho dos. Me llegó la talla equivocada: pedí una M "
                 "y me habéis mandado una XL. Quiero devolverlo y que me enviéis la correcta, no el reembolso. "
                 "Ya os mandé dos correos y nadie me ha contestado.",
        "clave": ["cuatro siete ocho dos", "dos correos"],
    },
    {
        "id": "gestoria_iva",
        "tipo": "consulta a la gestoría",
        "texto": "Hola, Lucía, soy Pedro, el de la carpintería. Ya tengo todas las facturas del trimestre. "
                 "Hay una de un proveedor de Portugal de tres mil doscientos euros que no sé si lleva IVA. "
                 "¿Te la mando por correo o te la llevo el viernes a la oficina?",
        "clave": ["tres mil doscientos", "portugal", "viernes"],
    },
    {
        "id": "reserva_restaurante",
        "tipo": "reserva",
        "texto": "Buenas noches, quería reservar mesa para el sábado catorce, para ocho personas, a las nueve y media. "
                 "Una de ellas es celíaca, así que si nos podéis preparar algo sin gluten, mejor. "
                 "A nombre de Alberto Ruiz, teléfono seis cero cero, cero cero cero, cero dos uno.",
        "clave": ["sábado", "catorce", "ocho personas", "nueve y media", "seis cero cero cero cero cero cero dos uno"],
    },
    {
        "id": "averia_furgoneta",
        "tipo": "aviso interno",
        "texto": "Jefe, soy Toni. La furgoneta grande se ha quedado sin batería en la nave de Getafe. "
                 "He llamado a la grúa y me dicen que tardan una hora y cuarto. Tengo tres entregas pendientes, "
                 "así que habría que avisar a los clientes de que llegamos tarde.",
        "clave": ["getafe", "una hora y cuarto", "tres entregas"],
    },
    {
        "id": "pago_factura",
        "tipo": "cobro",
        "texto": "Hola, te llamo de administración. La factura de octubre, la de cuatrocientos treinta y cinco euros con "
                 "sesenta, todavía no nos ha llegado. ¿Me puedes confirmar si se hizo la transferencia? "
                 "Si no, la cuenta es la misma de siempre. Un saludo.",
        "clave": ["octubre", "cuatrocientos treinta y cinco", "sesenta"],
    },
    {
        "id": "visita_comercial",
        "tipo": "nota de un comercial",
        "texto": "Nota de la visita a Muebles Hernández. Están interesados en el modelo nuevo de silla, "
                 "piden precio para ciento veinte unidades con un descuento del ocho por ciento. "
                 "Quieren la oferta antes del día veinte y volver a quedar la semana que viene.",
        "clave": ["ciento veinte", "ocho por ciento", "veinte"],
    },
    {
        "id": "turnos_tienda",
        "tipo": "organización de turnos",
        "texto": "Chicas, para la semana que viene: Marta abre el lunes y el martes de nueve a tres, "
                 "Rosa cierra de tres a nueve, y el sábado estamos las dos de diez a dos. "
                 "Si alguien no puede, que me lo diga antes del viernes, por favor.",
        "clave": ["lunes", "martes", "nueve a tres", "tres a nueve", "sábado", "diez a dos", "viernes"],
    },
]

# Voces de síntesis de macOS (vienen con el sistema). Dos de España y una de México.
VOCES = ["Mónica", "Eddy (Español (España))", "Paulina"]
VOZ_ID = {"Mónica": "monica_es", "Eddy (Español (España))": "eddy_es", "Paulina": "paulina_mx"}
