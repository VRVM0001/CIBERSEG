"""
=========================================================================
 Módulo: crm.py (app/routes/crm.py)
 Módulo CRM (Fase 2): Empresas, Clientes y Contactos.

 Patrón de cada entidad:
   - Lista con búsqueda/filtros.
   - Formulario de creación y edición (mismo template).
   - Desactivación lógica (nunca DELETE físico) con registro en auditoría.
 En las consultas, los valores del usuario nunca se pegan al texto SQL:
 van aparte, en la lista de parametros. Asi nadie puede colar codigo.
 Las columnas llevan delante el nombre completo de la tabla
 (empresas.nombre) para que se lea de un vistazo de donde sale cada dato.

 Este es el blueprint mas grande del proyecto: agrupa las tres
 entidades centrales del CRM (empresas, clientes, contactos) y ademas
 la vista 360 del cliente y la importacion/exportacion de CSV.
=========================================================================
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response

from ..db import query_all, query_one, execute, insertar
from ..seguridad import permiso_requerido, registrar_auditoria

bp = Blueprint("crm", __name__)

# Los valores que se aceptan en cada campo. Son los mismos que tiene
# puestos la base de datos: aqui sirven para llenar los desplegables y
# para comprobar lo que llega antes de guardarlo.
TAMANOS = ["Micro", "Pequena", "Mediana", "Grande", "Corporativo"]
TIPOS_CLIENTE = ["Corporativo", "Gobierno", "PYME", "Educacion", "Salud"]
SEGMENTOS = ["Estrategico", "Mayorista", "Regular"]
ESTADOS_CLIENTE = ["Prospecto", "Activo", "Inactivo", "Suspendido"]


# =====================================================================
#  EMPRESAS
# =====================================================================

"""
   Función: empresas
   Objetivo: Mostrar el listado paginado de empresas, con búsqueda por
             nombre, RNC o sector, y el conteo de cuántos clientes y
             contactos tiene cada una.
   Parámetros: No recibe directamente (lee 'q' y 'pagina' de la URL).
   Retorno: La plantilla empresas.html con las empresas de la página
            actual, el texto de búsqueda y si hay más páginas.
"""
@bp.route("/empresas")
@permiso_requerido("clientes.ver")
def empresas():
    q = (request.args.get("q") or "").strip()          # Lo que se escribio en la cajita de buscar
    sql = ("SELECT empresas.id, empresas.nombre, empresas.rnc, empresas.sector, "
           "       empresas.tamano, empresas.ciudad, empresas.telefono, "
           "       empresas.email, empresas.activo, "
           "       (SELECT COUNT(*) FROM clientes "
           "         WHERE clientes.empresa_id = empresas.id) AS n_clientes, "
           "       (SELECT COUNT(*) FROM contactos "
           "         WHERE contactos.empresa_id = empresas.id) AS n_contactos "
           "FROM empresas ")
    # Las dos consultas entre parentesis cuentan, para cada empresa de la
    # lista, cuantos clientes y cuantos contactos tiene. Se hacen aparte
    # porque si se unieran las tablas, los dos numeros se mezclarian: una
    # empresa con 3 clientes y 4 contactos daria 12 y saldrian inflados.
    params = []
    if q:
        sql += ("WHERE empresas.nombre LIKE ? OR empresas.rnc LIKE ? "
                "OR empresas.sector LIKE ? ")
        # Se va armando el texto de la consulta, pero lo que escribio el
        # usuario NO se pega aqui: viaja aparte, en params. Los tres campos
        # van con OR, asi que basta con que coincida uno.
        params = [f"%{q}%"] * 3       # El mismo texto de busqueda sirve para los tres campos
        # Los porcentajes significan "que contenga esto en cualquier parte".
        # El *3 repite el mismo texto tres veces, uno por cada interrogacion.
    pagina = max(1, int(request.args.get("pagina", 1) or 1))    # Nunca menor que 1
    sql += "ORDER BY empresas.nombre OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
    # La base de datos devuelve solo 15 filas por pagina, en vez de mandar
    # las mil que pueda haber. Hace falta el ORDER BY: sin un orden fijo,
    # "las siguientes quince" no significaria nada.
    params += [(pagina - 1) * 15, 15]        # Paginacion: salta (pagina-1)*15 filas y trae 15
    filas = query_all(sql, params)
    return render_template("empresas.html", active="empresas",
                           empresas=filas, buscar=q, pagina=pagina, hay_mas=len(filas) == 15)
    # Si la pagina trajo justo 15, se asume que hay otra despues. Se hace
    # asi para no gastar una consulta mas solo en contar el total.


"""
   Función: empresa_nueva
   Objetivo: Mostrar el formulario de alta de empresa (GET) y procesar
             su creación (POST), incluyendo la detección de posibles
             duplicados por nombre parecido o mismo RNC antes de
             insertar.
   Parámetros: No recibe directamente (lee el formulario con request.form).
   Retorno: En GET, formulario vacío. En POST correcto, redirige al
            listado. Si falta el nombre o hay un posible duplicado sin
            forzar, vuelve a mostrar el formulario con el aviso.
