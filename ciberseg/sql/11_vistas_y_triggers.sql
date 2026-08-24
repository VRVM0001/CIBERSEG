/* =====================================================================
   CIBERSEG - Vistas y Triggers adicionales (T-SQL)
   Ejecutar UNA vez en SSMS. Seguro de re-ejecutar (CREATE OR ALTER).
   =====================================================================

   CONTENIDO: 5 vistas de reporte y 4 triggers.

     VISTAS (consultas guardadas que se usan como si fueran tablas)
       V1 vw_cotizaciones_detalle   -> cotizaciones con datos de negocio
       V2 vw_cartera_ejecutivos     -> cuanto vende cada ejecutivo
       V3 vw_pipeline               -> embudo de oportunidades ponderado
       V4 vw_actividades_pendientes -> seguimientos por hacer
       V5 vw_clientes_resumen       -> ficha 360 de cada cliente

     TRIGGERS (codigo que el motor dispara solo ante un cambio)
       T1 trg_facturas_auditoria    -> audita cambios en facturas
       T2 trg_cotizaciones_auditoria-> audita cambios en cotizaciones
       T3 trg_usuarios_no_delete    -> prohibe borrar usuarios
       T4 trg_oportunidad_ganada    -> crea seguimiento al ganar un negocio

   POR QUE ESTO VIVE EN LA BASE Y NO EN PYTHON:
     Las vistas centralizan consultas complejas: la aplicacion pide una
     linea sencilla en vez de repetir tres JOIN con agrupaciones, y si la
     formula cambia se corrige en un solo sitio.
     Los triggers garantizan reglas que se cumplen SIEMPRE, incluso si
     alguien modifica los datos directamente desde SSMS sin pasar por la
     aplicacion. Esa es la diferencia entre validar y garantizar.

   REQUISITOS PREVIOS (este archivo los usa pero no los crea):
     schema.sql, mejoras_crm.sql (oportunidades) y mejoras_crm_fase2.sql
     (actividades). Sin ellos, V3, V4, V5 y T4 fallarian.
   ===================================================================== */
USE ciberseg;
GO

/* ============================ VISTAS ============================ */

/* V1. Cotizaciones con toda su informacion de negocio en una sola consulta
   ---------------------------------------------------------------------
   Objetivo: evitar que cada pantalla tenga que repetir el mismo triple
             JOIN para mostrar el nombre del cliente y del ejecutivo.
   Devuelve: los datos de la cotizacion + cliente + ejecutivo + cuantas
             lineas tiene + si ya fue facturada.
   --------------------------------------------------------------------- */
CREATE OR ALTER VIEW vw_cotizaciones_detalle AS
-- CREATE OR ALTER: la crea si no existe y la reemplaza si ya estaba. Es lo
-- que permite volver a ejecutar el archivo sin errores.
SELECT co.id, co.numero, co.fecha, co.estado, co.subtotal, co.impuesto, co.total,
       -- Datos propios de la cotizacion, tomados tal cual de su tabla.
       e.nombre AS cliente, c.codigo AS codigo_cliente, u.nombre AS ejecutivo,
       -- Datos TRAIDOS de otras tablas. Se renombran con AS porque las tres
       -- tablas tienen una columna llamada 'nombre' y hay que distinguirlas.
       (SELECT COUNT(*) FROM detalle_cotizacion d WHERE d.cotizacion_id = co.id) AS lineas,
       -- SUBCONSULTA CORRELACIONADA: se ejecuta una vez por cada fila del
       -- resultado, y la condicion depende de esa fila (d.cotizacion_id =
       -- co.id). Cuenta cuantos productos tiene esa cotizacion concreta.
       -- Se resuelve asi, y no con un JOIN + GROUP BY, para no tener que
       -- agrupar todas las demas columnas del SELECT.
       (SELECT COUNT(*) FROM facturas f WHERE f.cotizacion_id = co.id) AS facturada
       -- Misma tecnica: si devuelve 0, la cotizacion aun no se facturo; si
       -- devuelve 1 o mas, ya tiene factura. La aplicacion lo usa para
       -- mostrar la marca de "Facturada" y para ocultar el boton de generar.
