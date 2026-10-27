"""Sistema local de reservas de equipos de laboratorio.

``create_app`` es la fábrica de la aplicación Flask. La lógica de negocio
vive en ``app.reservas`` (sin dependencias de Flask); ``app.db`` maneja
SQLite y el inventario fijo se define en ``app.inventory``; ``app.views``
define las rutas de la API JSON.
"""

from pathlib import Path

from flask import Flask, g, jsonify
from werkzeug.exceptions import HTTPException

from . import db
from .views import api

_RUTA_DB_POR_DEFECTO = Path(__file__).resolve().parent.parent / "data" / "reservas.db"


def create_app(ruta_db=None) -> Flask:
    """Crea la aplicación, inicializa la base y registra rutas y errores.

    ``ruta_db`` permite apuntar a otra base de datos; las pruebas la usan
    para trabajar sobre archivos temporales sin tocar los datos locales.
    La inicialización es idempotente: no duplica unidades ni borra reservas.
    """
    aplicacion = Flask(__name__)
    aplicacion.config["RUTA_DB"] = str(
        ruta_db if ruta_db is not None else _RUTA_DB_POR_DEFECTO
    )

    conexion = db.conectar(aplicacion.config["RUTA_DB"])
    try:
        db.inicializar(conexion)
    finally:
        conexion.close()

    aplicacion.register_blueprint(api)

    @aplicacion.teardown_appcontext
    def cerrar_conexion(excepcion=None):
        """Cierra la conexión SQLite abierta durante la solicitud."""
        conexion_solicitud = g.pop("conexion", None)
        if conexion_solicitud is not None:
            conexion_solicitud.close()

    @aplicacion.errorhandler(HTTPException)
    def error_http(err):
        """Errores HTTP del propio framework (ruta desconocida, método, etc.)."""
        codigo = err.code if err.code is not None else 500
        return (
            jsonify(
                {
                    "error": {
                        "codigo": err.name.lower().replace(" ", "_"),
                        "mensaje": err.description,
                    }
                }
            ),
            codigo,
        )

    @aplicacion.errorhandler(Exception)
    def error_inesperado(err):
        """Error no previsto: se registra con traza y se responde sin detalles."""
        aplicacion.logger.exception("Error inesperado en la aplicación")
        return (
            jsonify(
                {
                    "error": {
                        "codigo": "error_interno",
                        "mensaje": "Ocurrió un error inesperado.",
                    }
                }
            ),
            500,
        )

    return aplicacion
