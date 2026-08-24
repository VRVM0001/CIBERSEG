"""
=========================================================================
 Módulo: ventas.py (app/routes/ventas.py)
 Módulo Ventas (Fase 3): Cotizaciones (con líneas de productos),
 Facturas y Contratos.

 Flujo comercial:
   1. Se crea una COTIZACIÓN con líneas de productos (cantidad, precio, descuento).
      El sistema calcula subtotal, ITBIS (18%) y total.
   2. La cotización cambia de estado: Borrador → Enviada → Aprobada/Rechazada.
   3. Una cotización Aprobada se puede FACTURAR con un clic (genera la factura).
   4. La factura se marca como Pagada / Vencida / Anulada.
   5. Los CONTRATOS (soporte, mantenimiento, licenciamiento) se gestionan aparte.

 Este es el blueprint MAS IMPORTANTE para la defensa: contiene las dos
 funcionalidades robustas de la matriz de trazabilidad (cotizacion_nueva,
 que demuestra la relacion cabecera-detalle con trigger y procedimiento,
 y cotizacion_facturar, que demuestra reglas de negocio con su
 equivalente transaccional ACID en la base de datos).
=========================================================================
"""
import datetime      # Para calcular fechas: hoy, validez de la cotizacion, vencimiento de la factura

from flask import Blueprint, render_template, request, redirect, url_for, flash

from ..db import query_all, query_one, execute, insertar
from ..seguridad import permiso_requerido, registrar_auditoria

bp = Blueprint("ventas", __name__)
# Crea el blueprint "ventas". Sus rutas se invocan despues como
# url_for("ventas.cotizaciones"), url_for("ventas.facturas"), etc.

"""
   Función: obtener_itbis
   Objetivo: Devolver el porcentaje de impuesto vigente, leyéndolo de
             la tabla de configuración del sistema (clave 'itbis_pct'),
             con un valor de respaldo si algo falla al consultarla.
   Parámetros: No recibe.
   Retorno: Número decimal (float) entre 0 y 1. Por ejemplo, 0.18
            representa un 18% de ITBIS.
"""
def obtener_itbis():
    """Porcentaje de impuesto desde configuración (por defecto 18%)."""
    from ..configuracion import leer_config
    # Import DENTRO de la funcion, no al inicio del archivo, para
    # evitar un import circular: configuracion.py tambien depende de
    # db.py, y estructurarlo asi evita problemas de orden de carga.
    try:
        return int(leer_config()["itbis_pct"]) / 100
        # leer_config() devuelve todos los parametros como TEXTO
        # (la columna configuracion.valor es VARCHAR). Se convierte
        # primero a entero ("18" -> 18) y luego se divide entre 100
        # para obtener la proporcion (18 -> 0.18) que usan los calculos.
    except Exception:
        return 0.18       # Respaldo: si la tabla no existiera aun, o el valor no fuera un numero valido
# Listas de valores permitidos, replicando en Python los CHECK de las
# tablas. Sirven para llenar los desplegables de los formularios y
# para validar en el servidor antes de que la consulta llegue al motor.
ESTADOS_COT = ["Borrador", "Enviada", "Aprobada", "Rechazada", "Vencida"]
ESTADOS_FAC = ["Pendiente", "Pagada", "Vencida", "Anulada"]
TIPOS_CONTRATO = ["Soporte", "Mantenimiento", "Licenciamiento", "Servicios Profesionales"]
ESTADOS_CONTRATO = ["Vigente", "Por vencer", "Vencido", "Cancelado"]


# =====================================================================
#  COTIZACIONES
# =====================================================================

"""
   Función: cotizaciones
   Objetivo: Mostrar el listado paginado de cotizaciones, con
             búsqueda por número o cliente, filtro opcional por
             estado, y el conteo de cuántas líneas y facturas tiene
             cada una.
   Parámetros: No recibe directamente (lee 'q', 'estado' y 'pagina'
               de la URL).
   Retorno: La plantilla cotizaciones.html con las cotizaciones de la
            página actual.
"""
@bp.route("/cotizaciones")
@permiso_requerido("ventas.ver")
def cotizaciones():
    q = (request.args.get("q") or "").strip()
    estado = (request.args.get("estado") or "").strip()
    sql = ("SELECT co.id, co.numero, co.fecha, co.fecha_validez, co.estado, co.total, "
           "       co.moneda, e.nombre AS cliente, "
           "       (SELECT COUNT(*) FROM detalle_cotizacion d WHERE d.cotizacion_id = co.id) AS n_lineas, "
           "       (SELECT COUNT(*) FROM facturas f WHERE f.cotizacion_id = co.id) AS n_facturas "
           "FROM cotizaciones co JOIN clientes c ON c.id = co.cliente_id "
           "JOIN empresas e ON e.id = c.empresa_id WHERE 1=1 ")
    # Dos subconsultas correlacionadas: por cada cotizacion, cuentan sus
    # lineas de detalle y si ya tiene factura generada. Se resuelven en
    # la misma consulta principal, sin necesidad de un JOIN que
    # multiplicaria las filas del resultado.
    params = []
    if q:
        sql += "AND (co.numero LIKE ? OR e.nombre LIKE ?) "
        params += [f"%{q}%", f"%{q}%"]
    if estado:
        sql += "AND co.estado = ? "
        params.append(estado)
    pagina = max(1, int(request.args.get("pagina", 1) or 1))
    sql += "ORDER BY co.fecha DESC, co.id DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
    # El ORDER BY es obligatorio: OFFSET/FETCH exige un orden explicito
    # para saber que significa "saltar las primeras N filas".
    params += [(pagina - 1) * 15, 15]
    filas = query_all(sql, params)
    return render_template("cotizaciones.html", active="cotizaciones",
                           cotizaciones=filas, buscar=q, estado=estado,
                           estados=ESTADOS_COT, pagina=pagina, hay_mas=len(filas) == 15)


