/* =====================================================================
   CIBERSEG - Unidad 5 aplicada: TRANSACCIONES (ACID) + SEGURIDAD (DCL)
   + Funcion definida por usuario (Unidad 4 Parte II)
   Ejecutar UNA vez en SSMS. Seguro de re-ejecutar.
   =====================================================================

   CONTENIDO Y CONCEPTOS QUE DEMUESTRA CADA PARTE:

     1. fn_total_facturado      -> FUNCION DEFINIDA POR USUARIO (UDF)
     2. sp_aprobar_y_facturar   -> TRANSACCION ACID + control de concurrencia
     3. sp_registrar_pago       -> TRANSACCION con validacion de estados
     4. GRANT / REVOKE          -> SEGURIDAD DCL (control de acceso)

   QUE SIGNIFICA ACID (marco teorico de las partes 2 y 3):
     Atomicidad   -> o se hace TODO o no se hace NADA. Es lo que garantiza
                     el par COMMIT / ROLLBACK.
     Consistencia -> la base pasa de un estado valido a otro valido. Aqui
                     lo aseguran los THROW que validan antes de escribir.
     Aislamiento  -> dos operaciones simultaneas no se estorban. Aqui se
                     refuerza con el bloqueo UPDLOCK.
     Durabilidad  -> lo confirmado con COMMIT sobrevive incluso a un corte
                     de energia; el motor lo garantiza por su registro de
                     transacciones.

   POR QUE HACEN FALTA TRANSACCIONES:
     Aprobar una cotizacion y crear su factura son DOS escrituras. Si la
     primera funciona y la segunda falla (por un corte de red, por
     ejemplo), quedaria una cotizacion aprobada sin factura: la base en un
     estado incoherente. La transaccion impide ese escenario.

   REQUISITOS PREVIOS: schema.sql y vistas_y_triggers.sql (la parte 4
   concede permisos sobre vistas creadas alli).
   ===================================================================== */
USE ciberseg;
GO

/* =============== 1. FUNCION DEFINIDA POR USUARIO (UDF) ===============
   Escalar: devuelve el total facturado (pagado) de un cliente.
   A diferencia de un procedimiento, se usa DENTRO de consultas.
   ---------------------------------------------------------------------
   DIFERENCIA ENTRE FUNCION Y PROCEDIMIENTO (pregunta clasica):
     - La FUNCION devuelve un valor y se usa dentro de un SELECT, un WHERE
       o un ORDER BY, como si fuera una columna calculada. No puede
       modificar datos.
     - El PROCEDIMIENTO se invoca aparte con EXEC, no se puede incrustar en
       una consulta, y si puede modificar datos (INSERT/UPDATE/DELETE).
   "Escalar" significa que devuelve UN solo valor, no una tabla.

   Parametros: @cliente_id INT - de que cliente se quiere el total.
   Retorno: DECIMAL(12,2) con la suma de sus facturas pagadas, o 0.

   Como usarla:
     SELECT codigo, dbo.fn_total_facturado(id) AS facturado FROM clientes;
     (las funciones escalares se llaman con el prefijo del esquema: dbo.)
   ===================================================================== */
CREATE OR ALTER FUNCTION fn_total_facturado (@cliente_id INT)
RETURNS DECIMAL(12,2)
-- RETURNS declara el TIPO del valor que la funcion devolvera. Es
-- obligatorio y el motor lo exige cumplir.
AS
BEGIN
  DECLARE @total DECIMAL(12,2);
  -- Variable interna donde se acumula el resultado antes de devolverlo.
  SELECT @total = COALESCE(SUM(total),0)
  -- SELECT @variable = ... es la forma de ASIGNAR el resultado de una
  -- consulta a una variable, en vez de mostrarlo en pantalla.
  -- COALESCE(...,0): SUM sobre cero filas devuelve NULL, no 0. Sin esto,
  -- un cliente sin facturas pagadas devolveria NULL y cualquier suma
  -- posterior que lo incluyera daria NULL tambien.
  FROM facturas WHERE cliente_id = @cliente_id AND estado = 'Pagada';
  -- Doble filtro: solo las facturas DE ESE CLIENTE y solo las COBRADAS. Una
  -- factura pendiente o anulada no es dinero recibido.
  RETURN @total;
  -- RETURN entrega el valor y termina la funcion.
END;
GO

/* =============== 2. TRANSACCION ATOMICA (BEGIN/COMMIT/ROLLBACK) ======
   Aprueba una cotizacion Y genera su factura como UNA SOLA unidad:
   si cualquier paso falla, TODO se deshace (atomicidad).
   ---------------------------------------------------------------------
   Parametros: @cot_id INT - la cotizacion a aprobar y facturar.
   Efecto: deja la cotizacion en estado 'Aprobada' y crea su factura.
   Errores que controla:
     50001 - la cotizacion no existe
     50002 - esta Rechazada o Vencida (no se puede aprobar)
     50003 - ya tiene factura (evita facturar dos veces lo mismo)

   Como probarlo:
     EXEC sp_aprobar_y_facturar 3;
     EXEC sp_aprobar_y_facturar 3;   -- la segunda vez debe fallar con 50003
   ===================================================================== */
