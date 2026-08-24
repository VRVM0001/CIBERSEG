/* =====================================================================
   CIBERSEG - Seguridad de acceso. Ejecutar UNA vez en SSMS.

   Agrega a la tabla usuarios las columnas que usa el modulo de login
   (app/routes/auth.py) para bloquear la cuenta tras varios intentos
   fallidos, y registra el parametro de expiracion de sesion.

   Politica implementada:
     - 5 intentos fallidos consecutivos bloquean la cuenta 15 minutos.
     - La sesion expira tras 30 minutos de inactividad (configurable).

   Es seguro re-ejecutarlo: cada bloque comprueba primero si ya existe.
   =====================================================================

   CONTRA QUE PROTEGE ESTO (util para explicarlo):
     Contra el ataque de FUERZA BRUTA: un atacante que prueba miles de
     contrasenas hasta acertar. Con el bloqueo, tras 5 intentos la cuenta
     queda inaccesible 15 minutos, y esa espera hace inviable probar miles
     de combinaciones.
     El timeout de sesion protege de algo distinto: una sesion abierta y
     olvidada en un equipo compartido. Pasado el tiempo configurado, se
     cierra sola.

   POR QUE ES UN ARCHIVO APARTE Y NO PARTE DE schema.sql:
     Es una MIGRACION: se escribio despues, cuando la base ya estaba
     creada y con datos. Por eso usa ALTER TABLE (modificar una tabla
     existente) en lugar de CREATE TABLE, que obligaria a rehacerla.
   ===================================================================== */
USE ciberseg;
GO

/* Contador de intentos de inicio de sesion fallidos consecutivos.
   Se reinicia a 0 cuando el usuario entra correctamente. */
IF COL_LENGTH('usuarios', 'intentos_fallidos') IS NULL
-- COL_LENGTH('tabla','columna') devuelve el tamano en bytes de la columna,
-- o NULL si esa columna no existe. Es la forma estandar de preguntar "ya
-- agregue este campo?" y lo que permite volver a ejecutar el script sin
-- el error "ya existe una columna con ese nombre".
    ALTER TABLE usuarios ADD intentos_fallidos INT NOT NULL DEFAULT 0;
    -- ALTER TABLE ... ADD agrega una columna a una tabla que ya tiene datos.
    -- NOT NULL junto con DEFAULT 0 es la combinacion obligatoria en este
    -- caso: al agregar la columna, las filas existentes necesitan un valor,
    -- y el DEFAULT es el que se les asigna automaticamente. Sin el DEFAULT,
    -- SQL Server rechazaria el NOT NULL si la tabla no estuviera vacia.
    -- La cuenta la lleva auth.py: suma 1 con cada clave incorrecta y lo
    -- devuelve a 0 al entrar bien.
GO

/* Fecha y hora hasta la que la cuenta permanece bloqueada.
   NULL significa que la cuenta no esta bloqueada. */
IF COL_LENGTH('usuarios', 'bloqueado_hasta') IS NULL
    ALTER TABLE usuarios ADD bloqueado_hasta DATETIME2 NULL;
    -- Se guarda el INSTANTE EN QUE TERMINA el bloqueo, no un simple
    -- interruptor "bloqueado si/no". La ventaja es que el desbloqueo
    -- ocurre solo con el paso del tiempo: no hace falta ningun proceso
    -- programado que recorra la tabla liberando cuentas.
    -- auth.py lo escribe con DATEADD(MINUTE, 15, SYSDATETIME()) y en cada
    -- intento compara si esa fecha ya paso.
    -- NULL explicito = la cuenta no tiene bloqueo activo.
GO

/* Minutos de inactividad antes de cerrar la sesion automaticamente.
   Se lee desde la pantalla de Configuracion del sistema. */
IF NOT EXISTS (SELECT 1 FROM configuracion WHERE clave = 'sesion_timeout_min')
-- Aqui el objeto que puede faltar no es una columna sino una FILA, por eso
-- se comprueba con NOT EXISTS sobre la tabla configuracion y no con
-- COL_LENGTH.
    INSERT INTO configuracion (clave, valor) VALUES ('sesion_timeout_min', '30');
    -- 30 minutos por defecto. Este valor lo lee la funcion exigir_sesion()
    -- de auth.py, que se ejecuta ANTES de cada peticion de la aplicacion:
    -- si pasa mas tiempo del configurado sin actividad, borra la sesion y
    -- redirige al login.
    -- El valor 0 tiene un significado especial: desactiva el cierre
    -- automatico (sesion sin caducidad).
GO

PRINT 'Seguridad de acceso instalada: bloqueo por intentos y timeout de sesion.';
GO
