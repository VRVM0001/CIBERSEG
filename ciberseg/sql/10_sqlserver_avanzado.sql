/* =====================================================================
   CIBERSEG - OBJETOS AVANZADOS DE T-SQL
   Archivo: sql/sqlserver_avanzado.sql
   ---------------------------------------------------------------------
   QUE CONTIENE ESTE ARCHIVO (4 objetos de base de datos):
     1) sp_recalcular_totales_cotizacion  -> PROCEDIMIENTO ALMACENADO
     2) trg_detalle_totales               -> TRIGGER de negocio
     3) trg_clientes_auditoria            -> TRIGGER de auditoria
     4) vw_facturacion_mensual            -> VISTA de reporte
        vw_top_clientes                   -> VISTA de reporte

   IDEA CENTRAL DEL ARCHIVO:
     Mover logica de negocio DESDE la aplicacion HACIA la base de datos.
     Los totales de una cotizacion NO se calculan en Python: los calcula
     el motor. Asi el dato queda correcto aunque alguien inserte una
     linea directamente desde SSMS, sin pasar por la aplicacion.
     Esa es la diferencia entre "validar en la app" y "garantizar en la BD".

   COMO EJECUTARLO:
     Abrir en SSMS y presionar F5. Es seguro re-ejecutarlo cuantas veces
     haga falta, porque todos los objetos usan CREATE OR ALTER (ver nota
     mas abajo).

   REQUISITOS PREVIOS (este archivo NO los crea, deben existir ya):
     - schema.sql ejecutado (tablas cotizaciones, detalle_cotizacion,
       clientes, facturas, empresas, auditoria)
     - configuracion.sql ejecutado (tabla configuracion con 'itbis_pct')
   ===================================================================== */

USE ciberseg;
-- USE cambia la base de datos "activa" de la sesion. Sin esta linea,
-- SSMS crearia los objetos en la base que este seleccionada en el
-- desplegable de la barra de herramientas (normalmente 'master'),
-- que seria un error dificil de notar.
GO
-- GO no es T-SQL: es un separador de LOTES propio de SSMS. Corta el
-- script en bloques que se envian al servidor por separado. Es
-- obligatorio antes de cada CREATE PROCEDURE / VIEW / TRIGGER, porque
-- SQL Server exige que esas instrucciones sean la PRIMERA del lote.


/* =====================================================================
   1) PROCEDIMIENTO ALMACENADO: sp_recalcular_totales_cotizacion
   ---------------------------------------------------------------------
   Objetivo: Recalcular los tres totales de una cotizacion (subtotal,
             impuesto y total) sumando las lineas de su detalle y
             aplicando el porcentaje de ITBIS configurado.

   Parametros:
     - @cot_id INT : el id de la cotizacion a recalcular. Es de ENTRADA
                     (no lleva OUTPUT), o sea, solo recibe un valor.

   Retorno: No devuelve filas. Su EFECTO es un UPDATE sobre la fila
            correspondiente de la tabla cotizaciones.

   Formula aplicada:
       subtotal = SUMA de los subtotales de todas las lineas
       impuesto = subtotal * porcentaje_itbis / 100
       total    = subtotal + impuesto

   Por que es un PROCEDIMIENTO y no codigo Python:
     Porque asi se puede invocar desde DOS lugares distintos sin
     duplicar la formula: (a) desde el trigger de mas abajo, de forma
     automatica, y (b) a mano desde SSMS si hiciera falta reparar una
     cotizacion. Un solo lugar con la formula = un solo lugar que
     corregir si el calculo cambia.

   Como probarlo manualmente en SSMS:
       EXEC sp_recalcular_totales_cotizacion 1;
       SELECT subtotal, impuesto, total FROM cotizaciones WHERE id = 1;
   ===================================================================== */
