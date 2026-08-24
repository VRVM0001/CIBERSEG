/* CIBERSEG - FASE 5: claves SMTP y plantillas. Ejecutar UNA vez. */
/* =====================================================================
   QUE AGREGA: siete parametros nuevos a la tabla 'configuracion': los
   cinco datos del servidor de correo saliente (SMTP) y las dos plantillas
   de mensaje que usa el sistema al enviar cotizaciones y avisos de
   renovacion.

   PARA QUE: permitir que el envio de correos se configure desde la
   pantalla de Configuracion, sin tocar el codigo.

   LO INTERESANTE DE ESTE ARCHIVO (tecnica destacable):
     Los archivos anteriores insertaban con un IF NOT EXISTS por delante,
     lo que obliga a repetir el bloque para cada clave. Aqui se resuelve
     con UNA sola instruccion que inserta las siete y omite sola las que
     ya existieran. Es el patron "insertar solo lo que falta".

   REQUISITO PREVIO: configuracion.sql (la tabla debe existir).
   ===================================================================== */
USE ciberseg;
GO
INSERT INTO configuracion (clave, valor)
SELECT v.clave, v.valor FROM (VALUES
-- CONSTRUCTOR DE TABLA POR VALORES: la clausula VALUES entre parentesis
-- crea una tabla TEMPORAL en memoria, que existe solo mientras dura esta
-- consulta. Permite tratar una lista escrita a mano como si fuera una
-- tabla real, y por tanto compararla contra la tabla verdadera.
 ('smtp_host',''),('smtp_puerto','587'),('smtp_usuario',''),('smtp_clave',''),
 -- Datos del servidor de correo. Se cargan VACIOS a proposito: son datos
 -- propios de cada instalacion y el administrador los llena desde la
 -- pantalla de Configuracion. Cargar credenciales de ejemplo en un script
 -- de base de datos seria una mala practica de seguridad.
 -- El puerto 587 si trae valor porque es el estandar de SMTP con cifrado
 -- STARTTLS, valido para la mayoria de proveedores.
 ('smtp_remitente',''),
 ('plantilla_seguimiento','Estimado cliente {cliente}: adjunto la cotizacion {numero}. Saludos, CIBERSEG.'),
 ('plantilla_renovacion','Estimado cliente {cliente}: tiene servicios proximos a renovar. Saludos, CIBERSEG.')) v(clave,valor)
 -- {cliente} y {numero} son MARCADORES DE POSICION: Python los sustituye
 -- por los datos reales antes de enviar el correo. Se guardan tal cual,
 -- con las llaves incluidas.
 -- v(clave,valor) le pone nombre a esa tabla temporal (v) y a sus dos
 -- columnas, para poder referirse a ellas como v.clave y v.valor.
WHERE NOT EXISTS (SELECT 1 FROM configuracion c WHERE c.clave = v.clave);
-- ESTA ES LA LINEA CLAVE. El WHERE se evalua UNA VEZ POR CADA FILA de la
-- lista de arriba: para cada clave propuesta, comprueba si ya hay una fila
-- con ese mismo nombre en la tabla real.
--   * Si ya existe -> la fila no pasa el filtro y NO se inserta (conserva
--     el valor que el administrador hubiera configurado).
--   * Si no existe -> se inserta con su valor inicial.
-- Resultado: el script se puede ejecutar mil veces sin duplicar filas ni
-- pisar configuraciones ya guardadas.
GO
PRINT 'Fase 5 instalada.';
GO
