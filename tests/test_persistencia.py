"""Pruebas de persistencia e integridad de la base de datos (Etapa 4).

Caso 12 de la consigna: las reservas activas y canceladas se conservan al
detener y reiniciar la aplicación.

Cómo se simula el reinicio: se crea una primera instancia completa de la
aplicación (``create_app``), se operan reservas sobre ella y se descartan
sus referencias (las conexiones SQLite se abren por solicitud y Flask las
cierra al terminar cada contexto). Después se crea una **segunda instancia
nueva** de la aplicación sobre exactamente la misma ruta de base de datos
temporal y se comprueba que los datos persisten. No son dos consultas a la
misma instancia: el segundo objeto Flask reconstruye todo desde cero, lo
que además ejercita que la aplicación puede reutilizar una base ya creada.

La verificación con un proceso real detenido con Ctrl+C queda como
procedimiento manual en docs/prueba_persistencia.md; no se afirma aquí
haber reiniciado un proceso del servidor.

Los intervalos usan fechas futuras calculadas respecto del reloj real
(siete días en adelante) porque la API usa el reloj del servidor: así las
pruebas no envejecen con el paso del tiempo.
"""

import sqlite3
from datetime import datetime, timedelta

import pytest

from app import create_app, reservas
from app.reservas import ZONA
from conftest import AHORA_FIJO, crear


def fecha_futura(dias: int = 7) -> str:
    """Fecha futura relativa al reloj real, en formato AAAA-MM-DD."""
    return (datetime.now(tz=ZONA) + timedelta(days=dias)).date().isoformat()


def crear_via_api(cliente, fecha, unidad="MIC-01", hora_inicio="10:00",
                  hora_fin="11:00", solicitante="alumno@test"):
    """Crea una reserva por la API y devuelve el cuerpo de la respuesta."""
    respuesta = cliente.post(
        "/api/reservas",
        json={
            "unidad": unidad,
            "solicitante": solicitante,
            "desde": f"{fecha}T{hora_inicio}",
            "hasta": f"{fecha}T{hora_fin}",
        },
    )
    assert respuesta.status_code == 201
    return respuesta.get_json()


def consultar_disponibilidad(cliente, fecha, hora_inicio, hora_fin):
    respuesta = cliente.get(
        f"/api/unidades?desde={fecha}T{hora_inicio}&hasta={fecha}T{hora_fin}"
    )
    assert respuesta.status_code == 200
    return {u["id"]: u["disponible"] for u in respuesta.get_json()["unidades"]}


# --------------------------------------------------------------------------
# Caso 12: persistencia de activas y canceladas tras reiniciar
# --------------------------------------------------------------------------


def test_reservas_activas_y_canceladas_persisten_tras_reiniciar(tmp_path):
    ruta_db = tmp_path / "reservas.db"
    fecha = fecha_futura()

    # --- Primera instancia de la aplicación -----------------------------
    app_primera = create_app(ruta_db=ruta_db)
    cliente_primera = app_primera.test_client()
    activa = crear_via_api(cliente_primera, fecha, unidad="MIC-01",
                           solicitante="Ana Prueba")
    otra = crear_via_api(cliente_primera, fecha, unidad="MIC-02",
                         solicitante="Beto Prueba")
    respuesta_cancelacion = cliente_primera.post(f"/api/reservas/{otra['id']}/cancelar")
    assert respuesta_cancelacion.status_code == 200
    cancelada = respuesta_cancelacion.get_json()
    # Conexiones cerradas por solicitud; se descarta la instancia.
    app_primera = None
    cliente_primera = None

    # --- Segunda instancia NUEVA sobre la misma base persistente --------
    app_reiniciada = create_app(ruta_db=ruta_db)
    cliente_reiniciada = app_reiniciada.test_client()
    listado = cliente_reiniciada.get("/api/reservas").get_json()["reservas"]
    por_id = {r["id"]: r for r in listado}

    assert set(por_id) == {activa["id"], cancelada["id"]}
    for guardada in (activa, cancelada):
        persistida = por_id[guardada["id"]]
        for campo in ("unidad", "solicitante", "inicio", "fin", "estado",
                      "creada_en", "cancelada_en"):
            assert persistida[campo] == guardada[campo], campo
    assert por_id[activa["id"]]["estado"] == "activa"
    assert por_id[cancelada["id"]]["estado"] == "cancelada"


# --------------------------------------------------------------------------
# Disponibilidad después de reiniciar
# --------------------------------------------------------------------------