"""
@bp.route("/empresas/nueva", methods=["GET", "POST"])
@permiso_requerido("clientes.crear")
def empresa_nueva():
    if request.method == "POST":
        d = _form_empresa()                       # Lee y limpia lo que se escribio
        if not d["nombre"]:
            flash("El nombre de la empresa es obligatorio.", "error")
            return render_template("empresa_form.html", active="empresas",
                                   titulo="Nueva empresa", empresa=d, tamanos=TAMANOS)
        # Detección de duplicados (por nombre similar o mismo RNC)
        if not request.form.get("forzar"):        # Si ya confirmaron que no es duplicado, se salta
            dup = query_one(
                "SELECT TOP 1 nombre FROM empresas WHERE nombre LIKE ? OR (rnc IS NOT NULL AND rnc = ?)",
                [f"%{d['nombre']}%", d["rnc"] or "-"])
            # Si no escribieron RNC se manda un guion, que no coincide con
            # ninguno real. Comparar contra un campo vacio no funcionaria.
            if dup:
                flash(f"Posible duplicado: ya existe '{dup['nombre']}'. Marca la casilla "
                      "'Crear de todos modos' si es una empresa distinta.", "error")
                return render_template("empresa_form.html", active="empresas",
                                       titulo="Nueva empresa", empresa=d, tamanos=TAMANOS,
                                       mostrar_forzar=True)     # Hace aparecer la casilla de confirmar
        nuevo_id = insertar(
            "INSERT INTO empresas (nombre, rnc, sector, tamano, sitio_web, telefono, "
            "email, direccion, ciudad, pais) OUTPUT INSERTED.id VALUES (?,?,?,?,?,?,?,?,?,?)",
            [d["nombre"], d["rnc"] or None, d["sector"], d["tamano"], d["sitio_web"],
             d["telefono"], d["email"], d["direccion"], d["ciudad"], d["pais"]],
        )
        # Si el RNC vino vacio se guarda como "sin dato" y no como texto
        # vacio. El RNC no se puede repetir, y dos textos vacios contarian
        # como repetidos; varios "sin dato" no.
        registrar_auditoria("empresas", "INSERT", nuevo_id, datos_nuevos=d)
        flash("Empresa creada correctamente.", "ok")
        return redirect(url_for("crm.empresas"))
    return render_template("empresa_form.html", active="empresas",
                           titulo="Nueva empresa", empresa=None, tamanos=TAMANOS)   # Al entrar: formulario vacio


"""
   Función: empresa_editar
   Objetivo: Mostrar el formulario con los datos actuales de una
             empresa (GET) y guardar sus modificaciones (POST).
   Parámetros:
     - empresa_id: identificador de la empresa a editar.
   Retorno: En GET, formulario con datos cargados. En POST correcto,
            redirige al listado.
"""
@bp.route("/empresas/<int:empresa_id>/editar", methods=["GET", "POST"])
@permiso_requerido("clientes.editar")
def empresa_editar(empresa_id):
    actual = query_one("SELECT * FROM empresas WHERE id = ?", [empresa_id])
    # Se busca la empresa antes de nada, porque hace falta en los dos casos:
    # para llenar el formulario y para comparar que cambio al guardar.
    if actual is None:
        flash("La empresa no existe.", "error")
        return redirect(url_for("crm.empresas"))
        # Sin esto, un numero inventado en la direccion daria un error feo
        # en pantalla en vez de un aviso.
    if request.method == "POST":
        d = _form_empresa()
        if not d["nombre"]:
            flash("El nombre de la empresa es obligatorio.", "error")
            return render_template("empresa_form.html", active="empresas",
                                   titulo="Editar empresa", empresa=d, tamanos=TAMANOS)
        execute(
            "UPDATE empresas SET nombre=?, rnc=?, sector=?, tamano=?, sitio_web=?, "
            "telefono=?, email=?, direccion=?, ciudad=?, pais=?, updated_at=SYSDATETIME() "
            "WHERE id=?",                          # Sin este WHERE cambiaria TODAS las empresas
            [d["nombre"], d["rnc"] or None, d["sector"], d["tamano"], d["sitio_web"],
             d["telefono"], d["email"], d["direccion"], d["ciudad"], d["pais"], empresa_id],
        )
        registrar_auditoria("empresas", "UPDATE", empresa_id,
                            # Se guarda como estaba y como quedo, para que el
                            # historial muestre que cambio exactamente.
                            datos_anteriores={k: actual[k] for k in d if k in actual},
                            # Solo los campos del formulario, para poder
                            # compararlos uno a uno.
                            datos_nuevos=d)
        flash("Empresa actualizada.", "ok")
        return redirect(url_for("crm.empresas"))
    return render_template("empresa_form.html", active="empresas",
                           titulo="Editar empresa", empresa=actual, tamanos=TAMANOS)


"""
   Función: empresa_estado
   Objetivo: Alternar la bandera 'activo' de una empresa (borrado
             lógico). Nunca borra la fila físicamente, porque
             empresas es el lado "padre" de clientes y contactos.
   Parámetros:
     - empresa_id: identificador de la empresa cuyo estado se cambia.
   Retorno: Redirige al listado de empresas, con un mensaje.
