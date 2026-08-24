"""
=========================================================================
 Módulo: db.py
 Capa de acceso a la base de datos (SQL Server con pyodbc).

 Usamos consultas PARAMETRIZADAS con '?' en todo el proyecto. En un
 sistema de ciberseguridad esto es clave: nunca concatenamos texto del
 usuario dentro del SQL, así evitamos inyección SQL.

 Este es el ÚNICO archivo del proyecto que importa pyodbc directamente.
 Ninguna ruta abre su propia conexión: todas pasan por las funciones
 de aquí (query_all, query_one, execute, insertar, db_status).
=========================================================================
"""
import pyodbc                          # Driver de Python para hablar con SQL Server via ODBC
from flask import g, current_app       # g: memoria de la petición actual; current_app: la app activa


"""
   Función: _connection_string
   Objetivo: Construir la cadena de conexión ODBC que pyodbc necesita
             para abrir la conexión con SQL Server.
   Parámetros: No recibe (lee la configuración de current_app.config,
               que a su vez viene del archivo .env vía config.py).
   Retorno: Texto (str) con la cadena de conexión completa, lista para
            pasarle a pyodbc.connect().
"""
def _connection_string():
    """Arma la cadena de conexion ODBC a partir de la configuracion."""
    cfg = current_app.config                       # Diccionario de configuracion de Flask (viene de config.py)
    partes = [
        f"DRIVER={{{cfg['DB_DRIVER']}}}",           # Nombre del driver ODBC instalado (ej. "ODBC Driver 17 for SQL Server")
        f"SERVER={cfg['DB_SERVER']}",               # Nombre de la instancia de SQL Server (ej. "THINKPAD")
        f"DATABASE={cfg['DB_NAME']}",                # Base de datos a la que nos conectamos (ciberseg)
    ]
    if str(cfg.get("DB_AUTH", "windows")).lower() == "windows":
        partes.append("Trusted_Connection=yes")      # Autenticacion integrada de Windows: no viaja contraseña
    else:
        partes.append(f"UID={cfg['DB_USER']}")       # Usuario de SQL Server (solo si DB_AUTH = 'sql')
        partes.append(f"PWD={cfg['DB_PASSWORD']}")   # Contraseña de ese usuario
    partes.append("TrustServerCertificate=yes")      # Acepta el certificado autofirmado del servidor local
    return ";".join(partes) + ";"                    # Ej: "DRIVER={...};SERVER=...;DATABASE=...;...;"


"""
   Función: get_db
   Objetivo: Entregar la conexión de base de datos correspondiente a la
             petición HTTP actual. Si todavía no existe, la crea; si ya
             existe, la reutiliza. Así solo se abre UNA conexión por
             petición, sin importar cuántas consultas se hagan dentro.
   Parámetros: No recibe.
   Retorno: Objeto de conexión de pyodbc (pyodbc.Connection).
"""
def get_db():
    """Devuelve la conexion de la peticion actual (la crea si no existe)."""
    if "db" not in g:                                        # g es exclusivo de esta peticion HTTP
        g.db = pyodbc.connect(_connection_string(),           # <-- AQUI se conecta realmente a SQL Server
                              autocommit=False)                # False: nada se confirma hasta hacer commit()
    return g.db                                                # Se devuelve la misma conexion en llamadas siguientes


"""
   Función: close_db
   Objetivo: Cerrar la conexión abierta en get_db() al terminar la
             petición HTTP, para no dejar conexiones huérfanas.
             La registra app/__init__.py con teardown_appcontext,
             así que se ejecuta SIEMPRE, haya habido error o no.
   Parámetros:
     - e: la excepción que Flask pasa si la petición terminó con error
          (aquí no se usa, pero Flask exige que la función la acepte).
   Retorno: No aplica.
"""
def close_db(e=None):
    """Cierra la conexion al terminar la peticion."""
    db = g.pop("db", None)          # Saca la conexion de g (o None si nunca se abrio)
    if db is not None:
        db.close()                  # Libera la conexion hacia SQL Server


"""
   Función: _filas_dict
   Objetivo: Convertir el resultado crudo de un cursor de pyodbc
             (tuplas sin nombre) en una lista de diccionarios, para que
             las plantillas Jinja2 puedan escribir fila.nombre en vez
             de fila[3].
   Parámetros:
     - cursor: el cursor de pyodbc que ya ejecuto un SELECT.
   Retorno: Lista de diccionarios, uno por cada fila del resultado.
"""
def _filas_dict(cursor):
    """Convierte las filas del cursor en una lista de diccionarios."""
    cols = [c[0] for c in cursor.description]                 # Nombres de columna que devolvio la consulta
    return [dict(zip(cols, fila)) for fila in cursor.fetchall()]  # Empareja cada nombre con su valor, fila por fila


"""
   Función: query_all
   Objetivo: Ejecutar una instruccion SELECT y devolver TODAS las filas
             que produce, ya convertidas a diccionarios.
   Parámetros:
     - sql: el texto de la consulta, con '?' como marcador de parametro.
     - params: lista de valores que reemplazan a los '?', en orden.
   Retorno: Lista de diccionarios (una fila = un diccionario).
"""
def query_all(sql, params=None):
    """Ejecuta un SELECT y devuelve todas las filas (lista de diccionarios)."""
    cur = get_db().cursor()             # Toma la conexion de la peticion y abre un cursor
    cur.execute(sql, params or [])      # Ejecuta el SQL; params or [] evita pasar None si no hay parametros
    return _filas_dict(cur)             # Convierte el resultado completo a lista de diccionarios


