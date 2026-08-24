/* =====================================================================
   CIBERSEG - Datos iniciales (seed)  -  SQL Server (T-SQL)
   Ejecutar DESPUES de schema.sql
   ---------------------------------------------------------------------
   QUE ES UN "SEED": la carga MINIMA de datos que el sistema necesita
   para poder arrancar. No son datos de ejemplo (esos van en
   seed_demo.sql): sin este archivo no existiria ningun rol, ningun
   permiso ni ningun usuario, y seria imposible iniciar sesion.

   QUE CARGA, EN ESTE ORDEN OBLIGATORIO:
     1. Roles                 (deben existir antes que los usuarios)
     2. Permisos              (catalogo de acciones del sistema)
     3. Asignacion rol-permiso (llena la tabla puente)
     4. Usuario administrador  (necesita un rol ya creado)
     5. Fabricantes           (deben existir antes que los productos)
     6. Productos             (necesitan un fabricante ya creado)

   POR QUE ESE ORDEN: cada bloque depende del anterior por LLAVE FORANEA.
   Insertar un usuario antes de crear su rol produciria el error
   "conflicto con la restriccion FOREIGN KEY".
   ===================================================================== */
USE ciberseg;   -- Todo lo que sigue se inserta dentro de la base ciberseg
GO

-- ---- Roles ----------------------------------------------------------
INSERT INTO roles (nombre, descripcion) VALUES
  -- Un solo INSERT con varias filas separadas por coma: es mas eficiente
  -- que repetir la instruccion, porque viaja al servidor una sola vez.
  -- No se indican id, activo, created_at ni updated_at: el id lo genera
  -- IDENTITY y los otros tres toman su valor DEFAULT.
  ('Administrador',       'Acceso total al sistema'),          -- Recibe el id 1 (primero insertado). auth.py y seed lo asumen asi
  ('Gerente Comercial',   'Gestiona ventas, clientes y reportes'),   -- id 2
  ('Ejecutivo de Ventas', 'Cotizaciones, clientes y facturas'),      -- id 3
  ('Ingeniero',           'Proyectos, equipos y soporte tecnico');   -- id 4

-- ---- Permisos (modulo.accion) ---------------------------------------
INSERT INTO permisos (nombre, modulo, descripcion) VALUES
  -- CONVENCION CLAVE DEL PROYECTO: el nombre sigue el patron
  -- 'modulo.accion'. Ese texto es EXACTAMENTE el que se escribe en los
  -- decoradores de Python, por ejemplo @permiso_requerido("clientes.crear"),
  -- y el que comparan las plantillas con {% if 'ventas.crear' in session.permisos %}.
  -- Si aqui se escribiera distinto, el permiso nunca coincidiria y el
  -- boton simplemente no aparaceria en pantalla.
  -- La columna 'modulo' repite el prefijo para poder asignar permisos por
  -- grupos, como se hace mas abajo con el rol 3.
  ('clientes.ver',       'clientes',  'Ver clientes'),
  ('clientes.crear',     'clientes',  'Crear clientes'),
  ('clientes.editar',    'clientes',  'Editar clientes'),
  ('clientes.eliminar',  'clientes',  'Eliminar clientes'),     -- "Eliminar" es en realidad desactivar (borrado logico)
  ('ventas.ver',         'ventas',    'Ver cotizaciones y facturas'),
  ('ventas.crear',       'ventas',    'Crear cotizaciones y facturas'),
  ('ventas.editar',      'ventas',    'Editar ventas'),
  ('ventas.eliminar',    'ventas',    'Eliminar ventas'),
  ('inventario.ver',     'inventario','Ver productos y equipos'),
  ('inventario.crear',   'inventario','Crear productos y equipos'),
  ('inventario.editar',  'inventario','Editar inventario'),     -- Incluye el ajuste de stock (+/-)
  ('inventario.eliminar','inventario','Eliminar inventario'),
  ('usuarios.ver',       'usuarios',  'Ver usuarios'),
  ('usuarios.crear',     'usuarios',  'Crear usuarios'),
  ('usuarios.editar',    'usuarios',  'Editar usuarios'),
  ('usuarios.eliminar',  'usuarios',  'Eliminar usuarios'),
  ('reportes.ver',       'reportes',  'Ver y exportar reportes');   -- Exportaciones a PDF y Excel

-- ---- El Administrador recibe TODOS los permisos ---------------------
INSERT INTO roles_permisos (rol_id, permiso_id)
  SELECT 1, id FROM permisos;
  -- INSERT ... SELECT en lugar de INSERT ... VALUES: en vez de escribir a
  -- mano 17 parejas, se genera una fila por cada permiso existente.
  -- El 1 es un valor FIJO (el rol Administrador) que se repite en cada
  -- fila, mientras que 'id' varia con cada permiso leido.
  -- Ventaja de hacerlo asi: si manana se agrega un permiso nuevo al
  -- bloque anterior, esta linea lo incluye sola, sin tener que editarla.

-- ---- Ejecutivo de Ventas: clientes + ventas + reportes --------------
INSERT INTO roles_permisos (rol_id, permiso_id)
  SELECT 3, id FROM permisos WHERE modulo IN ('clientes','ventas','reportes');
  -- Mismo mecanismo, pero filtrado: al rol 3 solo se le conceden los
  -- permisos de esos tres modulos.
  -- IN (...) equivale a escribir modulo='clientes' OR modulo='ventas' OR
  -- modulo='reportes', pero mas corto y legible.
  -- APLICACION DEL PRINCIPIO DE MINIMO PRIVILEGIO: un ejecutivo de ventas
  -- NO recibe permisos de 'usuarios' ni de 'inventario', porque su trabajo
  -- no los necesita. En consecuencia, los botones de esos modulos ni
  -- siquiera se dibujan cuando el inicia sesion.
  -- Los roles 2 (Gerente) y 4 (Ingeniero) quedan a proposito SIN permisos:
  -- existen en el catalogo pero se configuran despues desde el sistema.

