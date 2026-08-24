"""
=========================================================================
 Módulo: inventario.py (app/routes/inventario.py)
 Módulo Inventario (Fase 4): Productos (con control de stock),
 Equipos y Licencias.

 - Productos: catálogo con stock y stock mínimo; ajuste de stock
   (entradas/salidas) registrado en auditoría; alerta visual cuando
   stock <= stock_minimo.
 - Equipos: base instalada en clientes (firewalls, switches, APs...).
 - Licencias: suscripciones por cliente con fechas de vigencia y estado.

 Tres entidades relacionadas entre si: productos es el catalogo del
 que salen tanto los equipos instalados como las licencias vendidas.
=========================================================================
"""
import datetime      # Para calcular la fecha de fin por defecto de una licencia nueva (hoy + 1 año)

from flask import Blueprint, render_template, request, redirect, url_for, flash

from ..db import query_all, query_one, execute, insertar
from ..seguridad import permiso_requerido, registrar_auditoria

bp = Blueprint("inventario", __name__)

# Listas de valores permitidos, replicando los CHECK de las tablas.
CATEGORIAS = ["Firewall", "Switch", "Access Point", "Software", "Licencia", "Servicio", "Otro"]
TIPOS_PRODUCTO = ["Hardware", "Software", "Suscripcion", "Servicio"]
TIPOS_EQUIPO = ["Firewall", "Switch", "Access Point", "Servidor", "Otro"]
ESTADOS_EQUIPO = ["Operativo", "En mantenimiento", "Fuera de servicio", "En reemplazo"]
TIPOS_LICENCIA = ["Anual", "Multianual", "Perpetua", "Trial"]
ESTADOS_LICENCIA = ["Activa", "Por vencer", "Vencida", "Cancelada"]


# =====================================================================
#  PRODUCTOS
# =====================================================================

"""
   Función: productos
   Objetivo: Mostrar el catálogo de productos, con búsqueda por
             nombre, SKU o fabricante, y filtro opcional por
             categoría.
   Parámetros: No recibe directamente (lee 'q' y 'categoria' de la URL).
   Retorno: La plantilla productos.html con los productos encontrados.
"""
@bp.route("/productos")
@permiso_requerido("inventario.ver")
def productos():
    q = (request.args.get("q") or "").strip()
    categoria = (request.args.get("categoria") or "").strip()
    sql = ("SELECT p.id, p.sku, p.nombre, p.categoria, p.tipo, p.precio_lista, "
           "       p.stock, p.stock_minimo, p.activo, f.nombre AS fabricante "
           "FROM productos p JOIN fabricantes f ON f.id = p.fabricante_id WHERE 1=1 ")
    # JOIN normal (no LEFT): fabricante_id es NOT NULL, todo producto
    # tiene fabricante, asi que no hay riesgo de perder filas.
    params = []
    if q:
        sql += "AND (p.nombre LIKE ? OR p.sku LIKE ? OR f.nombre LIKE ?) "
        params += [f"%{q}%"] * 3
    if categoria:
        sql += "AND p.categoria = ? "
        params.append(categoria)
    sql += "ORDER BY p.nombre"
    return render_template("productos.html", active="productos",
                           productos=query_all(sql, params), buscar=q,
                           categoria=categoria, categorias=CATEGORIAS)
    # Nota: esta lista no pagina con OFFSET/FETCH como clientes o
    # empresas; se asume un catalogo de tamaño manejable.


