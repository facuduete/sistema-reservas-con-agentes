# Registro de delegación al agente de programación

Tres episodios reales de delegación, reconstruidos a partir del historial de
conversación con el usuario, de los commits del repositorio y de las pruebas
versionadas. Cada episodio sigue la secuencia: **objetivo y requisito →
contexto e instrucción → acción o resultado del agente → decisión humana y
motivo → evidencia verificable**.

No se transcriben conversaciones completas: se citan extractos breves y
representativos de las instrucciones realmente utilizadas. Los commits
citados existen en el historial del repositorio y fueron realizados por el
usuario (el agente no tuvo autorización para commitear).

---

## Episodio 1 — Detección de una contradicción en la especificación (Etapa 1)

**Objetivo y requisito.** Implementar las validaciones temporales del
dominio (formatos de fecha y hora, duración mínima, inicio no pasado) como
parte de las reglas de negocio de `app/reservas.py`.

**Contexto e instrucción (extractos reales).** La instrucción de la Etapa 1
pedía: «Implementá `app/reservas.py` con las reglas de negocio…» y, en la
lista de decisiones, decía: *«Formato de hora de entrada: HH, reloj de 24
horas»*. Esa redacción contradecía la especificación original del proyecto
(*«Formato de hora de entrada: HH:MM, con reloj de 24 horas»*) y hacía
inalcanzable otra regla de la misma instrucción: *«Duración mínima: 10
minutos exactos»* (con horas sin minutos, toda reserva duraría múltiplos de
una hora).

**Acción del agente.** No implementó sobre el valor ambiguo: detectó la
contradicción, la explicó (dos reglas del propio prompt eran
incompatibles entre sí y con la especificación original) y formuló una
consulta con dos opciones y una recomendación fundada («HH:MM
(Recomendado)», por coincidir con la especificación original y hacer
alcanzable la duración mínima).

**Decisión humana y motivo.** El usuario respondió eligiendo **HH:MM**,
confirmando que «HH» era un error de tipeo. Motivo: mantener coherencia con
la especificación original y con la regla de duración mínima.

**Evidencia verificable.**

- `docs/decisiones.md`, Etapa 1, decisión 1 («Formato de hora de entrada:
  HH:MM», con el motivo), versionada en el commit `b4da7fc`.
- `app/reservas.py`: `_PATRON_HORA = re.compile(r"\d{2}:\d{2}")` (formato
  HH:MM estricto).
- `tests/test_reglas.py`: `test_fechas_horas_invalidas_rechazadas[2026-10-27-9:30]`
  (rechaza horas sin dos dígitos) y `test_duracion_minima_aceptada`
  (reserva de 10:00 a 10:10 aceptada, que exige precisión de minutos).

---

## Episodio 2 — Implementación y validación del contrato de la API (Etapa 2)

**Objetivo y requisito.** Implementar la API HTTP con Flask delegando las
reglas de negocio en el dominio: consulta del inventario con disponibilidad
por intervalo, creación de reservas con identificador público, listado del
historial y cancelación, con errores HTTP coherentes y sin duplicar
validaciones en las rutas.

**Contexto e instrucción (extractos reales).** La instrucción de la Etapa 2
definía el contrato a implementar: la disponibilidad se consulta sobre el
listado de unidades mediante *«`GET
/api/unidades?desde=YYYY-MM-DDTHH:MM&hasta=YYYY-MM-DDTHH:MM`»*, y el cuerpo
de creación usa los momentos combinados, por ejemplo *«`"desde":
"2026-10-28T10:00"`»*. Una primera versión se implementó a partir de una
primera entrega incompleta de la instrucción; cuando el usuario envió la
definición completa del contrato, la capa HTTP se ajustó a ella.

**Acción del agente.** Implementó y validó el contrato definido: la
disponibilidad quedó integrada en `GET /api/unidades` mediante los
parámetros `desde`/`hasta` (momentos combinados `AAAA-MM-DDTHH:MM`; sin
parámetros la ruta devuelve solo el inventario) y el cuerpo de creación
usa `unidad`, `solicitante`, `desde` y `hasta`. Para no duplicar
validaciones en las rutas, trasladó el parseo del momento combinado al
dominio (`parsear_momento` y las variantes `crear_reserva_entre` /
`consultar_disponibilidad_entre` / `unidad_disponible_entre`), reescribió
`tests/test_api.py` al contrato (creación 201, disponibilidad por
intervalo, errores 400/404/409) y documentó el diseño de rutas y las
desviaciones 400/422.

