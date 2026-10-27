# Registro de decisiones

Registro cronológico y factual de las decisiones técnicas del proyecto. Cada
entrada describe la decisión, su motivo y, cuando corresponde, los supuestos
adoptados y la evidencia con la que se verificó. Solo se registran cosas que
realmente ocurrieron: comandos ejecutados, resultados reales y aclaraciones
reales con el equipo.

## Etapa 0 — Preparación del entorno (2026-10-27)

### Versiones comprobadas

Se verificaron ejecutando los comandos, no de memoria:

| Componente | Versión | Comando | Resultado |
|---|---|---|---|
| Python (sistema) | 3.14.3 | `python --version` | OK |
| Git | 2.45.2.windows.1 | `git --version` | OK |
| pip (dentro del venv) | 25.3 | `.venv\Scripts\python.exe -m pip --version` | OK |
| Flask | 3.1.3 | instalación + importación | OK |
| pytest | 9.1.1 | instalación + `pytest --version` | OK |
| SQLite (biblioteca incluida en Python) | 3.50.4 | `sqlite3.sqlite_version` | OK |

### Decisiones y hallazgos

1. **pip no estaba disponible en los Python del sistema** (3.14.3 y 3.13.2,
   ambos con "No module named pip"). Se resolvió creando el entorno virtual:
   `python -m venv .venv` arranca pip por sí solo vía `ensurepip`, sin
   reinstalar Python ni modificar configuraciones globales. El entorno
   virtual vive en `.venv/` dentro del proyecto y está ignorado por Git.
2. **Dependencias fijadas en `requirements.txt`**: `flask==3.1.3` y
   `pytest==9.1.1`. Las versiones se copiaron de la salida real de
   `pip install Flask pytest`.
3. **Sin `tzdata`**: se decidió manejar la zona horaria como UTC-3 fijo
   (`timezone(timedelta(hours=-3))`), la hora oficial vigente de Argentina
   (sin cambios de horario de verano desde 2008). Esto elimina la
   dependencia del paquete `tzdata`, que en Windows sería necesaria si se
   usara `zoneinfo("America/Argentina/Cordoba")`. Se verificó con una
   importación de prueba que `datetime(2026, 10, 27, 10, 0,
   tzinfo=timezone(timedelta(hours=-3))).isoformat()` produce
   `2026-10-27T10:00:00-03:00`.
4. **Bootstrap se vendorizará** en `static/vendor/` (decisión aprobada) para
   que la aplicación funcione sin conexión a internet. Pendiente de la etapa
   de interfaz.
5. Aviso menor observado: pip sugirió actualizarse a 26.2.2. No se actualizó
   para no introducir variables no verificadas; no afecta al proyecto.

## Etapa 1 — Dominio y persistencia (2026-10-27)

### Archivos creados

`app/__init__.py`, `app/inventory.py`, `app/db.py`, `app/reservas.py`,
`tests/test_reglas.py`, `pytest.ini`, `docs/decisiones.md` (este archivo).

### Decisiones técnicas

1. **Formato de hora de entrada: HH:MM.** La instrucción de la etapa decía
   "HH" en un punto, lo que contradecía la especificación original (HH:MM) y
   hacía inalcanzable la duración mínima de 10 minutos exactos (todo
   intervalo duraría múltiplos de una hora). Se consultó al usuario, quien
   confirmó HH:MM. Episodio real de aclaración, documentado también en
   `docs/delegacion.md` cuando corresponda.
2. **Zona horaria UTC-3 fija en todo el sistema** (decisión del usuario).
   Motivos: Argentina rige UTC-3 sin horario de verano desde 2008, el sistema
   es de zona única, y se evita la dependencia `tzdata`. Los objetos
   `datetime` se crean conscientes de zona (`tzinfo=ZONA`) y se comparan como
   datetimes aware, nunca como textos ni como naives.
3. **Persistencia de fechas como texto ISO 8601 con offset explícito**
   (`2026-10-27T10:00:00-03:00`). Motivos: el offset queda registrado en el
   dato (auditable), `datetime.fromisoformat` lo recupera sin ambigüedad y no
   hace falta conversión alguna para mostrarlo.
4. **Validación temporal estricta en el backend, en dos pasos**: primero un
   patrón (`\d{4}-\d{2}-\d{2}` y `\d{2}:\d{2}` con `fullmatch`) que garantiza
   el formato literal de la consigna (rechaza `9:30` o `27-10-2026`), y
   después `datetime.strptime`, que garantiza el calendario (rechaza
   `2026-02-30`, `25:00`, `10:60`).
5. **Reloj inyectable**: todas las operaciones que dependen del momento
   actual (`crear_reserva`, `cancelar_reserva`) aceptan el parámetro `ahora`;
   si falta, usan `datetime.now(tz=ZONA)`. Motivo: las pruebas del caso 10
   (inicio anterior al momento actual) son deterministas y no dependen de la
   hora real de ejecución.
