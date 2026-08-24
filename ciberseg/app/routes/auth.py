"""
=========================================================================
 Módulo: auth.py (app/routes/auth.py)
 Autenticación: inicio y cierre de sesión.

 El login valida el usuario contra la tabla `usuarios` comparando la
 contraseña con su hash (Werkzeug/scrypt). Al entrar, se cargan en la
 sesión los permisos del rol para usarlos en toda la aplicación.

 Además de las rutas de login/logout, este archivo tiene una funcion
 especial (exigir_sesion) que se ejecuta antes de CUALQUIER peticion
 de TODA la aplicacion, no solo de este blueprint: es el guardian
 global que bloquea el acceso sin sesion.
=========================================================================
"""
import datetime      # Para comparar fechas de bloqueo y calcular el tiempo de inactividad

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash    # Compara una contraseña contra un hash guardado

from ..db import query_one, query_all, execute, db_status    # Acceso a datos (db.py)
from ..seguridad import registrar_auditoria                   # Registro de auditoria (seguridad.py)

bp = Blueprint("auth", __name__)
# Crea el blueprint "auth". Sus rutas se llaman despues como
# url_for("auth.login") y url_for("auth.logout").

# Rutas que se pueden visitar sin sesión iniciada
RUTAS_PUBLICAS = {"auth.login", "static"}
# Conjunto con los UNICOS dos endpoints que no exigen sesion: el propio
# login (para poder llegar a el) y los archivos estaticos (css, js,
# imagenes), que deben cargar siempre sin importar si hay sesion.


"""
   Función: exigir_sesion
   Objetivo: Actuar como un guardián global que se ejecuta ANTES de
             cada petición de toda la aplicación (no solo de este
             blueprint). Bloquea el acceso a quien no tenga sesión
             iniciada, y cierra automáticamente la sesión si el
             usuario estuvo inactivo más tiempo del configurado.
   Parámetros: No recibe (Flask la invoca automáticamente en cada
               petición gracias al decorador @bp.before_app_request).
   Retorno: None si todo esta bien y la peticion puede continuar; o
            un redirect() hacia el login si falta sesion o si expiro
            por inactividad.
"""
@bp.before_app_request
# Este decorador es distinto a @bp.route: no declara una URL, sino que
# registra la funcion para que se ejecute ANTES de cualquier ruta de
# TODA la aplicacion (no solo las de este blueprint "auth").
def exigir_sesion():
    """Bloquea el sitio sin sesión y aplica el timeout de inactividad configurable."""
    endpoint = request.endpoint or ""              # Nombre de la ruta que se esta por ejecutar
    if endpoint in RUTAS_PUBLICAS or endpoint.startswith("static"):
        return None                                  # Rutas publicas: se deja pasar sin revisar nada
    if "usuario_id" not in session:
        return redirect(url_for("auth.login"))       # Sin sesion: se corta aqui, redirige al login

    # Timeout por inactividad (minutos definidos en Configuración)
    from ..configuracion import leer_config
    # Import dentro de la funcion (no arriba del archivo) para evitar
    # un import circular: configuracion.py tambien depende de db.py.

    try:
        limite = int(leer_config().get("sesion_timeout_min", "30"))   # Minutos permitidos de inactividad
    except Exception:
        limite = 30                                   # Respaldo si la configuracion fallara por algun motivo

    ahora = datetime.datetime.utcnow().timestamp()                # Momento actual, en segundos
    ultima = session.get("ultima_actividad", ahora)               # Ultima actividad registrada en la sesion
    if limite > 0 and ahora - ultima > limite * 60:               # Si paso mas tiempo que el limite (en segundos)
        session.clear()                                            # Se borra toda la sesion
        flash("Tu sesión expiró por inactividad. Inicia sesión de nuevo.", "error")
        return redirect(url_for("auth.login"))
    session["ultima_actividad"] = ahora            # Si todo esta bien, se actualiza la marca de actividad
    return None                                    # None permite que la peticion original continue normalmente