FROM cotizaciones co
JOIN clientes c  ON c.id = co.cliente_id
-- JOIN normal (INNER): exige coincidencia. Es correcto aqui porque
-- cotizaciones.cliente_id es NOT NULL, siempre hay cliente.
JOIN empresas e  ON e.id = c.empresa_id
-- Segundo salto: se pasa por clientes para llegar a empresas, que es donde
-- vive el nombre legible. Es el camino que marcan las llaves foraneas.
LEFT JOIN usuarios u ON u.id = co.ejecutivo_id;
-- LEFT JOIN y no JOIN: el ejecutivo es OPCIONAL (ejecutivo_id admite NULL).
-- Con un JOIN normal, las cotizaciones sin ejecutivo asignado
-- DESAPARECERIAN del resultado. Con LEFT JOIN se conservan y el nombre
-- del ejecutivo sale como NULL.
GO

/* V2. Cartera por ejecutivo: cuanto vende cada quien
   ---------------------------------------------------------------------
   Objetivo: medir el desempeno comercial de cada vendedor.
   Devuelve: por ejecutivo, cuantas cotizaciones hizo, cuantas se
             aprobaron y cuanto dinero suman las aprobadas.
   --------------------------------------------------------------------- */
CREATE OR ALTER VIEW vw_cartera_ejecutivos AS
SELECT COALESCE(u.nombre,'Sin asignar') AS ejecutivo,
       -- COALESCE devuelve el primer valor no nulo. Como el LEFT JOIN de
       -- abajo deja NULL en las cotizaciones sin vendedor, aqui se
       -- sustituye por el texto 'Sin asignar', mas claro en pantalla que
       -- una celda vacia.
       COUNT(*) AS cotizaciones,
       -- Total de cotizaciones del ejecutivo, sin importar su estado.
       SUM(CASE WHEN co.estado='Aprobada' THEN 1 ELSE 0 END) AS aprobadas,
       -- CONTEO CONDICIONAL: el CASE convierte cada fila en 1 si esta
       -- aprobada y en 0 si no, y SUM los suma. Es la forma de contar solo
       -- una parte de las filas sin filtrar el resto del resultado (un
       -- WHERE eliminaria las no aprobadas del conteo total de arriba).
       COALESCE(SUM(CASE WHEN co.estado='Aprobada' THEN co.total END),0) AS valor_aprobado
       -- Variante del mismo truco, pero sumando importes en vez de contar.
       -- Este CASE no lleva ELSE: sin el, las filas no aprobadas producen
       -- NULL, y SUM ignora los NULL. El COALESCE exterior convierte en 0
       -- el caso de un ejecutivo sin ninguna cotizacion aprobada, donde SUM
       -- devolveria NULL.
FROM cotizaciones co
LEFT JOIN usuarios u ON u.id = co.ejecutivo_id
GROUP BY u.nombre;
-- GROUP BY junta todas las cotizaciones de un mismo vendedor en una sola
-- fila. Regla general: toda columna del SELECT que no este dentro de una
-- funcion de agregado (COUNT, SUM) debe aparecer en el GROUP BY.
-- Se agrupa por u.nombre y no por u.id, porque es el nombre lo que se
-- muestra; todas las cotizaciones sin ejecutivo caen juntas en el grupo NULL.
GO

/* V3. Embudo de oportunidades con valor ponderado por probabilidad
   ---------------------------------------------------------------------
   Objetivo: dar la foto del pipeline comercial y una PREVISION realista.
   Devuelve: por etapa, cuantas oportunidades hay, su valor total y su
             valor ponderado.
   --------------------------------------------------------------------- */
