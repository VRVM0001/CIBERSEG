"""
=========================================================================
 Módulo: admin.py (app/routes/admin.py)
 Módulos del grupo Sistema (Fase 1):
   - Usuarios: listar, crear, editar y activar/desactivar (borrado lógico).
   - Roles: listado de roles con sus permisos.
   - Auditoría: registro de acciones del sistema.

 Este archivo es el blueprint 'admin'. A pesar del nombre del grupo
 "Sistema" en el menú, las rutas de usuarios, roles y auditoria viven
 aqui y no en un archivo llamado usuarios.py.
=========================================================================
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash    # Genera el hash de una contraseña nueva

from ..db import query_all, query_one, execute                        # Acceso a datos (db.py)
from ..seguridad import login_requerido, permiso_requerido, registrar_auditoria  # Seguridad (seguridad.py)

bp = Blueprint("admin", __name__)
# Crea el blueprint. Su nombre "admin" es el prefijo que se usa despues
# en url_for("admin.usuarios"), url_for("admin.roles"), etc.


# =====================================================================
#  USUARIOS
# =====================================================================

"""
   Función: usuarios
   Objetivo: Mostrar el listado de usuarios del sistema, con opción de
             buscar por nombre, usuario o correo.
   Parámetros: No recibe directamente (lee el parametro 'q' de la URL,
               si viene, a traves de request.args).
   Retorno: La plantilla usuarios.html renderizada con la lista de
            usuarios encontrados y el texto de busqueda actual.
"""
@bp.route("/usuarios")
@permiso_requerido("usuarios.ver")          # Exige el permiso de ver usuarios antes de ejecutar la funcion
def usuarios():
    buscar = (request.args.get("q") or "").strip()   # Texto de busqueda que llega en la URL (?q=...)
    sql = (
        "SELECT u.id, u.username, u.nombre, u.email, u.activo, u.ultimo_acceso, "
        "       r.nombre AS rol "                      # Trae tambien el nombre del rol via JOIN
        "FROM usuarios u JOIN roles r ON r.id = u.rol_id "
    )
    params = []
    if buscar:
        sql += "WHERE u.nombre LIKE ? OR u.username LIKE ? OR u.email LIKE ? "  # Filtro opcional
        like = f"%{buscar}%"                # El comodin va DENTRO del parametro, nunca concatenado al SQL
        params = [like, like, like]         # Un mismo valor sirve para los tres campos
    sql += "ORDER BY u.nombre"
    lista = query_all(sql, params)          # Ejecuta la consulta parametrizada y trae todas las filas
    return render_template("usuarios.html", active="usuarios", usuarios=lista, buscar=buscar)


"""
   Función: usuario_nuevo
   Objetivo: Mostrar el formulario de alta de usuario (GET) y procesar
             su creación (POST): valida los datos, cifra la contraseña
             y la guarda en la base de datos.
   Parámetros:
     - (ninguno declarado; usa request.form para leer el formulario)
   Retorno: En GET, el formulario vacío. En POST correcto, redirige al
            listado; si hay error de validación, vuelve a mostrar el
            formulario con el mensaje.