**Decisión humana y motivo.** El usuario revisó el resultado y lo aceptó:
«La Etapa 2 está completa y revisada», autorizando la etapa siguiente, y
versionó el resultado en el commit `e30ec93`. Motivo: el contrato
implementado coincidía con la definición de la instrucción y la suite
completa quedó en verde (48 pruebas en ese momento: 22 de API al nuevo
contrato + 26 de dominio, registradas en `docs/decisiones.md`).

**Evidencia verificable.**

- `app/views.py` (en `e30ec93`): `CAMPOS_DE_CREACION = ("unidad",
  "solicitante", "desde", "hasta")` y ruta `GET /api/unidades` con
  parámetros `desde`/`hasta`.
- `app/reservas.py`: `parsear_momento` y las variantes `_entre`.
- `tests/test_api.py` (en `e30ec93`): pruebas al contrato `desde`/`hasta`
  (por ejemplo, `test_unidades_con_intervalo_reflejan_reserva_activa` y
  `test_intervalo_incompleto_en_unidades_responde_400`).
- `docs/decisiones.md`, Etapa 2 (versionada en `e30ec93`): diseño de las
  rutas, formato de solicitudes y respuestas, desviaciones 400/422 y la
  verificación real (48 passed + prueba de humo sobre el servidor con
  `POST /api/reservas` → 201 y cancelación → 200).

---

## Episodio 3 — Bootstrap vendoreado solo con CSS (Etapa 3)

**Objetivo y requisito.** Construir la interfaz web con Bootstrap
almacenado localmente para que la aplicación funcione sin conexión a
internet, sin incorporar dependencias innecesarias.

**Contexto e instrucción (extractos reales).** *«Bootstrap debe
almacenarse localmente en `static/vendor/` para que la aplicación funcione
sin conexión a internet»* y *«No descargues ni incorpores dependencias
innecesarias»*.

**Acción del agente.** Descargó una única vez `bootstrap.min.css` 5.3.3
(232.803 bytes) desde jsDelivr a `app/static/vendor/bootstrap/` y verificó
la versión sobre el encabezado del archivo descargado (`Bootstrap
 v5.3.3`). **No** descargó `bootstrap.bundle.min.js`: la interfaz no usa
ningún componente JavaScript de Bootstrap (sin colapsables, modales ni
dropdowns; la confirmación de cancelación usa `window.confirm` nativo y
los avisos se cierran con un manejador propio), de modo que incluir el
bundle habría sido una dependencia sin uso. La desviación respecto del
"Bootstrap completo" quedó documentada con su motivo.

**Decisión humana y motivo.** El usuario aceptó el resultado al cerrar la
etapa («La Etapa 3 está completa») y autorizar la siguiente, sin objetar la
omisión del bundle, y versionó el trabajo en el commit `be00ab5`. Motivo: la
restricción de funcionamiento sin conexión queda satisfecha con el CSS y la
regla de no agregar dependencias innecesarias se respeta.

**Evidencia verificable.**

- `app/static/vendor/bootstrap/bootstrap.min.css` (en `be00ab5`).
- `tests/test_api.py::test_bootstrap_vendoreado_se_sirve_localmente`
  (comprueba que Flask sirve el archivo y que identifica la versión 5.3.3).
- `docs/decisiones.md`, Etapa 3, decisión 2 (motivo de no vendorizar el JS).
- Prueba de humo registrada en `docs/decisiones.md`: `GET /` → 200 y el CSS
  servido localmente (232.800 bytes por HTTP).

---

## Notas sobre la conservación del progreso

- El progreso se conservó mediante **archivos versionados** (código,
  pruebas y `docs/decisiones.md`) y commits realizados por el usuario al
  cierre de cada etapa (`b4da7fc`, `e30ec93`, `be00ab5`, `56a96ad`).
- Cada etapa trabajó sobre el estado del repositorio y los documentos; no
  se afirma que se hayan recuperado sesiones anteriores del agente.
- Las instrucciones y decisiones humanas vivieron en la conversación con el
  usuario; sus efectos verificables quedaron registrados en
  `docs/decisiones.md` y en los commits citados.
