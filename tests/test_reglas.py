"""Pruebas de las reglas de negocio y de la persistencia básica (Etapa 1).

Cubre los casos 1 a 11 de la consigna a nivel de dominio, sin HTTP ni
interfaz. El caso 12 (persistencia entre detenciones y reinicios de la
aplicación completa) se prueba en su propia etapa con dos instancias de la
app sobre la misma base.

El reloj se inyecta fijo (AHORA_FIJO) para que todas las pruebas sean
deterministas: ninguna depende de la hora real de ejecución.
"""

from datetime import datetime

import pytest

from app import db, reservas
from app.reservas import (
    DuracionInvalida,
    EstadoInvalido,
    FechaInvalida,
    InicioPasado,
    IntervaloInvalido,
    ReservaInexistente,
    Solapamiento,
    SolicitanteInvalido,
    UnidadInexistente,
    ZONA,
)

# Momento actual fijo: martes 2026-10-27, 09:00 (UTC-3).
AHORA_FIJO = datetime(2026, 10, 27, 9, 0, tzinfo=ZONA)


@pytest.fixture()
def conexion(tmp_path):
    """Base de datos nueva y inicializada por prueba, en un directorio temporal."""
    conexion = db.conectar(tmp_path / "reservas.db")
    db.inicializar(conexion)
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
    """Atajo para crear reservas válidas con el reloj fijo."""
    return reservas.crear_reserva(
        conexion, unidad, solicitante, fecha_i, hora_i, fecha_f, hora_f,
        ahora=AHORA_FIJO,
    )


# --------------------------------------------------------------------------
# Inventario e inicialización
# --------------------------------------------------------------------------


def test_inventario_precargado(conexion):
    unidades = reservas.listar_unidades(conexion)
    assert [u["id"] for u in unidades] == [
        "FUE-01", "MIC-01", "MIC-02", "MUL-01", "OSC-01",
    ]
    assert unidades[0]["descripcion"] == "Fuente de alimentación"


def test_inicializacion_idempotente(conexion):
    crear(conexion)
    db.inicializar(conexion)  # segunda pasada sobre la misma base
    assert len(reservas.listar_unidades(conexion)) == 5
    assert len(reservas.listar_reservas(conexion)) == 1  # no se borra ni duplica


# --------------------------------------------------------------------------
# Caso 1: creación de una reserva válida
# --------------------------------------------------------------------------


def test_crear_reserva_valida(conexion):
    reserva = crear(conexion)
    assert reserva["id"] == "RES-001"
    assert reserva["unidad"] == "MIC-01"
    assert reserva["solicitante"] == "alumno@test"
    assert reserva["inicio"] == "2026-10-27T10:00:00-03:00"
    assert reserva["fin"] == "2026-10-27T11:00:00-03:00"
    assert reserva["estado"] == "activa"
    assert reservas.listar_reservas(conexion) == [reserva]


def test_duracion_minima_aceptada(conexion):
    # Exactamente 10 minutos: permitido (la regla rechaza "inferior a 10").
    reserva = crear(conexion, hora_i="10:00", hora_f="10:10")
    assert reserva["fin"] == "2026-10-27T10:10:00-03:00"


# --------------------------------------------------------------------------
# Caso 2: rechazo de superposiciones en la misma unidad (intervalos [inicio, fin))
# --------------------------------------------------------------------------


def test_rechazo_solapamiento_misma_unidad(conexion):
    crear(conexion)  # MIC-01 reservada de 10:00 a 11:00
    # Ejemplo literal de la consigna: 10:30-11:30 debe rechazarse.
    with pytest.raises(Solapamiento):
        crear(conexion, hora_i="10:30", hora_f="11:30")
    with pytest.raises(Solapamiento):
        crear(conexion, hora_i="09:30", hora_f="10:30")  # pisa el inicio
    with pytest.raises(Solapamiento):
        crear(conexion, hora_i="10:15", hora_f="10:45")  # contenida
    with pytest.raises(Solapamiento):
        crear(conexion, hora_i="09:00", hora_f="12:00")  # contenedora
    # Los intentos rechazados no deben dejar registros parciales.
    assert len(reservas.listar_reservas(conexion)) == 1


# --------------------------------------------------------------------------
# Caso 3: reservas consecutivas permitidas (borde compartido)
# --------------------------------------------------------------------------


def test_intervalos_consecutivos_permitidos(conexion):
    crear(conexion, hora_i="10:00", hora_f="11:00")
    posterior = crear(conexion, hora_i="11:00", hora_f="12:00")  # empieza al fin exacto
    anterior = crear(conexion, hora_i="09:00", hora_f="10:00")   # termina al inicio exacto
    assert posterior["id"] == "RES-002"
    assert anterior["id"] == "RES-003"


# --------------------------------------------------------------------------
# Caso 4: reservas simultáneas en unidades diferentes
# --------------------------------------------------------------------------


def test_simultaneas_unidades_distintas_permitidas(conexion):
    primera = crear(conexion, unidad="MIC-01")
    segunda = crear(conexion, unidad="MIC-02")
    tercera = crear(conexion, unidad="OSC-01")
    assert [r["id"] for r in (primera, segunda, tercera)] == [
        "RES-001", "RES-002", "RES-003",
    ]
    assert {r["unidad"] for r in (primera, segunda, tercera)} == {
        "MIC-01", "MIC-02", "OSC-01",
    }


# --------------------------------------------------------------------------
# Caso 5: unidades inexistentes (los códigos coinciden exactamente)
# --------------------------------------------------------------------------


