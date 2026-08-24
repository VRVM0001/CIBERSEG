/* =====================================================================
   CIBERSEG  ·  Sistema de Gestion para Empresa de Ciberseguridad
   Esquema de base de datos  ·  Microsoft SQL Server (T-SQL)
   Fase 0 - Fundacion (estructura de tablas)
   -----------------------------------------------------------------
   Como ejecutarlo en SQL Server Management Studio (SSMS):
     1. Abre SSMS y conectate a tu servidor.
     2. Archivo > Abrir > Archivo... y elige este schema.sql
     3. Presiona Ejecutar (F5). Crea la base "ciberseg" con sus tablas.
   -----------------------------------------------------------------
   Notas de diseno:
     - Las llaves foraneas usan NO ACTION (no borrado en cascada).
       Para "borrar" registros usamos la columna 'activo' (borrado logico),
       que es la practica recomendada en un sistema de gestion.
     - Los antiguos ENUM se convirtieron a VARCHAR + CHECK (misma validacion).
   =====================================================================

   -----------------------------------------------------------------
   GUIA DE LECTURA (conceptos que se repiten en TODO el archivo)
   -----------------------------------------------------------------
   IDENTITY(1,1)   Numeracion automatica: la primera fila recibe 1 y cada
                   nueva suma 1. Evita tener que calcular el id a mano y
                   garantiza que nunca se repita.
   PRIMARY KEY     Identificador unico de la fila. No admite NULL ni
                   duplicados. SQL Server le crea un indice automatico.
   FOREIGN KEY     Apunta a la PRIMARY KEY de otra tabla. El motor impide
                   guardar un valor que no exista alla (integridad
                   referencial): no se puede crear un cliente de una
                   empresa inexistente.
   NOT NULL        Campo obligatorio: la fila no se guarda si va vacio.
   UNIQUE          No pueden existir dos filas con ese mismo valor.
   DEFAULT         Valor que se usa cuando el INSERT no menciona la columna.
   CHECK (x IN..)  Lista cerrada de valores permitidos. Sustituye al tipo
                   ENUM de MySQL, que SQL Server no tiene.
   VARCHAR(n)      Texto de longitud variable, maximo n caracteres.
   VARCHAR(MAX)    Texto largo sin limite practico (hasta 2 GB).
   DECIMAL(12,2)   Numero exacto: 12 digitos, 2 de ellos decimales. Se usa
                   para dinero porque FLOAT arrastra errores de redondeo.
   BIT             Booleano: 1 = si / 0 = no.
   DATE            Solo fecha (sin hora).
   DATETIME2       Fecha y hora con precision alta.
   SYSDATETIME()   Fecha y hora actuales del servidor, en DATETIME2.
   created_at /    Par de columnas de control presente en casi todas las
   updated_at      tablas: cuando se creo la fila y cuando se modifico
                   por ultima vez. Sirven para auditoria y ordenamiento.
   activo BIT      Bandera del BORRADO LOGICO: en vez de DELETE se pone en
                   0. El historico se conserva y las llaves foraneas de
                   otras tablas no quedan rotas.
   ===================================================================== */

USE master;
-- 'master' es la base de sistema de SQL Server. Hay que pararse en ella
-- porque no se puede eliminar una base de datos mientras se esta usando
-- esa misma base.
GO
-- GO no es una instruccion de T-SQL: es un separador de LOTES que
-- entiende SSMS. Divide el script en bloques independientes que se
-- envian al servidor de uno en uno.

-- Si la base existe, la elimina (cierra conexiones primero)
IF DB_ID('ciberseg') IS NOT NULL
-- DB_ID('nombre') devuelve el id interno de la base, o NULL si no existe.
-- Es la forma corta de preguntar "esta base ya esta creada?".
BEGIN
    ALTER DATABASE ciberseg SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    -- SINGLE_USER deja la base en modo de un solo usuario y
    -- ROLLBACK IMMEDIATE desconecta a los demas al instante, deshaciendo
    -- sus transacciones abiertas. Sin esto, si tienes una pestana de
    -- consulta abierta en SSMS, el DROP fallaria con "la base esta en uso".
    DROP DATABASE ciberseg;
    -- Elimina la base COMPLETA con todos sus datos. Este script es
    -- destructivo a proposito: siempre reconstruye desde cero.
END
GO

CREATE DATABASE ciberseg;   -- Crea la base de datos vacia
GO

USE ciberseg;               -- A partir de aqui, todo se crea DENTRO de ciberseg
GO

