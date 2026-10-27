"""Rutas HTTP de la API JSON.

Capa deliberadamente delgada: valida la *estructura* de la solicitud (cuerpo
presente, campos presentes, parámetros de consulta presentes) y delega toda
la validación de negocio en ``app.reservas``, cuyos errores se traducen a
respuestas JSON con el estado y el código que define el propio dominio.

Los momentos se reciben como ``AAAA-MM-DDTHH:MM`` (hora local UTC-3, sin
segundos ni offset) y se convierten mediante ``parsear_momento`` del propio
dominio: la validación de formato no está duplicada en esta capa.
"""

from flask import Blueprint, current_app, g, jsonify, request

from . import db
from .reservas import (
    ErrorNegocio,
    cancelar_reserva,
    consultar_disponibilidad_entre,
    crear_reserva_entre,
    listar_reservas,
    listar_unidades,
    parsear_momento,
)

api = Blueprint("api", __name__)

CAMPOS_DE_CREACION = ("unidad", "solicitante", "desde", "hasta")
ESTADOS_VALIDOS = ("activa", "cancelada")


def conexion():
    """Conexión SQLite por solicitud, cerrada al terminar el contexto."""
    if "conexion" not in g:
        g.conexion = db.conectar(current_app.config["RUTA_DB"])
    return g.conexion


def error(codigo: str, mensaje: str, estado: int):
    """Respuesta de error JSON con la estructura acordada del proyecto."""
    return jsonify({"error": {"codigo": codigo, "mensaje": mensaje}}), estado


def campos_faltantes(datos: dict, campos) -> list[str]:
    """Campos ausentes o explícitamente nulos en el cuerpo de la solicitud."""
    return [campo for campo in campos if datos.get(campo) is None]


@api.get("/api/unidades")
def listar_unidades_ruta():
    """Inventario precargado; con ?desde=&hasta= agrega la disponibilidad.

    Sin parámetros devuelve las cinco unidades. Con el intervalo completo
    (AAAA-MM-DDTHH:MM) cada unidad incluye ``disponible``, calculado con el
    mismo predicado de superposición que la creación de reservas. Con un
    solo parámetro responde 400.
    """
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    if bool(desde) != bool(hasta):
        faltante = "hasta" if not hasta else "desde"
        return error(
            "parametros_faltantes",
            f"Falta el parámetro de consulta: {faltante}.",
            400,
        )
    unidades = listar_unidades(conexion())
    if not desde:
        return jsonify({"unidades": unidades})
    try:
        inicio = parsear_momento(desde)
        fin = parsear_momento(hasta)
        unidades = consultar_disponibilidad_entre(conexion(), inicio, fin)
    except ErrorNegocio as e:
        return error(e.codigo, e.mensaje, e.codigo_http)
    return jsonify({"unidades": unidades})


@api.post("/api/reservas")
def crear_reserva_ruta():
    """Crea una reserva; todas las validaciones ocurren en el dominio.

    Cuerpo JSON: ``{"unidad", "solicitante", "desde", "hasta"}`` con
    ``AAAA-MM-DDTHH:MM``. Responde 201 con la reserva creada, incluido su
    identificador público. Un error de negocio aborta antes del INSERT, así
    que nunca quedan reservas parciales.
    """
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return error(
            "cuerpo_invalido",
            "El cuerpo de la solicitud debe ser un objeto JSON válido.",
            400,
        )
    faltan = campos_faltantes(datos, CAMPOS_DE_CREACION)
    if faltan:
        return error(
            "campos_faltantes",
            "Faltan campos obligatorios: " + ", ".join(faltan) + ".",
            400,
        )
    try:
        inicio = parsear_momento(datos["desde"])
        fin = parsear_momento(datos["hasta"])
        reserva = crear_reserva_entre(
            conexion(), datos["unidad"], datos["solicitante"], inicio, fin
        )
    except ErrorNegocio as e:
        return error(e.codigo, e.mensaje, e.codigo_http)
    return jsonify(reserva), 201


@api.get("/api/reservas")
def listar_reservas_ruta():
    """Historial completo de reservas (activas y canceladas).

    Filtros opcionales: ?unidad=MIC-01 y ?estado=activa|cancelada.
    """
    filtro_unidad = request.args.get("unidad")
    filtro_estado = request.args.get("estado")
    if filtro_estado is not None and filtro_estado not in ESTADOS_VALIDOS:
        return error(
            "parametro_invalido",
            "El parámetro 'estado' debe ser 'activa' o 'cancelada'.",
            400,
        )
    reservas_filtradas = listar_reservas(conexion())
    if filtro_unidad:
        reservas_filtradas = [
            r for r in reservas_filtradas if r["unidad"] == filtro_unidad
        ]
    if filtro_estado:
        reservas_filtradas = [
            r for r in reservas_filtradas if r["estado"] == filtro_estado
        ]
    return jsonify({"reservas": reservas_filtradas})


@api.post("/api/reservas/<reserva_id>/cancelar")
def cancelar_reserva_ruta(reserva_id: str):
    """Cancela una reserva activa; el dominio resuelve 404 y 409."""
    try:
        reserva = cancelar_reserva(conexion(), reserva_id)
    except ErrorNegocio as e:
        return error(e.codigo, e.mensaje, e.codigo_http)
    return jsonify(reserva)
