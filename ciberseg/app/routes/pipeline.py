"""
=========================================================================
 Módulo: pipeline.py (app/routes/pipeline.py)
 Mejoras CRM: pipeline de oportunidades (Kanban), actividades y métricas.

 Este blueprint agrupa tres cosas relacionadas con el seguimiento
 comercial que no encajan en el CRM base ni en Ventas: el embudo de
 oportunidades organizado como tablero Kanban, el registro de
 actividades (llamadas, reuniones, correos, tareas) y la pantalla de
 métricas que resume el desempeño comercial.
=========================================================================
"""
import datetime      # Se importa pero no se usa directamente en este archivo

from flask import Blueprint, render_template, request, redirect, url_for, flash, session

from ..db import query_all, query_one, execute, insertar
from ..seguridad import permiso_requerido, registrar_auditoria

bp = Blueprint("pipeline", __name__)
# Crea el blueprint "pipeline". Sus rutas se invocan despues como
# url_for("pipeline.oportunidades"), url_for("pipeline.actividades"), etc.

# Las cinco etapas del embudo de ventas, en el orden en que se
# recorren normalmente. Replica el CHECK de la columna etapa.
ETAPAS = ["Contacto", "Propuesta", "Negociacion", "Ganada", "Perdida"]


# ------------------ OPORTUNIDADES (Kanban) ------------------

"""
   Función: oportunidades
   Objetivo: Mostrar el tablero Kanban del embudo de ventas: trae
             TODAS las oportunidades con una sola consulta y luego,
             en Python, las agrupa por etapa para formar las columnas
             del tablero, calculando también el valor total de cada
             columna.
   Parámetros: No recibe.
   Retorno: La plantilla pipeline.html con las oportunidades
            agrupadas por etapa y el valor sumado de cada una.
"""
@bp.route("/oportunidades")
@permiso_requerido("clientes.ver")
def oportunidades():
    filas = query_all(
        "SELECT o.*, e.nombre AS cliente, u.nombre AS ejecutivo "
        "FROM oportunidades o JOIN clientes c ON c.id = o.cliente_id "
        "JOIN empresas e ON e.id = c.empresa_id "
        "LEFT JOIN usuarios u ON u.id = o.ejecutivo_id ORDER BY o.updated_at DESC")
    # JOIN a clientes y empresas: cliente_id es NOT NULL, no hay riesgo
    # de perder filas. LEFT JOIN a usuarios: ejecutivo_id admite NULL
    # (una oportunidad puede no tener ejecutivo asignado todavia).

    cols = {e: [] for e in ETAPAS}       # Diccionario vacio: una lista por cada etapa
    for f in filas:
        cols.setdefault(f["etapa"], []).append(f)
        # Recorre TODAS las oportunidades (una sola consulta a la base)
        # y las reparte en la columna que corresponda segun su etapa.
        # setdefault evita un error si llegara una etapa inesperada.

    valor = {e: sum(float(x["valor_estimado"] or 0) for x in v) for e, v in cols.items()}
    # Suma, en Python, el valor estimado de cada columna: el total que
    # se muestra en la cabecera de cada etapa del tablero.
    return render_template("pipeline.html", active="oportunidades",
                           cols=cols, etapas=ETAPAS, valor=valor)


"""
   Función: oportunidad_nueva
   Objetivo: Ser la ruta de alta de oportunidad. No tiene lógica
             propia: delega todo el trabajo al auxiliar compartido
             _oportunidad_form(), pasándole None para indicar que es
             un alta y no una edición.
   Parámetros: No recibe directamente (lee el formulario si es POST).
   Retorno: Lo que devuelva _oportunidad_form(None).
"""
@bp.route("/oportunidades/nueva", methods=["GET", "POST"])
@permiso_requerido("clientes.crear")
def oportunidad_nueva():
    return _oportunidad_form(None)


"""
   Función: oportunidad_editar
   Objetivo: Cargar la oportunidad existente por su id y delegar el
             resto (mostrar formulario o guardar cambios) al mismo
             auxiliar _oportunidad_form(), esta vez con los datos
             reales.
   Parámetros:
     - op_id: identificador de la oportunidad a editar.
   Retorno: Lo que devuelva _oportunidad_form(actual), o un redirect
            si la oportunidad no existe.
"""
@bp.route("/oportunidades/<int:op_id>/editar", methods=["GET", "POST"])
@permiso_requerido("clientes.editar")
def oportunidad_editar(op_id):
    actual = query_one("SELECT * FROM oportunidades WHERE id = ?", [op_id])
    if actual is None:
        flash("La oportunidad no existe.", "error")
        return redirect(url_for("pipeline.oportunidades"))
    return _oportunidad_form(actual)