CREATE OR ALTER VIEW vw_pipeline AS
SELECT etapa, COUNT(*) AS oportunidades,
       -- Cuantos negocios hay parados en cada etapa del embudo.
       SUM(valor_estimado) AS valor,
       -- Dinero total en juego en esa etapa (escenario optimista: asume
       -- que todo se gana).
       SUM(valor_estimado * probabilidad / 100.0) AS valor_ponderado
       -- PREVISION REALISTA: cada negocio aporta solo la parte que su
       -- probabilidad justifica. Un negocio de 100.000 al 20% aporta 20.000.
       -- El 100.0 se escribe CON DECIMAL a proposito: probabilidad es INT y,
       -- si se dividiera entre 100 (entero), SQL Server haria division
       -- entera y un 20% se convertiria en 0, dando cero en toda la columna.
       -- Escribir 100.0 fuerza la division decimal.
FROM oportunidades GROUP BY etapa;
-- Una fila de resultado por cada etapa que tenga al menos una oportunidad.
GO

/* V4. Seguimientos pendientes (para el equipo comercial)
   ---------------------------------------------------------------------
   Objetivo: responder "que tengo que hacer y para cuando".
   Devuelve: las actividades sin completar que tienen fecha comprometida,
             con los dias que faltan (o de atraso).
   --------------------------------------------------------------------- */
CREATE OR ALTER VIEW vw_actividades_pendientes AS
SELECT a.id, e.nombre AS cliente, a.tipo, a.asunto, a.proxima_accion,
       DATEDIFF(DAY, CAST(GETDATE() AS DATE), a.proxima_accion) AS dias_restantes,
       -- DATEDIFF(unidad, fecha_inicial, fecha_final) devuelve cuantas
       -- unidades hay entre las dos fechas. Aqui, cuantos DIAS faltan desde
       -- hoy hasta el compromiso.
       --   valor positivo -> aun queda tiempo
       --   valor cero     -> es hoy
       --   valor NEGATIVO -> el seguimiento esta ATRASADO
       -- CAST(GETDATE() AS DATE) recorta la hora y deja solo la fecha; sin
       -- ese recorte, la hora actual desvirtuaria el conteo de dias.
       u.nombre AS responsable
FROM actividades a
JOIN clientes c ON c.id = a.cliente_id
JOIN empresas e ON e.id = c.empresa_id
-- Mismo doble salto de V1 para obtener el nombre visible de la empresa.
LEFT JOIN usuarios u ON u.id = a.usuario_id
-- LEFT JOIN porque usuario_id es opcional: las actividades creadas
-- automaticamente por el trigger T4 pueden no tener responsable.
WHERE a.completada = 0 AND a.proxima_accion IS NOT NULL;
-- Doble filtro, y ambos son necesarios:
--   completada = 0            -> solo lo que sigue pendiente
--   proxima_accion IS NOT NULL-> solo lo que tiene fecha comprometida.
-- Se usa IS NOT NULL y no <> NULL: en SQL, NULL no es un valor sino
-- "desconocido", y cualquier comparacion con = o <> frente a NULL da
-- desconocido, nunca verdadero. IS NULL / IS NOT NULL son la unica forma
-- correcta de preguntarlo.
GO

/* V5. Resumen 360 por cliente (facturado, cotizado, equipos, actividades)
   ---------------------------------------------------------------------
   Objetivo: la ficha completa de un cliente en una sola fila, para la
             pantalla de detalle y para reportes de cartera.
   --------------------------------------------------------------------- */
