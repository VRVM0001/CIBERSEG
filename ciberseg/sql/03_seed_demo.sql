/* =====================================================================
   CIBERSEG - Datos de DEMOSTRACION (opcional, para poblar el dashboard)
   SQL Server (T-SQL). Ejecutar DESPUES de schema.sql y seed.sql.
   Las fechas son relativas a hoy (GETDATE()) para que los graficos
   siempre muestren datos.
   =====================================================================

   DIFERENCIA CON seed.sql (importante):
     seed.sql carga lo IMPRESCINDIBLE (roles, permisos, usuario admin,
     fabricantes y catalogo): sin el, el sistema no arranca.
     Este archivo es OPCIONAL: carga datos ficticios de ejemplo para que
     el dashboard, los graficos y los reportes tengan cifras que mostrar
     durante la demostracion. En una instalacion real no se ejecuta.

   LA TECNICA CLAVE DE TODO EL ARCHIVO - FECHAS RELATIVAS:
     Ninguna fecha esta escrita fija ('2025-03-14'). Todas se calculan
     con esta formula:

         DATEADD(DAY, -N, CAST(GETDATE() AS DATE))

     que se lee de dentro hacia afuera:
       GETDATE()            -> fecha y hora actuales del servidor
       CAST(... AS DATE)    -> recorta la hora y deja solo la fecha
       DATEADD(DAY, -N, ...)-> RESTA N dias a esa fecha (el signo menos
                               es lo que la lleva al pasado)

     POR QUE SE HACE ASI: con fechas fijas, los datos "envejecerian" y en
     unos meses el grafico de los ultimos 6 meses saldria vacio. Con
     fechas relativas, el conjunto se desplaza solo: ejecutes el script
     hoy o dentro de un ano, siempre habra movimiento reciente.

   POR QUE LOS ids ESTAN ESCRITOS A MANO (1, 2, 3...):
     Las llaves foraneas apuntan a ids numericos concretos (cliente_id 6,
     producto_id 2, cotizacion_id 11...). Esos numeros funcionan porque el
     script se ejecuta sobre una base RECIEN CREADA por schema.sql, donde
     IDENTITY empieza a numerar desde 1 en cada tabla y el orden de
     insercion es predecible.
     CONSECUENCIA: si ejecutas este archivo dos veces, o sobre una base que
     ya tiene datos, los ids no coincidiran y las relaciones quedaran mal.
     Debe ejecutarse UNA sola vez, sobre base limpia.

   ORDEN DE LOS BLOQUES (lo impone la integridad referencial):
     empresas -> clientes -> cotizaciones/facturas -> detalle -> equipos
     Cada bloque necesita que exista el anterior.
   ===================================================================== */
USE ciberseg;
GO

-- =====================================================================
-- BLOQUE 1: EMPRESAS (10 organizaciones ficticias)
-- Van primero porque los clientes las referencian con empresa_id.
-- Reciben los ids 1 a 10 en este mismo orden.
-- Se eligieron empresas de sectores variados (banca, retail, salud,
-- gobierno, educacion) a proposito: asi el grafico "Clientes por tipo"
-- del dashboard muestra varias porciones y no una sola.
-- Columnas: nombre, rnc (registro fiscal), sector, tamano y ciudad.
-- Las demas (pais, activo, fechas) toman sus valores DEFAULT.
-- =====================================================================
-- Empresas
INSERT INTO empresas (nombre,rnc,sector,tamano,ciudad) VALUES ('Banco del Progreso','133126225','Banca','Grande','La Romana');
INSERT INTO empresas (nombre,rnc,sector,tamano,ciudad) VALUES ('Seguros Universal','137334053','Seguros','Grande','Santiago');
INSERT INTO empresas (nombre,rnc,sector,tamano,ciudad) VALUES ('Grupo Ramos','133809570','Retail','Corporativo','San Pedro');
INSERT INTO empresas (nombre,rnc,sector,tamano,ciudad) VALUES ('Universidad APEC','132719176','Educacion','Mediana','Punta Cana');
INSERT INTO empresas (nombre,rnc,sector,tamano,ciudad) VALUES ('Hospital General Plaza','131131244','Salud','Grande','Santo Domingo');
INSERT INTO empresas (nombre,rnc,sector,tamano,ciudad) VALUES ('Claro Dominicana','136343962','Telecom','Corporativo','San Pedro');
INSERT INTO empresas (nombre,rnc,sector,tamano,ciudad) VALUES ('Ministerio de Hacienda','149127824','Gobierno','Grande','San Pedro');
INSERT INTO empresas (nombre,rnc,sector,tamano,ciudad) VALUES ('Cerveceria Nacional','136850800','Manufactura','Grande','San Pedro');
INSERT INTO empresas (nombre,rnc,sector,tamano,ciudad) VALUES ('Farmacia Carol','143331148','Retail','Mediana','Punta Cana');
INSERT INTO empresas (nombre,rnc,sector,tamano,ciudad) VALUES ('AERODOM','148391704','Aeropuertos','Mediana','Santo Domingo');

