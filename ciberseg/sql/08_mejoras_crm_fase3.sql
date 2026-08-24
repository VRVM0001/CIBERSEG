/* CIBERSEG - FASE 3: etiquetas. Ejecutar UNA vez. */
/* =====================================================================
   QUE AGREGA: la columna 'etiquetas' a la tabla clientes, para clasificar
   libremente ("renovacion Q3", "riesgo de fuga", "cuenta clave").

   POR QUE UNA COLUMNA DE TEXTO Y NO UNA TABLA DE ETIQUETAS:
     Lo normalizado seria crear dos tablas (etiquetas y clientes_etiquetas).
     Aqui se optó por guardar las etiquetas separadas por coma en un solo
     campo. Es una DESNORMALIZACION deliberada: la funcionalidad es
     auxiliar, las etiquetas se escriben libremente y no se hacen reportes
     agregados sobre ellas, asi que el costo de dos tablas mas no se
     justificaba. La aplicacion las separa por coma al mostrarlas y filtra
     con LIKE.
     Limitacion que trae, y conviene reconocer: no se puede renombrar una
     etiqueta en todos los clientes de una sola vez.
   ===================================================================== */
USE ciberseg;
GO
IF COL_LENGTH('clientes','etiquetas') IS NULL
-- COL_LENGTH devuelve NULL si la columna no existe: evita el error al
-- volver a ejecutar el script.
  ALTER TABLE clientes ADD etiquetas VARCHAR(255);
  -- Se agrega SIN NOT NULL y sin DEFAULT: los clientes existentes quedan
  -- con NULL (sin etiquetas), que es justo lo correcto. Es la diferencia
  -- con seguridad.sql, donde el contador de intentos si necesitaba un
  -- valor inicial obligatorio.
GO
PRINT 'Fase 3 (etiquetas) instalada.';
GO
