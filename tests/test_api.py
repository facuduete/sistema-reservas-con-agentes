"""Pruebas de la capa HTTP (Etapa 2) con el cliente de pruebas de Flask.

No repite las reglas de dominio ya cubiertas por test_reglas.py: verifica
que la API traduzca correctamente las operaciones y sus errores.

Contrato de la API: los momentos viajan como ``AAAA-MM-DDTHH:MM`` (hora
local UTC-3), tanto en los parámetros ``desde``/``hasta`` de
``GET /api/unidades`` como en el cuerpo de ``POST /api/reservas``.

Todas las reservas que estas pruebas crean usan FECHA_FUTURA (2027-03-15),
porque la API usa el reloj real del servidor: así el resultado no depende
del momento en que se ejecuten las pruebas.
"""

import pytest

from app import reservas
from conftest import AHORA_FIJO, FECHA_FUTURA, crear


def cuerpo_valido(**cambios):
    """Cuerpo JSON válido de creación, con reemplazos puntuales por prueba."""
    cuerpo = {
        "unidad": "MIC-01",
        "solicitante": "alumno@test",
        "desde": f"{FECHA_FUTURA}T10:00",
        "hasta": f"{FECHA_FUTURA}T11:00",
    }
    cuerpo.update(cambios)
    return cuerpo


# --------------------------------------------------------------------------
# Consulta de unidades y disponibilidad
# --------------------------------------------------------------------------


def test_consulta_unidades_devuelve_las_cinco_esperadas(cliente):
    respuesta = cliente.get("/api/unidades")
    assert respuesta.status_code == 200
    unidades = respuesta.get_json()["unidades"]
    assert [u["id"] for u in unidades] == [
        "FUE-01", "MIC-01", "MIC-02", "MUL-01", "OSC-01",
    ]
    assert unidades[1]["descripcion"] == "Microscopio digital"
    # Sin intervalo pedido no hay indicador de disponibilidad.
    assert all("disponible" not in u for u in unidades)


def test_unidades_con_intervalo_reflejan_reserva_activa(cliente, conexion_api):
    crear(conexion_api, fecha_i=FECHA_FUTURA, fecha_f=FECHA_FUTURA)  # MIC-01 10-11
    respuesta = cliente.get(
        f"/api/unidades?desde={FECHA_FUTURA}T10:30&hasta={FECHA_FUTURA}T11:30"
    )
    assert respuesta.status_code == 200
    por_unidad = {
        u["id"]: u["disponible"] for u in respuesta.get_json()["unidades"]
    }
    assert por_unidad == {
        "MIC-01": False,
        "MIC-02": True,
        "OSC-01": True,
        "MUL-01": True,
        "FUE-01": True,
    }


def test_disponibilidad_se_libera_tras_cancelar(cliente, conexion_api):
    crear(conexion_api, fecha_i=FECHA_FUTURA, fecha_f=FECHA_FUTURA)
    reservas.cancelar_reserva(conexion_api, "RES-001", ahora=AHORA_FIJO)
    respuesta = cliente.get(
        f"/api/unidades?desde={FECHA_FUTURA}T10:00&hasta={FECHA_FUTURA}T11:00"
    )
    por_unidad = {
        u["id"]: u["disponible"] for u in respuesta.get_json()["unidades"]
    }
    assert por_unidad["MIC-01"] is True


def test_intervalo_incompleto_en_unidades_responde_400(cliente):
    solo_desde = cliente.get(f"/api/unidades?desde={FECHA_FUTURA}T10:00")
    assert solo_desde.status_code == 400
    assert solo_desde.get_json()["error"]["codigo"] == "parametros_faltantes"
    solo_hasta = cliente.get(f"/api/unidades?hasta={FECHA_FUTURA}T11:00")
    assert solo_hasta.status_code == 400
    assert solo_hasta.get_json()["error"]["codigo"] == "parametros_faltantes"


# --------------------------------------------------------------------------
# Creación de reservas
# --------------------------------------------------------------------------


def test_creacion_valida_devuelve_201_e_identificador_publico(cliente):
    respuesta = cliente.post("/api/reservas", json=cuerpo_valido())
    assert respuesta.status_code == 201
    reserva = respuesta.get_json()
    assert reserva["id"] == "RES-001"
    assert reserva["unidad"] == "MIC-01"
    assert reserva["solicitante"] == "alumno@test"
    assert reserva["estado"] == "activa"
    assert reserva["inicio"] == f"{FECHA_FUTURA}T10:00:00-03:00"
    assert reserva["fin"] == f"{FECHA_FUTURA}T11:00:00-03:00"
    # La reserva quedó persistida y visible en el listado.
    listado = cliente.get("/api/reservas").get_json()["reservas"]
    assert [r["id"] for r in listado] == ["RES-001"]


def test_cuerpo_json_mal_formado_responde_400(cliente):
    respuesta = cliente.post(
        "/api/reservas", data="{esto no es json", content_type="application/json"
    )
    assert respuesta.status_code == 400
    assert respuesta.get_json()["error"]["codigo"] == "cuerpo_invalido"


def test_campos_ausentes_responden_400(cliente):
    respuesta = cliente.post("/api/reservas", json={"unidad": "MIC-01"})
    assert respuesta.status_code == 400
    cuerpo = respuesta.get_json()["error"]
    assert cuerpo["codigo"] == "campos_faltantes"
    assert "solicitante" in cuerpo["mensaje"]
    assert "desde" in cuerpo["mensaje"]
    assert "hasta" in cuerpo["mensaje"]


def test_unidad_inexistente_responde_404(cliente):
    respuesta = cliente.post("/api/reservas", json=cuerpo_valido(unidad="XXX-99"))
    assert respuesta.status_code == 404
    assert respuesta.get_json()["error"]["codigo"] == "unidad_inexistente"