-- =====================================================================
-- BLOQUE 2: CLIENTES (la relacion comercial con cada empresa)
-- empresa_id va de 1 a 10, emparejando con las empresas de arriba en el
-- mismo orden.
-- ejecutivo_id = 1 en todos: el usuario admin creado por seed.sql, que es
-- el unico que existe en este punto.
-- Los estados se mezclan a proposito ('Activo', 'Prospecto', 'Inactivo')
-- para que los filtros del listado y los KPIs de clientes activos frente
-- al total tengan algo que diferenciar.
-- fecha_alta usa la formula de fechas relativas explicada en la cabecera:
-- cada cliente entro hace una cantidad distinta de dias.
-- =====================================================================
-- Clientes
INSERT INTO clientes (codigo,empresa_id,tipo,segmento,ejecutivo_id,estado,limite_credito,fecha_alta) VALUES ('CLI-0001',1,'Corporativo','Mayorista',1,'Activo',150000,DATEADD(DAY,-159,CAST(GETDATE() AS DATE)));
INSERT INTO clientes (codigo,empresa_id,tipo,segmento,ejecutivo_id,estado,limite_credito,fecha_alta) VALUES ('CLI-0002',2,'Corporativo','Mayorista',1,'Activo',150000,DATEADD(DAY,-678,CAST(GETDATE() AS DATE)));
INSERT INTO clientes (codigo,empresa_id,tipo,segmento,ejecutivo_id,estado,limite_credito,fecha_alta) VALUES ('CLI-0003',3,'Corporativo','Estrategico',1,'Activo',250000,DATEADD(DAY,-807,CAST(GETDATE() AS DATE)));
INSERT INTO clientes (codigo,empresa_id,tipo,segmento,ejecutivo_id,estado,limite_credito,fecha_alta) VALUES ('CLI-0004',4,'Educacion','Regular',1,'Prospecto',250000,DATEADD(DAY,-187,CAST(GETDATE() AS DATE)));
INSERT INTO clientes (codigo,empresa_id,tipo,segmento,ejecutivo_id,estado,limite_credito,fecha_alta) VALUES ('CLI-0005',5,'Salud','Estrategico',1,'Activo',150000,DATEADD(DAY,-625,CAST(GETDATE() AS DATE)));
INSERT INTO clientes (codigo,empresa_id,tipo,segmento,ejecutivo_id,estado,limite_credito,fecha_alta) VALUES ('CLI-0006',6,'Corporativo','Regular',1,'Activo',150000,DATEADD(DAY,-693,CAST(GETDATE() AS DATE)));
INSERT INTO clientes (codigo,empresa_id,tipo,segmento,ejecutivo_id,estado,limite_credito,fecha_alta) VALUES ('CLI-0007',7,'Gobierno','Regular',1,'Inactivo',50000,DATEADD(DAY,-256,CAST(GETDATE() AS DATE)));
INSERT INTO clientes (codigo,empresa_id,tipo,segmento,ejecutivo_id,estado,limite_credito,fecha_alta) VALUES ('CLI-0008',8,'Corporativo','Estrategico',1,'Activo',100000,DATEADD(DAY,-737,CAST(GETDATE() AS DATE)));
INSERT INTO clientes (codigo,empresa_id,tipo,segmento,ejecutivo_id,estado,limite_credito,fecha_alta) VALUES ('CLI-0009',9,'Corporativo','Mayorista',1,'Activo',100000,DATEADD(DAY,-141,CAST(GETDATE() AS DATE)));
INSERT INTO clientes (codigo,empresa_id,tipo,segmento,ejecutivo_id,estado,limite_credito,fecha_alta) VALUES ('CLI-0010',10,'Corporativo','Estrategico',1,'Activo',150000,DATEADD(DAY,-449,CAST(GETDATE() AS DATE)));

