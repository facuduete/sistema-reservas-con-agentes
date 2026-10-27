/*
 * Interfaz del sistema de reservas de laboratorio.
 *
 * El navegador solo prepara las solicitudes y presenta resultados: toda
 * validación de negocio (solapamientos, duración mínima, inicio no pasado,
 * intervalos semiabiertos) la resuelve el backend mediante la API JSON.
 * Las comprobaciones locales existen para mejorar la experiencia, nunca
 * para reemplazar la autoridad del servidor.
 *
 * Contrato de la API usado (verificado en app/views.py):
 * - GET  /api/unidades                       -> {unidades: [{id, descripcion}]}
 * - GET  /api/unidades?desde=&hasta=         -> ídem + {disponible} por unidad
 *      (momentos en formato AAAA-MM-DDTHH:MM, hora local UTC-3)
 * - POST /api/reservas {unidad, solicitante, desde, hasta} -> 201 con la reserva
 * - GET  /api/reservas                       -> {reservas: [...]} activas y canceladas
 * - POST /api/reservas/<id>/cancelar         -> 200 con la reserva cancelada
 *
 * Errores: {error: {codigo, mensaje}}; los mensajes se muestran tal cual
 * llegan del backend porque ya son comprensibles para el usuario.
 */

"use strict";

/* ------------------------------------------------------------------ */
/* Utilidades                                                          */
/* ------------------------------------------------------------------ */

function qs(selector) {
  return document.querySelector(selector);
}

/* Combina los campos de fecha y hora en el formato de la API:
   "2026-10-28" + "10:00" -> "2026-10-28T10:00". */
function momentoDesdeCampos(fecha, hora) {
  return `${fecha}T${hora}`;
}

/* Formatea el ISO con offset que devuelve la API
   ("2027-03-15T10:00:00-03:00" -> "15/03/2027 10:00").
   Se usa un recorte textual y no new Date() a propósito: el valor ya está
   en hora local UTC-3 y convertirlo a la zona del navegador podría
   mostrar otra hora. */
function formatearMomento(iso) {
  const coincidencia = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso || "");
  if (!coincidencia) {
    return iso || "";
  }
  const [, anio, mes, dia, hora, minutos] = coincidencia;
  return `${dia}/${mes}/${anio} ${hora}:${minutos}`;
}

function mostrarMensaje(tipo, texto) {
  const alerta = document.createElement("div");
  alerta.className = `alert alert-${tipo} alert-dismissible fade show`;
  alerta.setAttribute("role", "alert");
  const contenido = document.createElement("div");
  contenido.textContent = texto;
  alerta.appendChild(contenido);
  const botonCerrar = document.createElement("button");
  botonCerrar.type = "button";
  botonCerrar.className = "btn-close";
  botonCerrar.setAttribute("aria-label", "Cerrar");
  botonCerrar.addEventListener("click", () => alerta.remove());
  alerta.appendChild(botonCerrar);
  qs("#mensajes").replaceChildren(alerta);
}

function limpiarMensajes() {
  qs("#mensajes").replaceChildren();
}

/* Extrae el mensaje comprensible de una respuesta HTTP no exitosa. */
async function mensajeDeError(respuesta) {
  try {
    const cuerpo = await respuesta.json();
    if (cuerpo && cuerpo.error && cuerpo.error.mensaje) {
      return cuerpo.error.mensaje;
    }
  } catch (error) {
    /* La respuesta no tenía el JSON de error esperado. */
  }
  return `El servidor respondió con el estado HTTP ${respuesta.status}.`;
}

function estadoVacio(texto) {
  const parrafo = document.createElement("p");
  parrafo.className = "text-body-secondary fst-italic";
  parrafo.textContent = texto;
  return parrafo;
}

function indicadorCarga(texto) {
  const parrafo = document.createElement("p");
  parrafo.className = "text-body-secondary mb-0";
  const giro = document.createElement("span");
  giro.className = "spinner-border spinner-border-sm me-2";
  giro.setAttribute("role", "status");
  giro.setAttribute("aria-hidden", "true");
  parrafo.appendChild(giro);
  parrafo.appendChild(document.createTextNode(texto));
  return parrafo;
}