CREATE OR ALTER PROCEDURE sp_recalcular_totales_cotizacion @cot_id INT AS
-- CREATE OR ALTER: si el procedimiento no existe lo crea, y si ya
-- existe lo reemplaza. Es lo que hace que el script sea re-ejecutable
-- sin dar el error "ya existe un objeto con ese nombre".
BEGIN
  SET NOCOUNT ON;
  -- Suprime los mensajes "(N rows affected)" que el motor envia tras
  -- cada instruccion. No es cosmetico: esos mensajes viajan por la red
  -- y algunos drivers (pyodbc entre ellos) los interpretan como si
  -- fueran un resultado, lo que rompe la lectura de datos reales.

  DECLARE @sub DECIMAL(12,2) =
    (SELECT COALESCE(SUM(subtotal),0) FROM detalle_cotizacion WHERE cotizacion_id=@cot_id);
  -- DECLARE crea una variable local (solo vive dentro de esta ejecucion).
  -- DECIMAL(12,2) = hasta 12 digitos en total, 2 de ellos decimales.
  --   Se usa DECIMAL y no FLOAT porque el dinero exige precision exacta:
  --   FLOAT es binario y arrastra errores de redondeo (0.1 + 0.2 != 0.3).
  -- SUM(subtotal) suma el subtotal de todas las lineas de esa cotizacion.
  -- COALESCE(...,0) devuelve 0 cuando SUM da NULL. SUM sobre CERO filas
  --   devuelve NULL, no 0. Sin este COALESCE, borrar la ultima linea de
  --   una cotizacion dejaria sus totales en NULL en vez de en 0.

  DECLARE @pct DECIMAL(5,2) =
    COALESCE((SELECT TRY_CAST(valor AS DECIMAL(5,2)) FROM configuracion WHERE clave='itbis_pct'),18);
  -- Lee el porcentaje de impuesto desde la tabla configuracion, para que
  -- el administrador pueda cambiarlo desde la pantalla de Configuracion
  -- sin tocar el codigo ni este script.
  -- La columna 'valor' es VARCHAR(255) (guarda cualquier parametro del
  -- sistema como texto), por eso hay que convertirla a numero.
  -- TRY_CAST intenta la conversion y devuelve NULL si falla, en vez de
  --   reventar con un error. Si alguien guardara "dieciocho" en esa
  --   clave, CAST normal abortaria el procedimiento; TRY_CAST no.
  -- COALESCE(...,18) es la red de seguridad final: si la clave no existe
  --   o la conversion fallo, se asume el 18% de Republica Dominicana.

  UPDATE cotizaciones SET subtotal=@sub, impuesto=ROUND(@sub*@pct/100,2),
         total=ROUND(@sub*(1+@pct/100),2), updated_at=SYSDATETIME() WHERE id=@cot_id;
  -- Escribe los tres totales en la cotizacion, en UNA sola instruccion.
  -- ROUND(x, 2) redondea a 2 decimales: sin esto, @sub*@pct/100 podria
  --   arrastrar mas decimales de los que la columna admite.
  -- @sub*(1+@pct/100) calcula el total directamente desde el subtotal,
  --   en lugar de sumar subtotal + impuesto ya redondeado. Se hace asi
  --   para evitar acumular el error de redondeo del impuesto.
  -- updated_at=SYSDATETIME() deja constancia de cuando cambio la fila.
  --   SYSDATETIME() es mas preciso que GETDATE() (nanosegundos vs 3 ms)
  --   y devuelve DATETIME2, que es el tipo de la columna.
  -- WHERE id=@cot_id: sin este WHERE, el UPDATE afectaria a TODAS las
  --   cotizaciones de la tabla.
END;
GO


/* =====================================================================
   2) TRIGGER DE NEGOCIO: trg_detalle_totales
   ---------------------------------------------------------------------
   Objetivo: Mantener los totales de la cotizacion SIEMPRE sincronizados
             con sus lineas de detalle, sin que nadie tenga que acordarse
             de recalcularlos.

   Tabla vigilada: detalle_cotizacion
   Momento: AFTER (despues de que el cambio ya ocurrio)
   Eventos: INSERT, UPDATE y DELETE (los tres)

   Por que los tres eventos:
     - INSERT: se agrego una linea  -> el total sube
     - UPDATE: cambio una cantidad  -> el total cambia
     - DELETE: se quito una linea   -> el total baja
     En los tres casos el total guardado quedaria desactualizado.

   LAS TABLAS 'inserted' Y 'deleted' (concepto clave para la defensa):
     Dentro de un trigger, SQL Server crea dos tablas virtuales en memoria:
       inserted = como quedaron las filas DESPUES del cambio
       deleted  = como estaban las filas ANTES del cambio
     Se llenan asi segun la operacion:
       INSERT -> inserted tiene datos, deleted esta vacia
       DELETE -> inserted esta vacia, deleted tiene datos
       UPDATE -> AMBAS tienen datos (deleted = valor viejo, inserted = nuevo)

   PUNTO MAS IMPORTANTE DE ESTE TRIGGER:
     Un trigger se dispara UNA VEZ POR INSTRUCCION, no una vez por fila.
     Si alguien ejecuta un INSERT que agrega 10 lineas de 3 cotizaciones
     distintas, el trigger corre UNA sola vez con las 10 filas dentro de
     'inserted'. Por eso hace falta recorrer las cotizaciones afectadas
     una por una: es el motivo de que exista el cursor de mas abajo.
   ===================================================================== */