"""
   Función: cotizacion_nueva
   Objetivo: Mostrar el formulario de alta de cotización (GET, con
             fechas sugeridas) y procesar su creación (POST): genera
             el número correlativo, inserta la cabecera y todas sus
             líneas de producto. FUNCIONALIDAD 5 de la matriz de
             trazabilidad (robusta): demuestra la relación
             cabecera-detalle y la delegación del cálculo de totales
             en un trigger de la base de datos.
   Parámetros: No recibe directamente (lee el formulario a través del
               auxiliar _leer_cotizacion()).
   Retorno:
     - GET: el formulario vacío, con fecha de hoy y validez sugerida
       a 30 días.
     - POST inválido: el mismo formulario repintado con el mensaje de
       error y lo que el usuario ya había escrito.
     - POST válido: un redirect() a la vista de la cotización recién
       creada (no al listado).
"""
@bp.route("/cotizaciones/nueva", methods=["GET", "POST"])
@permiso_requerido("ventas.crear")
def cotizacion_nueva():
    # ---------- Contexto para los desplegables (siempre se calcula) ----------
    ctx = _ctx_cotizacion()
    # Trae clientes, ejecutivos, productos (con su precio de catalogo)
    # y el porcentaje de ITBIS vigente. Se pide ANTES del if porque
    # hace falta tanto en el GET como si el POST falla la validacion.

    if request.method == "POST":
        # ---------- Lectura, validación y cálculo provisional ----------
        cab, lineas, error = _leer_cotizacion()
        # _leer_cotizacion() hace TODO el trabajo pesado: lee la
        # cabecera y las lineas del formulario, valida que haya cliente
        # y al menos una linea, y calcula subtotal/impuesto/total
        # PROVISIONALES (los que despues sobrescribira el trigger).

        if error:
            flash(error, "error")
            return render_template("cotizacion_form.html", active="cotizaciones",
                                   titulo="Nueva cotización", cot=cab, lineas=lineas, **ctx)
            # Se repinta el formulario con 'cab' y 'lineas' tal como el
            # usuario los habia escrito, para que no pierda su trabajo.

        # ---------- Generación del número correlativo ----------
        sig = query_one("SELECT ISNULL(MAX(id),0)+1 AS n FROM cotizaciones")["n"]
        # ISNULL(MAX(id),0)+1: si la tabla estuviera vacia, MAX(id) daria
        # NULL: ISNULL lo convierte en 0, y se le suma 1 para obtener 1.
        numero = f"COT-{datetime.date.today().year}-{sig:04d}"
        # {sig:04d} rellena con ceros a la izquierda hasta 4 digitos:
        # COT-2026-0001, COT-2026-0002, etc.

        # ---------- PRIMERA ESCRITURA: la cabecera ----------
        cot_id = insertar(
            "INSERT INTO cotizaciones (numero, cliente_id, ejecutivo_id, fecha, "
            "fecha_validez, estado, subtotal, impuesto, total, notas) "
            "OUTPUT INSERTED.id VALUES (?,?,?,?,?,?,?,?,?,?)",
            [numero, cab["cliente_id"], cab["ejecutivo_id"], cab["fecha"],
             cab["fecha_validez"] or None, cab["estado"], cab["subtotal"],
             cab["impuesto"], cab["total"], cab["notas"]],
        )
        # Los tres totales que se envian aqui (subtotal/impuesto/total)
        # SON PROVISIONALES: se calcularon en Python dentro de
        # _leer_cotizacion(). En cuanto se inserte la primera linea del
        # detalle (paso siguiente), el trigger trg_detalle_totales los
        # va a SOBRESCRIBIR con el valor definitivo. Se envian de todas
        # formas para que la fila quede completa desde el primer instante
        # (la columna no admite NULL).

        # ---------- SEGUNDA ESCRITURA (repetida N veces): el detalle ----------
        _guardar_lineas(cot_id, lineas)
        # Inserta una fila en detalle_cotizacion por cada linea de
        # producto. Cada INSERT dispara el trigger trg_detalle_totales,
        # que llama a sp_recalcular_totales_cotizacion y actualiza
        # subtotal/impuesto/total de la cabecera con el valor real,
        # leyendo el porcentaje de ITBIS directamente de la tabla
        # configuracion. Si hay 3 lineas, el trigger se ejecuta 3 veces.

        registrar_auditoria("cotizaciones", "INSERT", cot_id,
                            datos_nuevos={**cab, "numero": numero, "lineas": len(lineas)})
        # {**cab, ...}: desempaqueta el diccionario de la cabecera y le
        # agrega el numero y la cantidad de lineas, todo en un solo
        # diccionario para la auditoria.

        flash(f"Cotización {numero} creada.", "ok")
        return redirect(url_for("ventas.cotizacion_ver", cot_id=cot_id))
        # Redirige a la VISTA de la cotizacion (no al listado): asi el
        # usuario ve de inmediato los totales YA recalculados por el
        # trigger, confirmando que el proceso funciono de punta a punta.

    # ---------- Caso GET: formulario vacío con sugerencias ----------
    hoy = datetime.date.today()
    cab = {"fecha": hoy.isoformat(),
           "fecha_validez": (hoy + datetime.timedelta(days=30)).isoformat(),
           # Sugerencia: la cotizacion es valida por 30 dias desde hoy.
           # El usuario puede cambiar esta fecha si lo necesita.
           "estado": "Borrador"}
    return render_template("cotizacion_form.html", active="cotizaciones",
                           titulo="Nueva cotización", cot=cab, lineas=[], **ctx)


"""
   Función: cotizacion_ver
   Objetivo: Mostrar el detalle completo de una cotización: su
             cabecera, todas sus líneas de producto, y si ya tiene
             una factura generada (para decidir si mostrar el botón
             Facturar en la plantilla).
   Parámetros:
     - cot_id: identificador de la cotización a mostrar.
   Retorno: La plantilla cotizacion_ver.html con la cotización, sus
            líneas y la factura asociada (si existe, o None).
"""
@bp.route("/cotizaciones/<int:cot_id>")
@permiso_requerido("ventas.ver")
def cotizacion_ver(cot_id):
    cot = query_one(
        "SELECT co.*, e.nombre AS cliente, u.nombre AS ejecutivo "
        "FROM cotizaciones co JOIN clientes c ON c.id = co.cliente_id "
        "JOIN empresas e ON e.id = c.empresa_id "
        "LEFT JOIN usuarios u ON u.id = co.ejecutivo_id WHERE co.id = ?", [cot_id])
    if cot is None:
        flash("La cotización no existe.", "error")
        return redirect(url_for("ventas.cotizaciones"))
    lineas = query_all(
        "SELECT d.*, p.nombre AS producto, p.sku FROM detalle_cotizacion d "
        "JOIN productos p ON p.id = d.producto_id WHERE d.cotizacion_id = ? ORDER BY d.id",
        [cot_id])
    factura = query_one(
        "SELECT id, numero, estado FROM facturas WHERE cotizacion_id = ?", [cot_id])
    # Se busca si ya existe factura: la plantilla usa este dato (None
    # o con datos) para mostrar u ocultar el boton "Facturar".
    return render_template("cotizacion_ver.html", active="cotizaciones",
                           cot=cot, lineas=lineas, factura=factura, estados=ESTADOS_COT)