-- =====================================================================
--  MODULO 1 - SEGURIDAD Y ACCESO
--  Contiene el modelo de control de acceso basado en roles (RBAC):
--  un usuario tiene UN rol, y un rol tiene MUCHOS permisos.
-- =====================================================================
CREATE TABLE roles (
  id          INT IDENTITY(1,1) PRIMARY KEY,   -- Id automatico del rol
  nombre      VARCHAR(50)  NOT NULL UNIQUE,    -- 'Administrador', 'Ejecutivo de Ventas'... UNIQUE evita dos roles iguales
  descripcion VARCHAR(255),                    -- Texto libre que explica el alcance del rol (opcional)
  activo      BIT          NOT NULL DEFAULT 1, -- 1 = rol vigente. Permite retirar un rol sin borrarlo
  created_at  DATETIME2    DEFAULT SYSDATETIME(),  -- Momento en que se creo el rol
  updated_at  DATETIME2    DEFAULT SYSDATETIME()   -- Ultima modificacion
);

CREATE TABLE permisos (
  id          INT IDENTITY(1,1) PRIMARY KEY,
  nombre      VARCHAR(80)  NOT NULL UNIQUE,    -- Formato 'modulo.accion' (ej. 'clientes.crear'). Es el texto EXACTO que compara permiso_requerido() en seguridad.py
  modulo      VARCHAR(50)  NOT NULL,           -- Agrupa los permisos por area ('clientes','ventas','inventario'...) para asignarlos en bloque
  descripcion VARCHAR(255),                    -- Explicacion legible del permiso
  created_at  DATETIME2    DEFAULT SYSDATETIME()
  -- Esta tabla NO lleva updated_at ni activo: los permisos son un
  -- catalogo fijo del sistema, no se editan desde la aplicacion.
);

CREATE TABLE roles_permisos (
  -- TABLA PUENTE de la relacion MUCHOS A MUCHOS entre roles y permisos:
  -- un rol tiene varios permisos y un permiso pertenece a varios roles.
  -- Sin ella habria que repetir permisos en cada rol.
  rol_id     INT NOT NULL,                     -- Que rol
  permiso_id INT NOT NULL,                     -- Que permiso se le concede
  PRIMARY KEY (rol_id, permiso_id),
  -- LLAVE PRIMARIA COMPUESTA (dos columnas): la combinacion no puede
  -- repetirse, o sea, no se puede conceder dos veces el mismo permiso al
  -- mismo rol. La tabla no necesita un id propio.
  FOREIGN KEY (rol_id)     REFERENCES roles(id),      -- Debe existir el rol
  FOREIGN KEY (permiso_id) REFERENCES permisos(id)    -- Debe existir el permiso
);

CREATE TABLE usuarios (
  id            INT IDENTITY(1,1) PRIMARY KEY,
  username      VARCHAR(50)  NOT NULL UNIQUE,  -- Nombre de inicio de sesion. UNIQUE porque es la credencial de acceso
  nombre        VARCHAR(100) NOT NULL,         -- Nombre real, el que se muestra en pantalla
  email         VARCHAR(120) NOT NULL UNIQUE,  -- Correo, tambien unico (sirve de contacto e identificador alterno)
  password_hash VARCHAR(255) NOT NULL,
  -- NUNCA se guarda la contrasena en texto plano: se guarda su HASH
  -- (scrypt, generado por Werkzeug). El hash es irreversible; al iniciar
  -- sesion se compara hash contra hash, nunca la clave original.
  -- 255 caracteres porque el formato scrypt incluye algoritmo, parametros,
  -- sal y hash, todo en la misma cadena.
  rol_id        INT          NOT NULL,         -- Rol asignado. NOT NULL: todo usuario debe tener rol, no hay acceso sin permisos definidos
  activo        BIT          NOT NULL DEFAULT 1,  -- 0 = cuenta desactivada (no puede entrar, pero su historial se conserva)
  ultimo_acceso DATETIME2,                     -- Se actualiza en cada login correcto (auth.py). NULL = nunca ha entrado
  created_at    DATETIME2    DEFAULT SYSDATETIME(),
  updated_at    DATETIME2    DEFAULT SYSDATETIME(),
  FOREIGN KEY (rol_id) REFERENCES roles(id)
  -- Relacion 1:N -> un rol lo tienen MUCHOS usuarios, cada usuario tiene UNO.
  -- Ademas impide eliminar un rol que todavia este en uso.
);