CREATE OR ALTER VIEW vw_clientes_resumen AS
SELECT c.id, c.codigo, e.nombre AS cliente, c.estado,
  (SELECT COALESCE(SUM(f.total),0) FROM facturas f
    WHERE f.cliente_id = c.id AND f.estado='Pagada')       AS facturado,
  -- Dinero REALMENTE COBRADO. El filtro estado='Pagada' es lo que
  -- diferencia un ingreso de una simple emision. COALESCE(...,0) evita que
  -- un cliente sin facturas pagadas muestre NULL en lugar de 0.
  (SELECT COUNT(*) FROM cotizaciones co WHERE co.cliente_id = c.id) AS cotizaciones,
  -- Actividad comercial: cuantas veces se le ha cotizado.
  (SELECT COUNT(*) FROM equipos eq WHERE eq.cliente_id = c.id)      AS equipos,
  -- Huella tecnica: cuantos aparatos tiene instalados.
  (SELECT COUNT(*) FROM actividades a
    WHERE a.cliente_id = c.id AND a.completada = 0)        AS seguimientos_abiertos
  -- Cuanta gestion tiene pendiente.
  -- LAS CUATRO SON SUBCONSULTAS CORRELACIONADAS, cada una contra una tabla
  -- distinta. Se resuelve asi porque con JOIN + GROUP BY los conteos se
  -- MULTIPLICARIAN entre si: un cliente con 3 facturas y 4 equipos
  -- generaria 12 filas combinadas y los totales saldrian inflados. Cada
  -- subconsulta se calcula por separado y evita ese producto cartesiano.
FROM clientes c JOIN empresas e ON e.id = c.empresa_id;
GO

/* ============================ TRIGGERS ============================

   RECORDATORIO DE COMO FUNCIONA UN TRIGGER (aplica a los cuatro):
     Es codigo que el motor ejecuta SOLO, sin que nadie lo llame, cuando
     ocurre un cambio en la tabla vigilada.
     Dentro dispone de dos tablas virtuales:
       inserted = como quedaron las filas DESPUES del cambio
       deleted  = como estaban ANTES
     INSERT llena solo inserted; DELETE solo deleted; UPDATE llena AMBAS.
     Y se dispara UNA VEZ POR INSTRUCCION, no una vez por fila: si un
     UPDATE toca 50 filas, el trigger corre una sola vez con las 50 dentro.
     Por eso todo el codigo de abajo trabaja con conjuntos y no fila a fila.
   ================================================================= */

/* T1. Auditoria automatica de FACTURAS (cualquier cambio, incluso desde SSMS)
   ---------------------------------------------------------------------
   Objetivo: que ningun cambio en una factura quede sin registrar, ni
             siquiera los hechos por fuera de la aplicacion.
   --------------------------------------------------------------------- */
CREATE OR ALTER TRIGGER trg_facturas_auditoria ON facturas
AFTER INSERT, UPDATE, DELETE AS
-- AFTER: se ejecuta DESPUES de que el cambio ya se aplico. Los tres
-- eventos comparten el mismo bloque de codigo.
BEGIN
  SET NOCOUNT ON;
  -- Suprime los mensajes "(N rows affected)" que generaria el trigger; si
  -- viajaran al cliente, se mezclarian con los de la instruccion original
  -- y confundirian al driver que lee los resultados.
  INSERT INTO auditoria (tabla_afectada, accion, registro_id, datos_nuevos)
  SELECT 'facturas',
  -- INSERT ... SELECT: genera tantas filas de auditoria como filas haya
  -- afectado la operacion. 'facturas' es un texto fijo que se repite igual
  -- en todas ellas.
         CASE WHEN EXISTS(SELECT 1 FROM deleted) AND EXISTS(SELECT 1 FROM inserted)
              THEN 'UPDATE'
              WHEN EXISTS(SELECT 1 FROM inserted) THEN 'INSERT' ELSE 'DELETE' END,
  -- DEDUCE QUE OPERACION FUE, a partir de que tablas virtuales tienen datos:
  --     hay deleted Y hay inserted -> UPDATE
  --     solo inserted              -> INSERT
  --     ninguna de las dos anterior-> DELETE
  -- El orden del CASE importa: UPDATE debe ir primero, porque en un UPDATE
  -- tambien "hay inserted" y caeria por error en la rama INSERT.
         COALESCE(i.id, d.id),
  -- Id de la factura afectada: se toma de inserted y, si es NULL (caso
  -- DELETE, donde no hay fila nueva), de deleted.
         CONCAT('{"numero": "', COALESCE(i.numero, d.numero),
                '", "estado": "', COALESCE(i.estado, d.estado), '", "origen": "trigger BD"}')
  -- Arma a mano una cadena JSON con los dos datos que importan de una
  -- factura (numero y estado) mas la marca de origen.
  -- CONCAT tiene una ventaja sobre el operador +: trata los NULL como
  -- texto vacio, asi que un valor nulo no anula toda la cadena.
  -- "origen": "trigger BD" es lo que permite distinguir despues, en la
  -- pantalla de Auditoria, este registro de los que escribe la aplicacion.
  FROM inserted i FULL OUTER JOIN deleted d ON d.id = i.id;
  -- FULL OUTER JOIN es la unica union que conserva las filas de AMBOS lados
  -- aunque no tengan pareja. Es lo que hace que un mismo trigger sirva para
  -- los tres eventos:
  --     INSERT -> filas solo en i     DELETE -> filas solo en d
  --     UPDATE -> filas emparejadas por id en los dos lados
  -- Con un JOIN normal, los INSERT y los DELETE no se registrarian.