"""
   Función: cotizacion_editar
   Objetivo: Mostrar el formulario con los datos actuales de una
             cotización (GET) y guardar sus modificaciones (POST),
             reemplazando por completo el detalle anterior (se borra
             y se vuelve a insertar) para simplificar la lógica de
             edición de líneas.
   Parámetros:
     - cot_id: identificador de la cotización a editar.
   Retorno: En GET, formulario con datos cargados. En POST correcto,
            redirige a la vista de la cotización.
"""
@bp.route("/cotizaciones/<int:cot_id>/editar", methods=["GET", "POST"])
@permiso_requerido("ventas.editar")
def cotizacion_editar(cot_id):
    actual = query_one("SELECT * FROM cotizaciones WHERE id = ?", [cot_id])
    if actual is None:
        flash("La cotización no existe.", "error")
        return redirect(url_for("ventas.cotizaciones"))
    ctx = _ctx_cotizacion()
    if request.method == "POST":
        cab, lineas, error = _leer_cotizacion()
        if error:
            flash(error, "error")
            return render_template("cotizacion_form.html", active="cotizaciones",
                                   titulo=f"Editar {actual['numero']}",
                                   cot={**cab, "id": cot_id}, lineas=lineas, **ctx)
        execute(
            "UPDATE cotizaciones SET cliente_id=?, ejecutivo_id=?, fecha=?, "
            "fecha_validez=?, estado=?, subtotal=?, impuesto=?, total=?, notas=?, "
            "updated_at=SYSDATETIME() WHERE id=?",
            [cab["cliente_id"], cab["ejecutivo_id"], cab["fecha"],
             cab["fecha_validez"] or None, cab["estado"], cab["subtotal"],
             cab["impuesto"], cab["total"], cab["notas"], cot_id],
        )
        execute("DELETE FROM detalle_cotizacion WHERE cotizacion_id = ?", [cot_id])
        # Estrategia "borrar y reinsertar": en vez de comparar linea por
        # linea cuales cambiaron, se agregaron o se quitaron, se
        # elimina TODO el detalle anterior de un solo golpe...
        _guardar_lineas(cot_id, lineas)
        # ...y se inserta de nuevo el detalle completo tal como llego
        # del formulario. Es mas simple de programar, aunque el DELETE
        # y cada INSERT disparan por separado el trigger de totales.
        registrar_auditoria("cotizaciones", "UPDATE", cot_id,
                            datos_anteriores={"total": float(actual["total"]),
                                              "estado": actual["estado"]},
                            datos_nuevos={"total": cab["total"], "estado": cab["estado"],
                                          "lineas": len(lineas)})
        flash("Cotización actualizada.", "ok")
        return redirect(url_for("ventas.cotizacion_ver", cot_id=cot_id))
    lineas = query_all(
        "SELECT d.producto_id, d.cantidad, d.precio_unitario, d.descuento_pct, d.subtotal "
        "FROM detalle_cotizacion d WHERE d.cotizacion_id = ? ORDER BY d.id", [cot_id])
    cab = dict(actual)
    cab["fecha"] = actual["fecha"].isoformat() if actual["fecha"] else ""
    cab["fecha_validez"] = actual["fecha_validez"].isoformat() if actual["fecha_validez"] else ""
    return render_template("cotizacion_form.html", active="cotizaciones",
                           titulo=f"Editar {actual['numero']}", cot=cab,
                           lineas=lineas, **ctx)


"""
   Función: cotizacion_estado
   Objetivo: Cambiar el estado de una cotización, validando que el
             nuevo estado esté dentro de los permitidos.
   Parámetros:
     - cot_id: identificador de la cotización.
   Retorno: Redirige a la vista de la cotización, con un mensaje.
"""
@bp.route("/cotizaciones/<int:cot_id>/estado", methods=["POST"])
@permiso_requerido("ventas.editar")
def cotizacion_estado(cot_id):
    nuevo = request.form.get("estado")
    actual = query_one("SELECT id, numero, estado FROM cotizaciones WHERE id = ?", [cot_id])
    if actual is None or nuevo not in ESTADOS_COT:
        flash("Operación inválida.", "error")
    else:
        execute("UPDATE cotizaciones SET estado=?, updated_at=SYSDATETIME() WHERE id=?",
                [nuevo, cot_id])
        registrar_auditoria("cotizaciones", "UPDATE", cot_id,
                            datos_anteriores={"estado": actual["estado"]},
                            datos_nuevos={"estado": nuevo})
        flash(f"Cotización {actual['numero']} marcada como {nuevo}.", "ok")
    return redirect(url_for("ventas.cotizacion_ver", cot_id=cot_id))