"""
@bp.route("/empresas/<int:empresa_id>/estado", methods=["POST"])   # Solo POST: modifica datos
@permiso_requerido("clientes.eliminar")
def empresa_estado(empresa_id):
    actual = query_one("SELECT id, nombre, activo FROM empresas WHERE id = ?", [empresa_id])
    # Se pide solo lo justo. Hace falta saber como esta ahora para poder
    # ponerlo al reves.
    if actual is None:
        flash("La empresa no existe.", "error")
    else:
        nuevo = 0 if actual["activo"] else 1        # Le da la vuelta: si estaba activa, la apaga
        # El mismo boton activa y desactiva, segun como este.
        execute("UPDATE empresas SET activo=?, updated_at=SYSDATETIME() WHERE id=?",
                [nuevo, empresa_id])
        # Nunca se borra de verdad, solo se marca como inactiva. Si se
        # borrara, sus clientes y contactos quedarian apuntando a una
        # empresa que ya no existe, y se perderia el historial.
        registrar_auditoria("empresas", "UPDATE", empresa_id,
                            datos_anteriores={"activo": bool(actual["activo"])},
                            datos_nuevos={"activo": bool(nuevo)})
        # La base guarda 1 y 0; se pasan a si/no para que el historial se
        # lea mejor.
        flash(f"Empresa {'activada' if nuevo else 'desactivada'}.", "ok")
    return redirect(url_for("crm.empresas"))


"""
   Función: _form_empresa
   Objetivo: Leer y limpiar los campos del formulario de empresa,
             aplicando valores por defecto que replican los DEFAULT
             de la tabla.
   Parámetros: No recibe (lee de request.form).
   Retorno: Diccionario con los diez campos de empresas.
"""
def _form_empresa():
    g = lambda k: (request.form.get(k) or "").strip()  # noqa: E731
    # g() lee un campo del formulario, le quita los espacios de los lados
    # y devuelve texto vacio si no vino nada.
    return {"nombre": g("nombre"), "rnc": g("rnc"), "sector": g("sector"),
            "tamano": g("tamano") or "Mediana",              # El mismo valor por defecto que la tabla
            "sitio_web": g("sitio_web"),
            "telefono": g("telefono"), "email": g("email"), "direccion": g("direccion"),
            "ciudad": g("ciudad"), "pais": g("pais") or "Republica Dominicana"}   # Igual: valor por defecto


# =====================================================================
#  CLIENTES
# =====================================================================

"""
   Función: clientes
   Objetivo: Mostrar el listado paginado de clientes, con búsqueda por
             nombre de empresa o código, y filtros opcionales por
             estado, etiqueta y tipo, todos combinables entre sí.
   Parámetros: No recibe directamente (lee 'q', 'estado', 'etiqueta',
               'tipo' y 'pagina' de la URL).
   Retorno: La plantilla clientes.html con los clientes de la página
            actual y los valores de cada filtro aplicado.
"""
@bp.route("/clientes")
@permiso_requerido("clientes.ver")
def clientes():
    q = (request.args.get("q") or "").strip()
    estado = (request.args.get("estado") or "").strip()
    etiqueta = (request.args.get("etiqueta") or "").strip()
    tipo = (request.args.get("tipo") or "").strip()
    sql = ("SELECT clientes.id, clientes.codigo, clientes.tipo, clientes.segmento, "
           "       clientes.estado, clientes.limite_credito, clientes.etiquetas, "
           "       clientes.fecha_alta, "
           "       empresas.nombre AS empresa, usuarios.nombre AS ejecutivo "
           "FROM clientes "
           "JOIN empresas ON empresas.id = clientes.empresa_id "            # Todo cliente tiene empresa
           "LEFT JOIN usuarios ON usuarios.id = clientes.ejecutivo_id WHERE 1=1 ")
    # Se unen tres tablas. Con empresas basta un JOIN normal porque todo
    # cliente tiene empresa. Con usuarios hace falta LEFT JOIN porque el
    # ejecutivo es opcional: con el normal, los clientes sin ejecutivo
    # desapareceran de la lista sin avisar de nada.
    # Cada columna lleva delante el nombre de su tabla porque las tres
    # tienen "id" y dos tienen "nombre". El WHERE 1=1 no filtra: solo
    # permite ir pegando los filtros de abajo.
    params = []
    # Cuatro filtros que se pueden combinar. Cada uno agrega su trozo de
    # consulta y su valor, siempre en el mismo orden: si se descolocan, el
    # dato acaba en el sitio equivocado.
    if q:
        sql += ("AND (empresas.nombre LIKE ? "
                "OR clientes.codigo LIKE ?) ")     # Busca por nombre de empresa O codigo
        # Los parentesis hacen falta: sin ellos este OR se mezclaria con
        # los AND de los otros filtros y la busqueda daria mal.
        params += [f"%{q}%", f"%{q}%"]
    if estado:
        sql += "AND clientes.estado = ? "
        # Aqui se busca el valor exacto, porque el estado sale de un
        # desplegable y no lo escribe el usuario.
        params.append(estado)
    if etiqueta:
        sql += "AND clientes.etiquetas LIKE ? "
        # Aqui si se busca "dentro" del texto, porque las etiquetas van
        # todas juntas en un mismo campo separadas por comas.
        params.append(f"%{etiqueta}%")
    if tipo:
        sql += "AND clientes.tipo = ? "
        params.append(tipo)
    pagina = max(1, int(request.args.get("pagina", 1) or 1))
    sql += "ORDER BY empresas.nombre OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
    params += [(pagina - 1) * 15, 15]
    filas = query_all(sql, params)
    return render_template("clientes.html", active="clientes",
                           clientes=filas, buscar=q, estado=estado,
                           estados=ESTADOS_CLIENTE, etiqueta=etiqueta,
                           pagina=pagina, hay_mas=len(filas) == 15)


"""
   Función: cliente_nuevo
   Objetivo: Mostrar el formulario de alta de cliente (GET) y procesar
             su creación (POST), generando el código correlativo
             CLI-0001 automáticamente.
   Parámetros: No recibe directamente (lee el formulario).
   Retorno: En GET, formulario vacío con los desplegables cargados. En
            POST correcto, redirige al listado con el código creado.
