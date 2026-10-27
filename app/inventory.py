"""Inventario fijo de unidades del laboratorio.

El inventario es precargado y no admite administración: cada identificador
representa una unidad física distinta (MIC-01 y MIC-02 son dos microscopios
independientes, no un stock de dos unidades de un mismo tipo).

Esta estructura es la única fuente de verdad del inventario y se siembra en
la base de datos mediante :func:`app.db.inicializar`.
"""

INVENTARIO = (
    {"id": "MIC-01", "descripcion": "Microscopio digital"},
    {"id": "MIC-02", "descripcion": "Microscopio digital"},
    {"id": "OSC-01", "descripcion": "Osciloscopio"},
    {"id": "MUL-01", "descripcion": "Multímetro"},
    {"id": "FUE-01", "descripcion": "Fuente de alimentación"},
)