/* Ejecuta una acción deshabilitando el botón que la disparó: indica carga
   y evita envíos repetidos mientras la solicitud está en curso. */
async function conCarga(boton, accion) {
  boton.disabled = true;
  boton.setAttribute("aria-busy", "true");
  const giro = document.createElement("span");
  giro.className = "spinner-border spinner-border-sm me-2";
  giro.setAttribute("aria-hidden", "true");
  boton.prepend(giro);
  try {
    return await accion();
  } finally {
    boton.disabled = false;
    boton.removeAttribute("aria-busy");
    giro.remove();
  }
}

/* ------------------------------------------------------------------ */
/* Disponibilidad                                                      */
/* ------------------------------------------------------------------ */

/* Último intervalo consultado, para refrescar la vista cuando cambian las
   reservas (creación o cancelación). */
let intervaloConsultado = null;

function leerIntervalo(prefijo) {
  const fechaInicio = qs(`#${prefijo}-fecha-inicio`).value;
  const horaInicio = qs(`#${prefijo}-hora-inicio`).value;
  const fechaFin = qs(`#${prefijo}-fecha-fin`).value;
  const horaFin = qs(`#${prefijo}-hora-fin`).value;
  if (!fechaInicio || !horaInicio || !fechaFin || !horaFin) {
    return null;
  }
  return {
    fechaInicio,
    horaInicio,
    fechaFin,
    horaFin,
    desde: momentoDesdeCampos(fechaInicio, horaInicio),
    hasta: momentoDesdeCampos(fechaFin, horaFin),
  };
}

function renderizarDisponibilidad(unidades) {
  const contenedor = qs("#resultado-disponibilidad");
  if (!unidades || unidades.length === 0) {
    contenedor.replaceChildren(estadoVacio("No hay unidades en el inventario."));
    return;
  }
  const fila = document.createElement("div");
  fila.className = "row g-3";
  for (const unidad of unidades) {
    const columna = document.createElement("div");
    columna.className = "col-12 col-md-6 col-lg-4";
    const tarjeta = document.createElement("div");
    tarjeta.className = "card h-100 shadow-sm tarjeta-unidad";
    const cuerpo = document.createElement("div");
    cuerpo.className = "card-body";

    const titulo = document.createElement("h3");
    titulo.className = "h6 card-title mb-0";
    titulo.textContent = `${unidad.id} — ${unidad.descripcion}`;
    cuerpo.appendChild(titulo);

    const insignia = document.createElement("span");
    insignia.className = `badge align-self-start ${
      unidad.disponible ? "text-bg-success" : "text-bg-secondary"
    }`;
    insignia.textContent = unidad.disponible ? "Disponible" : "Reservada";
    cuerpo.appendChild(insignia);

    if (!unidad.disponible) {
      const leyenda = document.createElement("p");
      leyenda.className = "leyenda-estado text-body-secondary mb-0";
      leyenda.textContent =
        "Tiene una reserva activa durante el intervalo consultado.";
      cuerpo.appendChild(leyenda);
    }

    tarjeta.appendChild(cuerpo);
    columna.appendChild(tarjeta);
    fila.appendChild(columna);
  }
  contenedor.replaceChildren(fila);
}

async function consultarDisponibilidad(intervalo, boton) {
  const consulta = `desde=${encodeURIComponent(intervalo.desde)}&hasta=${encodeURIComponent(
    intervalo.hasta
  )}`;
  await conCarga(boton, async () => {
    let respuesta;
    try {
      respuesta = await fetch(`/api/unidades?${consulta}`);
    } catch (error) {
      mostrarMensaje(
        "danger",
        "No se pudo conectar con el servidor. Verificá que la aplicación esté en ejecución."
      );
      return;
    }
    if (!respuesta.ok) {
      mostrarMensaje("danger", await mensajeDeError(respuesta));
      return;
    }
    const cuerpo = await respuesta.json();
    intervaloConsultado = intervalo;
    renderizarDisponibilidad(cuerpo.unidades);
  });
}