CREATE TABLE auditoria (
  -- Bitacora del sistema: registra QUIEN cambio QUE, CUANDO y DESDE DONDE.
  -- Se llena por dos vias (auditoria por partida doble):
  --   1. registrar_auditoria() en Python -> sabe el usuario de la sesion
  --   2. los triggers de la BD           -> capturan hasta los cambios
  --      hechos directamente en SSMS, sin pasar por la aplicacion
  id               BIGINT IDENTITY(1,1) PRIMARY KEY,
  -- BIGINT y no INT: esta tabla crece con CADA operacion del sistema y
  -- puede superar los 2,147 millones de filas que admite un INT.
  usuario_id       INT,
  -- Quien lo hizo. Admite NULL a proposito: los eventos generados por
  -- triggers no tienen sesion web, asi que no hay usuario que registrar.
  tabla_afectada   VARCHAR(64) NOT NULL,       -- Nombre de la tabla que cambio ('clientes','facturas'...)
  accion           VARCHAR(10) NOT NULL CHECK (accion IN ('INSERT','UPDATE','DELETE')),
  -- El CHECK limita el valor a las tres operaciones posibles. Es el mismo
  -- dominio que usa el parametro 'accion' de registrar_auditoria().
  registro_id      VARCHAR(64),
  -- Id de la fila afectada, guardado como TEXTO y no como INT: asi sirve
  -- tanto para ids numericos como para claves de texto (por ejemplo, la
  -- clave 'itbis_pct' de la tabla configuracion).
  datos_anteriores NVARCHAR(MAX),              -- Valores ANTES del cambio, en formato JSON (solo aplica a UPDATE/DELETE)
  datos_nuevos     NVARCHAR(MAX),              -- Valores DESPUES del cambio, en JSON
  -- NVARCHAR (con N) y no VARCHAR: N = Unicode, conserva tildes y enes en
  -- el JSON guardado.
  ip_origen        VARCHAR(45),
  -- Direccion IP del equipo que hizo el cambio. 45 caracteres porque una
  -- direccion IPv6 completa puede alcanzar esa longitud.
  fecha            DATETIME2   DEFAULT SYSDATETIME(),  -- Sello de tiempo del evento
  FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);

-- =====================================================================
--  MODULO 2 - CRM
--  Modelo de tres niveles: EMPRESA (la organizacion) -> CLIENTE (la
--  relacion comercial con ella) -> CONTACTOS (las personas).
--  Se separan empresa y cliente porque una empresa puede existir como
--  prospecto sin ser todavia cliente.
-- =====================================================================
CREATE TABLE empresas (
  id         INT IDENTITY(1,1) PRIMARY KEY,
  nombre     VARCHAR(150) NOT NULL,            -- Razon social. NO es UNIQUE: pueden existir nombres parecidos y el sistema avisa del posible duplicado en vez de bloquearlo
  rnc        VARCHAR(20)  UNIQUE,              -- Registro Nacional del Contribuyente (RD). UNIQUE porque identifica legalmente a la empresa; admite NULL si aun no se conoce
  sector     VARCHAR(80),                      -- Rubro: Banca, Retail, Salud...
  tamano     VARCHAR(20)  DEFAULT 'Mediana' CHECK (tamano IN ('Micro','Pequena','Mediana','Grande','Corporativo')),
  -- Clasificacion por tamano. El CHECK cierra la lista de valores validos
  -- y el DEFAULT decide cual se usa si el formulario no lo envia.
  sitio_web  VARCHAR(120),
  telefono   VARCHAR(30),
  -- Los telefonos se guardan como TEXTO, no como numero: pueden llevar
  -- signo +, guiones, parentesis y ceros a la izquierda.
  email      VARCHAR(120),
  direccion  VARCHAR(200),
  ciudad     VARCHAR(80),
  pais       VARCHAR(80)  DEFAULT 'Republica Dominicana',   -- Valor por defecto: la mayoria de clientes son locales
  activo     BIT          NOT NULL DEFAULT 1,  -- Borrado logico
  created_at DATETIME2    DEFAULT SYSDATETIME(),
  updated_at DATETIME2    DEFAULT SYSDATETIME()
);