CREATE OR ALTER TRIGGER trg_detalle_totales ON detalle_cotizacion
AFTER INSERT, UPDATE, DELETE AS
BEGIN
  SET NOCOUNT ON;
  -- Aqui es todavia mas necesario que en el procedimiento: los mensajes
  -- de conteo que genere el trigger se mezclarian con los de la
  -- instruccion original que lo disparo, confundiendo al driver.

  DECLARE @id INT;
  -- Variable donde se ira guardando, de una en una, cada cotizacion
  -- afectada por el cambio.

  DECLARE c CURSOR LOCAL FOR
    SELECT DISTINCT cotizacion_id FROM inserted
    UNION SELECT DISTINCT cotizacion_id FROM deleted;
  -- Un CURSOR permite recorrer un resultado FILA POR FILA (T-SQL trabaja
  --   normalmente con conjuntos completos, no fila a fila).
  -- LOCAL limita el cursor a este lote: se destruye solo al terminar y no
  --   choca con otro cursor del mismo nombre en otra sesion.
  -- La consulta arma la lista de cotizaciones a recalcular:
  --   * FROM inserted -> cubre INSERT y el lado nuevo de UPDATE
  --   * FROM deleted  -> cubre DELETE y el lado viejo de UPDATE
  --   Ambas son necesarias: si una linea se MOVIO de la cotizacion 5 a la
  --   7, hay que recalcular las DOS, y cada tabla virtual conoce solo una.
  -- UNION (no UNION ALL) elimina los duplicados automaticamente, asi una
  --   misma cotizacion no se recalcula dos veces innecesariamente.
  -- DISTINCT hace lo mismo dentro de cada lado, antes de unirlos.

  OPEN c; FETCH NEXT FROM c INTO @id;
  -- OPEN ejecuta la consulta del cursor y lo deja listo.
  -- FETCH NEXT saca la siguiente fila y guarda su valor en @id.
  -- Este primer FETCH es el que "carga la primera fila" antes del bucle.

  WHILE @@FETCH_STATUS = 0
  -- @@FETCH_STATUS es una variable del sistema que indica como salio el
  -- ultimo FETCH: 0 = trajo una fila correctamente, -1 = ya no hay mas.
  -- Es la condicion estandar para recorrer un cursor completo.
  BEGIN EXEC sp_recalcular_totales_cotizacion @id; FETCH NEXT FROM c INTO @id; END;
  -- Por cada cotizacion afectada: se llama al procedimiento del punto 1
  --   (AQUI se reutiliza la formula, en vez de repetirla) y se avanza a
  --   la siguiente. Sin ese segundo FETCH, el bucle seria infinito.

  CLOSE c; DEALLOCATE c;
  -- CLOSE libera las filas del cursor; DEALLOCATE elimina el cursor de
  -- memoria. Omitirlos deja recursos ocupados en el servidor.
END;
GO


/* =====================================================================
   3) TRIGGER DE AUDITORIA: trg_clientes_auditoria
   ---------------------------------------------------------------------
   Objetivo: Registrar en la tabla 'auditoria' cualquier cambio sobre la
             tabla clientes, HAYA PASADO O NO por la aplicacion.

   Por que existe si la aplicacion ya audita (seguridad.py):
     Este es el punto de la AUDITORIA POR PARTIDA DOBLE del proyecto.
       - registrar_auditoria() en Python sabe QUIEN hizo el cambio (lee
         el usuario de la sesion) pero solo se entera de lo que pasa
         por la aplicacion.
       - Este trigger no sabe quien fue (no hay sesion web), pero NO SE
         LE ESCAPA NADA: si un administrador edita un cliente
         directamente en SSMS, la aplicacion nunca se entera, y el
         trigger si lo registra.
     Se complementan: uno aporta identidad, el otro aporta cobertura total.

   Tabla vigilada: clientes
   Eventos: INSERT, UPDATE, DELETE
   ===================================================================== */