"""
   Función: login
   Objetivo: Mostrar el formulario de inicio de sesión (GET) y validar
             las credenciales (POST): comprueba usuario, contraseña,
             bloqueo por intentos fallidos y estado de la cuenta;
             si todo es correcto, crea la sesión con los permisos del
             rol y registra el ingreso en la auditoría.
   Parámetros: No recibe directamente (lee username y password del
               formulario a través de request.form).
   Retorno: Si la sesión ya existía, redirige al dashboard. En GET,
            el formulario de login. En POST correcto, redirige al
            dashboard; si hay error, vuelve a mostrar el formulario
            con el mensaje correspondiente.
"""
@bp.route("/login", methods=["GET", "POST"])
def login():
    # Si ya hay sesión, directo al dashboard
    if "usuario_id" in session:
        return redirect(url_for("main.index"))
    # Evita que un usuario ya conectado vea el formulario de login otra vez.

    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()   # Se limpia de espacios el usuario
        password = request.form.get("password") or ""              # La clave NO se limpia (podria llevar espacios)

        estado = db_status()                 # Primero se comprueba que la base de datos responda
        if not estado["conectada"]:
            error = "No hay conexión con la base de datos. Revisa el archivo .env."
        else:
            usuario = query_one(
                "SELECT u.id, u.username, u.nombre, u.password_hash, u.activo, "
                "       u.rol_id, u.intentos_fallidos, u.bloqueado_hasta, "
                "       r.nombre AS rol_nombre "                 # JOIN a roles: relacion "asignado" del diagrama
                "FROM usuarios u JOIN roles r ON r.id = u.rol_id "
                "WHERE u.username = ?",
                [username],
            )
            # UNICA consulta que trae todo lo necesario: credenciales,
            # estado de la cuenta, contador de intentos, bloqueo y rol.

            # --- Validaciones en orden, y por que van en ese orden ---
            if usuario and usuario.get("bloqueado_hasta") \
                    and usuario["bloqueado_hasta"] > datetime.datetime.now():
                # 1ra validacion: el bloqueo. Va primero para que un intento
                # sobre una cuenta bloqueada NO incremente el contador.
                error = "Cuenta bloqueada temporalmente por intentos fallidos. Intenta en unos minutos."

            elif usuario is None or not check_password_hash(usuario["password_hash"], password):
                # 2da validacion: la contraseña. Usuario inexistente y clave
                # incorrecta dan el MISMO mensaje, para no revelar que
                # usuarios existen (evita la enumeracion de usuarios).
                error = "Usuario o contraseña incorrectos."
                if usuario:                          # Solo cuenta intentos si el usuario SI existe
                    intentos = (usuario.get("intentos_fallidos") or 0) + 1
                    if intentos >= 5:
                        execute("UPDATE usuarios SET intentos_fallidos = 0, "
                                "bloqueado_hasta = DATEADD(MINUTE, 15, SYSDATETIME()) WHERE id = ?",
                                [usuario["id"]])
                        # Al quinto intento: bloquea 15 min y reinicia el
                        # contador (el bloqueo ya cumple su funcion via fecha).
                        error = "Cuenta bloqueada por 15 minutos tras 5 intentos fallidos."
                    else:
                        execute("UPDATE usuarios SET intentos_fallidos = ? WHERE id = ?",
                                [intentos, usuario["id"]])   # Suma un intento fallido mas

            elif not usuario["activo"]:
                # 3ra validacion: la cuenta desactivada. Va DESPUES de la
                # contraseña: solo se revela a quien ya demostro conocerla.
                error = "Este usuario está desactivado. Contacta al administrador."
                # Aca podria registrar un intento de inicio de sesión fallido
                # por usuario desactivado, si se desea llevar un registro.

            else:
                # --- Todo correcto: se crea la sesión ---
                session.clear()                        # Limpia cualquier resto anterior (previene fijacion de sesion)
                session["usuario_id"] = usuario["id"]
                session["usuario_nombre"] = usuario["nombre"]
                session["username"] = usuario["username"]
                session["rol_id"] = usuario["rol_id"]
                session["rol_nombre"] = usuario["rol_nombre"]

                permisos = query_all(
                    "SELECT p.nombre FROM roles_permisos rp "
                    "JOIN permisos p ON p.id = rp.permiso_id WHERE rp.rol_id = ?",
                    [usuario["rol_id"]],
                )
                # AQUI se recorre la relacion MUCHOS A MUCHOS entre roles y
                # permisos, via la tabla puente roles_permisos.

                session["permisos"] = [p["nombre"] for p in permisos]
                # Se guarda solo la lista de nombres, no los diccionarios
                # completos: es lo que compara permiso_requerido() despues.

                # Último acceso + auditoría del ingreso
                execute("UPDATE usuarios SET ultimo_acceso = SYSDATETIME(), "
                        "intentos_fallidos = 0, bloqueado_hasta = NULL WHERE id = ?", [usuario["id"]])
                # Sella el momento del acceso y limpia cualquier bloqueo previo.

                registrar_auditoria("usuarios", "UPDATE", usuario["id"],
                                    datos_nuevos={"evento": "inicio de sesión"})
                return redirect(url_for("main.index"))    # Login exitoso: al dashboard

    return render_template("login.html", error=error)     # GET, o POST con error: se muestra el formulario


"""
   Función: logout
   Objetivo: Cerrar la sesión del usuario actual, dejando constancia
             del evento en la auditoría antes de borrar los datos de
             sesión.
   Parámetros: No recibe.
   Retorno: Redirige siempre al login, con un mensaje de confirmación.
"""
@bp.route("/logout")
def logout():
    if "usuario_id" in session:              # Solo intenta auditar si de verdad habia una sesion activa
        try:
            registrar_auditoria("usuarios", "UPDATE", session["usuario_id"],
                                datos_nuevos={"evento": "cierre de sesión"})
        except Exception:  # noqa: BLE001 - si la BD no responde, igual cerramos sesión
            pass
        # Si la base de datos no respondiera en este momento, el registro
        # de auditoria fallaria, pero el cierre de sesion debe funcionar
        # de todas formas: por eso el error se ignora aqui a proposito.

    session.clear()                          # Borra todos los datos de la sesion (usuario, permisos, etc.)
    flash("Sesión cerrada correctamente.", "ok")
    return redirect(url_for("auth.login"))