CREATE TABLE clientes (
  id             INT IDENTITY(1,1) PRIMARY KEY,
  codigo         VARCHAR(20)  NOT NULL UNIQUE, -- Codigo comercial visible (CLI-0001). UNIQUE: es el identificador que usa el personal, no el id interno
  empresa_id     INT          NOT NULL,        -- A que empresa corresponde. NOT NULL: no existe un cliente sin empresa
  tipo           VARCHAR(20)  DEFAULT 'Corporativo' CHECK (tipo IN ('Corporativo','Gobierno','PYME','Educacion','Salud')),
  -- Naturaleza del cliente. Alimenta el grafico "Clientes por tipo" del dashboard.
  segmento       VARCHAR(20)  DEFAULT 'Regular' CHECK (segmento IN ('Estrategico','Mayorista','Regular')),
  -- Importancia comercial, usada para priorizar atencion y descuentos.
  ejecutivo_id   INT,
  -- Vendedor asignado (apunta a usuarios). Admite NULL: un prospecto
  -- recien creado puede no tener ejecutivo todavia.
  estado         VARCHAR(20)  DEFAULT 'Prospecto' CHECK (estado IN ('Prospecto','Activo','Inactivo','Suspendido')),
  -- Etapa del ciclo de vida comercial. Todo cliente nace como 'Prospecto'.
  limite_credito DECIMAL(12,2) DEFAULT 0,      -- Tope de credito en USD. DECIMAL por ser dinero
  fecha_alta     DATE,                         -- Cuando se volvio cliente (dato de negocio, distinto de created_at, que es dato de sistema)
  notas          VARCHAR(MAX),                 -- Observaciones libres, sin limite practico de longitud
  created_at     DATETIME2    DEFAULT SYSDATETIME(),
  updated_at     DATETIME2    DEFAULT SYSDATETIME(),
  FOREIGN KEY (empresa_id)   REFERENCES empresas(id),   -- 1 empresa : N clientes
  FOREIGN KEY (ejecutivo_id) REFERENCES usuarios(id)    -- 1 usuario : N clientes atendidos
);

CREATE TABLE contactos (
  id           INT IDENTITY(1,1) PRIMARY KEY,
  empresa_id   INT          NOT NULL,          -- Los contactos cuelgan de la EMPRESA, no del cliente: siguen siendo utiles aunque la relacion comercial cambie
  nombre       VARCHAR(100) NOT NULL,          -- Nombre de la persona
  cargo        VARCHAR(80),                    -- Puesto (Gerente de TI, CISO...)
  departamento VARCHAR(80),
  email        VARCHAR(120),
  telefono     VARCHAR(30),                    -- Telefono fijo / central
  celular      VARCHAR(30),                    -- Movil directo
  es_principal BIT          NOT NULL DEFAULT 0,
  -- Marca al interlocutor principal de la empresa. Es el contacto al que
  -- ventas.py envia las cotizaciones por correo.
  activo       BIT          NOT NULL DEFAULT 1,
  created_at   DATETIME2    DEFAULT SYSDATETIME(),
  updated_at   DATETIME2    DEFAULT SYSDATETIME(),
  FOREIGN KEY (empresa_id) REFERENCES empresas(id)
);

-- =====================================================================
--  MODULO 3 - PERSONAL TECNICO
-- =====================================================================
CREATE TABLE ingenieros (
  id              INT IDENTITY(1,1) PRIMARY KEY,
  usuario_id      INT,
  -- Enlace OPCIONAL con una cuenta del sistema: hay ingenieros que
  -- aparecen como recurso asignable a proyectos pero no inician sesion.
  nombre          VARCHAR(100) NOT NULL,
  especialidad    VARCHAR(80),                 -- Seguridad perimetral, redes, cloud...
  nivel           VARCHAR(20)  DEFAULT 'Junior' CHECK (nivel IN ('Junior','Semi-Senior','Senior','Lead')),
  -- Escalafon tecnico. La misma lista esta replicada en NIVELES_ING dentro
  -- de gestion.py, que valida el valor antes de enviarlo (doble validacion:
  -- aplicacion y motor).
  certificaciones VARCHAR(255),                -- NSE4, CCNA, CISSP... texto libre separado por comas
  email           VARCHAR(120),
  telefono        VARCHAR(30),
  activo          BIT          NOT NULL DEFAULT 1,   -- Solo los activos aparecen como lider asignable en proyectos
  created_at      DATETIME2    DEFAULT SYSDATETIME(),
  updated_at      DATETIME2    DEFAULT SYSDATETIME(),
  FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);

-- =====================================================================
--  MODULO 4 - CATALOGO DE PRODUCTOS
-- =====================================================================
CREATE TABLE fabricantes (
  id            INT IDENTITY(1,1) PRIMARY KEY,
  nombre        VARCHAR(80)  NOT NULL UNIQUE,  -- Fortinet, Cisco, Sophos... UNIQUE: un fabricante se registra una sola vez
  pais          VARCHAR(80),
  sitio_web     VARCHAR(120),
  soporte_email VARCHAR(120),                  -- Canal de soporte del fabricante (no del cliente)
  soporte_tel   VARCHAR(30),
  activo        BIT          NOT NULL DEFAULT 1,
  created_at    DATETIME2    DEFAULT SYSDATETIME(),
  updated_at    DATETIME2    DEFAULT SYSDATETIME()
);

