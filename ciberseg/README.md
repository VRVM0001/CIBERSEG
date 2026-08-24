# CIBERSEG - Sistema de Gestion para Empresa de Ciberseguridad

Sistema web de gestion (estilo consola empresarial) para una empresa
distribuidora de soluciones de ciberseguridad (partner Fortinet).

## Tecnologias
- **Base de datos:** Microsoft SQL Server (23 tablas, T-SQL)
- **Backend:** Python 3 + Flask (SQL puro parametrizado con pyodbc, sin ORM)
- **Frontend:** HTML + CSS + Chart.js (incluido localmente)

## Modulos (Fases 0 a 4)
**Fase 1:** Login con sesiones, proteccion de rutas por permiso,
CRUD de usuarios, vista de roles/permisos y registro de auditoria.
**Fase 2:** CRM completo - Empresas, Clientes y Contactos con
listas, busqueda, filtros, formularios de creacion/edicion y
desactivacion logica, todo registrado en auditoria.
**Fase 3 (nuevo):** Ventas - Cotizaciones con lineas de productos y calculo
automatico (subtotal + ITBIS 18%), flujo Borrador->Enviada->Aprobada,
generacion de Facturas en un clic, Contratos, busqueda global,
notificaciones reales, pagina de ayuda y perfil de usuario.
**Fase 4 (nuevo):** Inventario - Productos con control de stock (ajustes
+/- auditados y alerta de stock minimo), Equipos instalados por cliente
y Licencias con dias restantes y alerta de vencimiento a 30 dias.
**Fase 3 (nuevo):** Ventas completo - Cotizaciones con lineas de
productos dinamicas y calculo automatico de ITBIS, flujo de estados
(Borrador -> Enviada -> Aprobada) y generacion de Factura con un clic
desde una cotizacion aprobada; Facturas con cambio de estado; Contratos
con CRUD completo. Ademas: buscador global (topbar), notificaciones
reales calculadas desde la base de datos, y edicion de perfil/contrasena.

## Modulos de la base
Seguridad y acceso (roles, permisos, usuarios, auditoria) - CRM (empresas,
clientes, contactos) - Personal tecnico - Catalogo (fabricantes, productos,
licencias, renovaciones) - Ventas (cotizaciones, facturas, contratos) -
Inventario tecnico (equipos, firewalls, switches, access points) - Proyectos.

## Puesta en marcha (resumen)
1. En **SSMS** ejecuta en orden: `sql/schema.sql`, `sql/seed.sql` y
   opcionalmente `sql/seed_demo.sql` (datos de ejemplo para el dashboard).
2. Instala dependencias: `pip install -r requirements.txt`
3. Copia `.env.example` como `.env` y ajusta `DB_SERVER` a tu instancia.
4. Ejecuta: `python run.py` y abre `http://127.0.0.1:5000`

Usuario inicial: **admin** / **admin123** (pantalla de login ya activa).

## Estructura
```
ciberseg/
  run.py              # punto de entrada
  requirements.txt
  .env.example        # plantilla de configuracion
  sql/
    schema.sql        # crea la base "ciberseg" y sus 23 tablas
    seed.sql          # datos iniciales (roles, permisos, admin, catalogo)
    seed_demo.sql     # datos de demostracion (opcional)
  app/
    __init__.py       # fabrica de la aplicacion Flask
    config.py         # configuracion (lee .env)
    db.py             # conexion pyodbc + consultas parametrizadas
    routes/main.py    # dashboard y rutas
    templates/        # vistas (Jinja2)
    static/           # css y js
```