CREATE OR ALTER TRIGGER trg_clientes_auditoria ON clientes
AFTER INSERT, UPDATE, DELETE AS
BEGIN
  SET NOCOUNT ON;

  INSERT INTO auditoria (tabla_afectada, accion, registro_id, datos_nuevos)
  SELECT 'clientes',
  -- INSERT ... SELECT (no INSERT ... VALUES): inserta TANTAS filas de
  -- auditoria como filas haya afectado la operacion, en una sola
  -- instruccion. Vuelve a aplicar la regla "el trigger corre una vez por
  -- instruccion, no por fila".
  -- 'clientes' es un valor fijo: se repite igual en cada fila generada.

         CASE WHEN EXISTS(SELECT 1 FROM deleted) AND EXISTS(SELECT 1 FROM inserted)
              THEN 'UPDATE'
              WHEN EXISTS(SELECT 1 FROM inserted) THEN 'INSERT' ELSE 'DELETE' END,
  -- DEDUCCION DE LA OPERACION. El trigger atiende los tres eventos con un
  -- solo bloque de codigo, asi que debe averiguar cual ocurrio. Se deduce
  -- justamente de la combinacion de inserted/deleted explicada arriba:
  --     hay deleted Y hay inserted -> fue un UPDATE
  --     solo hay inserted          -> fue un INSERT
  --     no hay inserted            -> fue un DELETE
  -- El ORDEN del CASE importa: UPDATE debe evaluarse primero, porque en un
  --   UPDATE tambien "hay inserted" y caeria por error en la rama INSERT.
  -- EXISTS(SELECT 1 ...) es la forma estandar de preguntar "hay al menos
  --   una fila?": el motor deja de buscar en cuanto encuentra la primera,
  --   a diferencia de COUNT(*), que las recorreria todas.
  -- El texto resultante encaja con el CHECK de la columna 'accion', que
  --   solo admite 'INSERT', 'UPDATE' o 'DELETE'.

         COALESCE(i.id, d.id), '{"origen": "trigger BD"}'
  -- COALESCE(i.id, d.id) toma el id de 'inserted' y, si es NULL (caso
  --   DELETE, donde no hay fila nueva), usa el de 'deleted'. Asi siempre
  --   queda registrado a que cliente correspondio el evento.
  -- La cadena JSON fija marca el ORIGEN del registro. Es lo que permite
  --   distinguir despues, en la pantalla de Auditoria, un evento
  --   capturado por el motor de uno registrado por la aplicacion.

  FROM inserted i FULL OUTER JOIN deleted d ON d.id = i.id;
  -- FULL OUTER JOIN es la unica union que conserva las filas de AMBOS
  -- lados aunque no tengan pareja del otro. Es exactamente lo que se
  -- necesita para cubrir los tres casos con una sola consulta:
  --     INSERT -> filas solo en i (d queda en NULL)
  --     DELETE -> filas solo en d (i queda en NULL)
  --     UPDATE -> filas emparejadas por id en ambos lados
  -- Con un JOIN normal (INNER), los INSERT y los DELETE no se
  -- registrarian, porque no tienen contraparte para emparejar.
END;
GO


/* =====================================================================
   4) VISTAS PARA REPORTES
   ---------------------------------------------------------------------
   Que es una VISTA: una consulta guardada con nombre, que se usa despues
   como si fuera una tabla. No almacena datos propios; los recalcula en
   cada consulta a partir de las tablas reales.

   Para que sirven aqui:
     - Simplifican: la aplicacion pide "SELECT * FROM vw_top_clientes" en
       vez de repetir un JOIN de tres tablas con agrupacion.
     - Dan SEGURIDAD: en transacciones_y_seguridad.sql se le concede al
       usuario 'reportes_user' permiso de lectura SOLO sobre estas vistas.
       Ese usuario puede ver los totales facturados, pero no tiene acceso
       a la tabla clientes ni a facturas. Es la aplicacion practica del
       principio de minimo privilegio.
   ===================================================================== */

