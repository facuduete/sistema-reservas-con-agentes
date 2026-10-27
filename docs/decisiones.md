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

## Etapa 2 — API HTTP (2026-10-27)

### Archivos creados y modificados

- Creados: `app/views.py` (rutas), `run.py` (punto de entrada),
  `tests/conftest.py` (fixtures compartidas), `tests/test_api.py`.
- Modificados: `app/__init__.py` (pasa a contener la fábrica `create_app`),
  `app/reservas.py` (único cambio: atributo `codigo` en las excepciones de
  dominio), `tests/test_reglas.py` (las fixtures y el atajo `crear` se
  mudaron a `conftest.py`; las pruebas no cambiaron).

### Diseño de las rutas

| Método y ruta | Éxito | Errores posibles |
|---|---|---|
| `GET /api/unidades` | 200 `{"unidades": [...]}` | — |
| `GET /api/disponibilidad?fecha_inicio=&hora_inicio=&fecha_fin=&hora_fin=` | 200 `{"disponibilidad": [...]}` con `disponible` por unidad | 400 sin parámetros; 422 fechas/intervalo inválidos; 404 unidad inexistente (solo vía `unidad_disponible`) |
| `POST /api/reservas` | 201 con la reserva creada (incluye `id` público) | 400 cuerpo/ campos; 404 unidad inexistente; 409 solapamiento; 422 reglas de negocio |
| `GET /api/reservas` | 200 `{"reservas": [...]}` con activas y canceladas | 400 si el filtro `estado` no es válido |
| `POST /api/reservas/<id>/cancelar` | 200 con la reserva cancelada | 404 inexistente; 409 ya cancelada |

### Formato de solicitudes y respuestas

- Creación por JSON: `{"unidad", "solicitante", "fecha_inicio",
  "hora_inicio", "fecha_fin", "hora_fin"}` con `AAAA-MM-DD` y `HH:MM`.
- Convención de cuerpos: las colecciones van envueltas (`{"unidades":
  [...]}`, `{"disponibilidad": [...]}`, `{"reservas": [...]}`) y los objetos
  individuales van directos (creación 201 y cancelación 200 devuelven la
  reserva con `id`, `unidad`, `solicitante`, `inicio`, `fin`, `estado`,
  `creada_en`, `cancelada_en`).
- Errores: `{"error": {"codigo": "...", "mensaje": "..."}}`, con los
  códigos definidos por el dominio (`solicitante_invalido`,
  `fecha_invalida`, `intervalo_invalido`, `duracion_invalida`,
  `inicio_pasado`, `solapamiento`, `unidad_inexistente`,
  `reserva_inexistente`, `estado_invalido`, más `cuerpo_invalido`,
  `campos_faltantes`, `parametros_faltantes`, `parametro_invalido` de
  estructura, y `not_found`/`method_not_allowed` del framework).

### Traducción de errores de dominio a HTTP

1. **Único cambio en el dominio**: se agregó a cada excepción de
   `app/reservas.py` un atributo de clase `codigo` (además del
   `codigo_http` ya existente). La vista nunca interpreta la lógica: lee
   `e.codigo` y `e.codigo_http` y arma la respuesta JSON. El dominio sigue
   sin importar Flask.
2. **Frontera 400/422 decidida así**: lo *ausente o no parseable como
   solicitud* es 400 (JSON mal formado → `cuerpo_invalido`; campo obligatorio
   ausente o nulo → `campos_faltantes`; parámetro de consulta ausente →
   `parametros_faltantes`). Lo *presente pero inválido* lo valida el dominio
   y recibe su código (por ejemplo `solicitante: "   "` → 422
   `solicitante_invalido`; `fecha_inicio: "abc"` → 422 `fecha_invalida`).
   Motivo: no duplicar validación de negocio en la capa HTTP, lo que
   garantizaría dos fuentes de verdad.
3. **Errores del framework en JSON**: `HTTPException` (ruta desconocida,
   método no permitido) se traduce a la misma estructura con el nombre del
   error (`not_found`, `method_not_allowed`). `Exception` genérica se
   registra con `app.logger.exception` y responde 500 `error_interno` sin
   trazas ni detalles internos.

### Configuración de la base de datos

- `create_app(ruta_db=None)`: por defecto `data/reservas.db` (relativa a la
  raíz del proyecto); las pruebas pasan `tmp_path / "api.db"`.
- El esquema se inicializa al crear la aplicación con la operación
  idempotente de la Etapa 1 (no duplica unidades ni borra reservas).
- La conexión SQLite se abre **por solicitud** en `flask.g` y se cierra en
  `teardown_appcontext` (en SQLite la configuración es por conexión y el
  servidor de desarrollo atiende cada solicitud en su hilo).

### Pruebas

- Las fixtures compartidas (`conexion`, `crear`, `AHORA_FIJO`) se trasladaron
  a `tests/conftest.py` y `test_reglas.py` ahora las importa; la suite de
  dominio completa se re-ejecutó para verificar que el comportamiento quedó
  idéntico.
- `test_api.py` siembra datos por el dominio (no repite reglas ya probadas)
  y usa el cliente de Flask sobre bases temporales.
- **Fecha futura fija (2027-03-15) en todas las creaciones de la API**: la
  API usa el reloj real del servidor, así que una fecha "cercana" podría
  volverse pasada según cuándo se ejecuten las pruebas y provocar
  `inicio_pasado` espurios. Con 2027-03-15 el resultado no depende del
  momento de ejecución. La prueba del caso "inicio pasado" usa 2020-01-01,
  siempre pasado. El borde "inicio igual al momento actual" no es
  deterministicamente testeable vía API y queda cubierto en el dominio.