CREATE TABLE productos (
  id            INT IDENTITY(1,1) PRIMARY KEY,
  fabricante_id INT          NOT NULL,         -- Todo producto pertenece a un fabricante
  sku           VARCHAR(60)  NOT NULL UNIQUE,  -- Codigo de catalogo del fabricante (FG-60F). UNIQUE: identifica el articulo sin ambiguedad
  nombre        VARCHAR(150) NOT NULL,         -- Descripcion comercial
  categoria     VARCHAR(20)  DEFAULT 'Otro' CHECK (categoria IN ('Firewall','Switch','Access Point','Software','Licencia','Servicio','Otro')),
  -- QUE ES el producto. Se usa para filtrar el catalogo.
  tipo          VARCHAR(20)  DEFAULT 'Hardware' CHECK (tipo IN ('Hardware','Software','Suscripcion','Servicio')),
  -- COMO se entrega. Es distinto de la categoria y decide si el articulo
  -- lleva control de stock: en la vista de productos, los de tipo
  -- 'Suscripcion' y 'Servicio' muestran un guion en lugar de existencias.
  descripcion   VARCHAR(MAX),
  precio_lista  DECIMAL(12,2) NOT NULL DEFAULT 0,   -- Precio de referencia; en la cotizacion puede modificarse por linea
  moneda        VARCHAR(3)   DEFAULT 'USD' CHECK (moneda IN ('USD','DOP','EUR')),
  -- Codigo ISO de 3 letras. Por defecto USD, moneda habitual en la
  -- distribucion de tecnologia.
  stock         INT          NOT NULL DEFAULT 0,    -- Existencias actuales. Solo cambia por ajustes auditados (+/-), nunca a mano en el formulario
  stock_minimo  INT          NOT NULL DEFAULT 0,    -- Umbral de alerta: si stock <= stock_minimo, la aplicacion marca "stock bajo"
  activo        BIT          NOT NULL DEFAULT 1,
  created_at    DATETIME2    DEFAULT SYSDATETIME(),
  updated_at    DATETIME2    DEFAULT SYSDATETIME(),
  FOREIGN KEY (fabricante_id) REFERENCES fabricantes(id)
);

CREATE TABLE licencias (
  -- Licencia concreta VENDIDA a un cliente (no el producto de catalogo).
  id           INT IDENTITY(1,1) PRIMARY KEY,
  producto_id  INT          NOT NULL,          -- Que producto licenciado es
  cliente_id   INT          NOT NULL,          -- A quien pertenece
  clave        VARCHAR(120),                   -- Serial o clave de activacion entregada por el fabricante
  tipo         VARCHAR(20)  DEFAULT 'Anual' CHECK (tipo IN ('Anual','Multianual','Perpetua','Trial')),
  fecha_inicio DATE         NOT NULL,          -- Inicio de vigencia. Obligatoria: sin ella no se puede calcular el vencimiento
  fecha_fin    DATE,                           -- Fin de vigencia. NULL = licencia perpetua (no vence nunca)
  estado       VARCHAR(20)  DEFAULT 'Activa' CHECK (estado IN ('Activa','Por vencer','Vencida','Cancelada')),
  created_at   DATETIME2    DEFAULT SYSDATETIME(),
  updated_at   DATETIME2    DEFAULT SYSDATETIME(),
  FOREIGN KEY (producto_id) REFERENCES productos(id),
  FOREIGN KEY (cliente_id)  REFERENCES clientes(id)
);

