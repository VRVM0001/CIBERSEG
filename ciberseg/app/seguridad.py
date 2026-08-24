"""
=========================================================================
 Módulo: seguridad.py (app/seguridad.py)
 Utilidades de seguridad: control de sesión, permisos y auditoría.

 - login_requerido: protege una vista; si no hay sesión, redirige al login.
 - permiso_requerido('modulo.accion'): además exige un permiso específico.
 - registrar_auditoria(): guarda en la tabla `auditoria` quién hizo qué.

 Este archivo está separado de auth.py a propósito: auth.py es un
 blueprint con rutas (el login y el logout en sí), mientras que esto
 son utilidades que TODOS los demás blueprints importan para proteger
 sus propias rutas y para dejar constancia de los cambios que hacen.
=========================================================================
"""
import json                                            # Para convertir diccionarios a texto (formato JSON)
from functools import wraps                             # Conserva el nombre original de la funcion decorada

from flask import session, redirect, url_for, flash, request   # session: datos del usuario conectado

from .db import execute                                 # Funcion de escritura definida en db.py


"""
   Función: login_requerido
   Objetivo: Ser un decorador que protege una vista (una ruta) para que
             solo pueda usarse si hay una sesión iniciada. Si no la
             hay, redirige automáticamente al login en vez de ejecutar
             la vista.
   Parámetros:
     - vista: la función de la ruta que se está protegiendo (se recibe
              automáticamente al escribir @login_requerido encima de
              una función).
   Retorno: Una nueva función (envoltura) que reemplaza a la original:
            primero verifica la sesión y solo después, si corresponde,
            ejecuta la vista real.
"""
def login_requerido(vista):
    """La vista solo se puede ver con sesión iniciada."""
    @wraps(vista)                                # Conserva el nombre de 'vista' para que Flask no se confunda
    def envoltura(*args, **kwargs):              # *args/**kwargs: acepta vistas con o sin parametros propios
        if "usuario_id" not in session:          # Si no hay usuario guardado en la sesion...
            return redirect(url_for("auth.login"))    # ...manda directo al login, sin ejecutar la vista
        return vista(*args, **kwargs)            # Si hay sesion, ejecuta la vista real normalmente
    return envoltura                             # Devuelve la version "protegida" de la vista


"""
   Función: permiso_requerido
   Objetivo: Ser un decorador CON PARÁMETRO que protege una vista
             exigiendo, además de la sesión iniciada, un permiso
             concreto (por ejemplo 'clientes.crear'). Es el mecanismo
             central de autorización de todo el sistema.
   Parámetros:
     - permiso: texto con el nombre del permiso exigido, en formato
                "modulo.accion" (por ejemplo "usuarios.crear").
   Retorno: Un decorador (funcion 'decorador') que, aplicado sobre una
            vista, la envuelve con la verificacion de sesion y permiso.
            Por tener parametro, se usa con parentesis:
            @permiso_requerido("clientes.crear")
"""
def permiso_requerido(permiso):
    """La vista exige, además de la sesión, un permiso concreto (ej. 'usuarios.crear')."""
    def decorador(vista):                        # Funcion intermedia: recibe la vista a proteger
        @wraps(vista)
        def envoltura(*args, **kwargs):
            if "usuario_id" not in session:                     # Primero, verifica que haya sesion
                return redirect(url_for("auth.login"))
            if permiso not in session.get("permisos", []):      # Luego, verifica el permiso especifico
                flash("No tienes permiso para realizar esta acción.", "error")   # Aviso visible al usuario
                return redirect(url_for("main.index"))          # Redirige al dashboard, no muestra la vista
            return vista(*args, **kwargs)        # Solo si pasa las dos verificaciones, ejecuta la vista real
        return envoltura
    return decorador                             # Se devuelve el decorador, que a su vez se aplicara a la vista


"""
   Función: registrar_auditoria
   Objetivo: Insertar un evento en la tabla 'auditoria', dejando
             constancia de quién hizo qué cambio, cuándo y desde qué
             dirección IP. Es la mitad "aplicación" de la auditoría
             por partida doble (la otra mitad la hacen los triggers
             de la base de datos).
   Parámetros:
     - tabla: nombre de la tabla afectada (por ejemplo "clientes").
     - accion: tipo de operación realizada: 'INSERT', 'UPDATE' o
               'DELETE' (el mismo dominio que valida el CHECK de la
               columna 'accion' en la base de datos).
     - registro_id: identificador de la fila afectada (opcional).
     - datos_anteriores: diccionario con los valores previos al
                          cambio (opcional, solo aplica en UPDATE).
     - datos_nuevos: diccionario con los valores nuevos (opcional).
   Retorno: No aplica (no devuelve nada; inserta directo en la base).
"""
def registrar_auditoria(tabla, accion, registro_id=None, datos_anteriores=None, datos_nuevos=None):
    """
    Inserta un evento en la tabla `auditoria`.
    accion: 'INSERT' | 'UPDATE' | 'DELETE' (validado por CHECK en la BD).
    Los datos se guardan como JSON legible para poder revisarlos después.
    """
    execute(
        "INSERT INTO auditoria (usuario_id, tabla_afectada, accion, registro_id, "
        "datos_anteriores, datos_nuevos, ip_origen) VALUES (?,?,?,?,?,?,?)",
        [
            session.get("usuario_id"),
            # Quien hizo el cambio: se lee de la sesion, no se recibe
            # como parametro. Este dato el motor NUNCA podria saberlo
            # por su cuenta, por eso hace falta esta funcion.

            tabla,          # En que tabla ocurrio el cambio
            accion,         # Que tipo de cambio fue (INSERT/UPDATE/DELETE)

            str(registro_id) if registro_id is not None else None,
            # Convierte el id a texto (la columna es VARCHAR, para poder
            # admitir tanto ids numericos como la clave de configuracion).
            # Si no se paso registro_id, guarda NULL.

            json.dumps(datos_anteriores, ensure_ascii=False, default=str) if datos_anteriores else None,
            # Convierte el diccionario de valores anteriores a texto JSON.
            # ensure_ascii=False conserva las tildes legibles.
            # default=str resuelve fechas y Decimales, que json.dumps
            # no sabe convertir por si solo.

            json.dumps(datos_nuevos, ensure_ascii=False, default=str) if datos_nuevos else None,
            # Lo mismo, pero para los valores nuevos.

            request.remote_addr,
            # Direccion IP de quien hizo la peticion HTTP: el "desde
            # donde" del evento.
        ],
    )