"""
@bp.route("/clientes/nuevo", methods=["GET", "POST"])
@permiso_requerido("clientes.crear")
def cliente_nuevo():
    ctx = _ctx_cliente()      # Las listas de los desplegables del formulario
    if request.method == "POST":
        d = _form_cliente()
        if not d["empresa_id"]:
            # Es lo unico obligatorio: sin empresa no hay cliente, y de
            # ella sale el nombre que se ve en pantalla.
            flash("Selecciona la empresa del cliente.", "error")
            return render_template("cliente_form.html", active="clientes",
                                   titulo="Nuevo cliente", cliente=d, **ctx)
            # **ctx pasa de golpe todas las listas de los desplegables,
            # para no escribirlas una por una.
        sig = query_one("SELECT ISNULL(MAX(id),0)+1 AS n FROM clientes")["n"]
        # Busca el numero mas alto y le suma uno. El ISNULL hace falta
        # porque con la tabla vacia no devolveria cero sino "nada", y el
        # primer cliente se quedaria sin codigo.
        codigo = f"CLI-{sig:04d}"        # Rellena con ceros hasta 4 cifras: CLI-0007
        # El codigo lo pone el sistema, no el usuario. Es el que se ve en
        # pantalla (CLI-0007); el numero interno va aparte.
        nuevo_id = insertar(
            "INSERT INTO clientes (codigo, empresa_id, tipo, segmento, ejecutivo_id, "
            "estado, limite_credito, fecha_alta, notas, etiquetas) OUTPUT INSERTED.id "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            # Las interrogaciones y los valores de abajo van en el mismo
            # orden. Si se cruzan dos, no da error: el dato se guarda en el
            # campo que no era. Las fechas de creacion las pone la tabla sola.
            # El OUTPUT sirve para saber que numero le toco al cliente nuevo.
            [codigo, d["empresa_id"], d["tipo"], d["segmento"], d["ejecutivo_id"],
             d["estado"], d["limite_credito"], d["fecha_alta"] or None, d["notas"], d["etiquetas"]],
            # Si no pusieron fecha se guarda "sin dato", porque ese campo
            # solo admite fechas y no texto vacio.
        )
        registrar_auditoria("clientes", "INSERT", nuevo_id,
                            datos_nuevos={**d, "codigo": codigo})
        # Se guarda lo del formulario mas el codigo, que lo genero el
        # sistema y no venia de ninguna casilla.
        flash(f"Cliente {codigo} creado correctamente.", "ok")
        return redirect(url_for("crm.clientes"))
    return render_template("cliente_form.html", active="clientes",
                           titulo="Nuevo cliente", cliente=None, **ctx)


"""
   Función: cliente_editar
   Objetivo: Mostrar el formulario con los datos actuales de un
             cliente (GET) y guardar sus modificaciones (POST).
   Parámetros:
     - cliente_id: identificador del cliente a editar (convertido a
                   entero por el convertidor <int:> de Flask).
   Retorno: En GET, formulario con datos cargados. En POST correcto,
            redirige al listado.
"""
@bp.route("/clientes/<int:cliente_id>/editar", methods=["GET", "POST"])
@permiso_requerido("clientes.editar")
def cliente_editar(cliente_id):
    actual = query_one("SELECT * FROM clientes WHERE id = ?", [cliente_id])
    # Esta es la primera de las dos consultas que la matriz de
    # trazabilidad asigna a esta pantalla.
    if actual is None:
        flash("El cliente no existe.", "error")
        return redirect(url_for("crm.clientes"))
    ctx = _ctx_cliente()
    if request.method == "POST":
        d = _form_cliente()
        if not d["empresa_id"]:
            flash("Selecciona la empresa del cliente.", "error")
            return render_template("cliente_form.html", active="clientes",
                                   titulo="Editar cliente", cliente=d, **ctx)
        execute(
            "UPDATE clientes SET empresa_id=?, tipo=?, segmento=?, ejecutivo_id=?, "
            "estado=?, limite_credito=?, fecha_alta=?, notas=?, etiquetas=?, updated_at=SYSDATETIME() "
            # Se guardan los nueve campos siempre, aunque solo haya
            # cambiado uno: es mas simple y cuesta igual. La fecha de
            # modificacion la pone el servidor, no el equipo del usuario.
            "WHERE id=?",                          # Sin este WHERE cambiaria TODOS los clientes
            [d["empresa_id"], d["tipo"], d["segmento"], d["ejecutivo_id"], d["estado"],
             d["limite_credito"], d["fecha_alta"] or None, d["notas"], d["etiquetas"], cliente_id],
        )
        registrar_auditoria("clientes", "UPDATE", cliente_id,
                            # Solo se anotan cinco campos, los que importan
                            # para el negocio. Las notas y etiquetas cambian
                            # a cada rato y llenarian el historial de ruido.
                            datos_anteriores={k: actual[k] for k in
                                              ("empresa_id", "tipo", "segmento", "estado",
                                               "limite_credito")},
                            datos_nuevos=d)
        # Este cambio queda anotado dos veces: aqui, que se sabe quien lo
        # hizo, y ademas en la base de datos, que lo apunta aunque alguien
        # edite el cliente sin pasar por el sistema.
        flash("Cliente actualizado.", "ok")
        return redirect(url_for("crm.clientes"))
    return render_template("cliente_form.html", active="clientes",
                           titulo=f"Editar cliente {actual['codigo']}",
                           cliente=actual, **ctx)


"""
   Función: _ctx_cliente
   Objetivo: Reunir las listas necesarias para los desplegables del
             formulario de cliente (empresas activas, ejecutivos
             activos, y los catálogos de tipo/segmento/estado).
   Parámetros: No recibe.
   Retorno: Diccionario con las claves empresas_lista, ejecutivos,
            tipos, segmentos y estados, listo para desempaquetar
            con **ctx en render_template.