/* ---------------------------------------------------------------------
   VISTA 1: vw_facturacion_mensual
   Objetivo: Total facturado y cantidad de facturas, agrupado por mes.
   Consumida por: el grafico "Facturacion por mes" del dashboard.
   Columnas que devuelve: mes (texto 'AAAA-MM'), total, facturas
   --------------------------------------------------------------------- */
CREATE OR ALTER VIEW vw_facturacion_mensual AS
  SELECT FORMAT(fecha_emision,'yyyy-MM') AS mes, SUM(total) AS total, COUNT(*) AS facturas
  -- FORMAT(fecha,'yyyy-MM') convierte una fecha a texto tipo '2026-08'.
  --   Ese recorte es lo que permite agrupar por mes: todas las facturas de
  --   agosto de 2026 producen la misma cadena y caen en el mismo grupo.
  --   'yyyy-MM' ordena correctamente como texto, algo que 'MM-yyyy' no haria.
  -- SUM(total) suma el importe; COUNT(*) cuenta cuantas facturas hubo.
  -- AS renombra cada columna calculada para que tenga un nombre usable.
  FROM facturas WHERE estado='Pagada' GROUP BY FORMAT(fecha_emision,'yyyy-MM');
  -- WHERE estado='Pagada' filtra ANTES de agrupar: se reporta el dinero
  --   realmente cobrado, no el emitido. Una factura pendiente o anulada
  --   no es un ingreso.
  -- GROUP BY debe repetir la misma expresion FORMAT(...) del SELECT: SQL
  --   Server no permite agrupar por el alias 'mes', porque los alias se
  --   resuelven despues del GROUP BY en el orden de ejecucion.
GO

/* ---------------------------------------------------------------------
   VISTA 2: vw_top_clientes
   Objetivo: Ranking de los 10 clientes que mas dinero han pagado.
   Consumida por: el bloque "Mayores clientes por facturacion" del dashboard.
   Columnas que devuelve: nombre (de la empresa), facturado (suma en USD)
   --------------------------------------------------------------------- */
CREATE OR ALTER VIEW vw_top_clientes AS
  SELECT TOP 10 e.nombre, SUM(f.total) AS facturado
  -- TOP 10 limita el resultado a las diez primeras filas.
  -- Se muestra e.nombre (el de la EMPRESA) y no un dato de clientes,
  --   porque la tabla clientes solo guarda el codigo (CLI-0001) y la
  --   relacion comercial; el nombre legible vive en empresas.
  FROM facturas f JOIN clientes c ON c.id=f.cliente_id JOIN empresas e ON e.id=c.empresa_id
  -- DOBLE JOIN ENCADENADO, que recorre el modelo entidad-relacion:
  --     facturas -> clientes -> empresas
  --   Hay que pasar por clientes porque facturas no apunta a empresas
  --   directamente: guarda cliente_id, y es el cliente quien pertenece a
  --   una empresa. Es el camino que marcan las llaves foraneas.
  -- f, c y e son ALIAS de tabla: acortan la escritura y evitan ambiguedad
  --   cuando dos tablas tienen columnas con el mismo nombre (aqui, 'id'
  --   y 'nombre' existen en varias).
  WHERE f.estado='Pagada' GROUP BY e.nombre ORDER BY facturado DESC;
  -- WHERE f.estado='Pagada': mismo criterio que la vista anterior, solo
  --   se cuenta lo efectivamente cobrado.
  -- GROUP BY e.nombre: junta todas las facturas de una misma empresa en
  --   una sola fila con su total acumulado.
  -- ORDER BY facturado DESC: de mayor a menor, para que TOP 10 se quede
  --   con los diez MEJORES y no con diez cualesquiera.
  -- NOTA TECNICA (util si el profesor pregunta): SQL Server solo admite
  --   ORDER BY dentro de una vista si va acompanado de TOP, como aqui.
  --   Aun asi, el orden garantizado es el de la seleccion interna: al
  --   consultar la vista conviene repetir el ORDER BY si se necesita que
  --   el resultado salga ordenado.
GO

PRINT 'Objetos avanzados creados: 1 proc, 2 triggers, 2 vistas.';
-- PRINT escribe un mensaje en la pestana "Messages" de SSMS. Sirve como
-- confirmacion visual de que el script llego hasta el final sin errores.
GO