"""
   Función: _oportunidad_form
   Objetivo: Ser el auxiliar COMPARTIDO entre el alta y la edición de
             oportunidades: un solo bloque de código maneja ambos
             casos, distinguiendo por si 'actual' viene con datos
             (modo edición) o es None (modo alta). Es el mismo patrón
             de auxiliar compartido que usa _ingeniero_form() en
             gestion.py.
   Parámetros:
     - actual: diccionario con la fila actual de la oportunidad
               (cuando la llama oportunidad_editar), o None (cuando
               la llama oportunidad_nueva).
   Retorno:
     - En GET: la plantilla oportunidad_form.html, con el formulario
       vacío (alta) o con los datos cargados (edición).
     - En POST válido: un redirect() al tablero de oportunidades.
     - En POST inválido: la misma plantilla, repintada con el error.
"""
def _oportunidad_form(actual):
    # ---------- Contexto para los desplegables del formulario ----------
    ctx = {"clientes_lista": query_all(
               "SELECT c.id, e.nombre FROM clientes c JOIN empresas e ON e.id=c.empresa_id ORDER BY e.nombre"),
           "ejecutivos": query_all("SELECT id, nombre FROM usuarios WHERE activo=1 ORDER BY nombre"),
           "etapas": ETAPAS}
    # Se calcula ANTES del if request.method, porque hace falta en los
    # tres caminos posibles de la funcion: el GET inicial, el POST que
    # falla validacion (hay que repintar el formulario con las mismas
    # listas), y hasta se reutiliza al final para el return del GET.
    # clientes_lista trae el nombre visible via JOIN a empresas (la
    # tabla clientes no guarda el nombre, solo el empresa_id).
    # ejecutivos solo trae usuarios activos: no tiene sentido asignar
    # una oportunidad a alguien dado de baja.

    if request.method == "POST":
        # ---------- Lectura y limpieza del formulario ----------
        g = lambda k: (request.form.get(k) or "").strip()  # noqa: E731
        # g(): funcion corta (una linea) que lee un campo del formulario,
        # sustituye None por cadena vacia si no vino, y quita espacios
        # sobrantes con strip(). Se define local a esta funcion porque
        # solo se usa aqui dentro.

        d = {"cliente_id": int(g("cliente_id") or 0) or None,
             # int(texto or 0): si el campo vino vacio, "or 0" evita que
             # int() falle con una cadena vacia. Luego "or None" convierte
             # el resultado 0 en None, porque 0 no es un id de cliente
             # valido (los IDENTITY empiezan en 1).
             "nombre": g("nombre"),
             "etapa": g("etapa") if g("etapa") in ETAPAS else "Contacto",
             # Se valida contra la lista ETAPAS ANTES de aceptar el valor:
             # si llegara algo manipulado (una etapa inventada), cae al
             # valor por defecto "Contacto" en vez de intentar guardarla.
             "valor_estimado": float(g("valor_estimado") or 0),
             "probabilidad": min(100, max(0, int(g("probabilidad") or 50))),
             # Doble acotacion anidada: max(0, ...) impide un numero
             # negativo; min(100, ...) impide superar el 100%. El
             # resultado siempre cae dentro de 0-100 sin importar lo que
             # haya escrito el usuario (o lo que enviara un formulario
             # manipulado). El valor por defecto es 50 (probabilidad
             # neutral) si el campo llega vacio.
             "fecha_cierre_estimada": g("fecha_cierre_estimada") or None,
             # "or None": una cadena vacia no es una fecha valida para
             # la columna DATE de la base; se guarda NULL en su lugar.
             "ejecutivo_id": int(g("ejecutivo_id") or 0) or None,
             # Mismo patron que cliente_id, pero aqui el resultado None
             # es perfectamente valido: el ejecutivo es OPCIONAL
             # (participacion parcial, la columna admite NULL).
             "notas": g("notas")}

        # ---------- Validación de negocio ----------
        if not d["nombre"] or not d["cliente_id"]:
            # Se exigen los dos unicos campos declarados NOT NULL en la
            # tabla ademas de la llave primaria: nombre y cliente_id.
            flash("El nombre y el cliente son obligatorios.", "error")
            return render_template("oportunidad_form.html", active="oportunidades",
                                   titulo="Oportunidad", op=d, **ctx)
            # Se devuelve el MISMO 'd' que se acaba de armar (no 'actual'),
            # para que el usuario no pierda lo que ya habia escrito. El
            # titulo aqui es generico ("Oportunidad") porque en este punto
            # no se distingue todavia si el error fue en un alta o una
            # edicion: ambos caminos llegan a esta misma validacion.

        # ---------- Escritura en la base: UPDATE o INSERT ----------
        if actual:
            # Modo EDICION: 'actual' tiene datos (no es None), asi que
            # se ejecuta un UPDATE sobre la fila existente.
            execute("UPDATE oportunidades SET cliente_id=?, nombre=?, etapa=?, valor_estimado=?, "
                    "probabilidad=?, fecha_cierre_estimada=?, ejecutivo_id=?, notas=?, "
                    "updated_at=SYSDATETIME() WHERE id=?",
                    [d["cliente_id"], d["nombre"], d["etapa"], d["valor_estimado"],
                     d["probabilidad"], d["fecha_cierre_estimada"], d["ejecutivo_id"],
                     d["notas"], actual["id"]])
            # El WHERE id=? con actual["id"] al final de la lista de
            # parametros es lo que limita el cambio a esta UNICA fila.
            registrar_auditoria("oportunidades", "UPDATE", actual["id"], datos_nuevos=d)
        else:
            # Modo ALTA: 'actual' es None, asi que se ejecuta un INSERT.
            nuevo = insertar("INSERT INTO oportunidades (cliente_id, nombre, etapa, valor_estimado, "
                             "probabilidad, fecha_cierre_estimada, ejecutivo_id, notas) "
                             "OUTPUT INSERTED.id VALUES (?,?,?,?,?,?,?,?)",
                             [d["cliente_id"], d["nombre"], d["etapa"], d["valor_estimado"],
                              d["probabilidad"], d["fecha_cierre_estimada"],
                              d["ejecutivo_id"], d["notas"]])
            # insertar() retira el OUTPUT INSERTED.id y lo sustituye por
            # SCOPE_IDENTITY() dentro de db.py (por el error 334 con
            # tablas que tienen triggers), y devuelve el id nuevo.
            registrar_auditoria("oportunidades", "INSERT", nuevo, datos_nuevos=d)
        # Este es el UNICO bloque de la funcion donde se escribe en la
        # base de datos: las dos ramas (UPDATE e INSERT) son mutuamente
        # excluyentes, decididas por una sola condicion (if actual).

        flash("Oportunidad guardada.", "ok")
        return redirect(url_for("pipeline.oportunidades"))
        # El mismo mensaje de exito sirve para alta y edicion: no hace
        # falta distinguirlos aqui, porque el usuario ya sabe que accion
        # estaba realizando.

    # ---------- Caso GET: preparar los datos para mostrar el formulario ----------
    op = dict(actual) if actual else None
    # dict(actual) crea una COPIA de la fila de la base (que pyodbc ya
    # entrega como diccionario via _filas_dict de db.py). Se copia en
    # vez de modificar 'actual' directamente para no alterar el
    # diccionario original si algo mas lo estuviera usando. Si 'actual'
    # es None (alta), 'op' tambien queda en None.

    if op and op.get("fecha_cierre_estimada"):
        op["fecha_cierre_estimada"] = op["fecha_cierre_estimada"].isoformat()
        # Solo entra aqui si op existe (edicion) Y la fecha no es NULL.
        # Convierte la fecha (que pyodbc entrega como objeto date de
        # Python) a texto "AAAA-MM-DD" con isoformat(), porque el campo
        # <input type="date"> del HTML solo entiende ese formato exacto
        # de texto, no un objeto date de Python.

    return render_template("oportunidad_form.html", active="oportunidades",
                           titulo="Editar oportunidad" if actual else "Nueva oportunidad",
                           op=op, **ctx)
    # El titulo se decide con un operador ternario segun el modo: si
    # 'actual' tiene datos, es una edicion; si es None, es un alta.
    # **ctx desempaqueta el diccionario de mas arriba como argumentos
    # con nombre (clientes_lista=..., ejecutivos=..., etapas=...): es
    # equivalente a escribir esos tres parametros uno por uno.