"""
def _ctx_cliente():
    return {
        "empresas_lista": query_all(
            "SELECT id, nombre FROM empresas WHERE activo = 1 ORDER BY nombre"),
        # Las dos listas dejan fuera lo desactivado: no se puede asignar un
        # cliente a una empresa dada de baja ni a un usuario apagado.
        "ejecutivos": query_all(
            "SELECT id, nombre FROM usuarios WHERE activo = 1 ORDER BY nombre"),
        "tipos": TIPOS_CLIENTE, "segmentos": SEGMENTOS, "estados": ESTADOS_CLIENTE,
    }


"""
   Función: _form_cliente
   Objetivo: Leer y limpiar los campos del formulario de cliente,
             aplicando valores por defecto y acotando el límite de
             crédito al máximo que admite la columna.
   Parámetros: No recibe (lee de request.form).
   Retorno: Diccionario con los nueve campos de clientes.
"""
def _form_cliente():
    g = lambda k: (request.form.get(k) or "").strip()  # noqa: E731
    return {
        "empresa_id": int(g("empresa_id") or 0) or None,     # Si no eligieron empresa, queda sin dato
        "tipo": g("tipo") or "Corporativo",
        "segmento": g("segmento") or "Regular",
        "ejecutivo_id": int(g("ejecutivo_id") or 0) or None,  # Puede quedar vacio: es opcional
        "estado": g("estado") or "Prospecto",
        "limite_credito": min(9_999_999_999.99, max(0, float(g("limite_credito") or 0))),
        # Se corta por los dos lados: nada de negativos, y nada por encima
        # del maximo que admite el campo. Si no, la base daria error.
        "fecha_alta": g("fecha_alta"),
        "notas": g("notas"),
        "etiquetas": g("etiquetas"),
    }


# =====================================================================
#  CONTACTOS
# =====================================================================

"""
   Función: contactos
   Objetivo: Mostrar el listado paginado de contactos, con búsqueda
             por nombre, correo o cargo, y un filtro opcional por
             empresa (llega como ?empresa_id=N en la URL).
   Parámetros: No recibe directamente (lee 'q', 'empresa_id' y
               'pagina' de la URL).
   Retorno: La plantilla contactos.html con los contactos de la
            página actual y la lista de empresas para el filtro.
"""
@bp.route("/contactos")
@permiso_requerido("clientes.ver")
def contactos():
    q = (request.args.get("q") or "").strip()
    empresa_id = int(request.args.get("empresa_id") or 0)     # 0 = sin filtro de empresa
    sql = ("SELECT contactos.id, contactos.nombre, contactos.cargo, "
           "       contactos.departamento, contactos.email, contactos.telefono, "
           "       contactos.celular, contactos.es_principal, contactos.activo, "
           "       empresas.nombre AS empresa "
           "FROM contactos "
           "JOIN empresas ON empresas.id = contactos.empresa_id WHERE 1=1 ")
    # JOIN normal porque todo contacto tiene empresa. Se trae el nombre de
    # la empresa porque la tabla de contactos solo guarda su numero.
    # El WHERE 1=1 esta para poder ir pegando los filtros de abajo.
    params = []
    if q:
        sql += ("AND (contactos.nombre LIKE ? OR contactos.email LIKE ? "
                "OR contactos.cargo LIKE ?) ")
        params += [f"%{q}%"] * 3
    if empresa_id:
        sql += "AND contactos.empresa_id = ? "
        # Este filtro usa el campo que conecta cada contacto con su
        # empresa: es la relacion "emplea" del diagrama.
        params.append(empresa_id)
    pagina = max(1, int(request.args.get("pagina", 1) or 1))
    sql += ("ORDER BY empresas.nombre, contactos.es_principal DESC, contactos.nombre "
            "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY")
    # Se ordena por tres cosas seguidas: cada una decide solo cuando la
    # anterior empata. El resultado es que los contactos salen agrupados por
    # empresa y el principal aparece primero dentro de cada grupo.
    params += [(pagina - 1) * 15, 15]
    empresas_lista = query_all("SELECT id, nombre FROM empresas ORDER BY nombre")   # Para el filtro
    # Aqui si aparecen las empresas desactivadas, al reves que en el
    # formulario. Es a proposito: esta lista sirve para buscar, y puede
    # hacer falta ver los contactos de una empresa que ya se dio de baja.
    filas = query_all(sql, params)
    return render_template("contactos.html", active="contactos",
                           contactos=filas, buscar=q, empresa_id=empresa_id,
                           empresas_lista=empresas_lista,
                           pagina=pagina, hay_mas=len(filas) == 15)
#Aca return render_template realiza la consulta 
# y devuelve la plantilla con los contactos de la 
# pagina actual, el texto de busqueda y si hay mas paginas.


"""
   Función: contacto_nuevo
   Objetivo: Mostrar el formulario de alta de contacto (GET) y
             procesar su creación (POST).
   Parámetros: No recibe directamente (lee el formulario).
   Retorno: En GET, formulario vacío. En POST correcto, redirige al
            listado.