"""
   Función: cotizacion_facturar
   Objetivo: Convertir una cotización Aprobada en una factura,
             copiando el cliente y los montos, tras validar que la
             cotización exista, esté en el estado correcto y no
             tenga ya una factura generada. FUNCIONALIDAD 6 de la
             matriz de trazabilidad (robusta): aplica tres reglas de
             negocio antes de escribir y tiene su equivalente
             transaccional en la base de datos (sp_aprobar_y_facturar,
             con BEGIN TRANSACTION / COMMIT / ROLLBACK y WITH (UPDLOCK)
             para evitar que dos usuarios facturen la misma cotización
             a la vez).
   Parámetros:
     - cot_id: identificador de la cotización a facturar (llega desde
               la URL, convertido a entero por Flask).
   Retorno: Si alguna validación falla, redirige a la vista de la
            cotización (o al listado, si ni siquiera existe). Si todo
            sale bien, redirige al listado de facturas.
"""
@bp.route("/cotizaciones/<int:cot_id>/facturar", methods=["POST"])
# methods=["POST"] SIN "GET": no existe formulario para esta accion,
# solo se llega aqui enviando el boton "Facturar" desde cotizacion_ver.
# Es una proteccion basica: una peticion GET (como abrir un enlace, o
# que un buscador la visite) nunca puede generar una factura por si sola.
@permiso_requerido("ventas.crear")
def cotizacion_facturar(cot_id):
    # ---------- 1ra VALIDACIÓN: que la cotización exista ----------
    cot = query_one("SELECT * FROM cotizaciones WHERE id = ?", [cot_id])
    if cot is None:
        flash("La cotización no existe.", "error")
        return redirect(url_for("ventas.cotizaciones"))
    # Se trae la fila COMPLETA (SELECT *) porque mas adelante se
    # necesitan varios de sus campos: cliente_id, subtotal, impuesto,
    # total y numero.

    # ---------- 2da VALIDACIÓN: regla de negocio del estado ----------
    if cot["estado"] != "Aprobada":
        flash("Solo se pueden facturar cotizaciones en estado Aprobada.", "error")
        return redirect(url_for("ventas.cotizacion_ver", cot_id=cot_id))
    # Solo se factura lo que el cliente aprobo comercialmente. Facturar
    # algo en Borrador, Enviada, Rechazada o Vencida no tiene respaldo:
    # se estaria cobrando por algo que el cliente nunca acepto.

    # ---------- 3ra VALIDACIÓN: evitar la doble facturación ----------
    existente = query_one("SELECT id, numero FROM facturas WHERE cotizacion_id = ?", [cot_id])
    if existente:
        flash(f"Esta cotización ya tiene la factura {existente['numero']}.", "error")
        return redirect(url_for("ventas.cotizacion_ver", cot_id=cot_id))
    # Se busca por la llave foranea cotizacion_id: si ya existe una
    # factura con ese valor, no se genera otra. El mensaje incluye el
    # numero de la factura existente para que el usuario pueda ir a
    # buscarla en vez de quedarse sin saber que paso.
    #
    # SOLO SE LLEGA A ESCRIBIR EN LA BASE SI LAS TRES VALIDACIONES
    # PASARON. Es el patron "validar todo primero, escribir despues".

    # ---------- Preparación del número correlativo y las fechas ----------
    hoy = datetime.date.today()
    sig = query_one("SELECT ISNULL(MAX(id),0)+1 AS n FROM facturas")["n"]
    numero = f"FAC-{hoy.year}-{sig:04d}"
    # Mismo patron y misma limitacion de concurrencia que en
    # cotizacion_nueva(): entre este SELECT y el INSERT de abajo hay
    # una ventana teorica en la que otro usuario podria leer el mismo
    # numero. En la version transaccional del motor (sp_aprobar_y_facturar)
    # ese problema se resuelve con WITH (UPDLOCK).

    # ---------- LA ÚNICA ESCRITURA DE NEGOCIO ----------
    fac_id = insertar(
        "INSERT INTO facturas (numero, cotizacion_id, cliente_id, fecha_emision, "
        "fecha_vencimiento, subtotal, impuesto, total, estado) "
        "OUTPUT INSERTED.id VALUES (?,?,?,?,?,?,?,?, 'Pendiente')",
        [numero, cot_id, cot["cliente_id"], hoy,
         hoy + datetime.timedelta(days=30), cot["subtotal"], cot["impuesto"], cot["total"]],
    )
    # cotizacion_id: materializa la relacion "origina" del diagrama
    # entre cotizaciones y facturas. Esta columna admite NULL en el
    # esquema (para permitir facturas directas via factura_nueva()),
    # pero por ESTE camino especifico siempre se llena.
    #
    # cliente_id: se copia de la cotizacion. Aunque podria deducirse
    # siempre con un JOIN a traves de cotizacion_id, guardarlo aqui
    # permite que una factura funcione de forma autonoma, sin depender
    # de que su cotizacion de origen siga existiendo intacta.
    #
    # subtotal, impuesto, total: se COPIAN de la cotizacion, NO se
    # recalculan ni se van a consultar despues de la cotizacion. Una
    # factura es un documento contable: sus importes deben quedar
    # CONGELADOS en el momento exacto de emitirse. Si la cotizacion se
    # modificara despues (lo cual normalmente no deberia pasar una vez
    # aprobada), la factura ya generada no debe cambiar.
    #
    # 'Pendiente' va escrito DIRECTAMENTE en el texto del SQL, no como
    # parametro (?): no es un dato que el usuario elija, toda factura
    # nueva por este camino nace en ese estado, sin excepcion.
    #
    # NOTA IMPORTANTE PARA LA DEFENSA: existe una version transaccional
    # de esta MISMA operacion implementada directamente en la base de
    # datos, el procedimiento sp_aprobar_y_facturar. Esa version hace
    # dos cosas mas que esta ruta de Python NO hace: (1) aprueba la
    # cotizacion Y factura dentro de UNA SOLA transaccion, de modo que
    # si el INSERT de la factura fallara, el UPDATE de aprobacion
    # tambien se deshace con ROLLBACK; y (2) usa WITH (UPDLOCK) al leer
    # la cotizacion, bloqueando la fila para que dos usuarios no puedan
    # facturar la misma cotizacion al mismo tiempo. Es la solucion
    # robusta al problema de concurrencia que esta version en Python
    # no resuelve del todo.

    registrar_auditoria("facturas", "INSERT", fac_id,
                        datos_nuevos={"numero": numero, "cotizacion": cot["numero"],
                                      "total": float(cot["total"])})
    # float(cot["total"]): convierte el tipo Decimal que devuelve
    # pyodbc a un float normal de Python, para que json.dumps lo pueda
    # convertir a texto sin fallar dentro de registrar_auditoria().

    flash(f"Factura {numero} generada a partir de {cot['numero']}.", "ok")
    return redirect(url_for("ventas.facturas"))
    # Redirige al LISTADO de facturas (no a la cotizacion): el usuario
    # acaba de crear un documento nuevo y lo natural es llevarlo a
    # verlo en su contexto, junto a las demas facturas.


"""
   Función: _ctx_cotizacion
   Objetivo: Reunir las listas necesarias para el formulario de
             cotización: clientes activos/prospecto, ejecutivos,
             catálogo de productos con precio, y el ITBIS vigente.
   Parámetros: No recibe.
   Retorno: Diccionario con clientes_lista, ejecutivos, productos,
            estados e itbis.
"""
def _ctx_cotizacion():
    return {
        "clientes_lista": query_all(
            "SELECT c.id, c.codigo, e.nombre FROM clientes c "
            "JOIN empresas e ON e.id = c.empresa_id "
            "WHERE c.estado IN ('Activo','Prospecto') ORDER BY e.nombre"),
        "ejecutivos": query_all(
            "SELECT id, nombre FROM usuarios WHERE activo = 1 ORDER BY nombre"),
        "productos": query_all(
            "SELECT id, sku, nombre, precio_lista FROM productos WHERE activo = 1 "
            "ORDER BY nombre"),
        "estados": ESTADOS_COT, "itbis": obtener_itbis(),
    }