"""
   Función: oportunidad_etapa
   Objetivo: Mover una oportunidad una posición hacia adelante o
             hacia atrás en la lista ETAPAS, implementando así los
             botones de flecha del tablero Kanban. Si la etapa nueva
             es "Ganada", el motor dispara por su cuenta el trigger
             trg_oportunidad_ganada, que crea una actividad de
             seguimiento automáticamente.
   Parámetros:
     - op_id: identificador de la oportunidad a mover.
   Retorno: Redirige siempre al tablero de oportunidades.
"""
@bp.route("/oportunidades/<int:op_id>/etapa", methods=["POST"])
@permiso_requerido("clientes.editar")
def oportunidad_etapa(op_id):
    actual = query_one("SELECT id, etapa FROM oportunidades WHERE id = ?", [op_id])
    dire = request.form.get("dir")               # "adelante" o cualquier otro valor (retrocede)
    if actual and actual["etapa"] in ETAPAS:
        i = ETAPAS.index(actual["etapa"]) + (1 if dire == "adelante" else -1)
        # ETAPAS.index(...) da la posicion actual (0 a 4); se suma o
        # resta 1 segun la direccion del boton que se presiono.
        if 0 <= i < len(ETAPAS):
            # Solo se mueve si el nuevo indice sigue dentro del rango
            # (0 a 4): evita "salirse" de Contacto hacia atras o de
            # Perdida hacia adelante.
            execute("UPDATE oportunidades SET etapa=?, updated_at=SYSDATETIME() WHERE id=?",
                    [ETAPAS[i], op_id])
            registrar_auditoria("oportunidades", "UPDATE", op_id,
                                datos_anteriores={"etapa": actual["etapa"]},
                                datos_nuevos={"etapa": ETAPAS[i]})
    return redirect(url_for("pipeline.oportunidades"))