"""
@bp.route("/contactos/nuevo", methods=["GET", "POST"])
@permiso_requerido("clientes.crear")
def contacto_nuevo():
    empresas_lista = query_all(
        "SELECT id, nombre FROM empresas WHERE activo = 1 ORDER BY nombre")
    # Se pide fuera del if porque hace falta las dos veces: al abrir el
    # formulario y si hay que volver a mostrarlo por un error.
    if request.method == "POST":
        d = _form_contacto()
        if not d["empresa_id"] or not d["nombre"]:
            flash("La empresa y el nombre del contacto son obligatorios.", "error")
            return render_template("contacto_form.html", active="contactos",
                                   titulo="Nuevo contacto", contacto=d,
                                   empresas_lista=empresas_lista)
        nuevo_id = insertar(
            "INSERT INTO contactos (empresa_id, nombre, cargo, departamento, email, "
            "telefono, celular, es_principal) OUTPUT INSERTED.id VALUES (?,?,?,?,?,?,?,?)",
            # empresa_id es el campo que enlaza el contacto con su empresa.
            # Si alguien trucara el formulario para mandar una empresa que
            # no existe, la propia base de datos rechazaria el guardado.
            [d["empresa_id"], d["nombre"], d["cargo"], d["departamento"], d["email"],
             d["telefono"], d["celular"], d["es_principal"]],
            # La casilla de "principal" llega ya convertida a 1 o 0, que es
            # lo unico que admite ese campo.
        )
        registrar_auditoria("contactos", "INSERT", nuevo_id, datos_nuevos=d)
        flash("Contacto creado correctamente.", "ok")
        # Aqui no se avisa de duplicados, al reves que en empresas: una
        # persona puede estar en dos empresas y dos personas pueden
        # llamarse igual.
        return redirect(url_for("crm.contactos"))
    return render_template("contacto_form.html", active="contactos",
                           titulo="Nuevo contacto", contacto=None,
                           empresas_lista=empresas_lista)


"""
   Función: contacto_editar
   Objetivo: Mostrar el formulario con los datos actuales de un
             contacto (GET) y guardar sus modificaciones (POST).
   Parámetros:
     - contacto_id: identificador del contacto a editar.
   Retorno: En GET, formulario con datos cargados. En POST correcto,
            redirige al listado.
"""
@bp.route("/contactos/<int:contacto_id>/editar", methods=["GET", "POST"])
@permiso_requerido("clientes.editar")
def contacto_editar(contacto_id):
    actual = query_one("SELECT * FROM contactos WHERE id = ?", [contacto_id])
    if actual is None:
        flash("El contacto no existe.", "error")
        return redirect(url_for("crm.contactos"))
    empresas_lista = query_all(
        "SELECT id, nombre FROM empresas WHERE activo = 1 ORDER BY nombre")
    # Igual que en el alta: la lista hace falta las dos veces.
    if request.method == "POST":
        d = _form_contacto()
        if not d["empresa_id"] or not d["nombre"]:
            flash("La empresa y el nombre del contacto son obligatorios.", "error")
            return render_template("contacto_form.html", active="contactos",
                                   titulo="Editar contacto", contacto=d,
                                   empresas_lista=empresas_lista)
        execute(
            "UPDATE contactos SET empresa_id=?, nombre=?, cargo=?, departamento=?, "
            "email=?, telefono=?, celular=?, es_principal=?, updated_at=SYSDATETIME() "
            # Se puede cambiar de empresa: la base comprueba que la nueva
            # exista de verdad.
            "WHERE id=?",
            # El numero del contacto va al final de la lista, porque su
            # interrogacion es la ultima de la consulta.
            [d["empresa_id"], d["nombre"], d["cargo"], d["departamento"], d["email"],
             d["telefono"], d["celular"], d["es_principal"], contacto_id],
        )
        registrar_auditoria("contactos", "UPDATE", contacto_id,
                            # Se anotan cuatro campos: los que dicen quien es
                            # y a que empresa pertenece.
                            datos_anteriores={k: actual[k] for k in
                                              ("empresa_id", "nombre", "cargo", "email")},
                            datos_nuevos=d)
        flash("Contacto actualizado.", "ok")
        return redirect(url_for("crm.contactos"))
    return render_template("contacto_form.html", active="contactos",
                           titulo="Editar contacto", contacto=actual,
                           empresas_lista=empresas_lista)


"""
   Función: contacto_estado
   Objetivo: Alternar la bandera 'activo' de un contacto (borrado
             lógico).
   Parámetros:
     - contacto_id: identificador del contacto cuyo estado se cambia.
   Retorno: Redirige al listado de contactos, con un mensaje.
"""
@bp.route("/contactos/<int:contacto_id>/estado", methods=["POST"])
@permiso_requerido("clientes.eliminar")
def contacto_estado(contacto_id):
    actual = query_one("SELECT id, activo FROM contactos WHERE id = ?", [contacto_id])
    if actual is None:
        flash("El contacto no existe.", "error")
    else:
        nuevo = 0 if actual["activo"] else 1        # Invierte el valor actual
        execute("UPDATE contactos SET activo=?, updated_at=SYSDATETIME() WHERE id=?",
                [nuevo, contacto_id])
        # Igual que en empresas: no se borra, se apaga. Deja de aparecer
        # pero su historial se conserva.
        registrar_auditoria("contactos", "UPDATE", contacto_id,
                            datos_anteriores={"activo": bool(actual["activo"])},
                            datos_nuevos={"activo": bool(nuevo)})
        flash(f"Contacto {'activado' if nuevo else 'desactivado'}.", "ok")
    return redirect(url_for("crm.contactos"))


"""
   Función: _form_contacto
   Objetivo: Leer y limpiar los campos del formulario de contacto.
   Parámetros: No recibe (lee de request.form).
   Retorno: Diccionario con los ocho campos de contactos.
