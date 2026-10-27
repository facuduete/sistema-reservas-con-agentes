"""Reglas de negocio del sistema de reservas.

Este módulo no depende de Flask ni de la interfaz: la capa HTTP (etapa
posterior) solo traducirá estas funciones y sus errores a respuestas web.

Convenciones de tiempo adoptadas (detalle y motivos en docs/decisiones.md):

- Zona horaria fija UTC-3, hora oficial vigente de Argentina, representada
  con ``timezone(timedelta(hours=-3))``; no se usa ``tzdata`` ni zonas IANA.
- Entradas de texto: fecha ``AAAA-MM-DD`` y hora ``HH:MM`` en reloj de 24
  horas. La validación de formato y de calendario ocurre aquí (backend).
- Los intervalos son semiabiertos ``[inicio, fin)``: el instante ``fin`` no
  pertenece a la reserva, por lo que una reserva que termina a las 11:00 no
  impide otra que empiece a las 11:00.
- Las fechas se persisten como texto ISO 8601 con offset explícito, por
  ejemplo ``2026-10-27T10:00:00-03:00``.
- El momento actual se inyecta con el parámetro ``ahora`` (por defecto, el
  reloj real en la zona del proyecto) para que las pruebas sean
  deterministas.
"""

import re
import sqlite3
from datetime import datetime, timedelta, timezone

ZONA = timezone(timedelta(hours=-3))
DURACION_MINIMA = timedelta(minutes=10)

_PATRON_FECHA = re.compile(r"\d{4}-\d{2}-\d{2}")
_PATRON_HORA = re.compile(r"\d{2}:\d{2}")
_PATRON_MOMENTO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
_PATRON_ID_RESERVA = re.compile(r"RES-(\d+)")


class ErrorNegocio(Exception):
    """Base de los errores de reglas de negocio.

    ``codigo_http`` y ``codigo`` son datos (no dependencias de Flask) para
    que la capa HTTP traduzca cada error a su estado y a su identificador
    de respuesta sin conocer detalles internos del dominio.
    """

    codigo_http = 422
    codigo = "error_negocio"

    def __init__(self, mensaje: str) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje


class SolicitanteInvalido(ErrorNegocio):
    """El solicitante está vacío o compuesto solo por espacios."""

    codigo = "solicitante_invalido"


class FechaInvalida(ErrorNegocio):
    """Fecha u hora con formato o valor de calendario inválido."""

    codigo = "fecha_invalida"


class IntervaloInvalido(ErrorNegocio):
    """El inicio no es estrictamente anterior al fin."""

    codigo = "intervalo_invalido"


class DuracionInvalida(ErrorNegocio):
    """La duración es inferior a la mínima de 10 minutos."""

    codigo = "duracion_invalida"


class InicioPasado(ErrorNegocio):
    """El inicio es anterior al momento actual."""

    codigo = "inicio_pasado"


class Solapamiento(ErrorNegocio):
    """Otra reserva activa de la misma unidad superpone el intervalo."""

    codigo_http = 409
    codigo = "solapamiento"


class UnidadInexistente(ErrorNegocio):
    """El identificador de unidad no figura en el inventario."""

    codigo_http = 404
    codigo = "unidad_inexistente"


class ReservaInexistente(ErrorNegocio):
    """No existe una reserva con el identificador indicado."""

    codigo_http = 404
    codigo = "reserva_inexistente"


class EstadoInvalido(ErrorNegocio):
    """La operación no es válida para el estado actual de la reserva."""

    codigo_http = 409
    codigo = "estado_invalido"


# --------------------------------------------------------------------------
# Validación y utilidades internas
# --------------------------------------------------------------------------


def _validar_solicitante(solicitante: object) -> str:
    if not isinstance(solicitante, str) or not solicitante.strip():
        raise SolicitanteInvalido(
            "El solicitante es obligatorio y no puede estar vacío "
            "ni compuesto únicamente por espacios."
        )
    return solicitante.strip()


def _parsear_momento(fecha: object, hora: object) -> datetime:
    """Combina fecha y hora de entrada en un datetime consciente de zona."""
    if not isinstance(fecha, str) or not _PATRON_FECHA.fullmatch(fecha):
        raise FechaInvalida(f"La fecha {fecha!r} no cumple el formato AAAA-MM-DD.")
    if not isinstance(hora, str) or not _PATRON_HORA.fullmatch(hora):
        raise FechaInvalida(f"La hora {hora!r} no cumple el formato HH:MM (24 horas).")
    try:
        dia = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        raise FechaInvalida(f"La fecha {fecha!r} no es una fecha de calendario válida.") from None
    try:
        momento = datetime.strptime(hora, "%H:%M").time()
    except ValueError:
        raise FechaInvalida(f"La hora {hora!r} no es una hora válida.") from None
    return datetime.combine(dia, momento, tzinfo=ZONA)


def _validar_orden_intervalo(inicio: datetime, fin: datetime) -> None:
    """Exige que el inicio sea estrictamente anterior al fin."""
    if inicio >= fin:
        raise IntervaloInvalido("El inicio debe ser estrictamente anterior al fin.")