def test_reserva_solapada_responde_409(cliente):
    cliente.post("/api/reservas", json=cuerpo_valido())  # MIC-01 10:00-11:00
    respuesta = cliente.post(
        "/api/reservas",
        json=cuerpo_valido(desde=f"{FECHA_FUTURA}T10:30", hasta=f"{FECHA_FUTURA}T11:30"),
    )
    assert respuesta.status_code == 409
    assert respuesta.get_json()["error"]["codigo"] == "solapamiento"
    # El intento rechazado no dejó reservas parciales.
    listado = cliente.get("/api/reservas").get_json()["reservas"]
    assert [r["id"] for r in listado] == ["RES-001"]


@pytest.mark.parametrize(
    "cambios,codigo",
    [
        ({"solicitante": "   "}, "solicitante_invalido"),
        ({"desde": "2027-02-30T10:00"}, "fecha_invalida"),
        ({"desde": "2027-03-15 10:00"}, "fecha_invalida"),  # separador incorrecto
        ({"hasta": "2027-03-15T25:00"}, "fecha_invalida"),
        (
            {"desde": f"{FECHA_FUTURA}T10:00", "hasta": f"{FECHA_FUTURA}T10:00"},
            "intervalo_invalido",
        ),
        ({"hasta": f"{FECHA_FUTURA}T10:09"}, "duracion_invalida"),
        ({"desde": "2020-01-01T10:00", "hasta": "2020-01-01T11:00"}, "inicio_pasado"),
    ],
)
def test_errores_de_dominio_se_traducen_a_http(cliente, cambios, codigo):
    respuesta = cliente.post("/api/reservas", json=cuerpo_valido(**cambios))
    assert respuesta.status_code == 422
    assert respuesta.get_json()["error"]["codigo"] == codigo


# --------------------------------------------------------------------------
# Consulta de reservas (historial con activas y canceladas)
# --------------------------------------------------------------------------


def test_listado_incluye_activas_y_canceladas(cliente, conexion_api):
    crear(conexion_api, unidad="MIC-01", fecha_i=FECHA_FUTURA, fecha_f=FECHA_FUTURA)
    crear(conexion_api, unidad="MIC-02", fecha_i=FECHA_FUTURA, fecha_f=FECHA_FUTURA)
    reservas.cancelar_reserva(conexion_api, "RES-002", ahora=AHORA_FIJO)
    listado = cliente.get("/api/reservas").get_json()["reservas"]
    assert [(r["id"], r["estado"]) for r in listado] == [
        ("RES-001", "activa"),
        ("RES-002", "cancelada"),
    ]
    # Filtros opcionales.
    solo_canceladas = cliente.get("/api/reservas?estado=cancelada").get_json()["reservas"]
    assert [r["id"] for r in solo_canceladas] == ["RES-002"]
    solo_mic01 = cliente.get("/api/reservas?unidad=MIC-01").get_json()["reservas"]
    assert [r["id"] for r in solo_mic01] == ["RES-001"]


def test_filtro_estado_invalido_responde_400(cliente):
    respuesta = cliente.get("/api/reservas?estado=despachada")
    assert respuesta.status_code == 400
    assert respuesta.get_json()["error"]["codigo"] == "parametro_invalido"


# --------------------------------------------------------------------------
# Cancelación
# --------------------------------------------------------------------------


def test_cancelacion_valida_conserva_datos_originales(cliente):
    cliente.post("/api/reservas", json=cuerpo_valido())
    respuesta = cliente.post("/api/reservas/RES-001/cancelar")
    assert respuesta.status_code == 200
    cancelada = respuesta.get_json()
    assert cancelada["id"] == "RES-001"
    assert cancelada["estado"] == "cancelada"
    assert cancelada["unidad"] == "MIC-01"
    assert cancelada["solicitante"] == "alumno@test"
    assert cancelada["inicio"] == f"{FECHA_FUTURA}T10:00:00-03:00"
    assert cancelada["fin"] == f"{FECHA_FUTURA}T11:00:00-03:00"
    assert cancelada["cancelada_en"] is not None


def test_cancelar_inexistente_responde_404(cliente):
    respuesta = cliente.post("/api/reservas/RES-999/cancelar")
    assert respuesta.status_code == 404
    assert respuesta.get_json()["error"]["codigo"] == "reserva_inexistente"


def test_cancelar_repetida_responde_409(cliente):
    cliente.post("/api/reservas", json=cuerpo_valido())
    cliente.post("/api/reservas/RES-001/cancelar")
    respuesta = cliente.post("/api/reservas/RES-001/cancelar")
    assert respuesta.status_code == 409
    assert respuesta.get_json()["error"]["codigo"] == "estado_invalido"


# --------------------------------------------------------------------------
# Estructura consistente de las respuestas de error
# --------------------------------------------------------------------------


def test_estructura_de_error_coherente(cliente):
    respuestas = [
        cliente.post("/api/reservas", data="mal", content_type="application/json"),
        cliente.post("/api/reservas", json=cuerpo_valido(unidad="XXX-99")),
        cliente.post("/api/reservas/RES-999/cancelar"),
        cliente.get("/api/ruta-inexistente"),
        cliente.get(f"/api/unidades?desde={FECHA_FUTURA}T10:00"),
    ]
    for respuesta in respuestas:
        cuerpo = respuesta.get_json()
        assert set(cuerpo) == {"error"}
        assert set(cuerpo["error"]) == {"codigo", "mensaje"}
        assert isinstance(cuerpo["error"]["codigo"], str) and cuerpo["error"]["codigo"]
        assert isinstance(cuerpo["error"]["mensaje"], str) and cuerpo["error"]["mensaje"]