# Los cuatro tipos de actividad permitidos, replicando el CHECK de la
# columna tipo en la tabla actividades.
TIPOS_ACT = ["Llamada", "Reunion", "Correo", "Tarea"]


# ------------------ ACTIVIDADES ------------------

"""
   Función: actividades
   Objetivo: Mostrar el listado de actividades (llamadas, reuniones,
             correos y tareas), con un filtro opcional para ver solo
             las pendientes de completar.
   Parámetros: No recibe directamente (lee 'pendientes' de la URL).
   Retorno: La plantilla actividades.html con las actividades
            encontradas y la lista de clientes para el formulario
            rápido de registro.
"""
@bp.route("/actividades")
@permiso_requerido("clientes.ver")
def actividades():
    solo_pend = request.args.get("pendientes") == "1"    # ?pendientes=1 activa el filtro
    sql = ("SELECT a.*, e.nombre AS cliente, u.nombre AS usuario "
           "FROM actividades a JOIN clientes c ON c.id = a.cliente_id "
           "JOIN empresas e ON e.id = c.empresa_id "
           "LEFT JOIN usuarios u ON u.id = a.usuario_id ")
    # LEFT JOIN a usuarios: usuario_id admite NULL (participacion opcional)
    if solo_pend:
        sql += "WHERE a.completada = 0 AND a.proxima_accion IS NOT NULL "
    sql += "ORDER BY a.fecha DESC"
    return render_template("actividades.html", active="actividades",
                           actividades=query_all(sql), tipos=TIPOS_ACT,
                           solo_pend=solo_pend,
                           clientes_lista=query_all(
                               "SELECT c.id, e.nombre FROM clientes c "
                               "JOIN empresas e ON e.id=c.empresa_id ORDER BY e.nombre"))


"""
   Función: actividad_nueva
   Objetivo: Registrar una nueva actividad de seguimiento (llamada,
             reunión, correo o tarea) asociada a un cliente, tomando
             el usuario que la registra directamente de la sesión.
   Parámetros: No recibe directamente (lee el formulario, enviado
               solo por POST, sin ruta GET).
   Retorno: Redirige a la página desde donde se envió el formulario
            (request.referrer), o al listado de actividades si no
            hay una página anterior registrada.
"""
@bp.route("/actividades/nueva", methods=["POST"])   # Solo POST: no existe formulario GET aparte
@permiso_requerido("clientes.crear")
def actividad_nueva():
    g = lambda k: (request.form.get(k) or "").strip()  # noqa: E731
    if not g("cliente_id") or not g("asunto"):
        flash("Cliente y asunto son obligatorios.", "error")
    else:
        nuevo = insertar(
            "INSERT INTO actividades (cliente_id, usuario_id, tipo, asunto, notas, proxima_accion) "
            "OUTPUT INSERTED.id VALUES (?,?,?,?,?,?)",
            [int(g("cliente_id")), session.get("usuario_id"),
             # session.get("usuario_id"): quien la registra sale de la
             # sesion, no de un campo del formulario, para que no se
             # pueda falsear atribuyendole la actividad a otro usuario.
             g("tipo") if g("tipo") in TIPOS_ACT else "Llamada",
             g("asunto"), g("notas"), g("proxima_accion") or None])
        registrar_auditoria("actividades", "INSERT", nuevo,
                            datos_nuevos={"asunto": g("asunto"), "tipo": g("tipo")})
        flash("Actividad registrada.", "ok")
    return redirect(request.referrer or url_for("pipeline.actividades"))
    # request.referrer: la URL de la pagina que envio el formulario.
    # Como esta funcion se puede llamar desde varias pantallas (el
    # listado de actividades, o la vista 360 de un cliente), regresar
    # al referrer evita "perder" al usuario en un listado distinto.