CREATE OR ALTER PROCEDURE sp_aprobar_y_facturar @cot_id INT
AS
BEGIN
  SET NOCOUNT ON;
  BEGIN TRY
  -- BEGIN TRY ... END TRY delimita el codigo "que puede fallar". Si dentro
  -- ocurre cualquier error, la ejecucion salta INMEDIATAMENTE al bloque
  -- CATCH del final, sin ejecutar lo que quedaba.
    BEGIN TRANSACTION;   -- inicia la unidad atomica
    -- A partir de aqui, nada se guarda de forma definitiva hasta el COMMIT.
    -- Todos los cambios quedan en un estado provisional que puede
    -- deshacerse por completo.

      DECLARE @estado VARCHAR(20), @cliente INT,
              @sub DECIMAL(12,2), @imp DECIMAL(12,2), @tot DECIMAL(12,2);
      -- Variables donde se guardan los datos de la cotizacion para poder
      -- copiarlos despues a la factura. Un solo DECLARE puede declarar
      -- varias separadas por coma.
      SELECT @estado = estado, @cliente = cliente_id,
             @sub = subtotal, @imp = impuesto, @tot = total
      FROM cotizaciones WITH (UPDLOCK)   -- bloqueo exclusivo (control de concurrencia)
      -- WITH (UPDLOCK) es una SUGERENCIA DE BLOQUEO. Reserva la fila para
      -- esta transaccion desde el momento de leerla, no solo al escribirla.
      -- QUE PROBLEMA EVITA: si dos usuarios pulsan "Generar factura" sobre
      -- la misma cotizacion en el mismo instante, ambos leerian "no tiene
      -- factura" y ambos crearian una. Con UPDLOCK, el segundo espera a que
      -- el primero termine, y al continuar ya encuentra la factura creada y
      -- se detiene con el error 50003. Es la aplicacion practica del
      -- AISLAMIENTO de ACID.
      WHERE id = @cot_id;

      IF @estado IS NULL
        THROW 50001, 'La cotizacion no existe.', 1;
      -- Si el SELECT no encontro nada, las variables quedan en NULL. Esa es
      -- la forma de detectar que el id recibido no corresponde a ninguna
      -- cotizacion.
      -- THROW numero, mensaje, estado: lanza un error controlado. Los
      -- codigos propios deben ser 50000 o mayores; por debajo estan
      -- reservados para el sistema.
      IF @estado IN ('Rechazada','Vencida')
        THROW 50002, 'No se puede aprobar una cotizacion Rechazada o Vencida.', 1;
      -- REGLA DE NEGOCIO: un documento ya descartado no puede revivir y
      -- facturarse. 'Borrador' y 'Enviada' si pueden aprobarse.
      IF EXISTS (SELECT 1 FROM facturas WHERE cotizacion_id = @cot_id)
        THROW 50003, 'La cotizacion ya tiene factura.', 1;
      -- Evita la doble facturacion. EXISTS deja de buscar en cuanto
      -- encuentra la primera coincidencia, por eso es mas eficiente que
      -- contar con COUNT(*).
      -- LAS TRES VALIDACIONES VAN ANTES DE ESCRIBIR NADA: es preferible
      -- detenerse antes de tocar la base que tener que deshacer cambios.

      UPDATE cotizaciones SET estado = 'Aprobada', updated_at = SYSDATETIME()
      WHERE id = @cot_id;
      -- PRIMERA ESCRITURA de la transaccion.

      DECLARE @num VARCHAR(20) =
        CONCAT('FAC-', YEAR(GETDATE()), '-',
               RIGHT('0000' + CAST((SELECT ISNULL(MAX(id),0)+1 FROM facturas) AS VARCHAR), 4));
      -- GENERACION DEL NUMERO DE FACTURA, de dentro hacia afuera:
      --   1. MAX(id) FROM facturas  -> el id mas alto existente
      --   2. ISNULL(...,0)          -> si la tabla esta vacia, MAX da NULL;
      --                                se sustituye por 0
      --   3. +1                     -> el numero que le tocaria a la nueva
      --   4. CAST(... AS VARCHAR)   -> se convierte a texto para poder
      --                                pegarlo con otros textos
      --   5. '0000' + ese texto     -> se le anteponen cuatro ceros
      --   6. RIGHT(..., 4)          -> se toman solo los 4 caracteres de la
      --                                derecha. Este par de pasos es el
      --                                truco clasico para RELLENAR CON
      --                                CEROS A LA IZQUIERDA: 7 -> '0007',
      --                                123 -> '0123'
      --   7. CONCAT con 'FAC-' y el ano -> 'FAC-2026-0007'
      -- NOTA HONESTA: usar MAX(id)+1 es sencillo pero no es infalible en un
      -- entorno de mucha concurrencia. Aqui es seguro porque ocurre DENTRO
      -- de la transaccion y con la cotizacion ya bloqueada.
      INSERT INTO facturas (numero, cotizacion_id, cliente_id, fecha_emision,
                            fecha_vencimiento, subtotal, impuesto, total, estado)
      VALUES (@num, @cot_id, @cliente, CAST(GETDATE() AS DATE),
              DATEADD(DAY,30,CAST(GETDATE() AS DATE)), @sub, @imp, @tot, 'Pendiente');
      -- SEGUNDA ESCRITURA. Los importes se copian tal cual de la cotizacion
      -- (las variables leidas al principio): la factura CONGELA esos
      -- valores y ya no cambiara aunque la cotizacion se edite despues.
      -- CAST(GETDATE() AS DATE) -> hoy, sin la hora.
      -- DATEADD(DAY,30,...)     -> vencimiento a 30 dias, la condicion de
      --                            pago habitual del negocio.
      -- Nace 'Pendiente': emitida pero aun no cobrada.

    COMMIT TRANSACTION;  -- exito: cambios permanentes (persistencia)
    -- Solo al llegar aqui las DOS escrituras se vuelven definitivas, y lo
    -- hacen juntas. Es el punto donde se cumple la atomicidad.
    PRINT CONCAT('Transaccion exitosa: cotizacion aprobada y factura ', @num, ' creada.');
  END TRY
  BEGIN CATCH
  -- Todo error ocurrido dentro del TRY aterriza aqui: tanto los THROW
  -- propios como cualquier fallo inesperado del motor.
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;   -- fallo: se deshace TODO
    -- @@TRANCOUNT es una variable del sistema que indica cuantas
    -- transacciones hay abiertas en esta sesion. Se comprueba antes de
    -- deshacer porque intentar un ROLLBACK sin transaccion abierta seria,
    -- a su vez, otro error.
    -- ROLLBACK devuelve la base al estado exacto que tenia antes del BEGIN
    -- TRANSACTION: si el INSERT de la factura fallo, el UPDATE de la
    -- cotizacion tambien se deshace. Nunca queda a medias.
    PRINT CONCAT('Transaccion revertida (ROLLBACK): ', ERROR_MESSAGE());
    -- ERROR_MESSAGE() devuelve el texto del error que provoco el salto.
    THROW;
    -- THROW sin argumentos RE-LANZA el error original hacia quien llamo al
    -- procedimiento. Es imprescindible: sin esta linea, la aplicacion
    -- creeria que todo salio bien, porque el error se habria quedado
    -- silenciado aqui dentro.
  END CATCH