"""
def _form_contacto():
    g = lambda k: (request.form.get(k) or "").strip()  # noqa: E731
    return {"empresa_id": int(g("empresa_id") or 0) or None, "nombre": g("nombre"),
            "cargo": g("cargo"), "departamento": g("departamento"), "email": g("email"),
            "telefono": g("telefono"), "celular": g("celular"),
            "es_principal": 1 if request.form.get("es_principal") else 0}
            # Si la casilla esta marcada llega algo; si no, no llega nada.
            # Se convierte a 1 o 0, que es lo que guarda la base.


"""
   Función: cliente_ver
   Objetivo: Mostrar la vista 360 del cliente: su ficha completa mas
             un bloque por cada relación 1—N que tiene en el modelo
             (contactos de su empresa, cotizaciones, facturas, equipos,
             proyectos, oportunidades, actividades e historial de
             auditoría), reunido todo en una sola pantalla.
   Parámetros:
     - cliente_id: identificador del cliente a mostrar.
   Retorno: La plantilla cliente_ver.html con la ficha y los ocho
            bloques de información relacionada.
"""
@bp.route("/clientes/<int:cliente_id>")
@permiso_requerido("clientes.ver")
def cliente_ver(cliente_id):
    """Vista 360 del cliente: todo lo relacionado en una sola página."""
    cli = query_one(
        "SELECT clientes.*, empresas.nombre AS empresa, empresas.sector, empresas.ciudad, "
        "       empresas.telefono AS emp_tel, usuarios.nombre AS ejecutivo "
        "FROM clientes "
        "JOIN empresas ON empresas.id = clientes.empresa_id "
        "LEFT JOIN usuarios ON usuarios.id = clientes.ejecutivo_id "
        "WHERE clientes.id = ?", [cliente_id])
    # Al telefono de la empresa se le pone otro nombre para que no choque
    # con el del cliente.
    if cli is None:
        flash("El cliente no existe.", "error")
        return redirect(url_for("crm.clientes"))

    datos = {
        # Cada bloque de la pantalla es una consulta aparte. Se hace asi y
        # no todo junto porque son cosas que no tienen que ver entre si:
        # unirlas mezclaria las filas y los datos saldrian repetidos.
        "contactos": query_all(
            "SELECT nombre, cargo, email, celular, telefono, es_principal FROM contactos "
            "WHERE empresa_id = ? AND activo = 1 ORDER BY es_principal DESC", [cli["empresa_id"]]),
        # Busca por la empresa del cliente y no por el cliente, porque los
        # contactos pertenecen a la empresa.

        "cotizaciones": query_all(
            "SELECT id, numero, fecha, estado, total FROM cotizaciones "
            "WHERE cliente_id = ? ORDER BY fecha DESC", [cliente_id]),
        "facturas": query_all(
            "SELECT numero, fecha_emision, estado, total FROM facturas "
            "WHERE cliente_id = ? ORDER BY fecha_emision DESC", [cliente_id]),
        "equipos": query_all(
            "SELECT tipo, numero_serie, hostname, estado FROM equipos "
            "WHERE cliente_id = ? ORDER BY tipo", [cliente_id]),
        "proyectos": query_all(
            "SELECT nombre, estado, presupuesto, fecha_inicio FROM proyectos "
            "WHERE cliente_id = ? ORDER BY fecha_inicio DESC", [cliente_id]),
        "oportunidades": query_all(
            "SELECT nombre, etapa, valor_estimado, probabilidad FROM oportunidades "
            "WHERE cliente_id = ? ORDER BY updated_at DESC", [cliente_id]),
        "actividades": query_all(
            "SELECT actividades.tipo, actividades.asunto, actividades.fecha, "
            "       actividades.proxima_accion, actividades.completada, "
            "       usuarios.nombre AS usuario "
            "FROM actividades "
            "LEFT JOIN usuarios ON usuarios.id = actividades.usuario_id "
            "WHERE actividades.cliente_id = ? "
            "ORDER BY actividades.fecha DESC", [cliente_id]),
        "historial": query_all(
            "SELECT TOP 20 auditoria.fecha, auditoria.accion, "
            "       usuarios.nombre AS usuario, auditoria.datos_nuevos "
            "FROM auditoria "
            "LEFT JOIN usuarios ON usuarios.id = auditoria.usuario_id "
            "WHERE auditoria.tabla_afectada = 'clientes' AND auditoria.registro_id = ? "
            "ORDER BY auditoria.fecha DESC", [str(cliente_id)]),
        # En la tabla de historial el numero se guarda como texto, por eso
        # hay que convertirlo antes de comparar.
    }
    total_fact = sum(float(f["total"] or 0) for f in datos["facturas"] if f["estado"] == "Pagada")
    # Se suma aqui mismo, aprovechando las facturas que ya se trajeron,
    # en vez de hacer otra consulta. Solo cuentan las que estan pagadas.
    return render_template("cliente_ver.html", active="clientes", cli=cli,
                           total_fact=total_fact, **datos)


"""
   Función: clientes_exportar
   Objetivo: Generar un archivo CSV con la lista completa de clientes,
             para descargarlo y abrirlo en Excel.
   Parámetros: No recibe.
   Retorno: Una respuesta HTTP de tipo texto/csv, con encabezado que
            indica al navegador que la descargue como "clientes.csv".
