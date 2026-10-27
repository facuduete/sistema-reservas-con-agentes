"""Punto de entrada de la aplicación: ``python run.py``.

Levanta el servidor de desarrollo de Flask en http://127.0.0.1:5000 con la
base por defecto en ``data/reservas.db``. La depuración queda desactivada
para no exponer detalles internos; no hay credenciales ni secretos.
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=False)
