/* CIBERSEG - Mejoras CRM FASE 1: Pipeline de oportunidades. Ejecutar UNA vez. */
/* =====================================================================
   QUE AGREGA: la tabla 'oportunidades', que es el EMBUDO DE VENTAS
   (pipeline) del CRM.

   QUE ES UNA OPORTUNIDAD Y EN QUE SE DIFERENCIA DE UNA COTIZACION:
     La oportunidad es un negocio POTENCIAL, todavia sin documento: "creo
     que este banco nos comprara unos 50 mil dolares en firewalls".
     La cotizacion es el documento formal que se emite cuando ese negocio
     ya se concreto lo suficiente.
     Una oportunidad avanza por ETAPAS y puede terminar perdida sin haber
     generado ninguna cotizacion. Por eso son tablas separadas.

   DONDE SE VE EN LA APLICACION: en el tablero Kanban de Oportunidades
   (pipeline.html), donde cada etapa es una columna.

   REQUISITO PREVIO: schema.sql (necesita las tablas clientes y usuarios).
   ===================================================================== */
USE ciberseg;
GO
IF OBJECT_ID('oportunidades') IS NULL
-- Solo crea la tabla si no existe: hace el script re-ejecutable sin error.
CREATE TABLE oportunidades (
  id INT IDENTITY(1,1) PRIMARY KEY,                          -- Id automatico
  cliente_id INT NOT NULL FOREIGN KEY REFERENCES clientes(id),
  -- De que cliente es la oportunidad. Obligatorio: no hay negocio sin
  -- alguien a quien venderle.
  -- Aqui la llave foranea se declara EN LINEA (dentro de la definicion de
  -- la columna). En schema.sql se declaran al final de la tabla; ambas
  -- formas son validas y producen exactamente la misma restriccion.
  nombre VARCHAR(150) NOT NULL,                              -- Descripcion del negocio ("Renovacion firewalls sede central")
  etapa VARCHAR(20) NOT NULL DEFAULT 'Contacto'
        CHECK (etapa IN ('Contacto','Propuesta','Negociacion','Ganada','Perdida')),
  -- EL EMBUDO. Las cinco etapas estan en ORDEN de avance y ese orden
  -- importa: los botones de flecha del Kanban mueven la oportunidad a la
  -- etapa anterior o siguiente de esta misma lista.
  -- 'Ganada' y 'Perdida' son estados finales. Toda oportunidad nace en
  -- 'Contacto' gracias al DEFAULT.
  valor_estimado DECIMAL(12,2) DEFAULT 0,                    -- Cuanto se espera vender, en USD
  probabilidad INT DEFAULT 50,
  -- Probabilidad de cierre, de 0 a 100. Sirve para calcular el VALOR
  -- PONDERADO del embudo: valor_estimado * probabilidad / 100. Diez
  -- oportunidades de 100 mil al 10% valen, en previsiones, lo mismo que
  -- una de 100 mil al 100%. Ese calculo lo hace la vista vw_pipeline.
  -- 50 por defecto: sin informacion, se asume una posibilidad intermedia.
  fecha_cierre_estimada DATE,                                -- Cuando se espera cerrar el negocio (para previsiones por periodo)
  ejecutivo_id INT FOREIGN KEY REFERENCES usuarios(id),      -- Vendedor responsable. Opcional (admite NULL al no llevar NOT NULL)
  notas VARCHAR(MAX),                                        -- Seguimiento libre
  created_at DATETIME2 DEFAULT SYSDATETIME(),
  updated_at DATETIME2 DEFAULT SYSDATETIME()
);
GO
PRINT 'Fase 1 (oportunidades) instalada.';
GO