- El handler de 500 existe pero **no** tiene prueba automatizada: con
  `app.testing = True` Flask re-lanza las excepciones no previstas
  (`PROPAGATE_EXCEPTIONS`), por lo que simular una falla interna exigiría
  monkeypatching que no aporta a la consigna. Queda registrado como límite.

### Desviaciones respecto del prompt

- El prompt de esta etapa llegó **truncado en su inicio**: faltan los
  encabezados de las secciones A y B. El contenido se implementó a partir de
  lo conservado (delegar validaciones, 201 con identificador público, sin
  reservas parciales) y de las secciones C y D. No se detectó requisito
  faltante al cruzar con la lista de pruebas mínimas.

### Verificación real

1. `.venv\Scripts\python.exe -m pytest -v` → **48 passed in 1.14s**
   (22 de API + 26 de dominio), primera ejecución sin correcciones.
2. Prueba de humo de `run.py`: se arrancó el proceso real
   (`Start-Process .venv\Scripts\python.exe run.py`), se consultó
   `http://127.0.0.1:5000/api/unidades` con `Invoke-WebRequest` →
   **STATUS: 200** con las cinco unidades en JSON, y el proceso se detuvo
   (`Stop-Process`). Esto creó `data/reservas.db`, ignorada por Git.

### Corrección tras recibir el prompt completo (2026-10-27)

El primer envío de las instrucciones de esta etapa llegó truncado y se
implementó sobre esa base; luego el usuario reenvió el prompt completo, que
especifica un contrato distinto al inferido. Correcciones aplicadas:

1. **`GET /api/unidades?desde=AAAA-MM-DDTHH:MM&hasta=AAAA-MM-DDTHH:MM`**
   reemplaza a la ruta propia `GET /api/disponibilidad` que había
   implementado: la disponibilidad se consulta sobre el listado de
   unidades, y sin parámetros la ruta devuelve las unidades sin el
   indicador `disponible`. Con un solo parámetro (`desde` o `hasta`)
   responde 400 `parametros_faltantes`. Motivo: alineación literal con el
   prompt completo y superficie de API más pequeña.
2. **`POST /api/reservas` ahora recibe `unidad`, `solicitante`, `desde` e
   `hasta`**, con los momentos como texto combinado `AAAA-MM-DDTHH:MM`
   (precisión de minutos, sin segundos ni offset), en lugar de los campos
   separados `fecha_inicio`/`hora_inicio`/`fecha_fin`/`hora_fin` de la
   primera versión. Las respuestas siguen exponiendo `inicio` y `fin` como
   ISO 8601 con offset (`2027-03-15T10:00:00-03:00`).
3. **El parseo del momento combinado vive en el dominio**, no en la vista:
   se agregaron a `app/reservas.py` la función pública `parsear_momento`
   (formato `AAAA-MM-DDTHH:MM`, reutiliza la validación de calendario
   existente) y las variantes `crear_reserva_entre`,
   `consultar_disponibilidad_entre` y `unidad_disponible_entre`, que
   aceptan datetimes aware. Las versiones por textos separados se
   conservan como delegados y siguen alimentando las pruebas de dominio y
   la futura interfaz. Así la regla "no duplicar validaciones en las
   rutas" se mantiene también para el nuevo formato.
4. **Desviación documentada sobre 400/422 en parámetros de consulta**: el
   prompt pide 400 para parámetros "ausentes/mal formados". Decisión:
   *ausentes* → 400 (`parametros_faltantes`); *presentes pero con formato
   o valor inválido* → el error del dominio (422 `fecha_invalida`, 422
   `intervalo_invalido`). Motivo: marcar el formato de fecha en la vista
   duplicaría la validación que la consigna prohíbe duplicar y crearía dos
   fuentes de verdad. El mismo criterio se aplica al cuerpo JSON.
5. **Orden de validación en la creación** quedó: estructura de la solicitud
   (400) → formato temporal de `desde`/`hasta` (422) → reglas de negocio en
   el dominio (solicitante, intervalo, unidad, duración, inicio pasado,
   solapamiento). Leve diferencia con la primera versión, donde el
   solicitante se validaba antes que el formato de las fechas; ningún
   requisito la exige de otra manera y quedó documentada.
6. Observación menor registrada: `creada_en`/`cancelada_en` incluyen
   microsegundos (proviene del reloj real), mientras que `inicio`/`fin`
   tienen precisión de minutos (proviene de la entrada). Es inocuo para
   las reglas; se unificará solo si la interfaz lo requiere.

### Verificación real de la corrección

1. `.venv\Scripts\python.exe -m pytest -v` → **48 passed in 1.13s**
   (22 de API reescritas al nuevo contrato + 26 de dominio sin cambios).
2. Prueba de humo completa sobre `run.py` (proceso real, `Invoke-WebRequest`):
   `GET /api/unidades` → 200; `GET /api/unidades?desde=2027-03-15T10:00&hasta=2027-03-15T11:00`
   → 200 con `disponible: true` en las cinco unidades; `POST /api/reservas`
   → **201** con `id: RES-001`; `GET /api/reservas` → 200 con la reserva
   activa; `POST /api/reservas/RES-001/cancelar` → **200** con estado
   `cancelada` y datos originales intactos. El proceso se detuvo y la base
   `data/reservas.db` generada por la prueba de humo se eliminó para dejar
   el entorno limpio.
