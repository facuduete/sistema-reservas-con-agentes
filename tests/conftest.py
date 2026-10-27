"""Fixtures y utilidades compartidas por las suites de pruebas.

El reloj se inyecta fijo (AHORA_FIJO) en el dominio y las pruebas usan bases
de datos SQLite temporales: ninguna prueba depende de la hora real de
ejecución ni toca los datos locales del proyecto.
"""

from datetime import datetime

import pytest

from app import create_app, db, reservas
from app.reservas import ZONA

# Momento actual fijo: martes 2026-10-27, 09:00 (UTC-3).
AHORA_FIJO = datetime(2026, 10, 27, 9, 0, tzinfo=ZONA)

# Fecha lejana en el futuro para las pruebas de la API, que usan el reloj
# real del servidor: así el resultado no depende del momento de ejecución.
FECHA_FUTURA = "2027-03-15"


@pytest.fixture()
def conexion(tmp_path):
    """Base de datos nueva e inicializada por prueba (nivel dominio)."""
    conexion = db.conectar(tmp_path / "reservas.db")
    db.inicializar(conexion)
    yield conexion
    conexion.close()


@pytest.fixture()
def app(tmp_path):
    """Aplicación Flask de prueba sobre una base SQLite temporal."""
    aplicacion = create_app(ruta_db=tmp_path / "api.db")
    aplicacion.testing = True
    yield aplicacion


@pytest.fixture()
def cliente(app):
    """Cliente de pruebas de Flask asociado a la app temporal."""
    return app.test_client()


@pytest.fixture()
def conexion_api(app):
    """Conexión directa a la base de la app, para sembrar datos de prueba."""
    conexion = db.conectar(app.config["RUTA_DB"])
    yield conexion
    conexion.close()


def crear(
    conexion,
    unidad="MIC-01",
    solicitante="alumno@test",
    fecha_i="2026-10-27",
    hora_i="10:00",
    fecha_f="2026-10-27",
    hora_f="11:00",
):
    """Atajo para crear reservas válidas con el reloj fijo (nivel dominio)."""
    return reservas.crear_reserva(
        conexion, unidad, solicitante, fecha_i, hora_i, fecha_f, hora_f,
        ahora=AHORA_FIJO,
    )
