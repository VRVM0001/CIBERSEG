"""
=========================================================================
 Módulo: gestion.py (app/routes/gestion.py)
 Módulo Proyectos (Fase 5): CRUD con líder de ingeniería y presupuesto.

 Este blueprint agrupa dos entidades relacionadas: Proyectos (con su
 llave foránea opcional al ingeniero líder) e Ingenieros (el personal
 técnico que puede liderarlos).
=========================================================================
"""
import datetime      # Se importa pero no se usa directamente en este archivo (las fechas llegan como texto)

from flask import Blueprint, render_template, request, redirect, url_for, flash

from ..db import query_all, query_one, execute, insertar
from ..seguridad import login_requerido, permiso_requerido, registrar_auditoria

bp = Blueprint("gestion", __name__)

# Estados posibles de un proyecto, replicando el CHECK de la tabla
ESTADOS = ["Planificado", "En curso", "En pausa", "Completado", "Cancelado"]


"""
   Función: proyectos
   Objetivo: Mostrar el listado de proyectos, con búsqueda por nombre
             de proyecto o de cliente, y filtro opcional por estado.
   Parámetros: No recibe directamente (lee 'q' y 'estado' de la URL).
   Retorno: La plantilla proyectos.html con los proyectos encontrados.
"""
@bp.route("/proyectos")
@login_requerido          # Solo exige sesion iniciada, sin permiso especifico
def proyectos():
    q = (request.args.get("q") or "").strip()
    estado = (request.args.get("estado") or "").strip()
    sql = ("SELECT p.id, p.nombre, p.fecha_inicio, p.fecha_fin_estimada, p.fecha_fin_real, "
           "       p.estado, p.presupuesto, e.nombre AS cliente, i.nombre AS lider "
           "FROM proyectos p JOIN clientes c ON c.id = p.cliente_id "     # JOIN: cliente_id es NOT NULL
           "JOIN empresas e ON e.id = c.empresa_id "                       # Para mostrar el nombre de la empresa
           "LEFT JOIN ingenieros i ON i.id = p.ingeniero_lider_id WHERE 1=1 ")
    # Triple JOIN encadenado: proyectos -> clientes -> empresas (para
    # llegar al nombre visible), y LEFT JOIN a ingenieros porque el
    # lider del proyecto es opcional (ingeniero_lider_id admite NULL).
    params = []
    if q:
        sql += "AND (p.nombre LIKE ? OR e.nombre LIKE ?) "     # Busca por nombre del proyecto O del cliente
        params += [f"%{q}%", f"%{q}%"]
    if estado:
        sql += "AND p.estado = ? "
        params.append(estado)
    sql += "ORDER BY p.fecha_inicio DESC, p.id DESC"     # Los mas recientes primero
    return render_template("proyectos.html", active="proyectos",
                           proyectos=query_all(sql, params), buscar=q,
                           estado=estado, estados=ESTADOS)


"""
   Función: proyecto_nuevo
   Objetivo: Mostrar el formulario de alta de proyecto (GET) y
             procesar su creación (POST).
   Parámetros: No recibe directamente (lee el formulario).
   Retorno: En GET, formulario vacío. En POST correcto, redirige al
            listado.
"""
@bp.route("/proyectos/nuevo", methods=["GET", "POST"])
@permiso_requerido("ventas.crear")
def proyecto_nuevo():
    ctx = _ctx()          # Listas de clientes e ingenieros para los desplegables
    if request.method == "POST":
        d = _form()
        if not d["nombre"] or not d["cliente_id"]:
            flash("El nombre y el cliente son obligatorios.", "error")
            return render_template("proyecto_form.html", active="proyectos",
                                   titulo="Nuevo proyecto", proyecto=d, **ctx)
        nuevo_id = insertar(
            "INSERT INTO proyectos (nombre, cliente_id, ingeniero_lider_id, fecha_inicio, "
            "fecha_fin_estimada, fecha_fin_real, estado, presupuesto, descripcion) "
            "OUTPUT INSERTED.id VALUES (?,?,?,?,?,?,?,?,?)",
            [d["nombre"], d["cliente_id"], d["ingeniero_lider_id"],
             d["fecha_inicio"] or None, d["fecha_fin_estimada"] or None,
             d["fecha_fin_real"] or None, d["estado"], d["presupuesto"], d["descripcion"]],
        )
        # Las tres fechas usan "or None": si el campo vino vacio, se
        # guarda NULL en vez de una cadena vacia (la columna es DATE).
        registrar_auditoria("proyectos", "INSERT", nuevo_id, datos_nuevos=d)
        flash("Proyecto creado.", "ok")
        return redirect(url_for("gestion.proyectos"))
    return render_template("proyecto_form.html", active="proyectos",
                           titulo="Nuevo proyecto", proyecto=None, **ctx)