"""
   Función: producto_nuevo
   Objetivo: Mostrar el formulario de alta de producto (GET) y
             procesar su creación (POST), validando que el SKU no
             esté repetido.
   Parámetros: No recibe directamente (lee el formulario).
   Retorno: En GET, formulario vacío. En POST correcto, redirige al
            catálogo.
"""
@bp.route("/productos/nuevo", methods=["GET", "POST"])
@permiso_requerido("inventario.crear")
def producto_nuevo():
    ctx = _ctx_producto()
    if request.method == "POST":
        d = _form_producto()
        error = _validar_producto(d, es_nuevo=True)
        if error:
            flash(error, "error")
            return render_template("producto_form.html", active="productos",
                                   titulo="Nuevo producto", producto=d, **ctx)
        nuevo_id = insertar(
            "INSERT INTO productos (fabricante_id, sku, nombre, categoria, tipo, "
            "descripcion, precio_lista, stock, stock_minimo) OUTPUT INSERTED.id "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [d["fabricante_id"], d["sku"], d["nombre"], d["categoria"], d["tipo"],
             d["descripcion"], d["precio_lista"], d["stock"], d["stock_minimo"]],
        )
        registrar_auditoria("productos", "INSERT", nuevo_id, datos_nuevos=d)
        flash("Producto creado.", "ok")
        return redirect(url_for("inventario.productos"))
    return render_template("producto_form.html", active="productos",
                           titulo="Nuevo producto", producto=None, **ctx)


"""
   Función: producto_editar
   Objetivo: Mostrar el formulario con los datos actuales de un
             producto (GET) y guardar sus modificaciones (POST). El
             stock NO se edita aquí: tiene su propia ruta dedicada
             (producto_stock) para dejar rastro de cada ajuste.
   Parámetros:
     - producto_id: identificador del producto a editar.
   Retorno: En GET, formulario con datos cargados. En POST correcto,
            redirige al catálogo.
"""
@bp.route("/productos/<int:producto_id>/editar", methods=["GET", "POST"])
@permiso_requerido("inventario.editar")
def producto_editar(producto_id):
    actual = query_one("SELECT * FROM productos WHERE id = ?", [producto_id])
    if actual is None:
        flash("El producto no existe.", "error")
        return redirect(url_for("inventario.productos"))
    ctx = _ctx_producto()
    if request.method == "POST":
        d = _form_producto()
        d["id"] = producto_id       # Se agrega para que _validar_producto excluya este mismo producto
        error = _validar_producto(d, es_nuevo=False)
        if error:
            flash(error, "error")
            return render_template("producto_form.html", active="productos",
                                   titulo="Editar producto", producto=d, **ctx)
        execute(
            "UPDATE productos SET fabricante_id=?, sku=?, nombre=?, categoria=?, tipo=?, "
            "descripcion=?, precio_lista=?, stock_minimo=?, updated_at=SYSDATETIME() "
            "WHERE id=?",
            [d["fabricante_id"], d["sku"], d["nombre"], d["categoria"], d["tipo"],
             d["descripcion"], d["precio_lista"], d["stock_minimo"], producto_id],
        )
        # OJO: este UPDATE no incluye la columna 'stock'. El stock solo
        # se cambia desde producto_stock(), para mantener el historial
        # de entradas y salidas separado del resto de los datos.
        registrar_auditoria("productos", "UPDATE", producto_id,
                            datos_anteriores={"sku": actual["sku"],
                                              "precio_lista": float(actual["precio_lista"])},
                            datos_nuevos={"sku": d["sku"], "precio_lista": d["precio_lista"]})
        flash("Producto actualizado.", "ok")
        return redirect(url_for("inventario.productos"))
    return render_template("producto_form.html", active="productos",
                           titulo=f"Editar {actual['sku']}", producto=actual, **ctx)


