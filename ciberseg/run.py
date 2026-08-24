"""
=========================================================================
 Modulo: run.py
 PUNTO DE ENTRADA de CIBERSEG. Es el archivo que se ejecuta para
 levantar el servidor web.

 Ejecutar con:  python run.py
 Luego abrir:   http://127.0.0.1:5000

 POR QUE ESTE ARCHIVO ES TAN CORTO:
   Porque no contiene logica: su unico trabajo es pedirle a la fabrica
   (create_app, en app/__init__.py) que arme la aplicacion, y ponerla a
   escuchar peticiones. Toda la configuracion real vive dentro del
   paquete 'app'.
   Esta separacion es la que permite que la aplicacion se pueda arrancar
   de otras formas sin tocar nada: con un servidor de produccion como
   Waitress o Gunicorn, o desde un archivo de pruebas automatizadas.
=========================================================================
"""
from app import create_app
# Importa la funcion fabrica desde el paquete 'app' (o sea, desde el
# archivo app/__init__.py). Python trata como paquete a toda carpeta que
# contenga un __init__.py, y al escribir "from app import X" ejecuta ese
# archivo y busca X dentro.

app = create_app()
# AQUI se construye la aplicacion: se carga la configuracion del .env, se
# engancha el cierre de conexion a la base de datos y se registran los
# ocho blueprints de rutas. Todo eso ocurre dentro de create_app().
# La variable se llama 'app' por convencion: es el nombre que los
# servidores de produccion buscan por defecto (run:app).

if __name__ == "__main__":
    # Esta condicion es verdadera SOLO si el archivo se ejecuta
    # directamente (python run.py), y falsa si otro archivo lo importa.
    # Sirve para que el servidor no se levante solo por importar este
    # modulo, por ejemplo desde una prueba automatizada.
    app.run(debug=True, host="127.0.0.1", port=5000)
    # app.run() arranca el servidor de desarrollo incluido en Flask.
    #   debug=True  -> dos efectos: (1) recarga automatica, el servidor se
    #                  reinicia solo al guardar un archivo; y (2) muestra
    #                  el detalle del error en el navegador si algo falla.
    #                  NUNCA debe usarse en produccion: esa pantalla de
    #                  error permite ejecutar codigo en el servidor.
    #   host="127.0.0.1" -> solo acepta conexiones desde ESTA maquina. Con
    #                  "0.0.0.0" quedaria accesible desde toda la red local.
    #   port=5000   -> puerto donde escucha. Si estuviera ocupado, bastaria
    #                  con cambiar este numero.