def parsear_momento(texto: object) -> datetime:
    """Convierte ``AAAA-MM-DDTHH:MM`` (hora local UTC-3) en datetime aware.

    Es el formato de entrada de la API HTTP: precisión de minutos, sin
    segundos ni offset. La validación de formato y de calendario ocurre
    aquí, en el dominio, no en la capa HTTP.
    """
    if not isinstance(texto, str) or not _PATRON_MOMENTO.fullmatch(texto):
        raise FechaInvalida(
            f"El momento {texto!r} no cumple el formato AAAA-MM-DDTHH:MM."
        )
    fecha, hora = texto.split("T")
    return _parsear_momento(fecha, hora)


def _solapa(inicio_a: datetime, fin_a: datetime, inicio_b: datetime, fin_b: datetime) -> bool:
    """Predicado único de superposición para intervalos semiabiertos.

    Dos intervalos ``[inicio, fin)`` se superponen si y solo si el inicio de
    cada uno es anterior al fin del otro. Toda consulta de disponibilidad y
    toda creación de reservas pasa por esta misma función.
    """
    return inicio_a < fin_b and inicio_b < fin_a


def _id_publico(numero: int) -> str:
    return f"RES-{numero:03d}"


def _numero_de_id(reserva_id: object) -> int:
    """Convierte ``RES-001`` en el número de fila; si no es válido, no existe."""
    if isinstance(reserva_id, str):
        coincidencia = _PATRON_ID_RESERVA.fullmatch(reserva_id.strip().upper())
        if coincidencia:
            return int(coincidencia.group(1))
    raise ReservaInexistente(f"No existe una reserva con identificador {reserva_id!r}.")


def _unidad_existe(conexion: sqlite3.Connection, unidad_id: object) -> bool:
    fila = conexion.execute(
        "SELECT 1 FROM unidades WHERE id = ?", (unidad_id,)
    ).fetchone()
    return fila is not None


def _reservas_activas(
    conexion: sqlite3.Connection, unidad_id: str
) -> list[tuple[datetime, datetime]]:
    filas = conexion.execute(
        "SELECT inicio, fin FROM reservas WHERE unidad_id = ? AND estado = 'activa'",
        (unidad_id,),
    ).fetchall()
    return [
        (datetime.fromisoformat(fila["inicio"]), datetime.fromisoformat(fila["fin"]))
        for fila in filas
    ]


def _esta_libre(
    conexion: sqlite3.Connection, unidad_id: str, inicio: datetime, fin: datetime
) -> bool:
    return not any(
        _solapa(inicio, fin, ocupacion_inicio, ocupacion_fin)
        for ocupacion_inicio, ocupacion_fin in _reservas_activas(conexion, unidad_id)
    )


def _fila_a_reserva(fila: sqlite3.Row) -> dict:
    return {
        "id": _id_publico(fila["id"]),
        "unidad": fila["unidad_id"],
        "solicitante": fila["solicitante"],
        "inicio": fila["inicio"],
        "fin": fila["fin"],
        "estado": fila["estado"],
        "creada_en": fila["creada_en"],
        "cancelada_en": fila["cancelada_en"],
    }


# --------------------------------------------------------------------------
# Operaciones públicas
# --------------------------------------------------------------------------


def listar_unidades(conexion: sqlite3.Connection) -> list[dict]:
    """Devuelve el inventario precargado ordenado por identificador."""
    filas = conexion.execute(
        "SELECT id, descripcion FROM unidades ORDER BY id"
    ).fetchall()
    return [{"id": fila["id"], "descripcion": fila["descripcion"]} for fila in filas]


def unidad_disponible_entre(
    conexion: sqlite3.Connection, unidad_id: str, inicio: datetime, fin: datetime
) -> bool:
    """Indica si una unidad está libre entre dos datetimes conscientes de zona.

    Aplica exactamente el mismo predicado de superposición que la creación
    de reservas. No evalúa reglas de creación (duración mínima ni inicio
    pasado): consultar la disponibilidad de un intervalo pasado es válido.
    """
    _validar_orden_intervalo(inicio, fin)
    if not _unidad_existe(conexion, unidad_id):
        raise UnidadInexistente(f"La unidad {unidad_id!r} no existe en el inventario.")
    return _esta_libre(conexion, unidad_id, inicio, fin)


def unidad_disponible(
    conexion: sqlite3.Connection,
    unidad_id: str,
    fecha_inicio: str,
    hora_inicio: str,
    fecha_fin: str,
    hora_fin: str,
) -> bool:
    """Versión por textos (AAAA-MM-DD / HH:MM) de ``unidad_disponible_entre``."""
    return unidad_disponible_entre(
        conexion,
        unidad_id,
        _parsear_momento(fecha_inicio, hora_inicio),
        _parsear_momento(fecha_fin, hora_fin),
    )


def consultar_disponibilidad_entre(
    conexion: sqlite3.Connection, inicio: datetime, fin: datetime
) -> list[dict]:
    """Disponibilidad de todas las unidades entre dos datetimes aware."""
    _validar_orden_intervalo(inicio, fin)
    return [
        {**unidad, "disponible": _esta_libre(conexion, unidad["id"], inicio, fin)}
        for unidad in listar_unidades(conexion)
    ]