"""
   Función: proyecto_editar
   Objetivo: Mostrar el formulario con los datos actuales de un
             proyecto (GET) y guardar sus modificaciones (POST).
   Parámetros:
     - proyecto_id: identificador del proyecto a editar.
   Retorno: En GET, formulario con datos cargados (fechas convertidas
            a texto para el campo <input type="date">). En POST
            correcto, redirige al listado.
"""
@bp.route("/proyectos/<int:proyecto_id>/editar", methods=["GET", "POST"])
@permiso_requerido("ventas.editar")
def proyecto_editar(proyecto_id):
    actual = query_one("SELECT * FROM proyectos WHERE id = ?", [proyecto_id])
    if actual is None:
        flash("El proyecto no existe.", "error")
        return redirect(url_for("gestion.proyectos"))
    ctx = _ctx()
    if request.method == "POST":
        d = _form()
        if not d["nombre"] or not d["cliente_id"]:
            flash("El nombre y el cliente son obligatorios.", "error")
            return render_template("proyecto_form.html", active="proyectos",
                                   titulo="Editar proyecto", proyecto=d, **ctx)
        execute(
            "UPDATE proyectos SET nombre=?, cliente_id=?, ingeniero_lider_id=?, "
            "fecha_inicio=?, fecha_fin_estimada=?, fecha_fin_real=?, estado=?, "
            "presupuesto=?, descripcion=?, updated_at=SYSDATETIME() WHERE id=?",
            [d["nombre"], d["cliente_id"], d["ingeniero_lider_id"],
             d["fecha_inicio"] or None, d["fecha_fin_estimada"] or None,
             d["fecha_fin_real"] or None, d["estado"], d["presupuesto"],
             d["descripcion"], proyecto_id],
        )
        registrar_auditoria("proyectos", "UPDATE", proyecto_id,
                            datos_anteriores={"estado": actual["estado"],
                                              "presupuesto": float(actual["presupuesto"] or 0)},
                            # float(): convierte el Decimal que devuelve pyodbc
                            # a un tipo que json.dumps pueda serializar.
                            datos_nuevos={"estado": d["estado"],
                                          "presupuesto": d["presupuesto"]})
        # Solo se auditan estado y presupuesto, no todos los campos: son
        # los dos datos con mas relevancia de seguimiento en un proyecto.
        flash("Proyecto actualizado.", "ok")
        return redirect(url_for("gestion.proyectos"))

    p = dict(actual)     # Copia la fila para poder modificarla sin afectar 'actual'
    for f in ("fecha_inicio", "fecha_fin_estimada", "fecha_fin_real"):
        p[f] = actual[f].isoformat() if actual[f] else ""
        # pyodbc devuelve las fechas como objetos date de Python, pero
        # el campo <input type="date"> del HTML necesita texto en
        # formato "AAAA-MM-DD". isoformat() hace exactamente esa
        # conversion; si la fecha es None, se deja cadena vacia.
    return render_template("proyecto_form.html", active="proyectos",
                           titulo=f"Editar: {actual['nombre']}", proyecto=p, **ctx)