6. **Borde del inicio pasado**: la regla prohíbe inicios *anteriores* al
   momento actual, de modo que un inicio **igual** al momento actual se
   acepta. Cubierto por prueba (`test_inicio_anterior_al_momento_actual_rechazado`).
7. **Duración mínima con borde inclusivo**: se exige `fin - inicio >= 10
   minutos`; 9 minutos se rechaza y 10 exactos se acepta, coherente con la
   redacción "duración inferior a 10 minutos". Ambos bordes cubiertos por
   pruebas.
8. **Superposición con un único predicado**: la función interna `_solapa`
   (`inicio_a < fin_b and inicio_b < fin_a`, correcto para intervalos
   semiabiertos `[inicio, fin)`) es la única definición de solapamiento del
   sistema y la usan tanto `crear_reserva` como `unidad_disponible` /
   `consultar_disponibilidad`. Motivo: el requisito de que ambas
   operaciones apliquen "exactamente las mismas reglas" queda garantizado
   estructuralmente, no por duplicación de código.
9. **Solapamiento verificado en Python, no en SQL**: se traen las reservas
   activas de la unidad y se compara en el dominio. Motivo: el volumen es
   diminuto (5 unidades, uso local) y así la regla es directamente
   testeable y legible. La consulta SQL solo filtra por unidad y estado.
10. **Errores de dominio con código HTTP asociado**: la jerarquía
    `ErrorNegocio` lleva un atributo `codigo_http` (422 por defecto, 404 para
    unidades/reservas inexistentes, 409 para solapamiento y estado
    inválido). `app/reservas.py` no importa Flask; el código es un dato que
    la futura capa HTTP traducirá. Orden de validación en la creación:
    solicitante → fechas e intervalo → unidad → duración → inicio pasado →
    superposición.
11. **Identificadores públicos `RES-001`, `RES-002`, …** generados a partir
    de la clave primaria autoincremental con al menos tres dígitos
    (`RES-{n:03d}`; a partir de RES-1000 crecen a cuatro dígitos, que sigue
    cumpliendo "al menos tres"). El identificador nunca cambia: la
    cancelación solo actualiza `estado` y `cancelada_en`. Para buscar por id
    se acepta `RES-001` en mayúsculas o minúsculas y con espacios laterales
    (se normaliza); un identificador mal formado se trata como reserva
    inexistente (404).
12. **Cancelar una reserva ya cancelada es un error** (`EstadoInvalido`,
    futuro 409), decisión aprobada por el usuario. Cancelar una reserva
    inexistente es `ReservaInexistente` (futuro 404).
13. **Inicialización idempotente**: `CREATE TABLE IF NOT EXISTS` +
    `INSERT OR IGNORE` para sembrar las cinco unidades. Reinicializar no
    duplica unidades ni borra reservas (probado en
    `test_inicializacion_idempotente`). No existe operación de reinicio de
    datos en el flujo normal, según lo acordado.
14. **Esquema**: dos tablas (`unidades`, `reservas`) con clave foránea de
    `reservas.unidad_id` hacia `unidades.id` y control de estado por
    `CHECK`. `PRAGMA foreign_keys = ON` se activa por conexión (en SQLite es
    por conexión, no global). Índice `(unidad_id, estado)` para la consulta
    de ocupación.
15. **El solicitante se normaliza con `strip()`** antes de guardarse: los
    espacios de los extremos no forman parte del dato. Un valor vacío o de
    solo espacios se rechaza.
16. **La consulta de disponibilidad puede hacerse sobre intervalos pasados**
    (supuesto registrado): las reglas de "inicio no pasado" y duración
    mínima aplican a la *creación* de reservas, no a la consulta. La
    disponibilidad sí valida formato de fechas y que el inicio sea anterior
    al fin.
17. **`pytest.ini` mínimo** con `testpaths = tests` y `pythonpath = .` para
    que `import app` funcione desde la raíz del proyecto sin instalar nada.

### Supuestos adoptados

- `MIC-01` y `MIC-02` son unidades físicas independientes que se reservan
  por separado (no un stock de dos microscopios).
- Los identificadores de unidad se escriben exactamente como figuran en el
  inventario (`MIC-01`, no `mic-01`); probado.
- `creada_en` y `cancelada_en` son marcas informativas de auditoría con la
  misma zona UTC-3; no participan en reglas de negocio.
- No hay duración máxima ni anticipación máxima: la única restricción
  temporal hacia el futuro es que el inicio no sea anterior al momento
  actual.

### Resultado de las pruebas (real)

Comando: `.venv\Scripts\python.exe -m pytest -v` (Python 3.14.3,
pytest 9.1.1, Windows).

Resultado: **26 passed in 0.63s**, en la primera ejecución, sin
modificaciones posteriores al código probado. Cubre los casos 1 a 11 de la
consigna (el caso 12, persistencia entre reinicios de la aplicación
completa, corresponde a su etapa propia).