"""
   Función: _leer_cotizacion
   Objetivo: Leer la cabecera y todas las líneas de producto del
             formulario, validarlas y calcular los totales
             provisionales (que después el trigger de la base
             sobrescribirá con el valor definitivo).
   Parámetros: No recibe (lee de request.form, incluidos los campos
               repetidos producto_id[], cantidad[], precio[] y
               descuento[]).
   Retorno: Tupla (cab, lineas, error): el diccionario de cabecera,
            la lista de líneas válidas, y un mensaje de error (o None
            si todo está correcto).
"""
def _leer_cotizacion():
    """Lee cabecera + líneas del formulario y calcula los totales en el servidor."""
    g = lambda k: (request.form.get(k) or "").strip()  # noqa: E731
    cab = {
        "cliente_id": int(g("cliente_id") or 0) or None,
        "ejecutivo_id": int(g("ejecutivo_id") or 0) or None,
        "fecha": g("fecha") or datetime.date.today().isoformat(),
        "fecha_validez": g("fecha_validez"),
        "estado": g("estado") if g("estado") in ESTADOS_COT else "Borrador",
        "notas": g("notas"),
    }
    lineas = []
    ids = request.form.getlist("producto_id[]")
    cants = request.form.getlist("cantidad[]")
    precios = request.form.getlist("precio[]")
    descs = request.form.getlist("descuento[]")
    for i, pid in enumerate(ids):
        if not pid:
            continue
        try:
            cantidad = max(1, int(cants[i] or 1))
            precio = max(0.0, float(precios[i] or 0))
            desc = min(100.0, max(0.0, float(descs[i] or 0)))
        except (ValueError, IndexError):
            continue
        sub = round(cantidad * precio * (1 - desc / 100), 2)
        lineas.append({"producto_id": int(pid), "cantidad": cantidad,
                       "precio_unitario": precio, "descuento_pct": desc, "subtotal": sub})
    if not cab["cliente_id"]:
        return cab, lineas, "Selecciona el cliente de la cotización."
    if not lineas:
        return cab, lineas, "Agrega al menos una línea con producto."
    cab["subtotal"] = round(sum(l["subtotal"] for l in lineas), 2)
    cab["impuesto"] = round(cab["subtotal"] * obtener_itbis(), 2)
    cab["total"] = round(cab["subtotal"] + cab["impuesto"], 2)
    return cab, lineas, None


"""
   Función: _guardar_lineas
   Objetivo: Insertar en la base una fila de detalle por cada línea
             de producto de la cotización.
   Parámetros:
     - cot_id: identificador de la cotización a la que pertenecen.
     - lineas: lista de diccionarios con los datos de cada línea.
   Retorno: No aplica (inserta directo en la base).
"""
def _guardar_lineas(cot_id, lineas):
    for l in lineas:
        execute(
            "INSERT INTO detalle_cotizacion (cotizacion_id, producto_id, cantidad, "
            "precio_unitario, descuento_pct, subtotal) VALUES (?,?,?,?,?,?)",
            [cot_id, l["producto_id"], l["cantidad"], l["precio_unitario"],
             l["descuento_pct"], l["subtotal"]],
        )


# =====================================================================
#  FACTURAS
# =====================================================================
"""
   Función: facturas
   Objetivo: Mostrar el listado paginado de facturas, con búsqueda
             por número o cliente y filtro opcional por estado,
             incluyendo el número de la cotización de origen si la
             tiene.
   Parámetros: No recibe directamente (lee 'q', 'estado' y 'pagina'
               de la URL).
   Retorno: La plantilla facturas.html con las facturas de la página
            actual.
"""
@bp.route("/facturas")
@permiso_requerido("ventas.ver")
def facturas():
    q = (request.args.get("q") or "").strip()
    estado = (request.args.get("estado") or "").strip()
    sql = ("SELECT f.id, f.numero, f.fecha_emision, f.fecha_vencimiento, f.total, "
           "       f.moneda, f.estado, e.nombre AS cliente, co.numero AS cotizacion "
           "FROM facturas f JOIN clientes c ON c.id = f.cliente_id "
           "JOIN empresas e ON e.id = c.empresa_id "
           "LEFT JOIN cotizaciones co ON co.id = f.cotizacion_id WHERE 1=1 ")
    # LEFT JOIN a cotizaciones: cotizacion_id admite NULL (facturas
    # directas sin cotizacion previa); con JOIN normal esas facturas
    # desaparecerian del listado.
    params = []
    if q:
        sql += "AND (f.numero LIKE ? OR e.nombre LIKE ?) "
        params += [f"%{q}%", f"%{q}%"]
    if estado:
        sql += "AND f.estado = ? "
        params.append(estado)
    pagina = max(1, int(request.args.get("pagina", 1) or 1))
    sql += "ORDER BY f.fecha_emision DESC, f.id DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
    params += [(pagina - 1) * 15, 15]
    filas = query_all(sql, params)
    return render_template("facturas.html", active="facturas",
                           facturas=filas, buscar=q, estado=estado,
                           estados=ESTADOS_FAC, pagina=pagina, hay_mas=len(filas) == 15)


