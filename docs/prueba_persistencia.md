# Prueba manual de persistencia (Windows)

Procedimiento para verificar en tu computadora que las reservas se
conservan al detener y reiniciar la aplicación (caso 12 de la consigna).
Complementa a `tests/test_persistencia.py`, que lo automatiza con dos
instancias de la aplicación sobre una base temporal.

## Ruta de la base de datos

La aplicación guarda los datos en:

```
<carpeta del proyecto>\data\reservas.db
```

La ruta se calcula a partir de la ubicación del archivo `app/__init__.py`
(no del directorio de trabajo), de modo que aunque lances `python run.py`
desde otra carpeta, la base siempre será la misma y no se creará una
segunda por accidente. El directorio `data\` se crea solo en el primer
arranque y está excluido del repositorio por `.gitignore`.

## Procedimiento

1. **Iniciar la aplicación.** Abrí PowerShell en la carpeta del proyecto y
   ejecutá:

   ```powershell
   .\.venv\Scripts\python.exe run.py
   ```

   (No hace falta activar el entorno virtual: se usa directamente el
   intérprete del venv.) Deberías ver el servidor en
   `http://127.0.0.1:5000`.

2. **Crear una reserva activa.** Abrí `http://127.0.0.1:5000/` en el
   navegador. En «Nueva reserva» elegí la unidad `MIC-01`, escribí un
   solicitante (por ejemplo `Prueba persistencia`) y cargá una fecha y
   hora de inicio y fin **futuras** (por ejemplo, mañana de 10:00 a
   11:00; recordá la duración mínima de 10 minutos). Pulsá «Crear
   reserva»: debe aparecer el aviso con el identificador (por ejemplo
   `RES-001`) y la reserva como **Activa** en el historial. Anotá ese
   identificador.

3. **Crear y cancelar otra reserva.** Creá una segunda reserva con otra
   unidad (por ejemplo `MIC-02`, mismo solicitante u otro) y anotá su
   identificador (por ejemplo `RES-002`). Después pulsá «Cancelar» en su
   fila y confirmá: debe quedar como **Cancelada** en el historial.

4. **Detener el servidor.** Volvé a la terminal y pulsá `Ctrl + C`.
   Esperá a que el proceso termine. **No borres ni muevas
   `data\reservas.db`.**

5. **Volver a iniciar la aplicación.** Ejecutá nuevamente:

   ```powershell
   .\.venv\Scripts\python.exe run.py
   ```

   y recargá `http://127.0.0.1:5000/` en el navegador.

6. **Comprobar el historial.** En «Historial de reservas» deben seguir
   estando ambas reservas, con los mismos identificadores, unidades,
   solicitantes, fechas y estados que anotaste: la primera **Activa** y
   la segunda **Cancelada**.

7. **Comprobar la disponibilidad.** En «Consulta de disponibilidad»:
   - Consultá el intervalo de la reserva activa (paso 2): `MIC-01` debe
     aparecer como **Reservada** y las demás unidades como Disponibles.
   - Consultá el intervalo de la reserva cancelada (paso 3): `MIC-02`
     debe aparecer como **Disponible**, porque una reserva cancelada deja
     de bloquear.

## Resultado esperado

Si los pasos 6 y 7 se cumplen, la persistencia entre reinicios queda
verificada en tu entorno, igual que lo automatiza
`tests/test_persistencia.py`.

## Notas

- Para "empezar de cero" podés borrar `data\reservas.db` con la
  aplicación detenida; el próximo arranque recrea el esquema y el
  inventario. Durante esta prueba, no lo hagas.
- La inicialización es idempotente: reiniciar la aplicación no duplica
  unidades ni borra reservas.