-- =====================================================================
-- BLOQUE 3: COTIZACIONES Y FACTURAS (el flujo comercial)
-- Las lineas se van alternando: tras una cotizacion 'Aprobada' aparece
-- casi siempre su factura correspondiente, tal como ocurre en el sistema
-- real (solo lo aprobado se factura).
--
-- COMO LEER ESTE BLOQUE:
--   * cotizacion_id de la factura -> apunta a la cotizacion insertada
--     antes; ese numero es la posicion de la cotizacion en la secuencia.
--   * estados variados ('Borrador','Enviada','Aprobada','Rechazada') ->
--     alimentan el KPI de cotizaciones pendientes y la tasa de conversion
--     de la pantalla de Metricas.
--   * estados de factura ('Pagada','Vencida','Pendiente') -> solo las
--     'Pagada' cuentan como ingreso en el dashboard y en las vistas de
--     reporte; las 'Vencida' generan notificaciones de cobro.
--   * subtotal / impuesto / total -> vienen ya calculados con el 18% de
--     ITBIS. Ejemplo: 6433.00 * 0.18 = 1157.94, y 6433.00 + 1157.94 =
--     7590.94. Se escriben directos porque estas cotizaciones se insertan
--     antes que su detalle.
--   * las fechas se reparten a lo largo de varios meses hacia atras, para
--     que el grafico "Facturacion por mes" tenga una serie con varias
--     barras y no una sola.
-- =====================================================================
-- Cotizaciones, detalle y facturas
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0001',6,1,DATEADD(DAY,-175,CAST(GETDATE() AS DATE)),DATEADD(DAY,-145,CAST(GETDATE() AS DATE)),'Aprobada',6433.0,1157.94,7590.94);
INSERT INTO facturas (numero,cotizacion_id,cliente_id,fecha_emision,fecha_vencimiento,subtotal,impuesto,total,estado) VALUES ('FAC-2025-0001',1,6,DATEADD(DAY,-171,CAST(GETDATE() AS DATE)),DATEADD(DAY,-141,CAST(GETDATE() AS DATE)),6433.0,1157.94,7590.94,'Pagada');
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0002',7,1,DATEADD(DAY,-172,CAST(GETDATE() AS DATE)),DATEADD(DAY,-142,CAST(GETDATE() AS DATE)),'Borrador',23775.0,4279.5,28054.5);
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0003',2,1,DATEADD(DAY,-174,CAST(GETDATE() AS DATE)),DATEADD(DAY,-144,CAST(GETDATE() AS DATE)),'Enviada',25525.0,4594.5,30119.5);
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0004',9,1,DATEADD(DAY,-163,CAST(GETDATE() AS DATE)),DATEADD(DAY,-133,CAST(GETDATE() AS DATE)),'Aprobada',8180.0,1472.4,9652.4);
INSERT INTO facturas (numero,cotizacion_id,cliente_id,fecha_emision,fecha_vencimiento,subtotal,impuesto,total,estado) VALUES ('FAC-2025-0002',4,9,DATEADD(DAY,-161,CAST(GETDATE() AS DATE)),DATEADD(DAY,-131,CAST(GETDATE() AS DATE)),8180.0,1472.4,9652.4,'Pagada');
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0005',3,1,DATEADD(DAY,-125,CAST(GETDATE() AS DATE)),DATEADD(DAY,-95,CAST(GETDATE() AS DATE)),'Borrador',7207.0,1297.26,8504.26);
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0006',5,1,DATEADD(DAY,-133,CAST(GETDATE() AS DATE)),DATEADD(DAY,-103,CAST(GETDATE() AS DATE)),'Rechazada',972.0,174.96,1146.96);
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0007',5,1,DATEADD(DAY,-126,CAST(GETDATE() AS DATE)),DATEADD(DAY,-96,CAST(GETDATE() AS DATE)),'Borrador',30150.0,5427.0,35577.0);
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0008',5,1,DATEADD(DAY,-134,CAST(GETDATE() AS DATE)),DATEADD(DAY,-104,CAST(GETDATE() AS DATE)),'Rechazada',760.0,136.8,896.8);
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0009',9,1,DATEADD(DAY,-131,CAST(GETDATE() AS DATE)),DATEADD(DAY,-101,CAST(GETDATE() AS DATE)),'Aprobada',8640.0,1555.2,10195.2);
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0010',1,1,DATEADD(DAY,-101,CAST(GETDATE() AS DATE)),DATEADD(DAY,-71,CAST(GETDATE() AS DATE)),'Aprobada',5820.0,1047.6,6867.6);
INSERT INTO facturas (numero,cotizacion_id,cliente_id,fecha_emision,fecha_vencimiento,subtotal,impuesto,total,estado) VALUES ('FAC-2025-0003',10,1,DATEADD(DAY,-100,CAST(GETDATE() AS DATE)),DATEADD(DAY,-70,CAST(GETDATE() AS DATE)),5820.0,1047.6,6867.6,'Vencida');
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0011',2,1,DATEADD(DAY,-97,CAST(GETDATE() AS DATE)),DATEADD(DAY,-67,CAST(GETDATE() AS DATE)),'Enviada',1440.0,259.2,1699.2);
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0012',8,1,DATEADD(DAY,-103,CAST(GETDATE() AS DATE)),DATEADD(DAY,-73,CAST(GETDATE() AS DATE)),'Aprobada',4580.0,824.4,5404.4);
INSERT INTO facturas (numero,cotizacion_id,cliente_id,fecha_emision,fecha_vencimiento,subtotal,impuesto,total,estado) VALUES ('FAC-2025-0004',12,8,DATEADD(DAY,-99,CAST(GETDATE() AS DATE)),DATEADD(DAY,-69,CAST(GETDATE() AS DATE)),4580.0,824.4,5404.4,'Pagada');
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0013',9,1,DATEADD(DAY,-106,CAST(GETDATE() AS DATE)),DATEADD(DAY,-76,CAST(GETDATE() AS DATE)),'Aprobada',1990.0,358.2,2348.2);
INSERT INTO facturas (numero,cotizacion_id,cliente_id,fecha_emision,fecha_vencimiento,subtotal,impuesto,total,estado) VALUES ('FAC-2025-0005',13,9,DATEADD(DAY,-104,CAST(GETDATE() AS DATE)),DATEADD(DAY,-74,CAST(GETDATE() AS DATE)),1990.0,358.2,2348.2,'Vencida');
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0014',10,1,DATEADD(DAY,-113,CAST(GETDATE() AS DATE)),DATEADD(DAY,-83,CAST(GETDATE() AS DATE)),'Aprobada',540.0,97.2,637.2);
INSERT INTO facturas (numero,cotizacion_id,cliente_id,fecha_emision,fecha_vencimiento,subtotal,impuesto,total,estado) VALUES ('FAC-2025-0006',14,10,DATEADD(DAY,-110,CAST(GETDATE() AS DATE)),DATEADD(DAY,-80,CAST(GETDATE() AS DATE)),540.0,97.2,637.2,'Pagada');
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0015',9,1,DATEADD(DAY,-83,CAST(GETDATE() AS DATE)),DATEADD(DAY,-53,CAST(GETDATE() AS DATE)),'Aprobada',11982.0,2156.76,14138.76);
INSERT INTO facturas (numero,cotizacion_id,cliente_id,fecha_emision,fecha_vencimiento,subtotal,impuesto,total,estado) VALUES ('FAC-2025-0007',15,9,DATEADD(DAY,-79,CAST(GETDATE() AS DATE)),DATEADD(DAY,-49,CAST(GETDATE() AS DATE)),11982.0,2156.76,14138.76,'Pagada');
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0016',6,1,DATEADD(DAY,-77,CAST(GETDATE() AS DATE)),DATEADD(DAY,-47,CAST(GETDATE() AS DATE)),'Enviada',993.0,178.74,1171.74);
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0017',6,1,DATEADD(DAY,-65,CAST(GETDATE() AS DATE)),DATEADD(DAY,-35,CAST(GETDATE() AS DATE)),'Rechazada',3980.0,716.4,4696.4);
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0018',8,1,DATEADD(DAY,-56,CAST(GETDATE() AS DATE)),DATEADD(DAY,-26,CAST(GETDATE() AS DATE)),'Enviada',25600.0,4608.0,30208.0);
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0019',2,1,DATEADD(DAY,-46,CAST(GETDATE() AS DATE)),DATEADD(DAY,-16,CAST(GETDATE() AS DATE)),'Rechazada',5097.0,917.46,6014.46);
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0020',8,1,DATEADD(DAY,-54,CAST(GETDATE() AS DATE)),DATEADD(DAY,-24,CAST(GETDATE() AS DATE)),'Rechazada',11515.0,2072.7,13587.7);
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0021',8,1,DATEADD(DAY,-51,CAST(GETDATE() AS DATE)),DATEADD(DAY,-21,CAST(GETDATE() AS DATE)),'Enviada',3898.0,701.64,4599.64);
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0022',9,1,DATEADD(DAY,-59,CAST(GETDATE() AS DATE)),DATEADD(DAY,-29,CAST(GETDATE() AS DATE)),'Borrador',6120.0,1101.6,7221.6);
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0023',2,1,DATEADD(DAY,-3,CAST(GETDATE() AS DATE)),DATEADD(DAY,27,CAST(GETDATE() AS DATE)),'Aprobada',760.0,136.8,896.8);
INSERT INTO facturas (numero,cotizacion_id,cliente_id,fecha_emision,fecha_vencimiento,subtotal,impuesto,total,estado) VALUES ('FAC-2025-0008',23,2,DATEADD(DAY,-1,CAST(GETDATE() AS DATE)),DATEADD(DAY,29,CAST(GETDATE() AS DATE)),760.0,136.8,896.8,'Vencida');
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0024',10,1,DATEADD(DAY,-11,CAST(GETDATE() AS DATE)),DATEADD(DAY,19,CAST(GETDATE() AS DATE)),'Aprobada',7100.0,1278.0,8378.0);
INSERT INTO facturas (numero,cotizacion_id,cliente_id,fecha_emision,fecha_vencimiento,subtotal,impuesto,total,estado) VALUES ('FAC-2025-0009',24,10,DATEADD(DAY,-7,CAST(GETDATE() AS DATE)),DATEADD(DAY,23,CAST(GETDATE() AS DATE)),7100.0,1278.0,8378.0,'Pagada');
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0025',6,1,DATEADD(DAY,-6,CAST(GETDATE() AS DATE)),DATEADD(DAY,24,CAST(GETDATE() AS DATE)),'Aprobada',840.0,151.2,991.2);
INSERT INTO facturas (numero,cotizacion_id,cliente_id,fecha_emision,fecha_vencimiento,subtotal,impuesto,total,estado) VALUES ('FAC-2025-0010',25,6,DATEADD(DAY,-3,CAST(GETDATE() AS DATE)),DATEADD(DAY,27,CAST(GETDATE() AS DATE)),840.0,151.2,991.2,'Vencida');
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0026',3,1,DATEADD(DAY,-19,CAST(GETDATE() AS DATE)),DATEADD(DAY,11,CAST(GETDATE() AS DATE)),'Aprobada',16000.0,2880.0,18880.0);
INSERT INTO facturas (numero,cotizacion_id,cliente_id,fecha_emision,fecha_vencimiento,subtotal,impuesto,total,estado) VALUES ('FAC-2025-0011',26,3,DATEADD(DAY,-16,CAST(GETDATE() AS DATE)),DATEADD(DAY,14,CAST(GETDATE() AS DATE)),16000.0,2880.0,18880.0,'Vencida');
INSERT INTO cotizaciones (numero,cliente_id,ejecutivo_id,fecha,fecha_validez,estado,subtotal,impuesto,total) VALUES ('COT-2025-0027',10,1,DATEADD(DAY,-5,CAST(GETDATE() AS DATE)),DATEADD(DAY,25,CAST(GETDATE() AS DATE)),'Borrador',5630.0,1013.4,6643.4);