"""
   Función: factura_nueva
   Objetivo: Crear una factura de forma manual, con dos modos: a
             partir de una cotización aprobada existente (copiando
             cliente y montos), o de forma directa indicando cliente
             y subtotal (calculando el ITBIS solo).
   Parámetros: No recibe directamente (lee el formulario).
   Retorno: En GET, formulario vacío. En POST correcto, redirige al
            listado de facturas.
"""
@bp.route("/facturas/nueva", methods=["GET", "POST"])
@permiso_requerido("ventas.crear")
def factura_nueva():
    """Crea una factura manualmente.

    La cotizacion es OPCIONAL (la FK cotizacion_id admite NULL):
      - Si se elige una cotizacion Aprobada, se copian su cliente y montos.
      - Si no, se factura directo indicando cliente y subtotal; el ITBIS
        se calcula con el porcentaje guardado en la tabla configuracion.
    """
    ctx = _ctx_factura()
    if request.method == "POST":
        g = lambda k: (request.form.get(k) or "").strip()  # noqa: E731
        cot_id = int(g("cotizacion_id") or 0) or None
        cliente_id = int(g("cliente_id") or 0) or None
        f_emision = g("fecha_emision")
        f_vence = g("fecha_vencimiento")
        estado = g("estado") if g("estado") in ESTADOS_FAC else "Pendiente"

        # --- Montos: de la cotizacion o calculados desde el subtotal ---
        if cot_id:
            cot = query_one("SELECT * FROM cotizaciones WHERE id = ?", [cot_id])
            if cot is None:
                flash("La cotización seleccionada no existe.", "error")
                return render_template("factura_form.html", active="facturas",
                                       titulo="Nueva factura", factura=None, **ctx)
            if query_one("SELECT id FROM facturas WHERE cotizacion_id = ?", [cot_id]):
                flash("Esa cotización ya tiene una factura.", "error")
                return render_template("factura_form.html", active="facturas",
                                       titulo="Nueva factura", factura=None, **ctx)
            cliente_id = cot["cliente_id"]
            subtotal = float(cot["subtotal"] or 0)
            impuesto = float(cot["impuesto"] or 0)
            total = float(cot["total"] or 0)
        else:
            subtotal = float(g("subtotal") or 0)
            impuesto = round(subtotal * obtener_itbis(), 2)
            total = round(subtotal + impuesto, 2)

        # --- Validaciones ---
        if not cliente_id:
            flash("Selecciona el cliente (o una cotización).", "error")
            return render_template("factura_form.html", active="facturas",
                                   titulo="Nueva factura", factura=None, **ctx)
        if subtotal <= 0:
            flash("El subtotal debe ser mayor que cero.", "error")
            return render_template("factura_form.html", active="facturas",
                                   titulo="Nueva factura", factura=None, **ctx)

        hoy = datetime.date.today()
        emision = f_emision or hoy.isoformat()
        vence = f_vence or (hoy + datetime.timedelta(days=30)).isoformat()

        sig = query_one("SELECT ISNULL(MAX(id),0)+1 AS n FROM facturas")["n"]
        numero = f"FAC-{hoy.year}-{sig:04d}"

        fac_id = insertar(
            "INSERT INTO facturas (numero, cotizacion_id, cliente_id, fecha_emision, "
            "fecha_vencimiento, subtotal, impuesto, total, estado) "
            "OUTPUT INSERTED.id VALUES (?,?,?,?,?,?,?,?,?)",
            [numero, cot_id, cliente_id, emision, vence,
             subtotal, impuesto, total, estado],
        )
        registrar_auditoria("facturas", "INSERT", fac_id,
                            datos_nuevos={"numero": numero, "cliente_id": cliente_id,
                                          "total": total, "estado": estado,
                                          "origen": "manual"})
        flash(f"Factura {numero} creada correctamente.", "ok")
        return redirect(url_for("ventas.facturas"))

    return render_template("factura_form.html", active="facturas",
                           titulo="Nueva factura", factura=None, **ctx)


"""
   Función: _ctx_factura
   Objetivo: Reunir las listas del formulario de factura manual:
             clientes activos/prospecto, y las cotizaciones aprobadas
             que aún NO tienen factura.
   Parámetros: No recibe.
   Retorno: Diccionario con clientes_lista, cotizaciones_lista,
            estados e itbis_pct.
"""
def _ctx_factura():
    """Listas para los desplegables del formulario de factura."""
    return {
        "clientes_lista": query_all(
            "SELECT c.id, c.codigo, e.nombre FROM clientes c "
            "JOIN empresas e ON e.id = c.empresa_id "
            "WHERE c.estado IN ('Activo','Prospecto') ORDER BY e.nombre"),
        # Solo cotizaciones aprobadas que aun no tienen factura
        "cotizaciones_lista": query_all(
            "SELECT co.id, co.numero, co.total, e.nombre AS cliente "
            "FROM cotizaciones co "
            "JOIN clientes c ON c.id = co.cliente_id "
            "JOIN empresas e ON e.id = c.empresa_id "
            "WHERE co.estado = 'Aprobada' "
            "  AND NOT EXISTS (SELECT 1 FROM facturas f WHERE f.cotizacion_id = co.id) "
            "ORDER BY co.numero DESC"),
        "estados": ESTADOS_FAC,
        "itbis_pct": round(obtener_itbis() * 100),
    }


"""
   Función: factura_estado
   Objetivo: Cambiar el estado de una factura (por ejemplo, marcarla
             como Pagada), validando el nuevo estado.
   Parámetros:
     - fac_id: identificador de la factura.
   Retorno: Redirige al listado de facturas.
"""
@bp.route("/facturas/<int:fac_id>/estado", methods=["POST"])
@permiso_requerido("ventas.editar")
def factura_estado(fac_id):
    nuevo = request.form.get("estado")
    actual = query_one("SELECT id, numero, estado FROM facturas WHERE id = ?", [fac_id])
    if actual is None or nuevo not in ESTADOS_FAC:
        flash("Operación inválida.", "error")
    else:
        execute("UPDATE facturas SET estado=?, updated_at=SYSDATETIME() WHERE id=?",
                [nuevo, fac_id])
        registrar_auditoria("facturas", "UPDATE", fac_id,
                            datos_anteriores={"estado": actual["estado"]},
                            datos_nuevos={"estado": nuevo})
        flash(f"Factura {actual['numero']} marcada como {nuevo}.", "ok")
    return redirect(url_for("ventas.facturas"))


# =====================================================================
#  CONTRATOS
# =====================================================================
"""
   Función: contratos
   Objetivo: Mostrar el listado de contratos, con búsqueda por
             número o cliente.
   Parámetros: No recibe directamente (lee 'q' de la URL).
   Retorno: La plantilla contratos.html con los contratos encontrados.
"""
@bp.route("/contratos")
@permiso_requerido("ventas.ver")
def contratos():
    q = (request.args.get("q") or "").strip()
    sql = ("SELECT ct.id, ct.numero, ct.tipo, ct.fecha_inicio, ct.fecha_fin, ct.monto, "
           "       ct.moneda, ct.estado, e.nombre AS cliente "
           "FROM contratos ct JOIN clientes c ON c.id = ct.cliente_id "
           "JOIN empresas e ON e.id = c.empresa_id WHERE 1=1 ")
    params = []
    if q:
        sql += "AND (ct.numero LIKE ? OR e.nombre LIKE ?) "
        params += [f"%{q}%", f"%{q}%"]
    sql += "ORDER BY ct.fecha_inicio DESC"
    return render_template("contratos.html", active="contratos",
                           contratos=query_all(sql, params), buscar=q)


"""
   Función: contrato_nuevo
   Objetivo: Mostrar el formulario de alta de contrato (GET) y
             procesar su creación (POST), generando el número
             correlativo CTR-2026-0001.
   Parámetros: No recibe directamente (lee el formulario).
   Retorno: En GET, formulario vacío. En POST correcto, redirige al
            listado.
"""
@bp.route("/contratos/nuevo", methods=["GET", "POST"])
@permiso_requerido("ventas.crear")
def contrato_nuevo():
    ctx = _ctx_contrato()
    if request.method == "POST":
        d = _form_contrato()
        if not d["cliente_id"] or not d["fecha_inicio"]:
            flash("El cliente y la fecha de inicio son obligatorios.", "error")
            return render_template("contrato_form.html", active="contratos",
                                   titulo="Nuevo contrato", contrato=d, **ctx)
        sig = query_one("SELECT ISNULL(MAX(id),0)+1 AS n FROM contratos")["n"]
        numero = f"CTR-{datetime.date.today().year}-{sig:04d}"
        nuevo_id = insertar(
            "INSERT INTO contratos (numero, cliente_id, tipo, fecha_inicio, fecha_fin, "
            "monto, estado, terminos) OUTPUT INSERTED.id VALUES (?,?,?,?,?,?,?,?)",
            [numero, d["cliente_id"], d["tipo"], d["fecha_inicio"], d["fecha_fin"] or None,
             d["monto"], d["estado"], d["terminos"]],
        )
        registrar_auditoria("contratos", "INSERT", nuevo_id,
                            datos_nuevos={**d, "numero": numero})
        flash(f"Contrato {numero} creado.", "ok")
        return redirect(url_for("ventas.contratos"))
    return render_template("contrato_form.html", active="contratos",
                           titulo="Nuevo contrato", contrato=None, **ctx)