-- =====================================================================
--  MODULO 5 - VENTAS
--  Flujo del negocio: COTIZACION (con sus lineas de detalle) -> al
--  aprobarse genera una FACTURA. Los CONTRATOS son acuerdos recurrentes
--  independientes de ese flujo.
-- =====================================================================
CREATE TABLE cotizaciones (
  id            INT IDENTITY(1,1) PRIMARY KEY,
  numero        VARCHAR(20)  NOT NULL UNIQUE,  -- Numero visible (COT-2025-0001). UNIQUE: es el folio del documento comercial
  cliente_id    INT          NOT NULL,         -- A quien se cotiza
  ejecutivo_id  INT,                           -- Quien la elaboro (puede quedar sin asignar)
  fecha         DATE         NOT NULL,         -- Fecha de emision
  fecha_validez DATE,                          -- Hasta cuando se respetan los precios
  estado        VARCHAR(20)  DEFAULT 'Borrador' CHECK (estado IN ('Borrador','Enviada','Aprobada','Rechazada','Vencida')),
  -- Flujo de estados. Solo una cotizacion 'Aprobada' puede convertirse en
  -- factura; esa regla la aplican ventas.py y el procedimiento
  -- sp_aprobar_y_facturar.
  subtotal      DECIMAL(12,2) NOT NULL DEFAULT 0,   -- Suma de las lineas, antes de impuesto
  impuesto      DECIMAL(12,2) NOT NULL DEFAULT 0,   -- ITBIS calculado sobre el subtotal
  total         DECIMAL(12,2) NOT NULL DEFAULT 0,   -- subtotal + impuesto
  -- Los tres totales estan DESNORMALIZADOS (podrian recalcularse desde el
  -- detalle). Se guardan por dos razones: el reporte es inmediato y el
  -- documento conserva el importe historico. De mantenerlos sincronizados
  -- se encarga el trigger trg_detalle_totales (sqlserver_avanzado.sql).
  moneda        VARCHAR(3)   DEFAULT 'USD' CHECK (moneda IN ('USD','DOP','EUR')),
  notas         VARCHAR(MAX),
  created_at    DATETIME2    DEFAULT SYSDATETIME(),
  updated_at    DATETIME2    DEFAULT SYSDATETIME(),
  FOREIGN KEY (cliente_id)   REFERENCES clientes(id),
  FOREIGN KEY (ejecutivo_id) REFERENCES usuarios(id)
);

CREATE TABLE detalle_cotizacion (
  -- Las LINEAS de la cotizacion: un renglon por producto cotizado.
  -- Es una tabla debil: sus filas no tienen sentido sin su cotizacion.
  id              INT IDENTITY(1,1) PRIMARY KEY,
  cotizacion_id   INT          NOT NULL,       -- A que cotizacion pertenece la linea
  producto_id     INT          NOT NULL,       -- Que producto se cotiza
  cantidad        INT          NOT NULL DEFAULT 1,
  precio_unitario DECIMAL(12,2) NOT NULL DEFAULT 0,
  -- Se COPIA el precio del producto en el momento de cotizar, en vez de
  -- leerlo del catalogo al mostrarlo. Asi, si el precio de lista sube
  -- manana, la cotizacion sigue reflejando lo que realmente se ofrecio.
  descuento_pct   DECIMAL(5,2)  NOT NULL DEFAULT 0,
  -- Descuento en porcentaje. DECIMAL(5,2) admite hasta 999.99, de sobra
  -- para un valor de 0 a 100.
  subtotal        DECIMAL(12,2) NOT NULL DEFAULT 0,
  -- Importe de la linea: cantidad * precio_unitario * (1 - descuento/100).
  -- Guardarlo evita repetir el calculo en cada consulta y es lo que suma
  -- el procedimiento sp_recalcular_totales_cotizacion.
  FOREIGN KEY (cotizacion_id) REFERENCES cotizaciones(id),
  FOREIGN KEY (producto_id)   REFERENCES productos(id)
  -- Esta tabla no lleva created_at/updated_at: las lineas se reemplazan
  -- por completo cada vez que se edita la cotizacion.
);

CREATE TABLE facturas (
  id                INT IDENTITY(1,1) PRIMARY KEY,
  numero            VARCHAR(20)  NOT NULL UNIQUE,   -- Folio fiscal visible (FAC-2025-0001)
  cotizacion_id     INT,
  -- Cotizacion de origen. Admite NULL porque se puede emitir una factura
  -- directa, sin cotizacion previa (ruta factura_nueva de ventas.py).
  cliente_id        INT          NOT NULL,     -- A quien se le factura. Obligatorio aunque no haya cotizacion
  fecha_emision     DATE         NOT NULL,     -- Cuando se emitio
  fecha_vencimiento DATE,                      -- Fecha limite de pago (por defecto, emision + 30 dias)
  subtotal          DECIMAL(12,2) NOT NULL DEFAULT 0,
  impuesto          DECIMAL(12,2) NOT NULL DEFAULT 0,
  total             DECIMAL(12,2) NOT NULL DEFAULT 0,
  -- Importes copiados de la cotizacion al facturar. Se congelan: la
  -- factura es un documento legal y no debe cambiar si la cotizacion se edita.
  moneda            VARCHAR(3)   DEFAULT 'USD' CHECK (moneda IN ('USD','DOP','EUR')),
  estado            VARCHAR(20)  DEFAULT 'Pendiente' CHECK (estado IN ('Pendiente','Pagada','Vencida','Anulada')),
  -- Solo las facturas 'Pagada' cuentan como ingreso real en el dashboard
  -- y en las vistas de reporte.
  created_at        DATETIME2    DEFAULT SYSDATETIME(),
  updated_at        DATETIME2    DEFAULT SYSDATETIME(),
  FOREIGN KEY (cotizacion_id) REFERENCES cotizaciones(id),
  FOREIGN KEY (cliente_id)    REFERENCES clientes(id)
);

