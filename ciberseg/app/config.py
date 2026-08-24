"""
=========================================================================
 Módulo: config.py (app/config.py)
 Configuracion de la aplicacion. Lee las variables del archivo .env

 Este archivo no se conecta a nada por si mismo: solo LEE los valores
 del archivo .env (mediante python-dotenv) y los deja organizados en
 una clase, para que app/__init__.py los cargue en Flask y cualquier
 otro modulo (como db.py) pueda consultarlos con current_app.config.
=========================================================================
"""
import os                          # Modulo estandar de Python para leer variables de entorno
from dotenv import load_dotenv     # Libreria que lee el archivo .env y lo carga como variables de entorno

load_dotenv()
# Linea anterior: busca un archivo .env en la raiz del proyecto y carga
# cada linea "CLAVE=valor" como si fuera una variable de entorno del
# sistema operativo. A partir de aqui, os.getenv("DB_SERVER") ya puede
# encontrar el valor que se escribio en el .env.


"""
   Clase: Config
   Objetivo: Agrupar en un solo lugar todos los valores de configuracion
             que la aplicacion necesita para funcionar: la clave de
             sesion y los datos para conectarse a SQL Server.
   Atributos:
     - SECRET_KEY: clave con la que Flask firma la cookie de sesion.
     - DB_SERVER, DB_NAME: servidor e instancia de SQL Server.
     - DB_AUTH: tipo de autenticacion ("windows" o "sql").
     - DB_USER, DB_PASSWORD: credenciales, solo si DB_AUTH es "sql".
     - DB_DRIVER: nombre del driver ODBC instalado en la maquina.
   Notas: Cada atributo usa os.getenv(clave, valor_por_defecto), asi
          que si el .env no define esa clave, la aplicacion sigue
          arrancando con el valor de respaldo en vez de fallar.
"""
class Config:
    # Clave secreta para sesiones (login). En produccion usa una larga y aleatoria.
    SECRET_KEY = os.getenv("SECRET_KEY", "cambia-esta-clave-en-produccion")
    # os.getenv("SECRET_KEY", "...") busca la variable SECRET_KEY; si no
    # existe, usa el texto de respaldo. Esta clave firma la cookie de
    # sesion: si cambiara, todas las sesiones abiertas se invalidarian.

    # --- Conexion a SQL Server ---
    # Nombre del servidor/instancia (lo ves en SSMS, campo "Server name").
    # Ejemplos: "localhost\\SQLEXPRESS", "localhost", ".\\SQLEXPRESS", "MIPC\\SQLEXPRESS"
    DB_SERVER = os.getenv("DB_SERVER", "localhost\\SQLEXPRESS")
    # Nombre de la instancia de SQL Server a la que nos conectamos.
    # En este proyecto, el valor real del .env es "THINKPAD".

    DB_NAME = os.getenv("DB_NAME", "ciberseg")
    # Nombre de la base de datos dentro de esa instancia.

    # Autenticacion: "windows" (Windows Authentication) o "sql" (usuario/clave SQL)
    DB_AUTH = os.getenv("DB_AUTH", "windows")
    # Decide como se identifica la aplicacion ante SQL Server. Con
    # "windows", usa la identidad del usuario del sistema operativo
    # (no viaja contraseña). Con "sql", usa DB_USER y DB_PASSWORD.

    DB_USER = os.getenv("DB_USER", "")
    # Usuario de SQL Server. Solo se usa si DB_AUTH = "sql".

    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    # Contraseña de ese usuario. Solo se usa si DB_AUTH = "sql".

    # Driver ODBC instalado (suele venir con SSMS). Usa 18 si tienes el mas nuevo.
    DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    # Nombre exacto del driver ODBC que pyodbc usara para hablar con
    # SQL Server. Debe coincidir con un driver realmente instalado en
    # la maquina (se puede verificar en el Administrador de origenes
    # de datos ODBC de Windows).