END;
GO

/* T2. Auditoria automatica de COTIZACIONES
   ---------------------------------------------------------------------
   Identico en estructura a T1, pero sobre la tabla cotizaciones. Se
   duplica en lugar de generalizarse porque un trigger pertenece siempre a
   UNA tabla concreta: no existe en SQL Server un trigger que vigile varias.
   --------------------------------------------------------------------- */
CREATE OR ALTER TRIGGER trg_cotizaciones_auditoria ON cotizaciones
AFTER INSERT, UPDATE, DELETE AS
BEGIN
  SET NOCOUNT ON;
  INSERT INTO auditoria (tabla_afectada, accion, registro_id, datos_nuevos)
  SELECT 'cotizaciones',
         CASE WHEN EXISTS(SELECT 1 FROM deleted) AND EXISTS(SELECT 1 FROM inserted)
              THEN 'UPDATE'
              WHEN EXISTS(SELECT 1 FROM inserted) THEN 'INSERT' ELSE 'DELETE' END,
         COALESCE(i.id, d.id),
         CONCAT('{"numero": "', COALESCE(i.numero, d.numero),
                '", "estado": "', COALESCE(i.estado, d.estado), '", "origen": "trigger BD"}')
  -- Se guardan numero y estado por la misma razon que en las facturas: el
  -- estado es el dato que mas cambia y el que interesa rastrear (quien y
  -- cuando la paso a 'Aprobada').
  FROM inserted i FULL OUTER JOIN deleted d ON d.id = i.id;
END;
GO

/* T3. PROTECCION: prohibe borrar usuarios fisicamente (politica de borrado logico)
   ---------------------------------------------------------------------
   Objetivo: hacer IMPOSIBLE el DELETE sobre usuarios, incluso ejecutado a
             mano por un administrador desde SSMS.
   Por que: la tabla auditoria guarda usuario_id. Si se borrara un usuario,
            se perderia para siempre el rastro de quien hizo cada cambio
            historico. Ademas, sus clientes y cotizaciones quedarian
            apuntando a un ejecutivo inexistente.
   La alternativa correcta es desactivarlo: UPDATE usuarios SET activo = 0.
   --------------------------------------------------------------------- */