CREATE TABLE contratos (
  id           INT IDENTITY(1,1) PRIMARY KEY,
  numero       VARCHAR(20)  NOT NULL UNIQUE,   -- Folio del contrato (CTR-2025-0001)
  cliente_id   INT          NOT NULL,
  tipo         VARCHAR(30)  DEFAULT 'Soporte' CHECK (tipo IN ('Soporte','Mantenimiento','Licenciamiento','Servicios Profesionales')),
  -- VARCHAR(30) y no 20 como en otras tablas: 'Servicios Profesionales'
  -- ocupa 23 caracteres y no cabria en 20.
  fecha_inicio DATE         NOT NULL,          -- Inicio de vigencia
  fecha_fin    DATE,                           -- Fin de vigencia. NULL = indefinido
  monto        DECIMAL(12,2) NOT NULL DEFAULT 0,    -- Valor total del contrato
  moneda       VARCHAR(3)   DEFAULT 'USD' CHECK (moneda IN ('USD','DOP','EUR')),
  estado       VARCHAR(20)  DEFAULT 'Vigente' CHECK (estado IN ('Vigente','Por vencer','Vencido','Cancelado')),
  terminos     VARCHAR(MAX),                   -- Clausulas y condiciones, texto largo
  created_at   DATETIME2    DEFAULT SYSDATETIME(),
  updated_at   DATETIME2    DEFAULT SYSDATETIME(),
  FOREIGN KEY (cliente_id) REFERENCES clientes(id)
);

-- =====================================================================
--  MODULO 6 - INVENTARIO TECNICO
--  Equipos FISICOS ya instalados en la sede del cliente. No confundir con
--  'productos', que es el catalogo de lo que se vende.
-- =====================================================================
CREATE TABLE equipos (
  id                INT IDENTITY(1,1) PRIMARY KEY,
  cliente_id        INT          NOT NULL,     -- En que cliente esta instalado. Obligatorio: un equipo instalado siempre esta en algun sitio
  producto_id       INT,
  -- Modelo de catalogo al que corresponde. Admite NULL para poder
  -- registrar equipos heredados o de marcas que no se distribuyen.
  tipo              VARCHAR(20)  DEFAULT 'Otro' CHECK (tipo IN ('Firewall','Switch','Access Point','Servidor','Otro')),
  numero_serie      VARCHAR(80)  UNIQUE,
  -- Serie del fabricante. UNIQUE: identifica fisicamente al aparato y no
  -- puede haber dos iguales. Admite NULL si aun no se ha registrado.
  hostname          VARCHAR(80),               -- Nombre en la red del cliente (FW-SEDE-01)
  ubicacion         VARCHAR(120),              -- Donde esta fisicamente (Datacenter, Sucursal Norte...)
  estado            VARCHAR(20)  DEFAULT 'Operativo' CHECK (estado IN ('Operativo','En mantenimiento','Fuera de servicio','En reemplazo')),
  -- Los equipos que no estan 'Operativo' generan notificaciones en el sistema.
  fecha_instalacion DATE,
  created_at        DATETIME2    DEFAULT SYSDATETIME(),
  updated_at        DATETIME2    DEFAULT SYSDATETIME(),
  FOREIGN KEY (cliente_id)  REFERENCES clientes(id),
  FOREIGN KEY (producto_id) REFERENCES productos(id)
);

-- =====================================================================
--  MODULO 7 - PROYECTOS
-- =====================================================================
CREATE TABLE proyectos (
  id                 INT IDENTITY(1,1) PRIMARY KEY,
  nombre             VARCHAR(150) NOT NULL,
  cliente_id         INT          NOT NULL,    -- Cliente para el que se ejecuta. Obligatorio
  ingeniero_lider_id INT,
  -- Responsable tecnico. OPCIONAL: un proyecto puede estar planificado sin
  -- lider asignado todavia. Por eso gestion.py lo consulta con LEFT JOIN.
  fecha_inicio       DATE,
  fecha_fin_estimada DATE,                     -- Lo planificado
  fecha_fin_real     DATE,                     -- Lo ocurrido. Comparar ambas mide la desviacion del proyecto
  estado             VARCHAR(20)  DEFAULT 'Planificado' CHECK (estado IN ('Planificado','En curso','En pausa','Completado','Cancelado')),
  presupuesto        DECIMAL(12,2) DEFAULT 0,
  moneda             VARCHAR(3)   DEFAULT 'USD' CHECK (moneda IN ('USD','DOP','EUR')),
  descripcion        VARCHAR(MAX),
  created_at         DATETIME2    DEFAULT SYSDATETIME(),
  updated_at         DATETIME2    DEFAULT SYSDATETIME(),
  FOREIGN KEY (cliente_id)         REFERENCES clientes(id),
  FOREIGN KEY (ingeniero_lider_id) REFERENCES ingenieros(id)
);