def consultar_disponibilidad(
    conexion: sqlite3.Connection,
    fecha_inicio: str,
    hora_inicio: str,
    fecha_fin: str,
    hora_fin: str,
) -> list[dict]:
    """Versión por textos (AAAA-MM-DD / HH:MM) de ``consultar_disponibilidad_entre``."""
    return consultar_disponibilidad_entre(
        conexion,
        _parsear_momento(fecha_inicio, hora_inicio),
        _parsear_momento(fecha_fin, hora_fin),
    )


def crear_reserva_entre(
    conexion: sqlite3.Connection,
    unidad_id: str,
    solicitante: str,
    inicio: datetime,
    fin: datetime,
    ahora: datetime | None = None,
) -> dict:
    """Crea una reserva entre dos datetimes aware, con todas las reglas.

    Orden de validación: solicitante, orden del intervalo, unidad, duración
    mínima, inicio no pasado y superposición. Un error aborta antes del
    INSERT, de modo que nunca quedan reservas parciales.
    """
    if ahora is None:
        ahora = datetime.now(tz=ZONA)
    solicitante_normalizado = _validar_solicitante(solicitante)
    _validar_orden_intervalo(inicio, fin)
    if not _unidad_existe(conexion, unidad_id):
        raise UnidadInexistente(f"La unidad {unidad_id!r} no existe en el inventario.")
    if fin - inicio < DURACION_MINIMA:
        raise DuracionInvalida("La duración mínima de una reserva es de 10 minutos.")
    if inicio < ahora:
        raise InicioPasado(
            "El inicio de la reserva no puede ser anterior al momento actual."
        )
    if not _esta_libre(conexion, unidad_id, inicio, fin):
        raise Solapamiento(
            f"La unidad {unidad_id} ya tiene una reserva activa que se superpone "
            "con el intervalo solicitado."
        )
    cursor = conexion.execute(
        "INSERT INTO reservas (unidad_id, solicitante, inicio, fin, estado, creada_en) "
        "VALUES (?, ?, ?, ?, 'activa', ?)",
        (unidad_id, solicitante_normalizado, inicio.isoformat(), fin.isoformat(),
         ahora.isoformat()),
    )
    conexion.commit()
    return obtener_reserva(conexion, _id_publico(cursor.lastrowid))


def crear_reserva(
    conexion: sqlite3.Connection,
    unidad_id: str,
    solicitante: str,
    fecha_inicio: str,
    hora_inicio: str,
    fecha_fin: str,
    hora_fin: str,
    ahora: datetime | None = None,
) -> dict:
    """Versión por textos (AAAA-MM-DD / HH:MM) de ``crear_reserva_entre``."""
    return crear_reserva_entre(
        conexion,
        unidad_id,
        solicitante,
        _parsear_momento(fecha_inicio, hora_inicio),
        _parsear_momento(fecha_fin, hora_fin),
        ahora=ahora,
    )


def obtener_reserva(conexion: sqlite3.Connection, reserva_id: str) -> dict:
    """Devuelve una reserva por su identificador público (por ejemplo RES-001)."""
    numero = _numero_de_id(reserva_id)
    fila = conexion.execute(
        "SELECT * FROM reservas WHERE id = ?", (numero,)
    ).fetchone()
    if fila is None:
        raise ReservaInexistente(
            f"No existe una reserva con identificador {reserva_id!r}."
        )
    return _fila_a_reserva(fila)


def listar_reservas(conexion: sqlite3.Connection) -> list[dict]:
    """Devuelve todas las reservas (activas y canceladas) ordenadas por id."""
    filas = conexion.execute("SELECT * FROM reservas ORDER BY id").fetchall()
    return [_fila_a_reserva(fila) for fila in filas]


def cancelar_reserva(
    conexion: sqlite3.Connection, reserva_id: str, ahora: datetime | None = None
) -> dict:
    """Cancela una reserva activa conservando su identificador y sus datos.

    La cancelación solo cambia el estado y registra el momento; el resto de
    los datos originales queda intacto y el intervalo deja de bloquear la
    disponibilidad. Cancelar una reserva ya cancelada es un error.
    """
    if ahora is None:
        ahora = datetime.now(tz=ZONA)
    numero = _numero_de_id(reserva_id)
    fila = conexion.execute(
        "SELECT estado FROM reservas WHERE id = ?", (numero,)
    ).fetchone()
    if fila is None:
        raise ReservaInexistente(
            f"No existe una reserva con identificador {reserva_id!r}."
        )
    if fila["estado"] != "activa":
        raise EstadoInvalido(
            f"La reserva {_id_publico(numero)} ya estaba cancelada."
        )
    conexion.execute(
        "UPDATE reservas SET estado = 'cancelada', cancelada_en = ? WHERE id = ?",
        (ahora.isoformat(), numero),
    )
    conexion.commit()
    return obtener_reserva(conexion, _id_publico(numero))