"""
   Función: producto_stock
   Objetivo: Ajustar la cantidad en existencia de un producto, ya sea
             sumando (entrada) o restando (salida) unidades, validando
             que el resultado nunca quede negativo.
   Parámetros:
     - producto_id: identificador del producto cuyo stock se ajusta.
   Retorno: Redirige siempre al catálogo, con un mensaje del resultado.
"""
@bp.route("/productos/<int:producto_id>/stock", methods=["POST"])
@permiso_requerido("inventario.editar")
def producto_stock(producto_id):
    """Ajuste de inventario: entrada (+) o salida (-) de unidades."""
    actual = query_one("SELECT id, sku, stock FROM productos WHERE id = ?", [producto_id])
    if actual is None:
        flash("El producto no existe.", "error")
        return redirect(url_for("inventario.productos"))
    try:
        ajuste = int(request.form.get("ajuste") or 0)     # Puede ser positivo (entrada) o negativo (salida)
    except ValueError:
        ajuste = 0                                          # Si escribieron texto invalido, no ajusta nada
    motivo = (request.form.get("motivo") or "").strip() or "Ajuste manual"
    nuevo_stock = actual["stock"] + ajuste                  # Suma directa: el ajuste ya trae su signo
    if ajuste == 0:
        flash("Indica una cantidad distinta de cero.", "error")
    elif nuevo_stock < 0:
        # Validacion de negocio en la aplicacion: el stock nunca puede
        # ser negativo. La base de datos NO tiene un CHECK para esto
        # (la columna admite cualquier entero), asi que esta es la
        # UNICA barrera que lo impide.
        flash(f"No puedes sacar {abs(ajuste)} unidades: solo hay {actual['stock']}.", "error")
    else:
        execute("UPDATE productos SET stock=?, updated_at=SYSDATETIME() WHERE id=?",
                [nuevo_stock, producto_id])
        registrar_auditoria("productos", "UPDATE", producto_id,
                            datos_anteriores={"stock": actual["stock"]},
                            datos_nuevos={"stock": nuevo_stock, "ajuste": ajuste,
                                          "motivo": motivo})
        # Se guarda el ajuste y el motivo en la auditoria, ademas del
        # stock antes y despues: asi queda un historial completo de
        # POR QUE cambio el inventario, no solo el numero final.
        flash(f"Stock de {actual['sku']}: {actual['stock']} → {nuevo_stock}.", "ok")
    return redirect(url_for("inventario.productos"))


"""
   Función: producto_estado
   Objetivo: Alternar la bandera 'activo' de un producto (borrado
             lógico).
   Parámetros:
     - producto_id: identificador del producto cuyo estado se cambia.
   Retorno: Redirige al catálogo, con un mensaje.
"""
@bp.route("/productos/<int:producto_id>/estado", methods=["POST"])
@permiso_requerido("inventario.eliminar")
def producto_estado(producto_id):
    actual = query_one("SELECT id, activo FROM productos WHERE id = ?", [producto_id])
    if actual is None:
        flash("El producto no existe.", "error")
    else:
        nuevo = 0 if actual["activo"] else 1
        execute("UPDATE productos SET activo=?, updated_at=SYSDATETIME() WHERE id=?",
                [nuevo, producto_id])
        registrar_auditoria("productos", "UPDATE", producto_id,
                            datos_anteriores={"activo": bool(actual["activo"])},
                            datos_nuevos={"activo": bool(nuevo)})
        flash(f"Producto {'activado' if nuevo else 'desactivado'}.", "ok")
    return redirect(url_for("inventario.productos"))


"""
   Función: _ctx_producto
   Objetivo: Reunir la lista de fabricantes activos y los catálogos
             de categoría y tipo para el formulario de producto.
   Parámetros: No recibe.
   Retorno: Diccionario con fabricantes, categorias y tipos.
"""
def _ctx_producto():
    return {"fabricantes": query_all(
        "SELECT id, nombre FROM fabricantes WHERE activo = 1 ORDER BY nombre"),
        "categorias": CATEGORIAS, "tipos": TIPOS_PRODUCTO}


"""
   Función: _form_producto
   Objetivo: Leer y limpiar los campos del formulario de producto.
   Parámetros: No recibe (lee de request.form).
   Retorno: Diccionario con los ocho campos de productos.
"""
def _form_producto():
    g = lambda k: (request.form.get(k) or "").strip()  # noqa: E731
    return {
        "fabricante_id": int(g("fabricante_id") or 0) or None,
        "sku": g("sku"), "nombre": g("nombre"),
        "categoria": g("categoria") if g("categoria") in CATEGORIAS else "Otro",
        "tipo": g("tipo") if g("tipo") in TIPOS_PRODUCTO else "Hardware",
        "descripcion": g("descripcion"),
        "precio_lista": float(g("precio_lista") or 0),
        "stock": int(g("stock") or 0),
        "stock_minimo": int(g("stock_minimo") or 0),
    }