-- =====================================================================
-- BLOQUE 4: DETALLE DE COTIZACIONES (las lineas de producto)
-- cotizacion_id apunta a las cotizaciones del bloque anterior y
-- producto_id a los 7 productos que cargo seed.sql (1 = FG-40F,
-- 2 = FG-60F, 3 = FG-100F, 4 = FS-108E, 5 = FAP-231F, 6 = FC-UTM-60F,
-- 7 = C1000-8T).
-- El subtotal de cada linea ya viene calculado: cantidad * precio *
-- (1 - descuento/100). Ejemplo: 5 x 995 sin descuento = 4975.00.
--
-- DATO IMPORTANTE PARA LA DEFENSA: al insertar estas lineas se dispara el
-- trigger trg_detalle_totales, que recalcula solo los totales de cada
-- cotizacion afectada. Es decir, aunque el bloque anterior ya traia los
-- totales escritos, el motor los vuelve a calcular aqui a partir del
-- detalle real. Si ambos coinciden, es la prueba de que el trigger y las
-- cifras de demostracion son consistentes.
-- (Ese trigger solo actua si ya se ejecuto sqlserver_avanzado.sql.)
-- =====================================================================
-- Detalle de cotizaciones
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (1,2,5,995,0,4975.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (1,6,3,540,10,1458.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (2,5,1,380,0,380.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (2,2,1,995,0,995.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (2,3,7,3200,0,22400.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (3,3,7,3200,5,21280.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (3,2,3,995,0,2985.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (3,4,3,420,0,1260.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (4,5,7,380,0,2660.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (4,4,4,420,0,1680.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (4,7,8,480,0,3840.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (5,5,7,380,5,2527.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (5,1,8,650,10,4680.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (6,6,2,540,10,972.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (7,1,7,650,0,4550.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (7,3,8,3200,0,25600.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (8,5,2,380,0,760.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (9,3,3,3200,10,8640.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (10,1,6,650,0,3900.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (10,7,4,480,0,1920.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (11,7,3,480,0,1440.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (12,5,7,380,0,2660.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (12,7,4,480,0,1920.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (13,2,2,995,0,1990.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (14,6,1,540,0,540.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (15,4,3,420,10,1134.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (15,2,8,995,0,7960.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (15,5,8,380,5,2888.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (16,7,1,480,0,480.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (16,6,1,540,5,513.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (17,2,4,995,0,3980.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (18,3,8,3200,0,25600.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (19,1,1,650,0,650.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (19,7,4,480,0,1920.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (19,5,7,380,5,2527.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (20,1,7,650,0,4550.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (20,2,7,995,0,6965.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (21,6,3,540,0,1620.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (21,5,5,380,0,1900.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (21,4,1,420,10,378.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (22,1,8,650,10,4680.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (22,7,3,480,0,1440.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (23,5,2,380,0,760.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (24,1,6,650,0,3900.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (24,4,4,420,0,1680.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (24,5,4,380,0,1520.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (25,4,2,420,0,840.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (26,3,5,3200,0,16000.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (27,1,5,650,0,3250.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (27,6,3,540,0,1620.0);
INSERT INTO detalle_cotizacion (cotizacion_id,producto_id,cantidad,precio_unitario,descuento_pct,subtotal) VALUES (27,5,2,380,0,760.0);

-- =====================================================================
-- BLOQUE 5: EQUIPOS INSTALADOS (inventario tecnico en sede del cliente)
-- cliente_id apunta a los clientes del bloque 2 y producto_id al catalogo.
-- numero_serie es unico en cada fila, como exige la restriccion UNIQUE de
-- la tabla.
-- Los estados se mezclan a proposito: los equipos 'Fuera de servicio' o
-- 'En mantenimiento' son los que generan las notificaciones de la campana
-- y hacen que el KPI "equipos operativos de N instalados" muestre una
-- diferencia visible en el dashboard.
-- El campo 'tipo' alimenta directamente el grafico circular "Equipos por
-- tipo" de la pantalla principal.
-- =====================================================================
-- Equipos instalados
INSERT INTO equipos (cliente_id,producto_id,tipo,numero_serie,hostname,ubicacion,estado,fecha_instalacion) VALUES (9,2,'Firewall','FGT47816686','fw-9-1','Datacenter Principal','En mantenimiento',DATEADD(DAY,-308,CAST(GETDATE() AS DATE)));
INSERT INTO equipos (cliente_id,producto_id,tipo,numero_serie,hostname,ubicacion,estado,fecha_instalacion) VALUES (4,6,'Otro','FGT37326368','fw-4-2','Datacenter Principal','Fuera de servicio',DATEADD(DAY,-381,CAST(GETDATE() AS DATE)));
INSERT INTO equipos (cliente_id,producto_id,tipo,numero_serie,hostname,ubicacion,estado,fecha_instalacion) VALUES (5,5,'Access Point','FGT43704923','fw-5-3','Datacenter Principal','Operativo',DATEADD(DAY,-530,CAST(GETDATE() AS DATE)));
INSERT INTO equipos (cliente_id,producto_id,tipo,numero_serie,hostname,ubicacion,estado,fecha_instalacion) VALUES (2,6,'Otro','FGT47135391','fw-2-4','Datacenter Principal','Operativo',DATEADD(DAY,-463,CAST(GETDATE() AS DATE)));
INSERT INTO equipos (cliente_id,producto_id,tipo,numero_serie,hostname,ubicacion,estado,fecha_instalacion) VALUES (1,3,'Firewall','FGT95511909','fw-1-5','Datacenter Principal','Operativo',DATEADD(DAY,-163,CAST(GETDATE() AS DATE)));
INSERT INTO equipos (cliente_id,producto_id,tipo,numero_serie,hostname,ubicacion,estado,fecha_instalacion) VALUES (3,6,'Otro','FGT84045292','fw-3-6','Datacenter Principal','Fuera de servicio',DATEADD(DAY,-482,CAST(GETDATE() AS DATE)));
INSERT INTO equipos (cliente_id,producto_id,tipo,numero_serie,hostname,ubicacion,estado,fecha_instalacion) VALUES (7,5,'Access Point','FGT25015458','fw-7-7','Datacenter Principal','Operativo',DATEADD(DAY,-39,CAST(GETDATE() AS DATE)));
INSERT INTO equipos (cliente_id,producto_id,tipo,numero_serie,hostname,ubicacion,estado,fecha_instalacion) VALUES (3,5,'Access Point','FGT59555330','fw-3-8','Datacenter Principal','En mantenimiento',DATEADD(DAY,-66,CAST(GETDATE() AS DATE)));
INSERT INTO equipos (cliente_id,producto_id,tipo,numero_serie,hostname,ubicacion,estado,fecha_instalacion) VALUES (9,2,'Firewall','FGT27105448','fw-9-9','Datacenter Principal','Operativo',DATEADD(DAY,-470,CAST(GETDATE() AS DATE)));
INSERT INTO equipos (cliente_id,producto_id,tipo,numero_serie,hostname,ubicacion,estado,fecha_instalacion) VALUES (5,3,'Firewall','FGT58024342','fw-5-10','Datacenter Principal','Operativo',DATEADD(DAY,-70,CAST(GETDATE() AS DATE)));
INSERT INTO equipos (cliente_id,producto_id,tipo,numero_serie,hostname,ubicacion,estado,fecha_instalacion) VALUES (4,6,'Otro','FGT57469942','fw-4-11','Datacenter Principal','En mantenimiento',DATEADD(DAY,-135,CAST(GETDATE() AS DATE)));
INSERT INTO equipos (cliente_id,producto_id,tipo,numero_serie,hostname,ubicacion,estado,fecha_instalacion) VALUES (7,5,'Access Point','FGT41774346','fw-7-12','Datacenter Principal','Operativo',DATEADD(DAY,-188,CAST(GETDATE() AS DATE)));
INSERT INTO equipos (cliente_id,producto_id,tipo,numero_serie,hostname,ubicacion,estado,fecha_instalacion) VALUES (3,4,'Switch','FGT34073380','fw-3-13','Datacenter Principal','Fuera de servicio',DATEADD(DAY,-55,CAST(GETDATE() AS DATE)));
INSERT INTO equipos (cliente_id,producto_id,tipo,numero_serie,hostname,ubicacion,estado,fecha_instalacion) VALUES (6,7,'Switch','FGT99913412','fw-6-14','Datacenter Principal','Fuera de servicio',DATEADD(DAY,-451,CAST(GETDATE() AS DATE)));
INSERT INTO equipos (cliente_id,producto_id,tipo,numero_serie,hostname,ubicacion,estado,fecha_instalacion) VALUES (4,3,'Firewall','FGT24508349','fw-4-15','Datacenter Principal','Operativo',DATEADD(DAY,-193,CAST(GETDATE() AS DATE)));
INSERT INTO equipos (cliente_id,producto_id,tipo,numero_serie,hostname,ubicacion,estado,fecha_instalacion) VALUES (1,7,'Switch','FGT39854548','fw-1-16','Datacenter Principal','Operativo',DATEADD(DAY,-511,CAST(GETDATE() AS DATE)));
GO
PRINT 'Datos de demostracion cargados.';
GO