END;
GO

/* =============== 3. TRANSACCION: registrar pago con validacion =======
   ---------------------------------------------------------------------
   Parametros: @factura_id INT - la factura que se marca como cobrada.
   Efecto: cambia su estado a 'Pagada'.
   Errores: 50010 no existe / 50011 esta Anulada / 50012 ya estaba pagada.

   Aunque solo modifica UNA tabla, se envuelve en transaccion igualmente:
   asi el bloqueo y la validacion forman una unidad indivisible y dos
   usuarios no pueden cobrar la misma factura a la vez.
   ===================================================================== */
CREATE OR ALTER PROCEDURE sp_registrar_pago @factura_id INT
AS
BEGIN
  SET NOCOUNT ON;
  BEGIN TRY
    BEGIN TRANSACTION;
      DECLARE @estado VARCHAR(20);
      SELECT @estado = estado FROM facturas WITH (UPDLOCK) WHERE id = @factura_id;
      -- Mismo bloqueo de lectura que en el procedimiento anterior: reserva
      -- la factura desde que se lee, para que nadie la modifique en el
      -- intervalo entre la comprobacion y la escritura.
      IF @estado IS NULL THROW 50010, 'La factura no existe.', 1;
      IF @estado = 'Anulada' THROW 50011, 'No se puede pagar una factura Anulada.', 1;
      -- Una factura anulada carece de validez: cobrarla seria un error contable.
      IF @estado = 'Pagada'  THROW 50012, 'La factura ya esta pagada.', 1;
      -- Evita registrar dos veces el mismo cobro, lo que descuadraria los
      -- ingresos del dashboard.
      UPDATE facturas SET estado='Pagada', updated_at=SYSDATETIME() WHERE id=@factura_id;
      -- Este UPDATE dispara ademas el trigger trg_facturas_auditoria, que
      -- deja el cambio de estado registrado en la bitacora sin que este
      -- procedimiento tenga que ocuparse de ello.
    COMMIT TRANSACTION;
    PRINT 'Pago registrado (COMMIT).';
  END TRY
  BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    PRINT CONCAT('ROLLBACK: ', ERROR_MESSAGE());
    THROW;
  END CATCH