"""
   Función: _validar_producto
   Objetivo: Verificar que los datos de un producto cumplan las
             reglas antes de guardarlos: campos obligatorios y SKU
             único.
   Parámetros:
     - d: diccionario con los datos del formulario.
     - es_nuevo: True si es alta, False si es edición (no cambia la
                 lógica aquí, pero mantiene la firma consistente con
                 _validar_usuario de admin.py).
   Retorno: Texto con el mensaje de error, o None si todo es válido.
"""
def _validar_producto(d, es_nuevo):
    if not d["fabricante_id"] or not d["sku"] or not d["nombre"]:
        return "Fabricante, SKU y nombre son obligatorios."
    dup = query_one("SELECT id FROM productos WHERE sku = ? AND id <> ?",
                    [d["sku"], d.get("id", 0)])
    # AND id <> ? excluye al propio producto de la busqueda al editar;
    # d.get("id", 0) devuelve 0 si es un alta, que nunca coincide con
    # un id real.
    if dup:
        return "Ya existe un producto con ese SKU."
    return None


# =====================================================================
#  EQUIPOS
# =====================================================================

"""
   Función: equipos
   Objetivo: Mostrar el listado de equipos instalados, con búsqueda
             por número de serie, hostname o cliente, y filtros
             opcionales por tipo y estado.
   Parámetros: No recibe directamente (lee 'q', 'tipo' y 'estado' de
               la URL).
   Retorno: La plantilla equipos.html con los equipos encontrados.
"""
@bp.route("/equipos")
@permiso_requerido("inventario.ver")
def equipos():
    q = (request.args.get("q") or "").strip()
    tipo = (request.args.get("tipo") or "").strip()
    estado = (request.args.get("estado") or "").strip()
    sql = ("SELECT eq.id, eq.tipo, eq.numero_serie, eq.hostname, eq.ubicacion, "
           "       eq.estado, eq.fecha_instalacion, e.nombre AS cliente, "
           "       p.nombre AS producto "
           "FROM equipos eq JOIN clientes c ON c.id = eq.cliente_id "     # JOIN: cliente_id es NOT NULL
           "JOIN empresas e ON e.id = c.empresa_id "
           "LEFT JOIN productos p ON p.id = eq.producto_id WHERE 1=1 ")
    # LEFT JOIN a productos: producto_id admite NULL (un equipo puede
    # no tener un modelo de catalogo asociado).
    params = []
    if q:
        sql += "AND (eq.numero_serie LIKE ? OR eq.hostname LIKE ? OR e.nombre LIKE ?) "
        params += [f"%{q}%"] * 3
    if tipo:
        sql += "AND eq.tipo = ? "
        params.append(tipo)
    if estado:
        sql += "AND eq.estado = ? "
        params.append(estado)
    sql += "ORDER BY e.nombre, eq.hostname"
    return render_template("equipos.html", active="equipos",
                           equipos=query_all(sql, params), buscar=q, tipo=tipo,
                           estado=estado, tipos=TIPOS_EQUIPO, estados=ESTADOS_EQUIPO)


"""
   Función: equipo_nuevo
   Objetivo: Mostrar el formulario de alta de equipo (GET) y procesar
             su creación (POST).
   Parámetros: No recibe directamente (lee el formulario).
   Retorno: En GET, formulario vacío. En POST correcto, redirige al
            listado.
"""
@bp.route("/equipos/nuevo", methods=["GET", "POST"])
@permiso_requerido("inventario.crear")
def equipo_nuevo():
    ctx = _ctx_equipo()
    if request.method == "POST":
        d = _form_equipo()
        if not d["cliente_id"]:
            flash("Selecciona el cliente dueño del equipo.", "error")
            return render_template("equipo_form.html", active="equipos",
                                   titulo="Nuevo equipo", equipo=d, **ctx)
        nuevo_id = insertar(
            "INSERT INTO equipos (cliente_id, producto_id, tipo, numero_serie, hostname, "
            "ubicacion, estado, fecha_instalacion) OUTPUT INSERTED.id "
            "VALUES (?,?,?,?,?,?,?,?)",
            [d["cliente_id"], d["producto_id"], d["tipo"], d["numero_serie"] or None,
             d["hostname"], d["ubicacion"], d["estado"], d["fecha_instalacion"] or None],
        )
        registrar_auditoria("equipos", "INSERT", nuevo_id, datos_nuevos=d)
        flash("Equipo registrado.", "ok")
        return redirect(url_for("inventario.equipos"))
    return render_template("equipo_form.html", active="equipos",
                           titulo="Nuevo equipo", equipo=None, **ctx)