"""
   Función: _ctx
   Objetivo: Reunir las listas necesarias para los desplegables del
             formulario de proyecto: clientes (con el nombre de su
             empresa) e ingenieros activos.
   Parámetros: No recibe.
   Retorno: Diccionario con las claves clientes_lista, ingenieros y
            estados.
"""
def _ctx():
    return {
        "clientes_lista": query_all(
            "SELECT c.id, e.nombre FROM clientes c JOIN empresas e ON e.id = c.empresa_id "
            "ORDER BY e.nombre"),
        "ingenieros": query_all(
            "SELECT id, nombre FROM ingenieros WHERE activo = 1 ORDER BY nombre"),
        "estados": ESTADOS,
    }


"""
   Función: _form
   Objetivo: Leer y limpiar los campos del formulario de proyecto.
   Parámetros: No recibe (lee de request.form).
   Retorno: Diccionario con los nueve campos de proyectos.
"""
def _form():
    g = lambda k: (request.form.get(k) or "").strip()  # noqa: E731
    return {
        "nombre": g("nombre"),
        "cliente_id": int(g("cliente_id") or 0) or None,
        "ingeniero_lider_id": int(g("ingeniero_lider_id") or 0) or None,   # Puede quedar None: es opcional
        "fecha_inicio": g("fecha_inicio"),
        "fecha_fin_estimada": g("fecha_fin_estimada"),
        "fecha_fin_real": g("fecha_fin_real"),
        "estado": g("estado") if g("estado") in ESTADOS else "Planificado",
        # Se valida contra la lista ESTADOS antes de aceptarlo: si
        # llegara un valor manipulado, cae al valor por defecto.
        "presupuesto": float(g("presupuesto") or 0),
        "descripcion": g("descripcion"),
    }


# ------------------ INGENIEROS ------------------
NIVELES_ING = ["Junior", "Semi-Senior", "Senior", "Lead"]     # Replica el CHECK de la columna nivel


"""
   Función: ingenieros
   Objetivo: Mostrar el listado de ingenieros, con búsqueda por nombre
             o especialidad.
   Parámetros: No recibe directamente (lee 'q' de la URL).
   Retorno: La plantilla ingenieros.html con los ingenieros encontrados.
"""
@bp.route("/ingenieros")
@permiso_requerido("usuarios.ver")
def ingenieros():
    q = (request.args.get("q") or "").strip()
    sql = "SELECT * FROM ingenieros "
    params = []
    if q:
        sql += "WHERE nombre LIKE ? OR especialidad LIKE ? "
        params = [f"%{q}%"] * 2
    sql += "ORDER BY nombre"
    return render_template("ingenieros.html", active="ingenieros",
                           ingenieros=query_all(sql, params), buscar=q)


"""
   Función: ingeniero_nuevo
   Objetivo: Ser la ruta de alta de ingeniero. No tiene lógica propia:
             delega todo el trabajo al auxiliar compartido
             _ingeniero_form(), pasándole None para indicar que es
             un alta y no una edición.
   Parámetros: No recibe directamente (lee el formulario si es POST).
   Retorno: Lo que devuelva _ingeniero_form(None).
"""
@bp.route("/ingenieros/nuevo", methods=["GET", "POST"])
@permiso_requerido("usuarios.crear")
def ingeniero_nuevo():
    return _ingeniero_form(None)


"""
   Función: ingeniero_editar
   Objetivo: Cargar el ingeniero existente por su id y delegar el
             resto (mostrar formulario o guardar cambios) al mismo
             auxiliar _ingeniero_form(), esta vez con los datos reales.
   Parámetros:
     - ing_id: identificador del ingeniero a editar.
   Retorno: Lo que devuelva _ingeniero_form(actual), o un redirect si
            el ingeniero no existe.
"""
@bp.route("/ingenieros/<int:ing_id>/editar", methods=["GET", "POST"])
@permiso_requerido("usuarios.editar")
def ingeniero_editar(ing_id):
    actual = query_one("SELECT * FROM ingenieros WHERE id = ?", [ing_id])
    if actual is None:
        flash("El ingeniero no existe.", "error")
        return redirect(url_for("gestion.ingenieros"))
    return _ingeniero_form(actual)


