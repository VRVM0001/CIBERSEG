"""
=========================================================================
 Módulo: __init__.py (app/__init__.py)
 Fábrica de la aplicación (patrón application factory).

 Crea y configura la app Flask. A medida que avancen las fases iremos
 registrando más blueprints (auth, clientes, ventas, soporte, etc.).

 Este archivo se ejecuta UNA sola vez, cuando run.py llama a
 create_app(). Es el punto donde se unen todas las piezas del proyecto:
 la configuracion, la conexion a la base de datos y los ocho modulos
 de rutas (blueprints).
=========================================================================
"""
from flask import Flask         # Clase principal del framework: representa la aplicacion web

from .config import Config      # Clase con los datos de conexion (lee el .env)
from . import db                # Modulo de acceso a datos (para enganchar el cierre de conexion)


"""
   Función: create_app
   Objetivo: Construir y devolver una instancia lista para usar de la
             aplicación Flask: con su configuración cargada, el cierre
             automático de conexión enganchado, y los ocho módulos de
             rutas (blueprints) registrados.
   Parámetros:
     - config_class: la clase de configuración a usar. Por defecto es
                      Config (la del archivo config.py), pero se puede
                      sustituir por otra, por ejemplo una de pruebas.
   Retorno: Objeto Flask ya configurado, listo para que run.py lo
            ejecute con app.run(...).
"""
def create_app(config_class=Config):
    app = Flask(__name__)                    # Crea la aplicacion; __name__ le dice a Flask donde esta este archivo
    app.config.from_object(config_class)     # Carga en app.config todos los atributos de la clase Config

    # Cerrar la conexión a la BD al final de cada petición
    app.teardown_appcontext(db.close_db)
    # Linea anterior: registra db.close_db() para que Flask la ejecute
    # SIEMPRE al terminar cada peticion HTTP, sin importar si hubo
    # error o no. Es lo que garantiza que ninguna conexion quede abierta.

    # --- Blueprints (rutas) ---
    # Cada import trae el Blueprint 'bp' definido en su propio archivo
    # dentro de app/routes/, y lo renombra para no chocar entre si.
    from .routes.main import bp as main_bp              # Dashboard, buscador, notificaciones, configuracion
    from .routes.auth import bp as auth_bp              # Login, logout, control de sesion
    from .routes.admin import bp as admin_bp            # Usuarios, roles, auditoria
    from .routes.crm import bp as crm_bp                # Empresas, clientes, contactos
    from .routes.ventas import bp as ventas_bp          # Cotizaciones, facturas, contratos
    from .routes.gestion import bp as gestion_bp        # Proyectos, ingenieros
    from .routes.pipeline import bp as pipeline_bp      # Oportunidades (Kanban), actividades, metricas
    from .routes.inventario import bp as inventario_bp  # Productos, equipos, licencias

    # Cada register_blueprint "activa" las rutas de ese modulo dentro
    # de la aplicacion. Sin esta linea, las rutas existirian en el
    # codigo pero Flask nunca las atenderia.
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(crm_bp)
    app.register_blueprint(ventas_bp)
    app.register_blueprint(gestion_bp)
    app.register_blueprint(pipeline_bp)
    app.register_blueprint(inventario_bp)

    return app     # Devuelve la aplicacion completa y lista para arrancar