CREATE OR ALTER TRIGGER trg_usuarios_no_delete ON usuarios
INSTEAD OF DELETE AS
-- INSTEAD OF (en lugar de AFTER) es la clave de este trigger: el codigo se
-- ejecuta EN VEZ DEL DELETE, no despues. El borrado nunca llega a ocurrir.
-- Con AFTER, la fila se eliminaria primero y habria que deshacerlo.
BEGIN
  SET NOCOUNT ON;
  RAISERROR('No se permite eliminar usuarios. Use el campo activo=0 (borrado logico).', 16, 1);
  -- RAISERROR lanza un error controlado con un mensaje propio.
  --   16 = nivel de gravedad. Del 11 al 16 significa "error del usuario,
  --        corregible": llega al cliente como excepcion pero no tumba la
  --        conexion ni indica fallo del servidor.
  --    1 = estado, un numero libre para distinguir de donde salio el error
  --        si el mismo mensaje se usara en varios sitios.
  -- El mensaje no solo prohibe: EXPLICA que hacer en su lugar. Un mensaje
  -- de error util es el que dice como resolver la situacion.
END;
GO

/* T4. NEGOCIO: al marcar una oportunidad como Ganada, crea automaticamente
       una actividad de seguimiento para iniciar el proceso de cotizacion
   ---------------------------------------------------------------------
   Objetivo: que ningun negocio ganado se quede sin siguiente paso.
   Es el unico trigger de los cuatro que implementa una REGLA DE NEGOCIO
   (los otros son de auditoria o de proteccion): reacciona a un hecho
   comercial ejecutando la accion que corresponde.
   --------------------------------------------------------------------- */
CREATE OR ALTER TRIGGER trg_oportunidad_ganada ON oportunidades
AFTER UPDATE AS
-- Solo UPDATE: ganar un negocio siempre implica CAMBIAR su etapa, nunca
-- insertarlo ya ganado ni borrarlo.
BEGIN
  SET NOCOUNT ON;
  INSERT INTO actividades (cliente_id, usuario_id, tipo, asunto, notas, proxima_accion)
  SELECT i.cliente_id, i.ejecutivo_id, 'Tarea',
  -- El cliente y el ejecutivo se heredan de la oportunidad ganada. El tipo
  -- es 'Tarea' porque lo que se crea es un pendiente, no un contacto ya
  -- ocurrido.
         CONCAT('Preparar cotizacion: ', i.nombre),
  -- Asunto autogenerado, que incluye el nombre del negocio para que se
  -- entienda sin abrir nada mas.
         'Generada automaticamente al ganar la oportunidad (trigger BD).',
  -- Nota que deja claro el origen: quien la vea sabra que no la escribio
  -- una persona.
         DATEADD(DAY, 2, CAST(GETDATE() AS DATE))
  -- Vencimiento a 2 dias: DATEADD(unidad, cantidad, fecha) suma tiempo a
  -- una fecha. El CAST recorta la hora para que el compromiso quede fijado
  -- al dia, no al minuto en que se gano el negocio.
  FROM inserted i JOIN deleted d ON d.id = i.id
  -- Se emparejan por id el estado NUEVO (i) y el ANTERIOR (d) de cada fila
  -- modificada. Aqui JOIN normal es lo correcto: en un UPDATE toda fila
  -- existe en ambos lados.
  WHERE i.etapa = 'Ganada' AND d.etapa <> 'Ganada';
  -- LA CONDICION MAS IMPORTANTE DEL TRIGGER, y hay que leer las dos partes:
  --   i.etapa = 'Ganada'  -> ahora esta ganada
  --   d.etapa <> 'Ganada' -> y ANTES no lo estaba
  -- La segunda parte es la que evita duplicados: si despues se edita el
  -- valor o las notas de una oportunidad que YA estaba ganada, el trigger
  -- se dispara igual, pero esta condicion no se cumple y no crea una
  -- segunda tarea. Detecta la TRANSICION, no el estado.
  -- Ademas, al ser un SELECT con WHERE, si en el mismo UPDATE se ganan tres
  -- oportunidades de golpe, se crean las tres tareas de una sola vez.
END;
GO

PRINT 'Creados: 5 vistas y 4 triggers.';
GO