"""
   Función: equipo_editar
   Objetivo: Mostrar el formulario con los datos actuales de un
             equipo (GET) y guardar sus modificaciones (POST).
   Parámetros:
     - equipo_id: identificador del equipo a editar.
   Retorno: En GET, formulario con datos cargados (fecha convertida a
            texto). En POST correcto, redirige al listado.
"""
@bp.route("/equipos/<int:equipo_id>/editar", methods=["GET", "POST"])
@permiso_requerido("inventario.editar")
def equipo_editar(equipo_id):
    actual = query_one("SELECT * FROM equipos WHERE id = ?", [equipo_id])
    if actual is None:
        flash("El equipo no existe.", "error")
        return redirect(url_for("inventario.equipos"))
    ctx = _ctx_equipo()
    if request.method == "POST":
        d = _form_equipo()
        if not d["cliente_id"]:
            flash("Selecciona el cliente dueño del equipo.", "error")
            return render_template("equipo_form.html", active="equipos",
                                   titulo="Editar equipo", equipo=d, **ctx)
        execute(
            "UPDATE equipos SET cliente_id=?, producto_id=?, tipo=?, numero_serie=?, "
            "hostname=?, ubicacion=?, estado=?, fecha_instalacion=?, "
            "updated_at=SYSDATETIME() WHERE id=?",
            [d["cliente_id"], d["producto_id"], d["tipo"], d["numero_serie"] or None,
             d["hostname"], d["ubicacion"], d["estado"], d["fecha_instalacion"] or None,
             equipo_id],
        )
        registrar_auditoria("equipos", "UPDATE", equipo_id,
                            datos_anteriores={"estado": actual["estado"],
                                              "hostname": actual["hostname"]},
                            datos_nuevos={"estado": d["estado"], "hostname": d["hostname"]})
        flash("Equipo actualizado.", "ok")
        return redirect(url_for("inventario.equipos"))
    cab = dict(actual)
    cab["fecha_instalacion"] = (actual["fecha_instalacion"].isoformat()
                                if actual["fecha_instalacion"] else "")
    # Convierte la fecha (objeto date de Python) a texto "AAAA-MM-DD"
    # para que el <input type="date"> del formulario la muestre bien.
    return render_template("equipo_form.html", active="equipos",
                           titulo="Editar equipo", equipo=cab, **ctx)


"""
   Función: _ctx_equipo
   Objetivo: Reunir las listas de clientes y productos activos para
             los desplegables del formulario de equipo.
   Parámetros: No recibe.
   Retorno: Diccionario con clientes_lista, productos_lista, tipos y
            estados.
"""
def _ctx_equipo():
    return {
        "clientes_lista": query_all(
            "SELECT c.id, e.nombre FROM clientes c JOIN empresas e ON e.id = c.empresa_id "
            "ORDER BY e.nombre"),
        "productos_lista": query_all(
            "SELECT id, sku, nombre FROM productos WHERE activo = 1 ORDER BY nombre"),
        "tipos": TIPOS_EQUIPO, "estados": ESTADOS_EQUIPO,
    }


"""
   Función: _form_equipo
   Objetivo: Leer y limpiar los campos del formulario de equipo.
   Parámetros: No recibe (lee de request.form).
   Retorno: Diccionario con los siete campos de equipos.
"""
def _form_equipo():
    g = lambda k: (request.form.get(k) or "").strip()  # noqa: E731
    return {
        "cliente_id": int(g("cliente_id") or 0) or None,
        "producto_id": int(g("producto_id") or 0) or None,   # Puede quedar None: el modelo es opcional
        "tipo": g("tipo") if g("tipo") in TIPOS_EQUIPO else "Otro",
        "numero_serie": g("numero_serie"), "hostname": g("hostname"),
        "ubicacion": g("ubicacion"),
        "estado": g("estado") if g("estado") in ESTADOS_EQUIPO else "Operativo",
        "fecha_instalacion": g("fecha_instalacion"),
    }


