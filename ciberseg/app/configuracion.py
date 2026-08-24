"""
=========================================================================
 Módulo: configuracion.py (app/configuracion.py)
 Configuración del sistema (tabla clave/valor) con valores por defecto
 seguros.

 Este archivo administra la tabla 'configuracion' de la base de datos,
 que guarda parametros globales del sistema en formato clave-valor
 (por ejemplo, el porcentaje de ITBIS o los datos del servidor SMTP).
 Lo usan main.py (pantalla de Configuracion), auth.py (tiempo de
 sesion) y ventas.py (porcentaje de impuesto y plantillas de correo).
=========================================================================
"""
from .db import query_all, execute   # Funciones de acceso a datos definidas en db.py


# DEFECTOS: valores de respaldo para cada parametro del sistema.
# Si la tabla 'configuracion' todavia no existe, o si una clave en
# particular no se ha guardado nunca, la aplicacion sigue funcionando
# con estos valores en vez de fallar.
DEFECTOS = {
    "notif_activas": "1",              # Interruptor general de notificaciones (1 = encendido)
    "notif_cotizaciones": "1",         # Avisar de cotizaciones por vencer
    "notif_facturas": "1",             # Avisar de facturas vencidas
    "notif_equipos": "1",              # Avisar de equipos con problemas
    "notif_prospectos": "1",           # Avisar de prospectos sin seguimiento
    "notif_inventario": "1",           # Avisar de stock bajo el minimo
    "itbis_pct": "18",                 # Porcentaje de impuesto (Republica Dominicana: 18%)
    "sesion_timeout_min": "30",        # Minutos de inactividad antes de cerrar sesion sola
    "notif_actividades": "1",          # Avisar de actividades pendientes
    "smtp_host": "", "smtp_puerto": "587", "smtp_usuario": "",   # Datos del servidor de correo
    "smtp_clave": "", "smtp_remitente": "",                       # Credenciales y remitente del correo
    "plantilla_seguimiento": "Estimado cliente {cliente}: adjunto la cotizacion {numero}. Saludos, CIBERSEG.",
    "plantilla_renovacion": "Estimado cliente {cliente}: tiene servicios proximos a renovar. Saludos, CIBERSEG.",
    # Las dos plantillas de arriba usan {cliente} y {numero} como marcadores
    # que la aplicacion reemplaza con datos reales al enviar el correo.
}


"""
   Función: leer_config
   Objetivo: Devolver un diccionario con TODOS los parametros del
             sistema, combinando los valores guardados en la base de
             datos con los valores por defecto (DEFECTOS) para
             cualquier clave que aun no se haya guardado.
   Parámetros: No recibe.
   Retorno: Diccionario {clave: valor} con todos los parametros,
            siempre completo aunque la tabla este vacia o no exista.
"""
def leer_config():
    cfg = dict(DEFECTOS)          # Copia de los valores por defecto (para no modificar el original)
    try:
        for f in query_all("SELECT clave, valor FROM configuracion"):
            cfg[f["clave"]] = f["valor"]     # Sobrescribe el valor por defecto con el guardado en la base
    except Exception:  # tabla aún no creada -> usar defectos
        pass                        # Si la tabla no existe todavia, cfg se queda con solo los DEFECTOS
    return cfg


"""
   Función: guardar_config
   Objetivo: Guardar en la base de datos los valores nuevos que el
             usuario escribio en la pantalla de Configuracion. Usa la
             instruccion MERGE para actualizar la clave si ya existe,
             o insertarla si es la primera vez (patron "upsert").
   Parámetros:
     - valores: diccionario {clave: valor} con los parametros a
                guardar. Solo se procesan las claves que ya estan
                definidas en DEFECTOS; el resto se ignora.
   Retorno: No aplica (no devuelve nada; escribe directo en la base).
"""
def guardar_config(valores):
    for clave, valor in valores.items():        # Recorre cada par clave-valor recibido
        if clave not in DEFECTOS:
            continue                             # Ignora claves desconocidas (proteccion contra datos invalidos)
        execute(
            "MERGE configuracion AS t USING (SELECT ? AS clave, ? AS valor) AS s "
            "ON t.clave = s.clave "
            "WHEN MATCHED THEN UPDATE SET valor = s.valor, updated_at = SYSDATETIME() "
            "WHEN NOT MATCHED THEN INSERT (clave, valor) VALUES (s.clave, s.valor);",
            [clave, valor],
        )
        # La instruccion MERGE compara la tabla real (t) contra el valor
        # nuevo (s). Si la clave YA existe (WHEN MATCHED), actualiza su
        # valor. Si NO existe (WHEN NOT MATCHED), la inserta. Todo en
        # una sola instruccion, sin tener que consultar primero si
        # existe.