def test_reserva_activa_sigue_bloqueando_tras_reiniciar(tmp_path):
    ruta_db = tmp_path / "reservas.db"
    fecha = fecha_futura()
    app_primera = create_app(ruta_db=ruta_db)
    crear_via_api(app_primera.test_client(), fecha, unidad="MIC-01",
                  hora_inicio="10:00", hora_fin="11:00")

    app_reiniciada = create_app(ruta_db=ruta_db)
    por_unidad = consultar_disponibilidad(
        app_reiniciada.test_client(), fecha, "10:30", "11:30"
    )
    assert por_unidad["MIC-01"] is False


def test_reserva_cancelada_no_bloquea_tras_reiniciar(tmp_path):
    ruta_db = tmp_path / "reservas.db"
    fecha = fecha_futura()
    app_primera = create_app(ruta_db=ruta_db)
    cliente_primera = app_primera.test_client()
    reservada = crear_via_api(cliente_primera, fecha, unidad="MIC-01")
    respuesta_cancelacion = cliente_primera.post(
        f"/api/reservas/{reservada['id']}/cancelar"
    )
    assert respuesta_cancelacion.status_code == 200

    app_reiniciada = create_app(ruta_db=ruta_db)
    cliente_reiniciada = app_reiniciada.test_client()
    por_unidad = consultar_disponibilidad(cliente_reiniciada, fecha, "10:00", "11:00")
    assert por_unidad["MIC-01"] is True
    # El intervalo liberado vuelve a ser reservable después del reinicio.
    nueva = crear_via_api(cliente_reiniciada, fecha, unidad="MIC-01")
    assert nueva["id"] != reservada["id"]


def test_consecutivas_siguieron_compatibles_tras_reiniciar(tmp_path):
    ruta_db = tmp_path / "reservas.db"
    fecha = fecha_futura()
    app_primera = create_app(ruta_db=ruta_db)
    primera = crear_via_api(app_primera.test_client(), fecha,
                            hora_inicio="10:00", hora_fin="11:00")

    app_reiniciada = create_app(ruta_db=ruta_db)
    cliente_reiniciada = app_reiniciada.test_client()
    # Consecutiva contra la reserva persistida: borde compartido [11:00, 12:00).
    segunda = crear_via_api(cliente_reiniciada, fecha,
                            hora_inicio="11:00", hora_fin="12:00")
    listado = cliente_reiniciada.get("/api/reservas").get_json()["reservas"]
    assert [r["id"] for r in listado] == [primera["id"], segunda["id"]]


def test_otra_unidad_no_afecta_disponibilidad_tras_reiniciar(tmp_path):
    ruta_db = tmp_path / "reservas.db"
    fecha = fecha_futura()
    app_primera = create_app(ruta_db=ruta_db)
    crear_via_api(app_primera.test_client(), fecha, unidad="MIC-01")

    app_reiniciada = create_app(ruta_db=ruta_db)
    por_unidad = consultar_disponibilidad(
        app_reiniciada.test_client(), fecha, "10:30", "11:30"
    )
    assert por_unidad["MIC-01"] is False   # la unidad reservada sigue ocupada
    assert por_unidad["MIC-02"] is True    # otra unidad, mismo intervalo, libre


# --------------------------------------------------------------------------
# Inicialización e integridad de la base de datos
# --------------------------------------------------------------------------


def test_clave_foranea_impide_reservas_de_unidades_inexistentes(conexion):
    """La FK activada por conexión rechaza filas con unidad inexistente."""
    with pytest.raises(sqlite3.IntegrityError):
        conexion.execute(
            "INSERT INTO reservas (unidad_id, solicitante, inicio, fin, estado, creada_en) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("XXX-99", "alguien", "2027-01-01T10:00:00-03:00",
             "2027-01-01T11:00:00-03:00", "activa", AHORA_FIJO.isoformat()),
        )


def test_cancelacion_solo_modifica_campos_de_estado(conexion):
    """A nivel de fila: la cancelación toca únicamente estado y cancelada_en."""
    crear(conexion)  # RES-001 (atajo de conftest con reloj fijo)
    antes = dict(conexion.execute("SELECT * FROM reservas WHERE id = 1").fetchone())
    reservas.cancelar_reserva(conexion, "RES-001", ahora=AHORA_FIJO)
    despues = dict(conexion.execute("SELECT * FROM reservas WHERE id = 1").fetchone())

    assert antes["estado"] == "activa"
    assert antes["cancelada_en"] is None
    assert despues["estado"] == "cancelada"
    assert despues["cancelada_en"] == AHORA_FIJO.isoformat()
    for campo in ("id", "unidad_id", "solicitante", "inicio", "fin", "creada_en"):
        assert despues[campo] == antes[campo], campo