# =====================================================================
#  LICENCIAS
# =====================================================================

"""
   Función: licencias
   Objetivo: Mostrar el listado de licencias, con búsqueda por
             producto, cliente o clave, filtro opcional por estado, y
             el cálculo de días restantes hasta el vencimiento.
   Parámetros: No recibe directamente (lee 'q' y 'estado' de la URL).
   Retorno: La plantilla licencias.html con las licencias encontradas.
"""
@bp.route("/licencias")
@permiso_requerido("inventario.ver")
def licencias():
    q = (request.args.get("q") or "").strip()
    estado = (request.args.get("estado") or "").strip()
    sql = ("SELECT l.id, l.clave, l.tipo, l.fecha_inicio, l.fecha_fin, l.estado, "
           "       p.nombre AS producto, p.sku, e.nombre AS cliente, "
           "       DATEDIFF(DAY, GETDATE(), l.fecha_fin) AS dias_restantes "
           "FROM licencias l JOIN productos p ON p.id = l.producto_id "
           "JOIN clientes c ON c.id = l.cliente_id "
           "JOIN empresas e ON e.id = c.empresa_id WHERE 1=1 ")
    # DATEDIFF(DAY, GETDATE(), fecha_fin) calcula, EN EL MOTOR, cuantos
    # dias faltan para el vencimiento. Si el resultado es negativo, la
    # licencia ya vencio; la plantilla usa ese numero para la alerta.
    params = []
    if q:
        sql += "AND (p.nombre LIKE ? OR e.nombre LIKE ? OR l.clave LIKE ?) "
        params += [f"%{q}%"] * 3
    if estado:
        sql += "AND l.estado = ? "
        params.append(estado)
    sql += "ORDER BY l.fecha_fin"     # Las que vencen antes aparecen primero
    return render_template("licencias.html", active="licencias",
                           licencias=query_all(sql, params), buscar=q,
                           estado=estado, estados=ESTADOS_LICENCIA)


"""
   Función: licencia_nueva
   Objetivo: Mostrar el formulario de alta de licencia (GET), con
             valores por defecto sugeridos (hoy como inicio, un año
             después como fin), y procesar su creación (POST).
   Parámetros: No recibe directamente (lee el formulario).
   Retorno: En GET, formulario con valores sugeridos. En POST
            correcto, redirige al listado.
"""
@bp.route("/licencias/nueva", methods=["GET", "POST"])
@permiso_requerido("inventario.crear")
def licencia_nueva():
    ctx = _ctx_licencia()
    if request.method == "POST":
        d = _form_licencia()
        if not d["producto_id"] or not d["cliente_id"] or not d["fecha_inicio"]:
            flash("Producto, cliente y fecha de inicio son obligatorios.", "error")
            return render_template("licencia_form.html", active="licencias",
                                   titulo="Nueva licencia", licencia=d, **ctx)
        nuevo_id = insertar(
            "INSERT INTO licencias (producto_id, cliente_id, clave, tipo, fecha_inicio, "
            "fecha_fin, estado) OUTPUT INSERTED.id VALUES (?,?,?,?,?,?,?)",
            [d["producto_id"], d["cliente_id"], d["clave"] or None, d["tipo"],
             d["fecha_inicio"], d["fecha_fin"] or None, d["estado"]],
        )
        registrar_auditoria("licencias", "INSERT", nuevo_id, datos_nuevos=d)
        flash("Licencia registrada.", "ok")
        return redirect(url_for("inventario.licencias"))

    hoy = datetime.date.today()
    licencia = {"fecha_inicio": hoy.isoformat(),
                "fecha_fin": hoy.replace(year=hoy.year + 1).isoformat(),
                # hoy.replace(year=hoy.year + 1): mismo dia y mes, un año
                # despues. Es una sugerencia de "licencia Anual" tipica.
                "tipo": "Anual", "estado": "Activa"}
    return render_template("licencia_form.html", active="licencias",
                           titulo="Nueva licencia", licencia=licencia, **ctx)