"""
@bp.route("/usuarios/nuevo", methods=["GET", "POST"])
@permiso_requerido("usuarios.crear")
def usuario_nuevo():
    roles = query_all("SELECT id, nombre FROM roles WHERE activo = 1 ORDER BY nombre")
    # Lista de roles activos para el desplegable; se pide siempre, tanto
    # en GET como si el POST falla y hay que repintar el formulario.

    if request.method == "POST":
        datos = _leer_formulario_usuario()      # Lee y limpia los campos del formulario (funcion auxiliar)
        error = _validar_usuario(datos, es_nuevo=True)   # Valida obligatorios, contraseña y duplicados
        if error:
            flash(error, "error")
            return render_template("usuario_form.html", active="usuarios",
                                   titulo="Nuevo usuario", usuario=datos, roles=roles)
        execute(
            "INSERT INTO usuarios (username, nombre, email, password_hash, rol_id, activo) "
            "VALUES (?,?,?,?,?,1)",
            [datos["username"], datos["nombre"], datos["email"],
             generate_password_hash(datos["password"]),    # NUNCA se guarda la contraseña en texto plano
             datos["rol_id"]],
        )
        creado = query_one("SELECT id FROM usuarios WHERE username = ?", [datos["username"]])
        # Como esta ruta usa execute() y no insertar(), se busca el id
        # recien creado con una consulta aparte, por su username unico.

        registrar_auditoria("usuarios", "INSERT", creado["id"],
                            datos_nuevos={"username": datos["username"], "nombre": datos["nombre"],
                                          "email": datos["email"], "rol_id": datos["rol_id"]})
        # No se guarda la contraseña ni su hash en la auditoria, por seguridad.

        flash("Usuario creado correctamente.", "ok")
        return redirect(url_for("admin.usuarios"))
    return render_template("usuario_form.html", active="usuarios",
                           titulo="Nuevo usuario", usuario=None, roles=roles)   # Caso GET: formulario vacio


"""
   Función: usuario_editar
   Objetivo: Mostrar el formulario con los datos actuales de un usuario
             (GET) y guardar sus modificaciones (POST). La contraseña
             solo se cambia si el usuario escribe una nueva.
   Parámetros:
     - usuario_id: identificador del usuario a editar (llega desde la
                   URL, convertido a entero por Flask).
   Retorno: En GET, el formulario con los datos cargados. En POST
            correcto, redirige al listado.
"""
@bp.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@permiso_requerido("usuarios.editar")
def usuario_editar(usuario_id):
    actual = query_one(
        "SELECT id, username, nombre, email, rol_id, activo FROM usuarios WHERE id = ?",
        [usuario_id],
    )
    if actual is None:
        flash("El usuario no existe.", "error")
        return redirect(url_for("admin.usuarios"))
    roles = query_all("SELECT id, nombre FROM roles WHERE activo = 1 ORDER BY nombre")

    if request.method == "POST":
        datos = _leer_formulario_usuario()
        datos["id"] = usuario_id
        error = _validar_usuario(datos, es_nuevo=False)   # es_nuevo=False: la contraseña es opcional aqui
        if error:
            flash(error, "error")
            return render_template("usuario_form.html", active="usuarios",
                                   titulo="Editar usuario", usuario=datos, roles=roles)
        execute(
            "UPDATE usuarios SET username=?, nombre=?, email=?, rol_id=?, "
            "updated_at=SYSDATETIME() WHERE id=?",
            [datos["username"], datos["nombre"], datos["email"], datos["rol_id"], usuario_id],
        )
        # Este UPDATE nunca toca password_hash: cambiar la clave es un paso aparte.

        if datos["password"]:  # solo cambia la clave si escribieron una nueva
            execute("UPDATE usuarios SET password_hash=? WHERE id=?",
                    [generate_password_hash(datos["password"]), usuario_id])
        # Segundo UPDATE, condicional: solo se ejecuta si el campo
        # contraseña vino lleno. Si el usuario lo deja vacio, la clave
        # anterior sigue siendo valida.

        registrar_auditoria("usuarios", "UPDATE", usuario_id,
                            datos_anteriores={k: actual[k] for k in ("username", "nombre", "email", "rol_id")},
                            datos_nuevos={"username": datos["username"], "nombre": datos["nombre"],
                                          "email": datos["email"], "rol_id": datos["rol_id"],
                                          "cambio_password": bool(datos["password"])})
        # Se registra si hubo cambio de contraseña (True/False), pero
        # jamas la contraseña ni su hash.

        flash("Usuario actualizado.", "ok")
        return redirect(url_for("admin.usuarios"))

    return render_template("usuario_form.html", active="usuarios",
                           titulo="Editar usuario", usuario=actual, roles=roles)


"""
   Función: usuario_estado
   Objetivo: Alternar la bandera 'activo' de un usuario (borrado
             lógico): si estaba activo lo desactiva, y viceversa.
             Nunca borra la fila de la base de datos.
   Parámetros:
     - usuario_id: identificador del usuario cuyo estado se cambia.
   Retorno: Redirige siempre al listado de usuarios, con un mensaje.