def test_unidad_inexistente_rechazada(conexion):
    with pytest.raises(UnidadInexistente):
        crear(conexion, unidad="XXX-99")
    with pytest.raises(UnidadInexistente):
        crear(conexion, unidad="mic-01")  # minúsculas no coinciden con MIC-01


# --------------------------------------------------------------------------
# Caso 6: solicitante vacío o solo espacios
# --------------------------------------------------------------------------


@pytest.mark.parametrize("solicitante", ["", "   ", "\t\n"])
def test_solicitante_vacio_rechazado(conexion, solicitante):
    with pytest.raises(SolicitanteInvalido):
        crear(conexion, solicitante=solicitante)


# --------------------------------------------------------------------------
# Caso 7: fechas y horas inválidas
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fecha,hora",
    [
        ("2026-13-01", "10:00"),  # mes fuera de rango
        ("2026-02-30", "10:00"),  # día inexistente en el calendario
        ("27-10-2026", "10:00"),  # formato incorrecto
        ("2026-10-27", "25:00"),  # hora fuera de rango
        ("2026-10-27", "10:60"),  # minutos fuera de rango
        ("2026-10-27", "9:30"),   # formato incorrecto (falta cero a la izquierda)
    ],
)
def test_fechas_horas_invalidas_rechazadas(conexion, fecha, hora):
    with pytest.raises(FechaInvalida):
        crear(conexion, fecha_i=fecha, hora_i=hora)


# --------------------------------------------------------------------------
# Caso 8: el inicio debe ser estrictamente anterior al fin
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hora_i,hora_f",
    [("10:00", "10:00"), ("11:00", "10:00")],
)
def test_inicio_debe_ser_anterior_al_fin(conexion, hora_i, hora_f):
    with pytest.raises(IntervaloInvalido):
        crear(conexion, hora_i=hora_i, hora_f=hora_f)


# --------------------------------------------------------------------------
# Caso 9: duración inferior a 10 minutos
# --------------------------------------------------------------------------


def test_duracion_menor_a_diez_minutos_rechazada(conexion):
    with pytest.raises(DuracionInvalida):
        crear(conexion, hora_i="10:00", hora_f="10:09")


# --------------------------------------------------------------------------
# Caso 10: inicio anterior al momento actual
# --------------------------------------------------------------------------


def test_inicio_anterior_al_momento_actual_rechazado(conexion):
    with pytest.raises(InicioPasado):
        crear(conexion, hora_i="08:59", hora_f="10:00")
    # "Anterior" es estricto: un inicio igual al momento actual está permitido.
    reserva = crear(conexion, hora_i="09:00", hora_f="10:00")
    assert reserva["estado"] == "activa"


# --------------------------------------------------------------------------
# Caso 11: cancelación conserva el registro y libera la disponibilidad
# --------------------------------------------------------------------------


def test_cancelar_conserva_datos_y_libera_disponibilidad(conexion):
    crear(conexion)  # RES-001, MIC-01, 10:00-11:00
    cancelada = reservas.cancelar_reserva(conexion, "RES-001", ahora=AHORA_FIJO)
    # Identificador y datos originales intactos.
    assert cancelada["id"] == "RES-001"
    assert cancelada["unidad"] == "MIC-01"
    assert cancelada["solicitante"] == "alumno@test"
    assert cancelada["inicio"] == "2026-10-27T10:00:00-03:00"
    assert cancelada["fin"] == "2026-10-27T11:00:00-03:00"
    assert cancelada["estado"] == "cancelada"
    assert cancelada["cancelada_en"] == AHORA_FIJO.isoformat()
    # El intervalo queda libre según la misma consulta de disponibilidad.
    assert reservas.unidad_disponible(
        conexion, "MIC-01", "2026-10-27", "10:00", "2026-10-27", "11:00"
    )
    nueva = crear(conexion)  # el mismo intervalo vuelve a ser reservable
    assert nueva["id"] == "RES-002"


def test_cancelar_ya_cancelada_es_error(conexion):
    crear(conexion)
    reservas.cancelar_reserva(conexion, "RES-001", ahora=AHORA_FIJO)
    with pytest.raises(EstadoInvalido):
        reservas.cancelar_reserva(conexion, "RES-001", ahora=AHORA_FIJO)


def test_cancelar_reserva_inexistente(conexion):
    with pytest.raises(ReservaInexistente):
        reservas.cancelar_reserva(conexion, "RES-999", ahora=AHORA_FIJO)


# --------------------------------------------------------------------------
# La consulta de disponibilidad aplica las mismas reglas que la creación
# --------------------------------------------------------------------------


def test_consulta_disponibilidad_usa_las_mismas_reglas(conexion):
    crear(conexion, unidad="MIC-01", hora_i="10:00", hora_f="11:00")
    disponibilidad = reservas.consultar_disponibilidad(
        conexion, "2026-10-27", "10:30", "2026-10-27", "11:30"
    )
    por_unidad = {u["id"]: u["disponible"] for u in disponibilidad}
    assert por_unidad == {
        "MIC-01": False,  # superpuesta con la reserva activa
        "MIC-02": True,
        "OSC-01": True,
        "MUL-01": True,
        "FUE-01": True,
    }


def test_consulta_disponibilidad_valida_el_intervalo(conexion):
    with pytest.raises(IntervaloInvalido):
        reservas.consultar_disponibilidad(
            conexion, "2026-10-27", "11:00", "2026-10-27", "10:00"
        )
    with pytest.raises(UnidadInexistente):
        reservas.unidad_disponible(
            conexion, "XXX-99", "2026-10-27", "10:00", "2026-10-27", "11:00"
        )