"""
   Función: licencia_editar
   Objetivo: Mostrar el formulario con los datos actuales de una
             licencia (GET) y guardar sus modificaciones (POST).
   Parámetros:
     - licencia_id: identificador de la licencia a editar.
   Retorno: En GET, formulario con datos cargados (fechas convertidas
            a texto). En POST correcto, redirige al listado.
"""
@bp.route("/licencias/<int:licencia_id>/editar", methods=["GET", "POST"])
@permiso_requerido("inventario.editar")
def licencia_editar(licencia_id):
    actual = query_one("SELECT * FROM licencias WHERE id = ?", [licencia_id])
    if actual is None:
        flash("La licencia no existe.", "error")
        return redirect(url_for("inventario.licencias"))
    ctx = _ctx_licencia()
    if request.method == "POST":
        d = _form_licencia()
        if not d["producto_id"] or not d["cliente_id"] or not d["fecha_inicio"]:
            flash("Producto, cliente y fecha de inicio son obligatorios.", "error")
            return render_template("licencia_form.html", active="licencias",
                                   titulo="Editar licencia", licencia=d, **ctx)
        execute(
            "UPDATE licencias SET producto_id=?, cliente_id=?, clave=?, tipo=?, "
            "fecha_inicio=?, fecha_fin=?, estado=?, updated_at=SYSDATETIME() WHERE id=?",
            [d["producto_id"], d["cliente_id"], d["clave"] or None, d["tipo"],
             d["fecha_inicio"], d["fecha_fin"] or None, d["estado"], licencia_id],
        )
        registrar_auditoria("licencias", "UPDATE", licencia_id,
                            datos_anteriores={"estado": actual["estado"]},
                            datos_nuevos={"estado": d["estado"]})
        flash("Licencia actualizada.", "ok")
        return redirect(url_for("inventario.licencias"))
    cab = dict(actual)
    cab["fecha_inicio"] = actual["fecha_inicio"].isoformat() if actual["fecha_inicio"] else ""
    cab["fecha_fin"] = actual["fecha_fin"].isoformat() if actual["fecha_fin"] else ""
    return render_template("licencia_form.html", active="licencias",
                           titulo="Editar licencia", licencia=cab, **ctx)


"""
   Función: _ctx_licencia
   Objetivo: Reunir las listas de productos licenciables (suscripción,
             software o categoría Licencia) y clientes para los
             desplegables del formulario de licencia.
   Parámetros: No recibe.
   Retorno: Diccionario con productos_lista, clientes_lista, tipos y
            estados.
"""
def _ctx_licencia():
    return {
        "productos_lista": query_all(
            "SELECT id, sku, nombre FROM productos "
            "WHERE tipo IN ('Suscripcion','Software') OR categoria = 'Licencia' "
            "ORDER BY nombre"),
        # Filtra el catalogo: no tiene sentido licenciar un firewall
        # fisico, asi que solo se ofrecen productos que son software,
        # suscripcion, o estan categorizados como Licencia.
        "clientes_lista": query_all(
            "SELECT c.id, e.nombre FROM clientes c JOIN empresas e ON e.id = c.empresa_id "
            "ORDER BY e.nombre"),
        "tipos": TIPOS_LICENCIA, "estados": ESTADOS_LICENCIA,
    }


"""
   Función: _form_licencia
   Objetivo: Leer y limpiar los campos del formulario de licencia.
   Parámetros: No recibe (lee de request.form).
   Retorno: Diccionario con los seis campos de licencias.
"""
def _form_licencia():
    g = lambda k: (request.form.get(k) or "").strip()  # noqa: E731
    return {
        "producto_id": int(g("producto_id") or 0) or None,
        "cliente_id": int(g("cliente_id") or 0) or None,
        "clave": g("clave"),
        "tipo": g("tipo") if g("tipo") in TIPOS_LICENCIA else "Anual",
        "fecha_inicio": g("fecha_inicio"), "fecha_fin": g("fecha_fin"),
        "estado": g("estado") if g("estado") in ESTADOS_LICENCIA else "Activa",
    }