"""
@bp.route("/clientes/exportar")
@permiso_requerido("clientes.ver")
def clientes_exportar():
    """Exporta la lista de clientes a CSV (abre en Excel)."""
    import csv, io               # Herramientas de Python para armar el archivo
    filas = query_all(
        "SELECT clientes.codigo, empresas.nombre AS empresa, clientes.tipo, "
        "       clientes.segmento, clientes.estado, clientes.limite_credito, "
        "       clientes.fecha_alta, clientes.etiquetas "
        "FROM clientes "
        "JOIN empresas ON empresas.id = clientes.empresa_id "
        "ORDER BY empresas.nombre")
    # Sin paginas ni filtros: la exportacion trae todo, que es lo que se
    # espera de un archivo para Excel. Las columnas se nombran una a una
    # porque su orden es el que tendran en el archivo, y tiene que coincidir
    # con los titulos que se escriben mas abajo.
    out = io.StringIO()                          # Archivo CSV construido en memoria, no en disco
    # El archivo se arma en memoria, no en el disco: asi no hay que crear
    # un archivo temporal ni acordarse de borrarlo.
    w = csv.writer(out, delimiter=';')            # Separador punto y coma (formato regional de Excel)
    # Excel en espanol espera punto y coma. Con coma, metaria toda la fila
    # en una sola casilla.
    w.writerow(["Codigo", "Empresa", "Tipo", "Segmento", "Estado",
                "Limite credito", "Fecha alta", "Etiquetas"])   # Fila de encabezados
    for f in filas:
        w.writerow([f["codigo"], f["empresa"], f["tipo"], f["segmento"], f["estado"],
                    f["limite_credito"], f["fecha_alta"], f["etiquetas"] or ""])
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=clientes.csv"})
    # Esa marca invisible del principio le dice a Excel como leer el
    # archivo, para que las tildes y las enes salgan bien.


"""
   Función: clientes_importar
   Objetivo: Mostrar el formulario para subir un archivo CSV (GET) y
             procesar la importación masiva de clientes (POST),
             creando también las empresas que no existan todavía.
   Parámetros: No recibe directamente (lee el archivo con
               request.files).
   Retorno: En GET, el formulario de carga. En POST, redirige al
            listado con un resumen de cuántos se crearon y cuántos
            fallaron.
"""
@bp.route("/clientes/importar", methods=["GET", "POST"])
@permiso_requerido("clientes.crear")
def clientes_importar():
    """Importa clientes desde CSV (columnas: empresa;tipo;segmento;estado)."""
    import csv, io
    if request.method == "POST":
        archivo = request.files.get("archivo")           # El archivo subido por el usuario
        if not archivo or not archivo.filename.lower().endswith(".csv"):
            flash("Sube un archivo .csv (separado por ;).", "error")
            return redirect(url_for("crm.clientes_importar"))
        contenido = archivo.read().decode("utf-8-sig", errors="replace")
        # Se limpia la marca que Excel pone al principio, y si viene algun
        # caracter raro se sustituye en vez de cortar la importacion entera.
        lector = csv.DictReader(io.StringIO(contenido), delimiter=';')
        # Lee el archivo tomando la primera fila como los nombres de las
        # columnas.
        creados, errores = 0, 0
        for fila in lector:                     # Una vuelta por cada fila del archivo
            try:
                nombre = (fila.get("empresa") or "").strip()
                if not nombre:
                    continue                     # Fila sin empresa: se salta
                emp = query_one("SELECT id FROM empresas WHERE nombre = ?", [nombre])
                # Aqui se busca el nombre exacto. Buscar por parecido podria
                # juntar "Banco Popular" con "Banco Popular Dominicano" y
                # mezclar dos empresas que no son la misma.
                emp_id = emp["id"] if emp else insertar(
                    "INSERT INTO empresas (nombre) OUTPUT INSERTED.id VALUES (?)", [nombre])
                # Si la empresa ya esta, se usa; si no, se crea sobre la
                # marcha con solo el nombre y se completa despues a mano.
                sig = query_one("SELECT ISNULL(MAX(id),0)+1 AS n FROM clientes")["n"]
                insertar(
                    "INSERT INTO clientes (codigo, empresa_id, tipo, segmento, estado, fecha_alta) "
                    "OUTPUT INSERTED.id VALUES (?,?,?,?,?, CAST(GETDATE() AS DATE))",
                    [f"CLI-{sig:04d}", emp_id,
                     (fila.get("tipo") or "Corporativo").strip() or "Corporativo",
                     (fila.get("segmento") or "Regular").strip() or "Regular",
                     (fila.get("estado") or "Prospecto").strip() or "Prospecto"])
                creados += 1
            except Exception:
                errores += 1        # Si una fila falla se cuenta y se sigue con la siguiente
        registrar_auditoria("clientes", "INSERT", None,
                            datos_nuevos={"importacion_csv": creados, "errores": errores})
        flash(f"Importación completada: {creados} cliente(s) creados, {errores} error(es).", "ok")
        return redirect(url_for("crm.clientes"))
    return render_template("clientes_importar.html", active="clientes")   # Al entrar: el formulario