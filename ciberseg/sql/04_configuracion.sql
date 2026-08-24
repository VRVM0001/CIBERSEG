/* CIBERSEG - Tabla de configuracion (Fase Config). Ejecutar una vez en SSMS. */
/* =====================================================================
   QUE HACE ESTE ARCHIVO:
     Crea (si no existe) la tabla 'configuracion' y le carga sus primeros
     siete parametros.

   POR QUE EXISTE SI schema.sql YA CREA ESA TABLA:
     Porque este archivo es POSTERIOR: nacio cuando se agrego la pantalla
     de Configuracion al sistema, y despues la tabla se incorporo tambien
     a schema.sql. Se conserva por dos motivos: sirve para instalar la
     funcionalidad sobre una base ya existente sin rehacerla desde cero, y
     documenta en que fase del proyecto aparecio.
     Ejecutarlo despues de schema.sql no rompe nada: el IF de abajo detecta
     que la tabla ya esta creada y no la vuelve a crear.

   QUE ES UNA TABLA CLAVE-VALOR:
     En vez de una columna por parametro (lo que obligaria a un ALTER TABLE
     cada vez que se agrega uno nuevo), se guarda una FILA por parametro:
     una columna con el nombre y otra con el valor. Agregar un ajuste nuevo
     al sistema es entonces un simple INSERT.
   ===================================================================== */
USE ciberseg;
GO
IF OBJECT_ID('configuracion') IS NULL
-- OBJECT_ID('nombre') devuelve el identificador interno del objeto, o NULL
-- si no existe. Es la forma habitual de preguntar "esta tabla ya esta
-- creada?" y es lo que hace el script re-ejecutable sin errores.
BEGIN
  CREATE TABLE configuracion (
    clave      VARCHAR(60) PRIMARY KEY,   -- El nombre del parametro ES la llave primaria: no se puede repetir y no hace falta un id numerico
    valor      VARCHAR(255) NOT NULL,     -- Todo se guarda como TEXTO (numeros, interruptores 1/0 y plantillas de correo). Quien lo lee lo convierte: TRY_CAST en SQL, int() en Python
    updated_at DATETIME2 DEFAULT SYSDATETIME()   -- Cuando se cambio por ultima vez ese parametro
  );
END
GO
IF NOT EXISTS (SELECT 1 FROM configuracion WHERE clave='notif_activas')
-- Solo carga los valores iniciales si la tabla esta "virgen". Se comprueba
-- una sola clave testigo ('notif_activas') como representante de todo el
-- bloque: si ella esta, el bloque completo ya se inserto antes.
-- SELECT 1 (en vez de SELECT *) porque a EXISTS solo le importa SI HAY
-- filas, no que contienen; el motor deja de buscar al hallar la primera.
  INSERT INTO configuracion (clave, valor) VALUES
    ('notif_activas','1'), ('notif_cotizaciones','1'), ('notif_facturas','1'),
    -- Interruptores de notificacion. '1' = encendido, '0' = apagado.
    -- 'notif_activas' es el interruptor GENERAL de la campana: si esta en
    -- 0, no se muestra ningun aviso aunque los demas esten encendidos.
    ('notif_equipos','1'), ('notif_prospectos','1'), ('notif_inventario','1'), ('itbis_pct','18');
    -- 'itbis_pct' = 18 es el impuesto de Republica Dominicana. Este valor
    -- es el que lee sp_recalcular_totales_cotizacion para calcular el
    -- impuesto de cada cotizacion, y tambien ventas.py. Cambiarlo aqui (o
    -- desde la pantalla de Configuracion) afecta a todo el sistema, sin
    -- tocar una sola linea de codigo.
GO
PRINT 'Configuracion lista.';
GO