"""
@bp.route("/usuarios/<int:usuario_id>/estado", methods=["POST"])   # Solo POST: es una accion que modifica datos
@permiso_requerido("usuarios.eliminar")
def usuario_estado(usuario_id):
    """Activa/desactiva (borrado lógico). Nunca borramos filas físicamente."""
    actual = query_one("SELECT id, username, activo FROM usuarios WHERE id = ?", [usuario_id])
    if actual is None:
        flash("El usuario no existe.", "error")
    else:
        nuevo = 0 if actual["activo"] else 1     # Invierte el valor actual (1 pasa a 0, 0 pasa a 1)
        execute("UPDATE usuarios SET activo=?, updated_at=SYSDATETIME() WHERE id=?",
                [nuevo, usuario_id])
        registrar_auditoria("usuarios", "UPDATE", usuario_id,
                            datos_anteriores={"activo": bool(actual["activo"])},
                            datos_nuevos={"activo": bool(nuevo)})
        flash(f"Usuario {'activado' if nuevo else 'desactivado'}.", "ok")
    return redirect(url_for("admin.usuarios"))


"""
   Función: _leer_formulario_usuario
   Objetivo: Leer y limpiar los campos del formulario de usuario
             (alta o edición), devolviéndolos en un diccionario listo
             para validar y usar en las consultas SQL.
   Parámetros: No recibe (lee directamente de request.form).
   Retorno: Diccionario con username, nombre, email, rol_id (entero) y
            password.
"""
def _leer_formulario_usuario():
    return {
        "username": (request.form.get("username") or "").strip(),
        "nombre": (request.form.get("nombre") or "").strip(),
        "email": (request.form.get("email") or "").strip(),
        "rol_id": int(request.form.get("rol_id") or 0),   # Convierte a entero; 0 si no vino
        "password": request.form.get("password") or "",   # SIN strip: un espacio podria ser parte de la clave
    }


"""
   Función: _validar_usuario
   Objetivo: Verificar que los datos de un usuario cumplan las reglas
             de negocio antes de guardarlos: campos obligatorios,
             contraseña obligatoria si es nuevo, longitud mínima de
             contraseña, y que username/email no estén ya en uso.
   Parámetros:
     - d: diccionario con los datos del formulario (viene de
          _leer_formulario_usuario, con "id" agregado si es edición).
     - es_nuevo: True si es un alta, False si es una edición (cambia
                 si la contraseña es obligatoria o no).
   Retorno: Texto (str) con el mensaje de error si algo esta mal, o
            None si todo es valido.
"""
def _validar_usuario(d, es_nuevo):
    if not d["username"] or not d["nombre"] or not d["email"] or not d["rol_id"]:
        return "Completa todos los campos obligatorios."
    if es_nuevo and not d["password"]:
        return "La contraseña es obligatoria para un usuario nuevo."     # Solo exige clave si es alta
    if d["password"] and len(d["password"]) < 6:
        return "La contraseña debe tener al menos 6 caracteres."         # Si escribio clave, valida longitud
    # username/email únicos (excluyendo al propio usuario si es edición)
    dup = query_one(
        "SELECT id FROM usuarios WHERE (username = ? OR email = ?) AND id <> ?",
        [d["username"], d["email"], d.get("id", 0)],
    )
    # El AND id <> ? excluye al propio usuario de la busqueda: al
    # editar, no debe chocar contra si mismo. d.get("id", 0) devuelve
    # 0 si es un alta (no existe "id" todavia), que nunca coincide con
    # un id real.
    if dup:
        return "Ya existe un usuario con ese nombre de usuario o email."
    return None      # Ningun problema encontrado: los datos son validos


# =====================================================================
#  ROLES (lectura con sus permisos)
# =====================================================================

"""
   Función: roles
   Objetivo: Mostrar el listado de roles del sistema, con cuántos
             permisos y cuántos usuarios tiene cada uno, y el detalle
             completo de qué permisos incluye cada rol.
   Parámetros: No recibe.
   Retorno: La plantilla roles.html con la lista de roles y un
            diccionario que agrupa los permisos de cada rol.
