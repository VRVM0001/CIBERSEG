/* CIBERSEG - Mejoras CRM FASE 2: Actividades. Ejecutar UNA vez. */
/* =====================================================================
   QUE AGREGA:
     1. La tabla 'actividades': la bitacora de seguimiento comercial.
     2. Una clave nueva en 'configuracion' para poder activar o desactivar
        sus notificaciones.

   PARA QUE SIRVE: registrar cada contacto con el cliente (llamadas,
   reuniones, correos, tareas) y, sobre todo, QUE HAY QUE HACER DESPUES.
   Es lo que evita que un cliente quede sin seguimiento.

   REQUISITOS PREVIOS: schema.sql y configuracion.sql.
   ===================================================================== */
USE ciberseg;
GO
IF OBJECT_ID('actividades') IS NULL
CREATE TABLE actividades (
  id INT IDENTITY(1,1) PRIMARY KEY,
  cliente_id INT NOT NULL FOREIGN KEY REFERENCES clientes(id),   -- Con que cliente fue la gestion. Obligatorio
  usuario_id INT FOREIGN KEY REFERENCES usuarios(id),
  -- Quien la registro. OPCIONAL a proposito: el trigger
  -- trg_oportunidad_ganada crea actividades automaticamente y puede que la
  -- oportunidad no tuviera ejecutivo asignado, en cuyo caso este campo
  -- queda en NULL.
  tipo VARCHAR(20) NOT NULL DEFAULT 'Llamada'
       CHECK (tipo IN ('Llamada','Reunion','Correo','Tarea')),
  -- Canal o naturaleza de la gestion. Las tres primeras son contactos ya
  -- ocurridos; 'Tarea' es un pendiente por hacer.
  asunto VARCHAR(150) NOT NULL,                                  -- Resumen en una linea. Obligatorio: una actividad sin asunto no informa nada
  notas VARCHAR(MAX),                                            -- Detalle extenso de lo conversado
  fecha DATETIME2 DEFAULT SYSDATETIME(),
  -- Cuando OCURRIO la gestion. Es DATETIME2 y no DATE porque en un mismo
  -- dia puede haber varias llamadas y el orden entre ellas importa.
  proxima_accion DATE,
  -- LA COLUMNA MAS IMPORTANTE DE LA TABLA: la fecha comprometida para el
  -- siguiente paso. Es la que alimenta las alertas de seguimiento vencido
  -- y la vista vw_actividades_pendientes. NULL = no requiere seguimiento.
  completada BIT NOT NULL DEFAULT 0
  -- 0 = pendiente, 1 = ya realizada. Nace en 0 y el boton "Completar" del
  -- listado la pone en 1. Combinada con proxima_accion, define que
  -- aparece como atrasado.
);
GO
IF NOT EXISTS (SELECT 1 FROM configuracion WHERE clave='notif_actividades')
  INSERT INTO configuracion (clave, valor) VALUES ('notif_actividades','1');
  -- Interruptor de las alertas de seguimiento ('1' = encendido). Se agrega
  -- aqui, y no en configuracion.sql, porque el parametro pertenece a esta
  -- funcionalidad: cada fase instala sus propias claves.
GO
PRINT 'Fase 2 (actividades) instalada.';
GO