CREATE TABLE configuracion (
  -- Tabla CLAVE-VALOR con los parametros globales del sistema (porcentaje
  -- de ITBIS, minutos de sesion, datos SMTP...). Este diseno permite
  -- agregar un parametro nuevo sin alterar la estructura de la tabla.
  clave      VARCHAR(60) PRIMARY KEY,
  -- El nombre del parametro ES la llave primaria: no hay id numerico y
  -- una clave no puede repetirse.
  valor      VARCHAR(255) NOT NULL,
  -- Todo se guarda como TEXTO, sea numero, interruptor o plantilla de
  -- correo. Quien lo consume se encarga de convertirlo (TRY_CAST en SQL,
  -- int() en Python).
  updated_at DATETIME2 DEFAULT SYSDATETIME()
);
GO

-- =====================================================================
--  INDICES (para acelerar busquedas frecuentes)
--  Un indice funciona como el indice de un libro: en vez de recorrer toda
--  la tabla fila por fila, el motor salta directo a las que interesan.
--  Se crean sobre las columnas que mas aparecen en WHERE y en JOIN.
--  Contrapartida: ocupan espacio y hacen un poco mas lentos los INSERT y
--  UPDATE, porque el indice tambien debe actualizarse.
--  No se indexan las llaves primarias: SQL Server ya les crea su indice.
-- =====================================================================
CREATE INDEX idx_permisos_modulo     ON permisos(modulo);            -- Para asignar permisos en bloque por modulo
CREATE INDEX idx_usuarios_rol        ON usuarios(rol_id);            -- Acelera el JOIN usuarios-roles del login
CREATE INDEX idx_auditoria_tabla     ON auditoria(tabla_afectada);   -- Filtro por tabla en la pantalla de Auditoria
CREATE INDEX idx_auditoria_fecha     ON auditoria(fecha);            -- Ordenar el historial por fecha (la tabla mas grande del sistema)
CREATE INDEX idx_empresas_nombre     ON empresas(nombre);            -- Busqueda de empresas por nombre
CREATE INDEX idx_clientes_empresa    ON clientes(empresa_id);        -- JOIN clientes-empresas, presente en casi toda consulta del CRM
CREATE INDEX idx_clientes_estado     ON clientes(estado);            -- Filtro por estado en el listado de clientes
CREATE INDEX idx_contactos_empresa   ON contactos(empresa_id);       -- Contactos de una empresa
CREATE INDEX idx_productos_fabricante ON productos(fabricante_id);   -- JOIN productos-fabricantes del catalogo
CREATE INDEX idx_productos_categoria ON productos(categoria);        -- Filtro por categoria
CREATE INDEX idx_licencias_cliente   ON licencias(cliente_id);       -- Licencias de un cliente
CREATE INDEX idx_licencias_estado    ON licencias(estado);           -- Alertas de licencias por vencer
CREATE INDEX idx_cotizaciones_cli    ON cotizaciones(cliente_id);    -- Cotizaciones de un cliente
CREATE INDEX idx_cotizaciones_estado ON cotizaciones(estado);        -- Filtro por estado y calculo de KPIs
CREATE INDEX idx_detcot_cotizacion   ON detalle_cotizacion(cotizacion_id);  -- Clave para el rendimiento: es la busqueda que hace el trigger de totales en CADA cambio de linea
CREATE INDEX idx_facturas_cliente    ON facturas(cliente_id);        -- Facturas de un cliente
CREATE INDEX idx_facturas_estado     ON facturas(estado);            -- Usado por todo reporte que filtra estado='Pagada'
CREATE INDEX idx_contratos_cliente   ON contratos(cliente_id);
CREATE INDEX idx_equipos_cliente     ON equipos(cliente_id);         -- Equipos instalados en un cliente
CREATE INDEX idx_equipos_tipo        ON equipos(tipo);               -- Grafico "Equipos por tipo" del dashboard
CREATE INDEX idx_proyectos_cliente   ON proyectos(cliente_id);
CREATE INDEX idx_proyectos_estado    ON proyectos(estado);
GO

PRINT 'Base de datos ciberseg creada: 19 tablas.';
-- PRINT escribe en la pestana "Messages" de SSMS: confirma que el script
-- llego hasta el final sin errores.
GO