"""
@bp.route("/roles")
@permiso_requerido("usuarios.ver")
def roles():
    lista = query_all(
        "SELECT r.id, r.nombre, r.descripcion, r.activo, "
        "       (SELECT COUNT(*) FROM roles_permisos rp WHERE rp.rol_id = r.id) AS n_permisos, "
        "       (SELECT COUNT(*) FROM usuarios u WHERE u.rol_id = r.id) AS n_usuarios "
        "FROM roles r ORDER BY r.id"
    )
    # Dos subconsultas correlacionadas: por cada rol, cuentan cuantos
    # permisos tiene (via roles_permisos) y cuantos usuarios lo usan.

    permisos_por_rol = {}
    for fila in query_all(
        "SELECT rp.rol_id, p.nombre, p.modulo FROM roles_permisos rp "
        "JOIN permisos p ON p.id = rp.permiso_id ORDER BY p.modulo, p.nombre"
    ):
        permisos_por_rol.setdefault(fila["rol_id"], []).append(fila)
        # setdefault(clave, []) crea la lista vacia la primera vez que
        # aparece ese rol_id, y en las siguientes vueltas simplemente
        # le agrega el permiso. Al final, permisos_por_rol queda como
        # {rol_id: [lista de sus permisos]} para los 4 roles.

    return render_template("roles.html", active="roles", roles=lista,
                           permisos_por_rol=permisos_por_rol)


# =====================================================================
#  AUDITORÍA
# =====================================================================

"""
   Función: auditoria
   Objetivo: Mostrar los últimos 200 eventos registrados en la tabla
             de auditoría, con la posibilidad de filtrar por tabla
             afectada.
   Parámetros: No recibe directamente (lee el parametro 'tabla' de la
               URL, si viene, a traves de request.args).
   Retorno: La plantilla auditoria.html con los eventos encontrados y
            la lista de tablas disponibles para el filtro.
"""
@bp.route("/auditoria")
@permiso_requerido("usuarios.ver")
def auditoria():
    tabla = (request.args.get("tabla") or "").strip()   # Filtro opcional que llega por la URL (?tabla=clientes)
    sql = (
        "SELECT TOP 200 a.id, a.tabla_afectada, a.accion, a.registro_id, "
        "       a.datos_anteriores, a.datos_nuevos, a.ip_origen, a.fecha, "
        "       u.nombre AS usuario "                    # Nombre del usuario que hizo el cambio
        "FROM auditoria a LEFT JOIN usuarios u ON u.id = a.usuario_id "
    )
    # LEFT JOIN (no JOIN normal) porque auditoria.usuario_id admite NULL:
    # los cambios que origina un trigger de la base no tienen usuario
    # asociado, y con JOIN normal esos eventos desaparecerian de la lista.

    params = []
    if tabla:
        sql += "WHERE a.tabla_afectada = ? "
        params = [tabla]
    sql += "ORDER BY a.fecha DESC"      # Los eventos mas recientes primero
    eventos = query_all(sql, params)
    tablas = [t["tabla_afectada"] for t in
              query_all("SELECT DISTINCT tabla_afectada FROM auditoria ORDER BY tabla_afectada")]
    # DISTINCT trae cada nombre de tabla una sola vez, para llenar el
    # desplegable de filtro sin repetidos.

    return render_template("auditoria.html", active="auditoria",
                           eventos=eventos, tablas=tablas, tabla=tabla)