-- ---- Usuario administrador ------------------------------------------
--  Usuario: admin   Contrasena: admin123   (CAMBIALA)
INSERT INTO usuarios (username, nombre, email, password_hash, rol_id) VALUES
  ('admin', 'Administrador del Sistema', 'admin@ciberseg.do',
   'scrypt:32768:8:1$hBBK7UriCFhR55dP$713bce44b725ab88a13b2328329eaf48c73b1dea6fb7c551b7094741ca57cf2cc1fb778958a94cbe86ee8be89c3a203118c557139349ad9bb7ba90ffa1dd070f',
   -- ESTA CADENA NO ES LA CONTRASENA: es su HASH, generado por Werkzeug.
   -- Se lee de izquierda a derecha, separada por $ y por dos puntos:
   --   scrypt      -> algoritmo de derivacion de clave usado
   --   32768:8:1   -> parametros de costo (memoria, bloque, paralelismo).
   --                  Cuanto mas altos, mas lento y costoso es intentar
   --                  descifrarla por fuerza bruta.
   --   hBBK7Uri... -> la SAL: texto aleatorio distinto para cada usuario.
   --                  Gracias a ella, dos personas con la misma clave
   --                  tienen hashes diferentes y no se pueden usar
   --                  tablas precalculadas (rainbow tables).
   --   713bce44... -> el hash resultante propiamente dicho.
   -- El proceso es IRREVERSIBLE: de aqui no se puede recuperar 'admin123'.
   -- Al iniciar sesion, check_password_hash() vuelve a aplicar scrypt a lo
   -- que se escribio, con esta misma sal, y compara los dos resultados.
   1);
   -- rol_id = 1 -> Administrador, el rol que recibio todos los permisos
   -- unas lineas mas arriba. Sin esto, el usuario existiria pero no podria
   -- hacer nada al entrar.
   -- activo no se indica: toma su DEFAULT 1 (cuenta habilitada).

-- ---- Fabricantes ----------------------------------------------------
INSERT INTO fabricantes (nombre, pais, sitio_web, soporte_email) VALUES
  -- Se insertan ANTES que los productos porque productos.fabricante_id es
  -- una llave foranea que apunta aqui. El orden de estas cuatro filas
  -- determina su id: Fortinet queda con el id 1 y Cisco con el 2, que son
  -- los que usa el bloque siguiente.
  ('Fortinet',  'Estados Unidos', 'https://www.fortinet.com',     'support@fortinet.com'),   -- id 1: la marca principal que distribuye la empresa
  ('Cisco',     'Estados Unidos', 'https://www.cisco.com',        'support@cisco.com'),      -- id 2
  ('Palo Alto', 'Estados Unidos', 'https://www.paloalto.com',     'support@paloalto.com'),   -- id 3
  ('Sophos',    'Reino Unido',    'https://www.sophos.com',       'support@sophos.com'),     -- id 4
  ('Aruba',     'Estados Unidos', 'https://www.arubanetworks.com','support@aruba.com');      -- id 5

-- ---- Productos de ejemplo (catalogo Fortinet) -----------------------
INSERT INTO productos (fabricante_id, sku, nombre, categoria, tipo, precio_lista, stock, stock_minimo) VALUES
  -- Columnas, en orden: a que fabricante pertenece, codigo de catalogo,
  -- nombre comercial, que es, como se entrega, precio en USD, existencias
  -- actuales y umbral de alerta de stock bajo.
  -- No se indican moneda ni activo: toman sus DEFAULT ('USD' y 1).
  (1, 'FG-40F',     'FortiGate 40F Firewall',          'Firewall',     'Hardware',    650.00, 15, 5),   -- Fabricante 1 = Fortinet
  (1, 'FG-60F',     'FortiGate 60F Firewall',          'Firewall',     'Hardware',    995.00, 12, 5),
  (1, 'FG-100F',    'FortiGate 100F Firewall',         'Firewall',     'Hardware',   3200.00,  6, 3),   -- Equipo de gama alta: menos existencias y umbral mas bajo
  (1, 'FS-108E',    'FortiSwitch 108E',                'Switch',       'Hardware',    420.00, 20, 5),
  (1, 'FAP-231F',   'FortiAP 231F Access Point',       'Access Point', 'Hardware',    380.00, 25, 8),
  (1, 'FC-UTM-60F', 'FortiCare UTM Bundle 60F (1 ano)','Licencia',     'Suscripcion', 540.00,  0, 0),
  -- Este articulo va con stock 0 y minimo 0 A PROPOSITO: al ser de tipo
  -- 'Suscripcion' no es algo fisico que se almacene, asi que no lleva
  -- control de existencias. La plantilla productos.html detecta ese tipo
  -- y muestra un guion en la columna Stock en lugar de una alerta.
  (2, 'C1000-8T',   'Cisco Catalyst 1000 8-Port',      'Switch',       'Hardware',    480.00, 10, 3);   -- Fabricante 2 = Cisco
GO

PRINT 'Datos iniciales cargados.';   -- Confirmacion visible en la pestana Messages de SSMS
GO