async function alConsultarDisponibilidad(evento) {
  evento.preventDefault();
  limpiarMensajes();
  const intervalo = leerIntervalo("disp");
  if (!intervalo) {
    mostrarMensaje(
      "warning",
      "Completá la fecha y la hora de inicio y de finalización para consultar la disponibilidad."
    );
    return;
  }
  await consultarDisponibilidad(intervalo, qs("#btn-consultar"));
  /* El formulario de reserva aprovecha el intervalo consultado, pero puede
     modificarse libremente. */
  qs("#res-fecha-inicio").value = intervalo.fechaInicio;
  qs("#res-hora-inicio").value = intervalo.horaInicio;
  qs("#res-fecha-fin").value = intervalo.fechaFin;
  qs("#res-hora-fin").value = intervalo.horaFin;
}

/* Refresca la disponibilidad visible si hay un intervalo consultado. */
async function refrescarDisponibilidad() {
  if (!intervaloConsultado) {
    return;
  }
  await consultarDisponibilidad(intervaloConsultado, qs("#btn-consultar"));
}

/* ------------------------------------------------------------------ */
/* Reservas                                                            */
/* ------------------------------------------------------------------ */

function insigniaEstado(estado) {
  const insignia = document.createElement("span");
  if (estado === "activa") {
    insignia.className = "badge text-bg-success";
    insignia.textContent = "Activa";
  } else {
    insignia.className = "badge text-bg-secondary";
    insignia.textContent = "Cancelada";
  }
  return insignia;
}

function celda(texto) {
  const celda = document.createElement("td");
  celda.textContent = texto;
  return celda;
}

function botonCancelar(reserva) {
  const boton = document.createElement("button");
  boton.type = "button";
  boton.className = "btn btn-outline-danger btn-sm";
  boton.textContent = "Cancelar";
  boton.addEventListener("click", () => cancelarReserva(reserva.id, boton));
  return boton;
}

function renderizarReservas(reservas) {
  const contenedor = qs("#listado-reservas");
  if (!reservas || reservas.length === 0) {
    contenedor.replaceChildren(
      estadoVacio("Todavía no hay reservas registradas. Creá la primera arriba.")
    );
    return;
  }
  const envoltorio = document.createElement("div");
  envoltorio.className = "table-responsive shadow-sm";
  const tabla = document.createElement("table");
  tabla.className = "table table-striped align-middle bg-white mb-0";
  const titulo = document.createElement("caption");
  titulo.className = "visually-hidden";
  titulo.textContent = "Historial de reservas, activas y canceladas";
  tabla.appendChild(titulo);

  const encabezado = document.createElement("thead");
  const filaEncabezado = document.createElement("tr");
  for (const texto of ["Identificador", "Unidad", "Solicitante", "Inicio", "Fin", "Estado", "Acciones"]) {
    const columna = document.createElement("th");
    columna.scope = "col";
    columna.textContent = texto;
    filaEncabezado.appendChild(columna);
  }
  encabezado.appendChild(filaEncabezado);
  tabla.appendChild(encabezado);

  const cuerpo = document.createElement("tbody");
  for (const reserva of reservas) {
    const fila = document.createElement("tr");
    fila.appendChild(celda(reserva.id));
    fila.appendChild(celda(reserva.unidad));
    fila.appendChild(celda(reserva.solicitante));
    fila.appendChild(celda(formatearMomento(reserva.inicio)));
    fila.appendChild(celda(formatearMomento(reserva.fin)));
    const celdaEstado = document.createElement("td");
    celdaEstado.appendChild(insigniaEstado(reserva.estado));
    fila.appendChild(celdaEstado);
    const celdaAcciones = document.createElement("td");
    if (reserva.estado === "activa") {
      celdaAcciones.appendChild(botonCancelar(reserva));
    } else {
      celdaAcciones.textContent = "—";
    }
    fila.appendChild(celdaAcciones);
    cuerpo.appendChild(fila);
  }
  tabla.appendChild(cuerpo);
  envoltorio.appendChild(tabla);
  contenedor.replaceChildren(envoltorio);
}

async function cargarReservas() {
  const contenedor = qs("#listado-reservas");
  contenedor.replaceChildren(indicadorCarga("Cargando reservas…"));
  let respuesta;
  try {
    respuesta = await fetch("/api/reservas");
  } catch (error) {
    contenedor.replaceChildren(
      estadoVacio("No se pudo conectar con el servidor para cargar las reservas.")
    );
    return;
  }
  if (!respuesta.ok) {
    contenedor.replaceChildren(estadoVacio(await mensajeDeError(respuesta)));
    return;
  }
  const cuerpo = await respuesta.json();
  renderizarReservas(cuerpo.reservas);
}

