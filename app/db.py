"""Acceso a SQLite: conexión, esquema e inicialización idempotente.

Se usa el módulo estándar ``sqlite3`` sin ORM, según la decisión técnica del
proyecto. Las fechas se guardan como texto ISO 8601 con offset explícito
(UTC-3); la interpretación de esos textos queda a cargo de ``app.reservas``.
"""

import sqlite3
from pathlib import Path

from .inventory import INVENTARIO

ESQUEMA = """
CREATE TABLE IF NOT EXISTS unidades (
    id          TEXT PRIMARY KEY,
    descripcion TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reservas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    unidad_id    TEXT NOT NULL REFERENCES unidades(id),
    solicitante  TEXT NOT NULL,
    inicio       TEXT NOT NULL,
    fin          TEXT NOT NULL,
    estado       TEXT NOT NULL CHECK (estado IN ('activa', 'cancelada')),
    creada_en    TEXT NOT NULL,
    cancelada_en TEXT
);

CREATE INDEX IF NOT EXISTS idx_reservas_unidad_estado
    ON reservas (unidad_id, estado);
"""


def conectar(ruta_db: str | Path) -> sqlite3.Connection:
    """Abre una conexión a la base con filas accesibles por nombre de columna.

    Activa el control de claves foráneas (en SQLite es por conexión) y crea
    el directorio contenedor si no existe, de modo que ``data/`` pueda
    generarse en la primera ejecución.
    """
    ruta = Path(ruta_db)
    if ruta.parent != Path(""):
        ruta.parent.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(ruta)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    return conexion


def inicializar(conexion: sqlite3.Connection) -> None:
    """Crea el esquema y siembra el inventario, sin duplicar ni borrar datos.

    La operación es idempotente: ``CREATE TABLE IF NOT EXISTS`` no modifica
    tablas existentes y ``INSERT OR IGNORE`` no duplica unidades. Las
    reservas previas se conservan intactas.
    """
    conexion.executescript(ESQUEMA)
    conexion.executemany(
        "INSERT OR IGNORE INTO unidades (id, descripcion) VALUES (?, ?)",
        [(unidad["id"], unidad["descripcion"]) for unidad in INVENTARIO],
    )
    conexion.commit()