"""
   Función: _ingeniero_form
   Objetivo: Ser el auxiliar COMPARTIDO entre el alta y la edición de
             ingenieros: un solo bloque de código maneja ambos casos,
             distinguiendo por si 'actual' viene con datos o es None.
   Parámetros:
     - actual: diccionario con los datos actuales del ingeniero (modo
               edición), o None (modo alta).
   Retorno: En GET, el formulario correspondiente. En POST correcto,
            redirige al listado de ingenieros.
"""
def _ingeniero_form(actual):
    if request.method == "POST":
        g = lambda k: (request.form.get(k) or "").strip()  # noqa: E731
        d = {"nombre": g("nombre"),
             "especialidad": g("especialidad"),
             "nivel": g("nivel") if g("nivel") in NIVELES_ING else "Junior",
             "certificaciones": g("certificaciones"),
             "email": g("email"), "telefono": g("telefono")}
        if not d["nombre"]:
            flash("El nombre es obligatorio.", "error")
            return render_template("ingeniero_form.html", active="ingenieros",
                                   titulo="Ingeniero", ing=d, niveles=NIVELES_ING)

        if actual:
            # Modo EDICION: actual tiene datos, entonces se hace UPDATE
            execute("UPDATE ingenieros SET nombre=?, especialidad=?, nivel=?, "
                    "certificaciones=?, email=?, telefono=?, updated_at=SYSDATETIME() WHERE id=?",
                    [d["nombre"], d["especialidad"], d["nivel"], d["certificaciones"],
                     d["email"], d["telefono"], actual["id"]])
            registrar_auditoria("ingenieros", "UPDATE", actual["id"], datos_nuevos=d)
        else:
            # Modo ALTA: actual es None, entonces se hace INSERT
            nuevo = insertar("INSERT INTO ingenieros (nombre, especialidad, nivel, "
                             "certificaciones, email, telefono) OUTPUT INSERTED.id "
                             "VALUES (?,?,?,?,?,?)",
                             [d["nombre"], d["especialidad"], d["nivel"],
                              d["certificaciones"], d["email"], d["telefono"]])
            registrar_auditoria("ingenieros", "INSERT", nuevo, datos_nuevos=d)

        flash("Ingeniero guardado.", "ok")
        return redirect(url_for("gestion.ingenieros"))

    return render_template("ingeniero_form.html", active="ingenieros",
                           titulo="Editar ingeniero" if actual else "Nuevo ingeniero",
                           ing=actual, niveles=NIVELES_ING)
    # El titulo tambien cambia segun el modo: "if actual" es verdadero
    # solo cuando hay datos, es decir, en edicion.


"""
   Función: ingeniero_estado
   Objetivo: Alternar la bandera 'activo' de un ingeniero (borrado
             lógico).
   Parámetros:
     - ing_id: identificador del ingeniero cuyo estado se cambia.
   Retorno: Redirige al listado de ingenieros, con un mensaje.
"""
@bp.route("/ingenieros/<int:ing_id>/estado", methods=["POST"])
@permiso_requerido("usuarios.eliminar")
def ingeniero_estado(ing_id):
    actual = query_one("SELECT id, activo FROM ingenieros WHERE id = ?", [ing_id])
    if actual:
        nuevo = 0 if actual["activo"] else 1
        execute("UPDATE ingenieros SET activo=?, updated_at=SYSDATETIME() WHERE id=?",
                [nuevo, ing_id])
        registrar_auditoria("ingenieros", "UPDATE", ing_id,
                            datos_nuevos={"activo": bool(nuevo)})
        flash(f"Ingeniero {'activado' if nuevo else 'desactivado'}.", "ok")
    return redirect(url_for("gestion.ingenieros"))