async function cancelarReserva(id, boton) {
  limpiarMensajes();
  const confirmado = window.confirm(
    `¿Cancelar la reserva ${id}? La reserva quedará en el historial con estado cancelada.`
  );
  if (!confirmado) {
    return;
  }
  await conCarga(boton, async () => {
    let respuesta;
    try {
      respuesta = await fetch(`/api/reservas/${encodeURIComponent(id)}/cancelar`, {
        method: "POST",
      });
    } catch (error) {
      mostrarMensaje(
        "danger",
        "No se pudo conectar con el servidor. La reserva no fue modificada."
      );
      return;
    }
    if (!respuesta.ok) {
      /* La reserva sigue en el listado con su estado anterior. */
      mostrarMensaje("danger", await mensajeDeError(respuesta));
      return;
    }
    const reserva = await respuesta.json();
    mostrarMensaje("success", `La reserva ${reserva.id} fue cancelada.`);
    await Promise.all([cargarReservas(), refrescarDisponibilidad()]);
  });
}

async function alCrearReserva(evento) {
  evento.preventDefault();
  limpiarMensajes();
  const unidad = qs("#res-unidad").value;
  const solicitante = qs("#res-solicitante").value.trim();
  const intervalo = leerIntervalo("res");
  /* Comprobación de completitud solo para la experiencia del usuario:
     las validaciones definitivas las hace el backend. */
  if (!unidad || !solicitante || !intervalo) {
    mostrarMensaje("warning", "Completá la unidad, el solicitante y las fechas y horas de la reserva.");
    return;
  }
  const cuerpo = {
    unidad,
    solicitante,
    desde: intervalo.desde,
    hasta: intervalo.hasta,
  };
  await conCarga(qs("#btn-reservar"), async () => {
    let respuesta;
    try {
      respuesta = await fetch("/api/reservas", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cuerpo),
      });
    } catch (error) {
      mostrarMensaje(
        "danger",
        "No se pudo conectar con el servidor. La reserva no fue creada."
      );
      return;
    }
    if (!respuesta.ok) {
      mostrarMensaje("danger", await mensajeDeError(respuesta));
      return;
    }
    const reserva = await respuesta.json();
    mostrarMensaje(
      "success",
      `Reserva ${reserva.id} creada para ${reserva.unidad} (${formatearMomento(
        reserva.inicio
      )} a ${formatearMomento(reserva.fin)}).`
    );
    qs("#form-reserva").reset();
    await Promise.all([cargarReservas(), refrescarDisponibilidad()]);
  });
}

/* ------------------------------------------------------------------ */
/* Inicio                                                              */
/* ------------------------------------------------------------------ */

async function cargarUnidadesAlSelect() {
  const selector = qs("#res-unidad");
  let respuesta;
  try {
    respuesta = await fetch("/api/unidades");
  } catch (error) {
    selector.replaceChildren();
    mostrarMensaje(
      "danger",
      "No se pudo conectar con el servidor para cargar el inventario."
    );
    return;
  }
  if (!respuesta.ok) {
    mostrarMensaje("danger", await mensajeDeError(respuesta));
    return;
  }
  const cuerpo = await respuesta.json();
  selector.replaceChildren();
  const opcionInicial = document.createElement("option");
  opcionInicial.value = "";
  opcionInicial.textContent = "Elegí una unidad…";
  selector.appendChild(opcionInicial);
  for (const unidad of cuerpo.unidades) {
    const opcion = document.createElement("option");
    opcion.value = unidad.id;
    opcion.textContent = `${unidad.id} — ${unidad.descripcion}`;
    selector.appendChild(opcion);
  }
}

async function iniciar() {
  qs("#form-disponibilidad").addEventListener("submit", alConsultarDisponibilidad);
  qs("#form-reserva").addEventListener("submit", alCrearReserva);
  await cargarUnidadesAlSelect();
  await cargarReservas();
}

document.addEventListener("DOMContentLoaded", iniciar);