END;
GO

/* =============== 4. SEGURIDAD DCL: GRANT / REVOKE =====================
   Mecanismo discrecional: usuario de SOLO LECTURA para reportes.
   ---------------------------------------------------------------------
   QUE ES DCL: Data Control Language, el tercer grupo de instrucciones de
   SQL, dedicado a los PERMISOS.
     DDL (Definicion)  -> CREATE, ALTER, DROP
     DML (Manipulacion)-> SELECT, INSERT, UPDATE, DELETE
     DCL (Control)     -> GRANT, REVOKE, DENY

   POR QUE "DISCRECIONAL": el control de acceso discrecional (DAC) es aquel
   en que el propietario del objeto decide a quien concede permisos, uno
   por uno, en lugar de venir impuestos por una clasificacion global.

   ESCENARIO REAL QUE RESUELVE: el area de finanzas necesita consultar los
   reportes de facturacion, pero no debe poder ver la tabla de usuarios ni
   modificar nada. Se le crea un acceso que SOLO puede leer las vistas
   autorizadas. Es el principio de MINIMO PRIVILEGIO llevado al motor.

   DIFERENCIA ENTRE LOGIN Y USER (suele preguntarse):
     LOGIN = identidad a nivel de SERVIDOR: permite conectarse.
     USER  = identidad dentro de UNA base de datos concreta: permite hacer
             cosas alli. Un login sin user puede conectarse al servidor
             pero no entrar a la base.
   ===================================================================== */
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = 'reportes_login')
-- sys.server_principals es el catalogo del sistema que lista todos los
-- logins del servidor. Se consulta para no intentar crear uno que ya exista.
  CREATE LOGIN reportes_login WITH PASSWORD = 'Reportes#2026', CHECK_POLICY = OFF;
  -- Crea la identidad de servidor con autenticacion propia de SQL Server.
  -- CHECK_POLICY = OFF desactiva la exigencia de las politicas de
  -- complejidad y caducidad de contrasenas de Windows. Se hace aqui para
  -- que el script funcione en cualquier equipo de pruebas; EN PRODUCCION
  -- debe dejarse en ON.
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'reportes_user')
-- sys.database_principals es el equivalente, pero de los usuarios DENTRO de
-- la base de datos actual.
  CREATE USER reportes_user FOR LOGIN reportes_login;
  -- Vincula el login del servidor con un usuario dentro de 'ciberseg'.
  -- Al crearse asi, el usuario NO recibe ningun permiso: parte de cero y
  -- solo tendra lo que se le conceda expresamente a continuacion.
GO
GRANT SELECT ON vw_facturacion_mensual   TO reportes_user;
-- GRANT permiso ON objeto TO usuario. Se concede SELECT (solo lectura) y
-- solo sobre VISTAS, nunca sobre las tablas.
-- POR QUE SOBRE VISTAS Y NO SOBRE TABLAS: la vista actua de filtro. A
-- traves de vw_facturacion_mensual, este usuario ve los totales mensuales,
-- pero no puede consultar la tabla facturas, ni clientes, ni ninguna otra.
-- Se le da exactamente el dato que necesita y nada mas.
GRANT SELECT ON vw_top_clientes          TO reportes_user;
GRANT SELECT ON vw_cotizaciones_detalle  TO reportes_user;
GRANT SELECT ON vw_cartera_ejecutivos    TO reportes_user;
GRANT SELECT ON vw_clientes_resumen      TO reportes_user;
-- Cinco permisos de lectura, uno por cada vista de reporte.
-- Nunca se concede INSERT, UPDATE ni DELETE: es un acceso de consulta.
-- Ejemplo de REVOKE (revocar un privilegio concedido):
REVOKE SELECT ON vw_cartera_ejecutivos FROM reportes_user;
-- REVOKE retira un permiso previamente concedido, dejandolo como si nunca
-- se hubiera dado. Aqui se retira a proposito el acceso a la cartera por
-- ejecutivo, por ser informacion sensible de desempeno del personal, y
-- ademas sirve de demostracion de la instruccion.
-- MATIZ QUE CONVIENE SABER: REVOKE y DENY no son lo mismo. REVOKE quita el
-- permiso, pero si el usuario lo tuviera por otra via (por pertenecer a un
-- rol, por ejemplo) seguiria teniendolo. DENY lo prohibe de forma
-- terminante y prevalece sobre cualquier concesion.
-- Resultado final: reportes_user puede leer 4 vistas y ninguna tabla.
GO

PRINT 'Instalado: 1 funcion, 2 procedimientos transaccionales y usuario de solo lectura.';
GO