"""
   Función: actividad_completar
   Objetivo: Marcar una actividad como completada.
   Parámetros:
     - act_id: identificador de la actividad a completar.
   Retorno: Redirige a la página desde donde se envió la petición, o
            al listado de actividades.
"""
@bp.route("/actividades/<int:act_id>/completar", methods=["POST"])
@permiso_requerido("clientes.editar")
def actividad_completar(act_id):
    execute("UPDATE actividades SET completada = 1 WHERE id = ?", [act_id])
    # Actualizacion minima: solo cambia la bandera completada, ningun
    # otro campo. No lleva registrar_auditoria() en esta version.
    flash("Actividad completada.", "ok")
    return redirect(request.referrer or url_for("pipeline.actividades"))


# ------------------ MÉTRICAS ------------------

"""
   Función: metricas
   Objetivo: Calcular los indicadores comerciales de la pantalla de
             métricas: tasa de conversión de cotizaciones, días
             promedio de cierre, cartera de ventas por ejecutivo y el
             embudo de oportunidades con su valor ponderado por
             probabilidad.
   Parámetros: No recibe.
   Retorno: La plantilla metricas.html con los cuatro bloques de
            indicadores ya calculados.
"""
@bp.route("/metricas")
@permiso_requerido("reportes.ver")
def metricas():
    tot = query_one("SELECT COUNT(*) n FROM cotizaciones WHERE estado IN "
                    "('Enviada','Aprobada','Rechazada')")["n"]
    # El total de "decididas" cuenta las que ya salieron de Borrador y
    # tuvieron una resolucion: Enviada (aun en curso), Aprobada o
    # Rechazada. No incluye Borrador ni Vencida.
    apro = query_one("SELECT COUNT(*) n FROM cotizaciones WHERE estado='Aprobada'")["n"]
    conversion = round(apro * 100 / tot) if tot else 0
    # La division solo se hace si tot es mayor que cero: evita el
    # error de division entre cero si todavia no hay cotizaciones.

    dias = query_one("SELECT AVG(CAST(DATEDIFF(DAY, fecha, updated_at) AS FLOAT)) d "
                     "FROM cotizaciones WHERE estado='Aprobada'")["d"]
    # DATEDIFF(DAY, fecha, updated_at) calcula, EN EL MOTOR, cuantos
    # dias pasaron entre que se creo la cotizacion y su ultima
    # modificacion (que para las Aprobadas es, tipicamente, el momento
    # de la aprobacion). AVG saca el promedio de todas.

    cartera = query_all(
        "SELECT COALESCE(u.nombre,'Sin asignar') ejecutivo, COUNT(*) n, "
        "COALESCE(SUM(co.total),0) total FROM cotizaciones co "
        "LEFT JOIN usuarios u ON u.id = co.ejecutivo_id "
        "WHERE co.estado='Aprobada' GROUP BY u.nombre ORDER BY total DESC")
    # LEFT JOIN a usuarios: si una cotizacion no tiene ejecutivo, no
    # desaparece del reporte; COALESCE la agrupa bajo "Sin asignar".

    embudo = query_all(
        "SELECT etapa, COUNT(*) n, COALESCE(SUM(valor_estimado),0) valor, "
        "COALESCE(SUM(valor_estimado*probabilidad/100.0),0) ponderado "
        "FROM oportunidades GROUP BY etapa")
    # El valor ponderado multiplica el valor estimado por la
    # probabilidad de cierre: una oportunidad de $10,000 al 50% pesa
    # lo mismo, en el ponderado, que una de $5,000 al 100%.

    embudo = sorted(embudo, key=lambda f: ETAPAS.index(f["etapa"]) if f["etapa"] in ETAPAS else 99)
    # GROUP BY no garantiza ningun orden en particular; se reordena en
    # Python segun la posicion de cada etapa en la lista ETAPAS
    # (Contacto, Propuesta, Negociacion, Ganada, Perdida), para que el
    # embudo se dibuje siempre en ese orden logico.

    return render_template("metricas.html", active="metricas",
                           conversion=conversion, total_cot=tot, aprobadas=apro,
                           dias_cierre=round(dias, 1) if dias else None,
                           cartera=cartera, embudo=embudo)