"""
   Función: contrato_editar
   Objetivo: Mostrar el formulario con los datos actuales de un
             contrato (GET) y guardar sus modificaciones (POST).
   Parámetros:
     - contrato_id: identificador del contrato a editar.
   Retorno: En GET, formulario con datos cargados. En POST correcto,
            redirige al listado.
"""
@bp.route("/contratos/<int:contrato_id>/editar", methods=["GET", "POST"])
@permiso_requerido("ventas.editar")
def contrato_editar(contrato_id):
    actual = query_one("SELECT * FROM contratos WHERE id = ?", [contrato_id])
    if actual is None:
        flash("El contrato no existe.", "error")
        return redirect(url_for("ventas.contratos"))
    ctx = _ctx_contrato()
    if request.method == "POST":
        d = _form_contrato()
        if not d["cliente_id"] or not d["fecha_inicio"]:
            flash("El cliente y la fecha de inicio son obligatorios.", "error")
            return render_template("contrato_form.html", active="contratos",
                                   titulo="Editar contrato", contrato=d, **ctx)
        execute(
            "UPDATE contratos SET cliente_id=?, tipo=?, fecha_inicio=?, fecha_fin=?, "
            "monto=?, estado=?, terminos=?, updated_at=SYSDATETIME() WHERE id=?",
            [d["cliente_id"], d["tipo"], d["fecha_inicio"], d["fecha_fin"] or None,
             d["monto"], d["estado"], d["terminos"], contrato_id],
        )
        registrar_auditoria("contratos", "UPDATE", contrato_id,
                            datos_anteriores={"estado": actual["estado"],
                                              "monto": float(actual["monto"])},
                            datos_nuevos={"estado": d["estado"], "monto": d["monto"]})
        flash("Contrato actualizado.", "ok")
        return redirect(url_for("ventas.contratos"))
    cab = dict(actual)
    cab["fecha_inicio"] = actual["fecha_inicio"].isoformat() if actual["fecha_inicio"] else ""
    cab["fecha_fin"] = actual["fecha_fin"].isoformat() if actual["fecha_fin"] else ""
    return render_template("contrato_form.html", active="contratos",
                           titulo=f"Editar {actual['numero']}", contrato=cab, **ctx)


"""
   Función: _ctx_contrato
   Objetivo: Reunir la lista de clientes y los catálogos de tipo y
             estado para el formulario de contrato.
   Parámetros: No recibe.
   Retorno: Diccionario con clientes_lista, tipos y estados.
"""
def _ctx_contrato():
    return {
        "clientes_lista": query_all(
            "SELECT c.id, e.nombre FROM clientes c JOIN empresas e ON e.id = c.empresa_id "
            "ORDER BY e.nombre"),
        "tipos": TIPOS_CONTRATO, "estados": ESTADOS_CONTRATO,
    }


"""
   Función: _form_contrato
   Objetivo: Leer y limpiar los campos del formulario de contrato.
   Parámetros: No recibe (lee de request.form).
   Retorno: Diccionario con los siete campos de contratos.
"""
def _form_contrato():
    g = lambda k: (request.form.get(k) or "").strip()  # noqa: E731
    return {
        "cliente_id": int(g("cliente_id") or 0) or None,
        "tipo": g("tipo") if g("tipo") in TIPOS_CONTRATO else "Soporte",
        "fecha_inicio": g("fecha_inicio"),
        "fecha_fin": g("fecha_fin"),
        "monto": float(g("monto") or 0),
        "estado": g("estado") if g("estado") in ESTADOS_CONTRATO else "Vigente",
        "terminos": g("terminos"),
    }


# ------------------ PDF Y ENVÍO POR EMAIL ------------------
"""
   Función: _generar_pdf
   Objetivo: Construir, con la librería reportlab, el documento PDF
             de una cotización: encabezado, datos del cliente, tabla
             de líneas de producto y resumen de totales, dibujado a
             mano con coordenadas exactas en centímetros.
   Parámetros:
     - cot: diccionario con los datos de la cabecera (incluye el
            nombre del cliente).
     - lineas: lista de diccionarios con las líneas de producto.
   Retorno: Los bytes del PDF generado, listos para descargarlos o
            adjuntarlos a un correo.
"""
def _generar_pdf(cot, lineas):
    """Genera el PDF de la cotización (bytes) con reportlab."""
    import io
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    an, al = letter
    c.setFillColorRGB(0.08, 0.39, 0.62)
    c.rect(0, al - 2.2 * cm, an, 2.2 * cm, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(2 * cm, al - 1.5 * cm, "CIBERSEG")
    c.setFont("Helvetica", 10)
    c.drawRightString(an - 2 * cm, al - 1.5 * cm, f"Cotizacion {cot['numero']}")
    c.setFillColorRGB(0.12, 0.16, 0.23)
    y = al - 3.4 * cm
    c.setFont("Helvetica", 10)
    for et, v in [("Cliente", cot["cliente"]),
                  ("Fecha", cot["fecha"].strftime("%d/%m/%Y") if cot["fecha"] else "-"),
                  ("Valida hasta", cot["fecha_validez"].strftime("%d/%m/%Y") if cot["fecha_validez"] else "-"),
                  ("Estado", cot["estado"])]:
        c.setFont("Helvetica-Bold", 10); c.drawString(2 * cm, y, f"{et}:")
        c.setFont("Helvetica", 10); c.drawString(5 * cm, y, str(v)); y -= 0.55 * cm
    y -= 0.4 * cm
    c.setFont("Helvetica-Bold", 9)
    for x, t in [(2, "SKU"), (4.2, "Producto"), (11.5, "Cant."), (13, "Precio"),
                 (15.2, "Desc."), (16.8, "Subtotal")]:
        c.drawString(x * cm, y, t)
    c.line(2 * cm, y - 0.15 * cm, an - 2 * cm, y - 0.15 * cm)
    y -= 0.6 * cm
    c.setFont("Helvetica", 9)
    for l in lineas:
        c.drawString(2 * cm, y, l["sku"] or "")
        c.drawString(4.2 * cm, y, (l["producto"] or "")[:38])
        c.drawRightString(12.3 * cm, y, str(l["cantidad"]))
        c.drawRightString(14.6 * cm, y, f"${l['precio_unitario']:,.2f}")
        c.drawRightString(16.2 * cm, y, f"{l['descuento_pct']:.0f}%")
        c.drawRightString(an - 2 * cm, y, f"${l['subtotal']:,.2f}")
        y -= 0.5 * cm
        if y < 4 * cm:
            c.showPage(); y = al - 2.5 * cm; c.setFont("Helvetica", 9)
    y -= 0.3 * cm
    c.line(12 * cm, y, an - 2 * cm, y); y -= 0.55 * cm
    c.setFont("Helvetica", 10)
    c.drawRightString(16.2 * cm, y, "Subtotal:"); c.drawRightString(an - 2 * cm, y, f"${cot['subtotal']:,.2f}")
    y -= 0.5 * cm
    c.drawRightString(16.2 * cm, y, "ITBIS:"); c.drawRightString(an - 2 * cm, y, f"${cot['impuesto']:,.2f}")
    y -= 0.55 * cm
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(16.2 * cm, y, "TOTAL:"); c.drawRightString(an - 2 * cm, y, f"${cot['total']:,.2f}")
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0.55, 0.6, 0.67)
    c.drawString(2 * cm, 1.5 * cm, "CIBERSEG - Distribuidor autorizado de soluciones de ciberseguridad")
    c.save()
    return buf.getvalue()