"""
   Función: query_one
   Objetivo: Ejecutar un SELECT y devolver SOLO la primera fila del
             resultado, o None si no hay ninguna. Se usa cuando se
             espera un unico registro (buscar por llave primaria,
             calcular un KPI, validar si algo existe).
   Parámetros:
     - sql: el texto de la consulta, con '?' como marcador de parametro.
     - params: lista de valores que reemplazan a los '?', en orden.
   Retorno: Un diccionario con la fila encontrada, o None.
"""
def query_one(sql, params=None):
    """Ejecuta un SELECT y devuelve la primera fila (o None)."""
    cur = get_db().cursor()
    cur.execute(sql, params or [])
    cols = [c[0] for c in cur.description]      # Nombres de columna del resultado
    fila = cur.fetchone()                       # Trae solo la primera fila (o None si no hay ninguna)
    return dict(zip(cols, fila)) if fila else None   # Arma el diccionario solo si sí hubo fila


"""
   Función: execute
   Objetivo: Ejecutar una instruccion que MODIFICA datos (INSERT, UPDATE
             o DELETE) y confirmar el cambio con commit(), para que
             quede permanente en la base de datos.
   Parámetros:
     - sql: el texto de la instruccion, con '?' como marcador de parametro.
     - params: lista de valores que reemplazan a los '?', en orden.
   Retorno: Numero entero de filas afectadas por la instruccion (rowcount).
"""
def execute(sql, params=None):
    """
    Ejecuta INSERT/UPDATE/DELETE y confirma la transaccion.
    Para obtener el id recien insertado en SQL Server, agrega
    'SELECT SCOPE_IDENTITY()' (lo usaremos en las fases de CRUD).
    """
    db = get_db()
    cur = db.cursor()
    cur.execute(sql, params or [])      # Ejecuta el INSERT/UPDATE/DELETE parametrizado
    db.commit()                         # Confirma el cambio: sin esta linea, se perderia al cerrar la conexion
    return cur.rowcount                 # Cuantas filas modifico realmente la instruccion


"""
   Función: db_status
   Objetivo: Comprobar si el motor de base de datos responde, contando
             cuantas tablas tiene el esquema activo. Se usa antes de
             intentar operaciones importantes (como el login) para dar
             un mensaje claro si la base no esta disponible, en vez de
             un error generico.
   Parámetros: No recibe.
   Retorno: Diccionario con:
              {"conectada": True,  "tablas": <numero>}   si respondio, o
              {"conectada": False, "error": "<detalle>"} si fallo.
"""
def db_status():
    """Comprueba si la base de datos responde (usado por la pagina de inicio)."""
    try:
        info = query_one(
            "SELECT COUNT(*) AS tablas FROM information_schema.tables "   # Catalogo del sistema: siempre existe
            "WHERE table_type = 'BASE TABLE'"                              # Solo cuenta tablas reales, no vistas
        )
        return {"conectada": True, "tablas": info["tablas"]}
    except Exception as err:  # noqa: BLE001    # Cualquier fallo de conexion cae aqui (servidor apagado, etc.)
        return {"conectada": False, "error": str(err)}


"""
   Función: insertar
   Objetivo: Ejecutar un INSERT y devolver el identificador (id) de la
             fila recien creada, resolviendo el problema del error 334
             (una tabla con triggers no admite OUTPUT sin INTO).
   Parámetros:
     - sql_insert_output: el INSERT escrito de forma NATURAL en T-SQL,
                           es decir, incluyendo la clausula literal
                           "OUTPUT INSERTED.id" en el texto. Ejemplo:
         insertar("INSERT INTO empresas (nombre) OUTPUT INSERTED.id VALUES (?)", ["Acme"])
     - params: lista de valores que reemplazan a los '?', en orden.
   Retorno: Numero entero (int) con el id recien generado por IDENTITY.
"""
def insertar(sql_insert_output, params=None):
    """
    Ejecuta un INSERT que incluye 'OUTPUT INSERTED.id' (T-SQL) y devuelve
    el id de la fila recién creada. Ejemplo:
      insertar("INSERT INTO empresas (nombre) OUTPUT INSERTED.id VALUES (?)", ["Acme"])
    """
    # OUTPUT INSERTED.id falla si la tabla tiene triggers (error 334),
    # asi que usamos SCOPE_IDENTITY() en el mismo lote.
    sql = "SET NOCOUNT ON; " + sql_insert_output.replace("OUTPUT INSERTED.id ", "") \
          + "; SELECT SCOPE_IDENTITY() AS id;"
    # Linea anterior, desglosada:
    #   "SET NOCOUNT ON; "                    -> suprime el mensaje "(1 row affected)"
    #   sql_insert_output.replace(...)        -> quita "OUTPUT INSERTED.id " del texto original
    #   "; SELECT SCOPE_IDENTITY() AS id;"    -> agrega una segunda instruccion que SI puede leerse
    db = get_db()
    cur = db.cursor()
    cur.execute(sql, params or [])            # Ejecuta el lote completo (INSERT + SELECT SCOPE_IDENTITY)
    nuevo_id = cur.fetchone()[0]              # Lee el resultado del SELECT: el id recien generado
    db.commit()                               # Confirma el INSERT
    return int(nuevo_id)                      # Devuelve el id como entero de Python