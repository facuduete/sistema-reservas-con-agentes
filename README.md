# Sistema de reservas de laboratorio

Trabajo de Tópicos Avanzados de Ingeniería de Software — desarrollo de un
sistema de reservas utilizando agentes de programación.

Sistema **local** de reservas de equipos de laboratorio: inventario fijo de
cinco unidades, creación y cancelación de reservas con validaciones de
negocio, historial con estados y persistencia en SQLite. Backend Flask con
API JSON, interfaz web sencilla (HTML + Bootstrap local + JavaScript
nativo) y pruebas automatizadas con pytest. Funciona sin conexión a
internet y sin servicios externos.

Índice:

1. [Especificación breve](#1-especificación-breve)
2. [Solución](#2-solución)
3. [Preparación del agente](#3-preparación-del-agente)
4. [Registro de decisiones y delegación](#4-registro-de-decisiones-y-delegación)

---

## 1. Especificación breve

### 1.1 Problema

Los equipos de un laboratorio académico se reservan de manera informal, a veces se confirma la misma unidad para horarios superpuestos y las reservas canceladas siguen bloqueando el horario.

### 1.2 Objetivo y alcance

Implementar un sistema local de reservas que permita **consultar** el
inventario y la disponibilidad por intervalo, **crear** reservas con
identificador, **cancelarlas** conservando el historial y **persistir**
todo entre ejecuciones. El alcance es deliberadamente pequeño, gratuito y
reproducible: una sola máquina, sin despliegue obligatorio en internet.

### 1.3 Inventario inicial (fijo, sin administración)

| Identificador | Descripción |
|---|---|
| `MIC-01` | Microscopio digital |
| `MIC-02` | Microscopio digital |
| `OSC-01` | Osciloscopio |
| `MUL-01` | Multímetro |
| `FUE-01` | Fuente de alimentación |

Cada identificador representa una **unidad física distinta**: `MIC-01` y
`MIC-02` se reservan por separado (no son un stock de dos microscopios).

### 1.4 Requisitos verificables

- **R1** — Consultar el inventario precargado y la disponibilidad de cada
  unidad para un intervalo dado.
- **R2** — Crear reservas con identificador público (`RES-001`, `RES-002`,
  …), unidad, solicitante, fecha y hora de inicio y fin.
- **R3** — Cancelar reservas conservando identificador y datos originales,
  cambiando el estado y liberando el intervalo.
- **R4** — Persistir reservas y estados para recuperarlos después de
  detener y reiniciar la aplicación.
- **R5** — Validar todas las reglas de negocio en el backend, con errores
  HTTP coherentes y mensajes comprensibles.
- **R6** — Interfaz web sencilla que consuma la API (consultar
  disponibilidad, crear, listar y cancelar), con estados activos y
  cancelados claramente diferenciados.

### 1.5 Reglas de negocio y validaciones

- Solo se pueden reservar unidades existentes; los códigos coinciden
  exactamente con el inventario (`MIC-01`, no `mic-01`).
- El solicitante es obligatorio: no vacío ni compuesto solo por espacios.
- Fechas `AAAA-MM-DD` y horas `HH:MM` (24 horas), validadas en calendario
  (se rechazan `2026-02-30`, `25:00`, `10:60`).
- El inicio debe ser **estrictamente anterior** al fin.
- Duración mínima de **10 minutos exactos** (9 se rechaza, 10 se acepta).
- Sin duración máxima ni anticipación máxima; solo se exige que el inicio
  no sea **anterior** al momento actual (un inicio igual al momento actual
  es válido).
- Los intervalos son **semiabiertos** `[inicio, fin)`: reservado
  `MIC-01` de 10:00 a 11:00, se rechaza 10:30–11:30 y se acepta 11:00–12:00.
- Solo se solapan reservas de la **misma unidad**; las de unidades
  distintas pueden ser simultáneas.
- Una reserva **cancelada** conserva su registro histórico (identificador y
  datos originales) y deja de bloquear la disponibilidad.
- Cancelar una reserva ya cancelada es un error (HTTP 409).
- La consulta de disponibilidad y la creación usan **exactamente el mismo
  predicado** de superposición (función única en el dominio).
- Zona horaria: **UTC−3 fijo** (hora oficial de Argentina).

### 1.6 Supuestos adoptados

- Uso monousuario/local: sin autenticación ni roles (excluidos por la
  consigna); cualquier usuario de la máquina puede cancelar cualquier
  reserva.
- La disponibilidad puede consultarse para intervalos pasados; las reglas
  de anticipación y duración mínima aplican solo a la **creación**.
- `creada_en` y `cancelada_en` son marcas de auditoría informativas; no
  participan en reglas de negocio.
- El servidor de desarrollo de Flask es suficiente; no se requiere
  servidor de producción.

### 1.7 Criterios de aceptación y su relación con las pruebas

| Criterio de aceptación | Pruebas (todas ejecutadas, ver §2.7) |
|---|---|
| El inventario devuelve exactamente las 5 unidades | `test_inventario_precargado`, `test_consulta_unidades_devuelve_las_cinco_esperadas` |
| Creación válida → 201 con `RES-001` y datos correctos | `test_crear_reserva_valida`, `test_creacion_valida_devuelve_201_e_identificador_publico` |
| Solapamiento en la misma unidad rechazado (incluye el ejemplo 10:30–11:30) | `test_rechazo_solapamiento_misma_unidad`, `test_reserva_solapada_responde_409` |
| Consecutivas permitidas (borde compartido) | `test_intervalos_consecutivos_permitidos`, `test_consecutivas_siguieron_compatibles_tras_reiniciar` |
| Simultáneas en unidades distintas permitidas | `test_simultaneas_unidades_distintas_permitidas`, `test_otra_unidad_no_afecta_disponibilidad_tras_reiniciar` |
| Unidad inexistente rechazada (404) | `test_unidad_inexistente_rechazada`, `test_unidad_inexistente_responde_404` |
| Solicitante vacío o solo espacios rechazado | `test_solicitante_vacio_rechazado`, caso `solicitante_invalido` de la API |
| Fechas/horas inválidas rechazadas | `test_fechas_horas_invalidas_rechazadas`, casos `fecha_invalida` de la API |
| Inicio ≥ fin rechazado | `test_inicio_debe_ser_anterior_al_fin`, caso `intervalo_invalido` de la API |
| Duración < 10 minutos rechazada | `test_duracion_menor_a_diez_minutos_rechazada`, `test_duracion_minima_aceptada`, caso `duracion_invalida` de la API |
| Inicio anterior al momento actual rechazado | `test_inicio_anterior_al_momento_actual_rechazado`, caso `inicio_pasado` de la API |
| Cancelación conserva registro, libera el intervalo y no permite re-cancelación (409) | `test_cancelar_conserva_datos_y_libera_disponibilidad`, `test_cancelacion_solo_modifica_campos_de_estado`, `test_cancelar_ya_cancelada_es_error`, `test_cancelar_repetida_responde_409` |
| Historial incluye activas y canceladas | `test_listado_incluye_activas_y_canceladas` |
| Persistencia tras reiniciar (activas y canceladas, con datos íntegros) | `test_reservas_activas_y_canceladas_persisten_tras_reiniciar` + 4 pruebas de disponibilidad tras reiniciar |
| Inicialización idempotente (no duplica unidades ni borra reservas) | `test_inicializacion_idempotente` |
| Errores HTTP coherentes, sin detalles internos | `test_estructura_de_error_coherente`, `test_error_interno_responde_500_sin_detalles` |

### 1.8 Funcionalidades expresamente excluidas

Autenticación y roles reales; notificaciones; pagos; integraciones
externas; despliegue obligatorio en internet; interfaces gráficas complejas
(sin frameworks de frontend); concurrencia distribuida y escalabilidad de
producción; administración del inventario (es fijo y precargado).

---

## 2. Solución

### 2.1 Estructura del proyecto

```
sistema-reservas-con-agentes/
├── run.py                     # Punto de entrada: python run.py
├── requirements.txt           # Dependencias con versiones fijadas
├── pytest.ini                 # Configuración de pytest
├── app/
│   ├── __init__.py            # Fábrica create_app(ruta_db) + manejo de errores
│   ├── inventory.py           # Inventario fijo (única fuente de verdad)
│   ├── db.py                  # SQLite: conexión, esquema, init idempotente
│   ├── reservas.py            # Reglas de negocio (sin dependencias de Flask)
│   ├── views.py               # Rutas HTTP (API JSON) y página principal
│   ├── templates/index.html   # Interfaz web (Jinja)
│   └── static/
│       ├── css/estilos.css    # Estilos propios
│       ├── js/app.js          # Lógica de la interfaz (fetch nativo)
│       └── vendor/bootstrap/  # Bootstrap 5.3.3 local (sin CDN)
├── tests/
│   ├── conftest.py            # Fixtures compartidas y reloj fijo de pruebas
│   ├── test_reglas.py         # Reglas de negocio (casos 1–11 de la consigna)
│   ├── test_api.py            # API HTTP, página y handler 500
│   └── test_persistencia.py   # Persistencia tras reiniciar (caso 12) e integridad
└── docs/
    ├── decisiones.md          # Registro cronológico de decisiones reales
    ├── delegacion.md          # Tres episodios reales de delegación al agente
    └── prueba_persistencia.md # Procedimiento manual de persistencia (Windows)
```

Responsabilidades: `reservas.py` concentra **toda** la lógica de negocio y
no importa Flask; `views.py` es una capa delgada que valida la estructura
de la solicitud (400) y traduce los errores del dominio a HTTP;
`db.py` maneja SQLite con esquema e inicialización idempotentes.

### 2.2 Decisiones técnicas significativas

- **Python + Flask + `sqlite3` estándar sin ORM**: mínimo de dependencias
  (`flask`, `pytest`), auditable y suficiente para el alcance.
- **UTC−3 fijo** (`timezone(timedelta(hours=-3))`) en lugar de zonas IANA:
  Argentina rige UTC−3; evita la dependencia `tzdata` en Windows.
- **Fábrica `create_app(ruta_db)`**: permite a las pruebas usar bases
  temporales sin tocar los datos locales.
- **Conexión SQLite por solicitud** (abierta en `flask.g`, cerrada al
  terminar el contexto).
- **Un único predicado de solapamiento** en el dominio, usado por creación
  y disponibilidad: garantiza estructuralmente que ambas operaciones
  apliquen las mismas reglas.
- **Errores de dominio con `codigo` y `codigo_http`**: la capa HTTP solo
  traduce; no duplica validaciones.
- **Bootstrap solo CSS, vendoreado**: la interfaz no usa componentes JS de
  Bootstrap, así que el bundle sería una dependencia sin uso.
- Detalle completo con motivos, alternativas y compromisos:
  [`docs/decisiones.md`](docs/decisiones.md).

### 2.3 Requisitos previos y versiones verificadas

| Componente | Versión verificada |
|---|---|
| Sistema operativo | Windows 10 (build 10.0.19045), PowerShell |
| Python | 3.14.3 |
| Git | 2.45.2.windows.1 |
| pip (dentro del venv) | 25.3 |
| Flask | 3.1.3 |
| pytest | 9.1.1 |
| SQLite (incluida en Python) | 3.50.4 |
| Bootstrap (vendoreado) | 5.3.3 |

Versiones fijadas en `requirements.txt` a partir de la salida real de
`pip install`; el detalle de los comandos ejecutados está en
`docs/decisiones.md` (Etapa 0).

### 2.4 Instalación

```powershell
# Dentro de la carpeta del proyecto (Windows, PowerShell)
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

No se requieren servicios externos, cuentas ni claves.

### 2.5 Inicialización y carga del inventario

No hay paso manual de inicialización: al crear la aplicación
(`create_app`, invocada por `run.py`) se ejecuta `db.inicializar()`, que

1. crea el esquema (`CREATE TABLE IF NOT EXISTS`) con las tablas `unidades`
   y `reservas`, y
2. siembra las cinco unidades con `INSERT OR IGNORE`.

**Es idempotente**: ejecutarla nuevamente no duplica unidades ni borra ni
modifica reservas (verificado por `test_inicializacion_idempotente` y por
las pruebas de persistencia, donde la segunda instancia de la aplicación
reinicializa la misma base).

### 2.6 Ejecución y detención

```powershell
.\.venv\Scripts\python.exe run.py
# Servidor de desarrollo en http://127.0.0.1:5000
# Detener: Ctrl + C en la terminal
```

La ruta de la base se calcula desde la ubicación de `app/__init__.py` (no
del directorio de trabajo), por lo que puede ejecutarse desde cualquier
carpeta sin crear bases duplicadas.

### 2.7 Pruebas automatizadas

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Última ejecución real registrada: **58 passed in 1.31s** (26 de dominio,
25 de API e integración, 7 de persistencia). Cobertura por requisito:
tabla en [`docs/decisiones.md`](docs/decisiones.md) (Etapa 4).

### 2.8 Endpoints

| Método y ruta | Descripción | Éxito | Errores |
|---|---|---|---|
| `GET /` | Página principal (interfaz web) | 200 HTML | — |
| `GET /api/unidades` | Inventario | 200 `{"unidades": [...]}` | — |
| `GET /api/unidades?desde=AAAA-MM-DDTHH:MM&hasta=AAAA-MM-DDTHH:MM` | Inventario + `disponible` por unidad en el intervalo | 200 | 400 parámetro faltante; 422 fechas/intervalo inválidos |
| `POST /api/reservas` | Crear reserva | 201 con la reserva (incluye `id` público) | 400 cuerpo/campos; 404 unidad inexistente; 409 solapamiento; 422 reglas de negocio |
| `GET /api/reservas` | Historial completo (activas y canceladas); filtros opcionales `?unidad=` y `?estado=activa\|cancelada` | 200 `{"reservas": [...]}` | 400 filtro `estado` inválido |
| `POST /api/reservas/<id>/cancelar` | Cancelar reserva activa | 200 con la reserva cancelada | 404 inexistente; 409 ya cancelada |

Los errores comparten la estructura `{"error": {"codigo": "...", "mensaje":
"..."}}`; los códigos provienen del dominio (`solicitante_invalido`,
`fecha_invalida`, `intervalo_invalido`, `duracion_invalida`,
`inicio_pasado`, `solapamiento`, `unidad_inexistente`,
`reserva_inexistente`, `estado_invalido`) más los de estructura
(`cuerpo_invalido`, `campos_faltantes`, `parametros_faltantes`,
`parametro_invalido`) y `error_interno` para fallos no previstos (500, sin
detalles internos).

**Ejemplo real** (registrado en la prueba de humo de la Etapa 2, sobre el
servidor real; el solicitante es ficticio y la fecha es futura a modo
ilustrativo):

Solicitud:

```
POST /api/reservas
{"unidad": "MIC-01", "solicitante": "Prueba de humo",
 "desde": "2027-03-15T10:00", "hasta": "2027-03-15T11:00"}
```

Respuesta (HTTP 201, salida real; `creada_en` varía en cada ejecución):

```json
{"cancelada_en": null,
 "creada_en": "2026-10-27T13:07:30.656441-03:00",
 "estado": "activa",
 "fin": "2027-03-15T11:00:00-03:00",
 "id": "RES-001",
 "inicio": "2027-03-15T10:00:00-03:00",
 "solicitante": "Prueba de humo",
 "unidad": "MIC-01"}
```

Y `POST /api/reservas/RES-001/cancelar` respondió **200** con el mismo
objeto y `"estado": "cancelada"`, conservando todos los datos originales.

### 2.9 Persistencia y reinicio de datos

- **Ubicación**: `<carpeta del proyecto>\data\reservas.db` (ruta calculada
  desde `app/__init__.py`, no del directorio de trabajo). El directorio
  `data\` se crea solo en el primer arranque y está excluido del
  repositorio por `.gitignore`.
- **Mecanismo**: SQLite mediante el módulo estándar; las fechas se guardan
  como texto ISO 8601 con offset UTC−3.
- **Instalación nueva**: la base se crea e inicializa automáticamente en
  el primer arranque (esquema + inventario), sin acción manual.
- **Idempotencia**: reinicializar no duplica unidades ni borra reservas.
- **Reinicio de la aplicación**: las reservas (activas y canceladas) se
  conservan con todos sus datos. Verificado de forma automatizada con dos
  instancias de la aplicación sobre la misma base
  (`tests/test_persistencia.py`) y manualmente mediante el procedimiento
  de [`docs/prueba_persistencia.md`](docs/prueba_persistencia.md)
  (detener con `Ctrl + C`, volver a iniciar, comprobar historial y
  disponibilidad).
- **Procedimiento de reinicio de datos**: **no existe** una operación de
  reinicio o borrado de datos en la aplicación (decisión de diseño: nada
  del flujo normal elimina reservas). La única forma de partir de cero es
  **manual y externa**: detener la aplicación y eliminar el archivo
  `data\reservas.db`. **Precaución**: eso elimina todo el historial de
  reservas, no solo las activas; el próximo arranque recrea el esquema y
  el inventario. No hay forma de borrar reservas selectivamente.

### 2.10 Limitaciones y pendientes conocidos

- Servidor de desarrollo de Flask, uso monousuario y local: no apto para
  despliegue de producción (fuera del alcance).

---

## 3. Preparación del agente

### 3.1 Agente y entorno

- **Agente**: OpenCode (harness de agente de programación), ejecutado como
  CLI/TUI en el proyecto. Versión verificada ejecutando
  `opencode --version`: **v2.2.0**.
- **Sistema operativo**: Windows 10, shell PowerShell.
- **Modelo utilizado**: según la configuración de la sesión del agente,
  **GLM-5.3-Flash Free**, identificador `opencode/glm-5.3-flash-free`
  (proveedor OpenCode).

### 3.2 Herramientas del entorno verificadas

| Componente | Versión | Verificación |
|---|---|---|
| Python | 3.14.3 | `python --version` |
| Git | 2.45.2.windows.1 | `git --version` |
| pip (venv) | 25.3 | `python -m pip --version` (tras `python -m venv .venv`, que autoinstala pip vía `ensurepip`) |
| Flask / pytest | 3.1.3 / 9.1.1 | instalación + importación + `pytest --version` |
| SQLite | 3.50.4 | `sqlite3.sqlite_version` |
| Node.js (solo para `node --check` del JS) | 24.22.1 | `node --version` |

### 3.3 Instrucciones, contexto y organización del trabajo

- Se dirigió el trabajo por **etapas numeradas (0 a 5)**, cada una
  con una instrucción escrita que incluía objetivo, requisitos,
  restricciones explícitas (no commitear sin autorización, no inventar
  resultados, no implementar etapas futuras) y pedido de reporte real.
- El agente recibió en cada etapa el estado previo (archivos existentes)
  y la consigna académica de fondo; la política general fue: inspeccionar
  antes de modificar, delegar validaciones al dominio, documentar
  decisiones reales en `docs/decisiones.md` y reportar solo resultados
  efectivamente ejecutados.
- **Permisos**: lectura/escritura de archivos del proyecto, ejecución de
  comandos en PowerShell (incluida una única descarga de Bootstrap y
  pruebas de humo con el servidor local) y consultas puntuales al usuario
  ante ambigüedades. Sin acceso a servicios externos durante la ejecución
  de la aplicación.
- **Decisiones reservadas al humano**: aprobar cada etapa, realizar todos
  los commits y pushes (el agente nunca commiteó), resolver ambigüedades
  de especificación (formato de hora, contrato de la API), y revisar cada
  entrega antes de continuar.

### 3.4 Etapas realizadas

| Etapa | Contenido | Commit |
|---|---|---|
| 0 | Entorno: venv, pip vía `ensurepip`, dependencias fijadas | (incluido en `b4da7fc`) |
| 1 | Dominio y persistencia (`inventory`, `db`, `reservas`) + pruebas de reglas | `b4da7fc` |
| 2 | API HTTP (contrato con `desde`/`hasta` combinados) + pruebas | `e30ec93` |
| 3 | Interfaz web + Bootstrap local + pruebas de integración | `be00ab5` |
| 4 | Persistencia tras reinicio, integridad, handler 500, procedimiento manual | `56a96ad` |
| 5 | Documentación final (este README, `docs/delegacion.md`) | pendiente de commit |

### 3.5 Adaptaciones durante el trabajo

Las adaptaciones significativas, con su motivo y evidencia, están
registradas en [`docs/decisiones.md`](docs/decisiones.md) y narradas como
episodios en [`docs/delegacion.md`](docs/delegacion.md): la aclaración del
formato de hora (HH → HH:MM), la implementación y validación del contrato
de la API (disponibilidad con `desde`/`hasta` en `GET /api/unidades` y
momentos combinados en la creación) y la decisión de vendorizar solo el
CSS de Bootstrap.

### 3.6 Conservación del progreso

- **Archivos versionados**: código, pruebas y documentación, con commits
  del usuario al cierre de cada etapa (ver tabla anterior).
- **Registro cronológico**: `docs/decisiones.md` creció etapa por etapa y
  quedó versionada en cada commit, por lo que el estado de las decisiones
  en cada momento es recuperable desde Git.
- **No se afirma recuperación de sesiones**: cada etapa se trabajó sobre
  el repositorio y los documentos existentes; no hay evidencia de sesiones
  del agente restauradas, y este documento no declara lo contrario.

---

## 4. Registro de decisiones y delegación

- **Registro cronológico de decisiones técnicas** (decisión, motivo,
  alternativas cuando existió disyuntiva, consecuencias y evidencia):
  [`docs/decisiones.md`](docs/decisiones.md). Es el registro de progreso
  del proyecto y está versionado desde la Etapa 1.
- **Tres episodios reales de delegación al agente** (objetivo → contexto e
  instrucción → acción del agente → decisión humana → evidencia
  verificable, con commits):
  [`docs/delegacion.md`](docs/delegacion.md).
  1. *Detección de una contradicción en la especificación* (Etapa 1):
     formato de hora «HH» vs. «HH:MM» y duración mínima de 10 minutos;
     el agente consultó y el usuario confirmó HH:MM (`b4da7fc`).
  2. *Implementación y validación del contrato de la API* (Etapa 2):
     disponibilidad por intervalo en `GET /api/unidades?desde=&hasta=` y
     creación con momentos combinados `desde`/`hasta`, con el parseo
     delegado al dominio (`e30ec93`).
  3. *Bootstrap vendoreado solo con CSS* (Etapa 3): cumplimiento offline
     sin incorporar el bundle JS innecesario (`be00ab5`).