"""
   Función: _cot_con_lineas
   Objetivo: Traer una cotización con el nombre de su cliente y
             empresa, junto a todas sus líneas de detalle. Auxiliar
             compartido entre la exportación a PDF y el envío por
             correo, para no repetir las mismas dos consultas.
   Parámetros:
     - cot_id: identificador de la cotización.
   Retorno: Tupla (cot, lineas): el diccionario de la cotización (o
            None si no existe) y la lista de sus líneas.
"""
def _cot_con_lineas(cot_id):
    cot = query_one(
        "SELECT co.*, e.nombre AS cliente, c.empresa_id FROM cotizaciones co "
        "JOIN clientes c ON c.id = co.cliente_id JOIN empresas e ON e.id = c.empresa_id "
        "WHERE co.id = ?", [cot_id])
    lineas = query_all(
        "SELECT d.*, p.nombre AS producto, p.sku FROM detalle_cotizacion d "
        "JOIN productos p ON p.id = d.producto_id WHERE d.cotizacion_id = ?", [cot_id]) if cot else []
    return cot, lineas


"""
   Función: cotizacion_pdf
   Objetivo: Ser la ruta que descarga el PDF de una cotización.
   Parámetros:
     - cot_id: identificador de la cotización.
   Retorno: Una respuesta HTTP con el PDF como descarga adjunta.
"""
@bp.route("/cotizaciones/<int:cot_id>/pdf")
@permiso_requerido("ventas.ver")
def cotizacion_pdf(cot_id):
    from flask import Response
    cot, lineas = _cot_con_lineas(cot_id)
    if cot is None:
        flash("La cotización no existe.", "error")
        return redirect(url_for("ventas.cotizaciones"))
    return Response(_generar_pdf(cot, lineas), mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={cot['numero']}.pdf"})


"""
   Función: cotizacion_enviar
   Objetivo: Enviar la cotización en PDF por correo electrónico al
             contacto principal de la empresa del cliente, usando los
             datos SMTP guardados en la configuración.
   Parámetros:
     - cot_id: identificador de la cotización a enviar.
   Retorno: Redirige a la vista de la cotización, con un mensaje.
"""
@bp.route("/cotizaciones/<int:cot_id>/enviar", methods=["POST"])
@permiso_requerido("ventas.editar")
def cotizacion_enviar(cot_id):
    """Envía la cotización en PDF por email al contacto principal (requiere SMTP en Configuración)."""
    import smtplib
    from email.message import EmailMessage
    from ..configuracion import leer_config

    cot, lineas = _cot_con_lineas(cot_id)
    if cot is None:
        flash("La cotización no existe.", "error")
        return redirect(url_for("ventas.cotizaciones"))
    contacto = query_one(
        "SELECT TOP 1 nombre, email FROM contactos WHERE empresa_id = ? AND activo = 1 "
        "AND email IS NOT NULL AND email <> '' ORDER BY es_principal DESC", [cot["empresa_id"]])
    if not contacto:
        flash("El cliente no tiene un contacto con email registrado.", "error")
        return redirect(url_for("ventas.cotizacion_ver", cot_id=cot_id))
    cfg = leer_config()
    if not cfg.get("smtp_host") or not cfg.get("smtp_remitente"):
        flash("Configura el servidor SMTP en Configuración antes de enviar correos.", "error")
        return redirect(url_for("ventas.cotizacion_ver", cot_id=cot_id))
    plantilla = request.form.get("plantilla") or "plantilla_seguimiento"
    cuerpo = cfg.get(plantilla, cfg["plantilla_seguimiento"]) \
        .replace("{cliente}", cot["cliente"]).replace("{numero}", cot["numero"])
    try:
        msg = EmailMessage()
        msg["Subject"] = f"Cotizacion {cot['numero']} - CIBERSEG"
        msg["From"] = cfg["smtp_remitente"]
        msg["To"] = contacto["email"]
        msg.set_content(cuerpo)
        msg.add_attachment(_generar_pdf(cot, lineas), maintype="application",
                           subtype="pdf", filename=f"{cot['numero']}.pdf")
        with smtplib.SMTP(cfg["smtp_host"], int(cfg.get("smtp_puerto") or 587), timeout=15) as s:
            s.starttls()
            if cfg.get("smtp_usuario"):
                s.login(cfg["smtp_usuario"], cfg["smtp_clave"])
            s.send_message(msg)
        registrar_auditoria("cotizaciones", "UPDATE", cot_id,
                            datos_nuevos={"email_enviado_a": contacto["email"]})
        flash(f"Cotización enviada a {contacto['email']}.", "ok")
    except Exception as err:  # noqa: BLE001
        flash(f"No se pudo enviar el correo: {err}", "error")
    return redirect(url_for("ventas.cotizacion_ver", cot_id=cot_id))