from fileinput import fileno
from flask import Flask, redirect, render_template, request, url_for, flash, send_from_directory, session
import pymysql
from flask import jsonify
from flask_cors  import CORS
import jinja2
from werkzeug.utils import secure_filename
import os
import io
from flask import send_file
import hashlib
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
import pymysql.cursors 
from pymysql.cursors import DictCursor




app = Flask(__name__)
CORS(app)
app.secret_key = 'your_secret_key'

# Configuración (aunque no guardamos en carpeta, puede ser útil si luego usas archivos)
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')


# ------------------ CONEXIÓN A BD ------------------
def connect_to_db():
    return pymysql.connect(
        host='localhost',
        user='root',
        password='',
        database='repositorio_cbc',
        cursorclass=DictCursor
    )

# ------------------ VER ARCHIVO DINÁMICO SEGÚN SU TIPO ------------------
@app.route("/ver_archivo/<int:id>")
def ver_archivo(id):
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute("SELECT archivo_pdf, titulo FROM documentos WHERE id = %s", (id,))
    resultado = cur.fetchone()
    cur.close()
    conn.close()

    if resultado and resultado['archivo_pdf']:
        extension = resultado['titulo'].split('.')[-1].lower()
        mimetipos = {
            'pdf': 'application/pdf',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'xls': 'application/vnd.ms-excel',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'zip': 'application/zip'
        }
        mimetype = mimetipos.get(extension, 'application/octet-stream')
        return send_file(
            io.BytesIO(resultado['archivo_pdf']),
            mimetype=mimetype,
            as_attachment=False,
            download_name=resultado['titulo']
        )
    else:
        return "Documento no encontrado", 404

# ------------------ DESCARGAR ARCHIVO ORIGINAL ------------------
@app.route("/descargar_archivo/<int:id>")
def descargar_archivo(id):
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute("SELECT archivo_pdf, titulo FROM documentos WHERE id = %s", (id,))
    resultado = cur.fetchone()
    cur.close()
    conn.close()

    if resultado and resultado['archivo_pdf']:
        return send_file(
            io.BytesIO(resultado['archivo_pdf']),
            as_attachment=True,
            download_name=resultado['titulo']
        )
    else:
        return "Documento no encontrado", 404

# ------------------ RUTAS BÁSICAS ------------------
@app.route('/')
def index():
    usuario = session.get('usuario', None)
    return render_template('index.html', usuario=usuario)

@app.route('/perfil')
def perfil():
    usuario = session.get('usuario', None)
    return render_template('perfil.html', usuario=usuario)

@app.route('/configuracion')
def configuracion():
    usuario = session.get('usuario', None)
    return render_template('configuracion.html', usuario=usuario)

@app.route('/guardar_configuracion', methods=['POST'])
def guardar_configuracion():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    usuario_id = session['usuario']['id']
    nombre = request.form['nombre']
    apellido = request.form['apellido']
    email = request.form['email']
    password_hash = request.form['password_hash']  # Puede venir vacía si no la cambia

    conn = connect_to_db()
    cur = conn.cursor()

    try:
        # Si se cambia la contraseña, se actualiza también
        if password_hash:
            password_hash = generate_password_hash(password_hash)
            cur.execute('''
                UPDATE usuarios
                SET nombre = %s, apellido = %s, email = %s, password_hash = %s
                WHERE id = %s
            ''', (nombre, apellido, email, password_hash, usuario_id))
        else:
            cur.execute('''
                UPDATE usuarios
                SET nombre = %s, apellido = %s, email = %s
                WHERE id = %s
            ''', (nombre, apellido, email, usuario_id))

        conn.commit()
        flash('Configuración actualizada correctamente.', 'success')

        # Actualiza sesión también
        session['usuario']['nombre'] = nombre
        session['usuario']['apellido'] = apellido
        session['usuario']['email'] = email

    except Exception as e:
        conn.rollback()
        flash(f'Error al guardar configuración: {e}', 'danger')
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('configuracion'))


@app.route('/asignar')
def asignar():
    usuario = session.get('usuario', None)

    conn = connect_to_db()
    cur = conn.cursor()

    cur.execute("SELECT u.*, r.nombre as rol_nombre FROM usuarios u JOIN roles r ON u.rol_id = r.id")
    usuarios = cur.fetchall()

    cur.execute("SELECT * FROM roles")
    roles = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('asignar.html', usuario=usuario, usuarios=usuarios, roles=roles)

@app.route('/cambiar_rol', methods=['POST'])
def cambiar_rol():
    conn = connect_to_db()
    cur = conn.cursor()

    usuario_id = request.form.get('usuario_id')
    rol_id = request.form.get('rol_id')

    try:
        cur.execute("UPDATE usuarios SET rol_id = %s WHERE id = %s", (rol_id, usuario_id))
        conn.commit()
        flash("Rol actualizado correctamente.")
    except Exception as e:
        conn.rollback()
        flash(f"Error al actualizar el rol: {e}")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('asignar'))

@app.route('/cambiar_tipo_documento', methods=['POST'])
def cambiar_tipo_documento():
    usuario_id = request.form.get('usuario_id')
    tipo_documento = request.form.get('tipo_documento')

    # Validar que no esté vacío
    if not tipo_documento:
        flash('Debes seleccionar un tipo de documento válido.', 'warning')
        return redirect(url_for('asignar'))

    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute("UPDATE usuarios SET tipo_identificacion = %s WHERE id = %s", (tipo_documento, usuario_id))
    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for('asignar'))

# FLASK
@app.route('/reportes')
def reportes():
    usuario = session.get('usuario', None)

    conn = connect_to_db()
    cur = conn.cursor(pymysql.cursors.DictCursor)  # Use DictCursor to get results as dictionaries

    try:
        cur.execute('''
            SELECT 
                d.id, 
                d.titulo, 
                d.fecha_subida, 
                d.fecha_finalizacion,
                COALESCE(GROUP_CONCAT(DISTINCT CONCAT(u.nombre, ' ', u.apellido) SEPARATOR ', '), 'Sin autor') AS autores,
                COALESCE(GROUP_CONCAT(DISTINCT c.nombre SEPARATOR ', '), 'Sin categoría') AS categorias
            FROM documentos d
            LEFT JOIN documento_autor da ON d.id = da.documento_id
            LEFT JOIN usuarios u ON da.usuario_id = u.id
            LEFT JOIN documento_categoria dc ON d.id = dc.documento_id
            LEFT JOIN categorias c ON dc.categoria_id = c.id
            GROUP BY d.id, d.titulo, d.fecha_subida, d.fecha_finalizacion
            ORDER BY d.fecha_subida DESC
        ''')
        
        proyectos = cur.fetchall()
        
        # Convert datetime objects to strings for template rendering
        for proyecto in proyectos:
            if proyecto['fecha_subida']:
                proyecto['fecha_subida'] = proyecto['fecha_subida'].strftime('%Y-%m-%d')
            if proyecto['fecha_finalizacion']:
                proyecto['fecha_finalizacion'] = proyecto['fecha_finalizacion'].strftime('%Y-%m-%d')
                
    except Exception as e:
        print(f"Error al obtener proyectos: {e}")
        proyectos = []
        
    finally:
        cur.close()
        conn.close()

    return render_template('reportes.html', proyectos=proyectos, usuario=usuario)
    
@app.route('/comunidad')
def comunidad():
    usuario = session.get('usuario', None)
    return render_template('Comunidad.html', usuario=usuario)
#--------------------RUTAS DE ESTADISTICAS ------------------   
@app.route('/estadisticas')
def estadisticas():
    usuario = session.get('usuario', None)
    return render_template('Estadisticas.html', usuario=usuario)
#---------------------RUTA DE API ESTADISTICAS ------------------

@app.route('/api/estadisticas')
def api_estadisticas():
    conn = connect_to_db()
    cur = conn.cursor()

    # Total de usuarios
    cur.execute("SELECT COUNT(*) as total FROM usuarios")
    row = cur.fetchone()
    total_users = list(row.values())[0] if row else 0

    # Total de documentos
    cur.execute("SELECT COUNT(*) as total FROM documentos")
    row = cur.fetchone()
    total_documents = list(row.values())[0] if row else 0

    # Descargas del último mes
    cur.execute("""
        SELECT COUNT(*) as total FROM descargas 
        WHERE fecha >= DATE_SUB(CURDATE(), INTERVAL 1 MONTH)
    """)
    row = cur.fetchone()
    monthly_downloads = list(row.values())[0] if row else 0

    cur.close()
    conn.close()

    return jsonify({
        "total_users": total_users,
        "total_documents": total_documents,
        "monthly_downloads": monthly_downloads
    })

@app.route('/equipo')
def equipo():
    usuario = session.get('usuario', None)
    return render_template('equipo.html', usuario=usuario)

@app.route('/api/top/usuarios')
def api_top_usuarios():
    conn = connect_to_db()
    cur = conn.cursor()

    query = """
        SELECT u.id, u.nombre, u.apellido,
               COUNT(da.documento_id) AS total_proyectos
        FROM usuarios u
        LEFT JOIN documento_autor da ON u.id = da.usuario_id
        GROUP BY u.id
        ORDER BY total_proyectos DESC
        LIMIT 10
    """

    cur.execute(query)
    usuarios = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify({
        'status': 'success',
        'data': usuarios
    })


@app.route('/top')
def top_usuarios():
    usuario = session.get('usuario', None)
    conn = connect_to_db()
    cur = conn.cursor()

    query = """
        SELECT u.id, u.nombre, u.apellido, u.rol_id,
               COUNT(da.documento_id) AS total_proyectos
        FROM usuarios u
        JOIN documento_autor da ON u.id = da.usuario_id
        JOIN documentos d ON d.id = da.documento_id
        GROUP BY u.id
        ORDER BY total_proyectos DESC
        LIMIT 10
    """

    cur.execute(query)
    top_usuarios = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('top_usuarios.html', top_usuarios=top_usuarios, usuario=usuario)


#--------------------RUTAS DE CONTACTO ------------------   
@app.route('/contacto', methods=['GET', 'POST'])
def contacto():
    usuario = session.get('usuario', None)
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        correo = request.form.get('correo')
        mensaje = request.form.get('mensaje')
        
        # Aquí podrías guardar el mensaje en la base de datos o enviarlo por email.
        print(f"Mensaje recibido de {nombre} ({correo}): {mensaje}")
        
        flash('Tu mensaje ha sido enviado correctamente.')
        return redirect(url_for('contacto'))

    return render_template('contacto.html', usuario=usuario)

@app.route('/almacenamiento')
def almacenamiento():
    usuario = session.get('usuario', None)
    return render_template('almacenamiento.html', usuario=usuario)

def tiene_permiso(nombre_permiso):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            rol_id = session.get('rol_id')
            if not rol_id:
                flash('Debes iniciar sesión')
                return redirect(url_for('login'))

            conn = connect_to_db()
            cur = conn.cursor()
            cur.execute('''
                SELECT 1 FROM rol_permiso rp
                JOIN permisos p ON rp.permiso_id = p.id
                WHERE rp.rol_id = %s AND p.nombre = %s
            ''', (rol_id, nombre_permiso))
            tiene = cur.fetchone()
            cur.close()
            conn.close()

            if tiene:
                return f(*args, **kwargs)
            else:
                flash('No tienes permiso para acceder a esta sección.')
                return redirect(url_for('index'))
        return decorated_function
    return decorator

@app.route('/subir_proyecto', methods=['GET', 'POST'])
@tiene_permiso('subir_documentos')
def subir_proyecto():
    if request.method == 'POST':
        conn = connect_to_db()
        cur = conn.cursor()

        try:
            titulo = request.form['titulo']
            descripcion = request.form['descripcion']
            palabras_clave = request.form['palabras_clave']
            competencias = request.form['competencias']
            enlace_git = request.form.get('enlace_git', '')
            enlace_drive = request.form.get('enlace_drive', '')
            fecha_subida = request.form['fecha_subida']
            fecha_finalizacion = request.form['fecha_finalizacion']
            archivo = request.files['archivo']

            if archivo.filename == '':
                flash('No se seleccionó ningún archivo.')
                return redirect(request.url)

            archivo_binario = archivo.read()
            nombre_archivo = archivo.filename
            tipo_mime = archivo.mimetype

            autores = request.form.getlist('autores')
            categorias_seleccionadas = request.form.getlist('categorias')

            # Insertar documento
            cur.execute('''
                INSERT INTO documentos (
                    titulo, descripcion, palabrasclave, archivo_pdf,
                    competencias, enlace_git, enlace_drive, fecha_subida, fecha_finalizacion,
                    nombre_archivo, tipo_mime
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (titulo, descripcion, palabras_clave, archivo_binario,
                  competencias, enlace_git, enlace_drive, fecha_subida, fecha_finalizacion,
                  nombre_archivo, tipo_mime))

            documento_id = cur.lastrowid  # Correcto para pymysql o mysql.connector

            # Insertar autores
            for autor_id in autores:
                try:
                    autor_id = int(autor_id)
                    cur.execute('SELECT id FROM usuarios WHERE id = %s', (autor_id,))
                    if cur.fetchone():
                        cur.execute('INSERT INTO documento_autor (documento_id, usuario_id) VALUES (%s, %s)', (documento_id, autor_id))
                except ValueError:
                    continue

            # Insertar categorías
            for categoria_id in categorias_seleccionadas:
                try:
                    categoria_id = int(categoria_id)
                    cur.execute('SELECT id FROM categorias WHERE id = %s', (categoria_id,))
                    if cur.fetchone():
                        cur.execute('INSERT INTO documento_categoria (documento_id, categoria_id) VALUES (%s, %s)', (documento_id, categoria_id))
                except ValueError:
                    continue

            conn.commit()
            flash("¡El proyecto se subió con éxito!", "success")
            return redirect(url_for('subir_proyecto'))

        except Exception as e:
            print("Error al subir proyecto:", e)  # Muy importante para depurar
            conn.rollback()
            flash(f'Error al subir proyecto: {e}')
        finally:
            cur.close()
            conn.close()

    # Método GET
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute('SELECT id, nombre, apellido FROM usuarios WHERE nombre IS NOT NULL AND apellido IS NOT NULL')
    autores = cur.fetchall()
    cur.execute('SELECT id, nombre FROM categorias')
    categorias = cur.fetchall()
    cur.close()
    conn.close()

    usuario = session.get('usuario', None)
    return render_template('subir_proyecto.html', usuario=usuario, autores=autores, categorias=categorias)


#--------------------RUTA CONSULTA -------------------
@app.route('/consulta')
def consulta():
    usuario = session.get('usuario', None)
    tipo = request.args.get('tipo')
    termino = request.args.get('q')

    conn = connect_to_db()
    cur = conn.cursor()

    base_query = '''
        SELECT d.id, d.titulo, d.fecha_subida, d.fecha_finalizacion,
               GROUP_CONCAT(DISTINCT CONCAT(u.nombre, ' ', u.apellido) SEPARATOR ', ') AS autores,
               GROUP_CONCAT(DISTINCT c.nombre SEPARATOR ', ') AS categorias
        FROM documentos d
        LEFT JOIN documento_autor da ON d.id = da.documento_id
        LEFT JOIN usuarios u ON da.usuario_id = u.id
        LEFT JOIN documento_categoria dc ON d.id = dc.documento_id
        LEFT JOIN categorias c ON dc.categoria_id = c.id
    '''

    filters = []
    values = []

    if tipo == 'titulo' and termino:
        filters.append("d.titulo LIKE %s")
        values.append(f"%{termino}%")
    elif tipo == 'autor' and termino:
        filters.append("CONCAT(u.nombre, ' ', u.apellido) LIKE %s")
        values.append(f"%{termino}%")
    elif tipo == 'categoria' and termino:
        filters.append("c.nombre LIKE %s")
        values.append(f"%{termino}%")
    elif tipo == 'fecha' and termino:
        filters.append("d.fecha_subida = %s")
        values.append(termino)

    if filters:
        base_query += " WHERE " + " AND ".join(filters)

    base_query += " GROUP BY d.id ORDER BY d.fecha_subida DESC"

    cur.execute(base_query, values)
    proyectos = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('consulta.html', proyectos=proyectos, usuario=usuario)

# ------------------ LOGIN ------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    usuario = session.get('usuario', None)
    if request.method == 'POST':
        email = request.form.get('email')
        contrasena = request.form.get('password')

        conn = connect_to_db()
        cur = conn.cursor()

        cur.execute("""
            SELECT u.*, c.password_hash, c.intentos_fallidos, c.bloqueado 
            FROM usuarios u 
            JOIN credenciales c ON u.id = c.usuario_id
            WHERE c.correo_institucional = %s
        """, (email,))
        usuario = cur.fetchone()

        if usuario:
            if usuario['bloqueado']:
                cur.close()
                conn.close()
                return "Cuenta bloqueada por múltiples intentos fallidos."

            if check_password_hash(usuario['password_hash'], contrasena):
                cur.execute("UPDATE credenciales SET intentos_fallidos = 0, ultimo_login = NOW() WHERE usuario_id = %s", (usuario['id'],))
                conn.commit()

                if not usuario.get('foto_perfil'):
                    hash_email = hashlib.md5(email.encode()).hexdigest()
                    usuario['foto_perfil'] = f"https://www.gravatar.com/avatar/{hash_email}?d=identicon"

                session['usuario'] = usuario
                session['rol_id'] = usuario['rol_id']

                cur.execute("INSERT INTO logs (usuario_id, accion) VALUES (%s, %s)", (usuario['id'], 'Inicio de sesión exitoso'))
                conn.commit()

                cur.close()
                conn.close()
                return redirect(url_for('index'))
            else:
                nuevos_intentos = usuario['intentos_fallidos'] + 1
                bloqueado = nuevos_intentos >= 5

                cur.execute("""
                    UPDATE credenciales 
                    SET intentos_fallidos = %s, bloqueado = %s 
                    WHERE usuario_id = %s
                """, (nuevos_intentos, bloqueado, usuario['id']))
                conn.commit()

                cur.close()
                conn.close()
                return "Contraseña incorrecta. Intento {}/5.".format(nuevos_intentos)
        else:
            cur.close()
            conn.close()
            return "Correo no registrado."

    return render_template('login.html', usuario=usuario)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/olvidar_contrasena')
def olvidar_contrasena():
    return render_template('olvidar_contrasena.html')

# ------------------ REGISTRO USUARIOS ------------------
@app.route('/registro', methods=['GET', 'POST'])
def registro():
    conn = connect_to_db()
    cur = conn.cursor()

    if request.method == 'POST':
        # Captura de datos desde el formulario
        nombre = request.form['nombre']
        apellido = request.form['apellido']
        email = request.form['email']
        telefono = request.form['telefono']
        institucion = request.form['institucion']
        programa = request.form['programa']
        tipo_identificacion = request.form['tipo_identificacion']
        numero_identificacion = request.form['numero_identificacion']
        rol_id = request.form.get('rol_id')  # Evita KeyError si algo falla
        password = request.form['password']

        password_hash = generate_password_hash(password)

        try:
            # Insertar usuario
            cur.execute('''
                INSERT INTO usuarios (nombre, apellido, email, telefono, institucion, programa, tipo_identificacion, numero_identificacion, rol_id, password_hash  )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (nombre, apellido, email, telefono, institucion, programa, tipo_identificacion, numero_identificacion, rol_id, password_hash))
            
            usuario_id = conn.insert_id()

            # Insertar credenciales asociadas
            cur.execute('''
                INSERT INTO credenciales (usuario_id, correo_institucional, password_hash)
                VALUES (%s, %s, %s)
            ''', (usuario_id, email, password_hash))

            conn.commit()
            cur.close()
            conn.close()

            flash('Usuario registrado correctamente')
            return redirect(url_for('login'))

        except Exception as e:
            conn.rollback()
            cur.close()
            conn.close()
            flash(f'Error al registrar: {e}')
            return redirect(url_for('registro'))

    else:
        # No need to load roles anymore since we're setting a default role
        cur.close()
        conn.close()

        usuario = session.get('usuario', None)
        return render_template('registro.html', usuario=usuario)

#------------------TIENE PERMISO------------------
def tiene_permiso(nombre_permiso):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            rol_id = session.get('rol_id')
            if not rol_id:
                flash('Debes iniciar sesión')
                return redirect(url_for('login'))

            conn = connect_to_db()
            cur = conn.cursor()
            cur.execute('''
                SELECT 1 FROM rol_permiso rp
                JOIN permisos p ON rp.permiso_id = p.id
                WHERE rp.rol_id = %s AND p.nombre = %s
            ''', (rol_id, nombre_permiso))
            tiene = cur.fetchone()
            cur.close()
            conn.close()

            if tiene:
                return f(*args, **kwargs)
            else:
                flash('No tienes permiso para acceder a esta sección.')
                return redirect(url_for('index'))
        return decorated_function
    return decorator
# ------------------ SUBIR Y LISTAR PROYECTOS ------------------
@app.route('/formacion', methods=['GET'])
@tiene_permiso('subir_documentos')  # O cambia el permiso si solo necesitas ver
def formacion():
    conn = connect_to_db()
    cur = conn.cursor()

    cur.execute('''
SELECT d.id, d.titulo, d.competencias, d.fecha_subida, d.fecha_finalizacion,
       GROUP_CONCAT(DISTINCT CONCAT(u.nombre, ' ', u.apellido) SEPARATOR ', ') AS autores,
       GROUP_CONCAT(DISTINCT c.nombre SEPARATOR ', ') AS categorias
FROM documentos d
LEFT JOIN documento_autor da ON d.id = da.documento_id
LEFT JOIN usuarios u ON da.usuario_id = u.id
LEFT JOIN documento_categoria dc ON d.id = dc.documento_id
LEFT JOIN categorias c ON dc.categoria_id = c.id
GROUP BY d.id
''')


    documentos = cur.fetchall()

    cur.execute('SELECT id, nombre, apellido FROM usuarios WHERE nombre IS NOT NULL AND apellido IS NOT NULL')
    autores = cur.fetchall()

    cur.execute('SELECT id, nombre FROM categorias')
    categorias = cur.fetchall()

    cur.close()
    conn.close()
    usuario = session.get('usuario', None)
    return render_template('formacion.html', documentos=documentos, autores=autores, categorias=categorias, usuario=usuario)

@app.route('/ver_proyecto/<int:proyecto_id>')
def ver_proyecto(proyecto_id):
    conn = connect_to_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM documentos WHERE id = %s", (proyecto_id,))
    proyecto = cur.fetchone()

    if not proyecto:
        cur.close()
        conn.close()
        return "Proyecto no encontrado", 404

    cur.execute('''
        SELECT u.nombre, u.apellido
        FROM documento_autor da
        JOIN usuarios u ON da.usuario_id = u.id
        WHERE da.documento_id = %s
    ''', (proyecto_id,))
    rows = cur.fetchall()
    autores = [f"{r['nombre'] or 'Nombre'} {r['apellido'] or 'Apellido'}" for r in rows]
    proyecto['autores'] = ', '.join(autores) if autores else 'N/A'

    cur.execute('''
        SELECT c.nombre
        FROM documento_categoria dc
        JOIN categorias c ON dc.categoria_id = c.id
        WHERE dc.documento_id = %s
    ''', (proyecto_id,))
    categorias = [row['nombre'] or 'Categoría' for row in cur.fetchall()]
    proyecto['categorias'] = ', '.join(categorias) if categorias else 'N/A'

    if 'usuario' in session:
        cur.execute(
            "INSERT INTO visualizaciones (documento_id, usuario_id) VALUES (%s, %s)",
            (proyecto_id, session['usuario']['id'])
        )
        conn.commit()

    cur.close()
    conn.close()
    usuario = session.get('usuario', None)
    return render_template('ver_proyecto.html', proyecto=proyecto, usuario=usuario)

# ------------------ DESCARGAR PDF DESDE BLOB ------------------
@app.route("/ver_pdf/<int:id>")
def ver_pdf(id):
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute("SELECT archivo_pdf, nombre_archivo, tipo_mime FROM documentos WHERE id = %s", (id,))
    resultado = cur.fetchone()
    cur.close()
    conn.close()

    if resultado and resultado['archivo_pdf']:
        return send_file(
            io.BytesIO(resultado['archivo_pdf']),
            mimetype=resultado['tipo_mime'] or 'application/octet-stream',
            as_attachment=True,
            download_name=resultado['nombre_archivo'] or f'documento_{id}'
        )
    else:
        return "Documento no encontrado", 404

#-------------------RUTA ELIMINAR PROYECTO-------------------
@app.route('/eliminar_proyecto/<int:proyecto_id>', methods=['POST'])
@tiene_permiso('eliminar_documentos')
def eliminar_proyecto(proyecto_id):
    conn = connect_to_db()
    cur = conn.cursor()

    try:
        # Eliminar primero las relaciones
        cur.execute('DELETE FROM documento_autor WHERE documento_id = %s', (proyecto_id,))
        cur.execute('DELETE FROM documento_categoria WHERE documento_id = %s', (proyecto_id,))
        cur.execute('DELETE FROM visualizaciones WHERE documento_id = %s', (proyecto_id,))

        # Luego el documento principal
        cur.execute('DELETE FROM documentos WHERE id = %s', (proyecto_id,))

        conn.commit()
        flash('Proyecto eliminado correctamente.')
    except Exception as e:
        conn.rollback()
        flash(f'Error al eliminar proyecto: {e}')
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('formacion'))
#----------------- FIN DE TODAS LAS RUTAS DE FORMACION-------------------

#-------------------TODAS LAS RUTAS QUE TENGAS QUE VER CON INVESTIGACION------------------
@app.route('/investigacion', methods=['GET', 'POST'])
@tiene_permiso('subir_documentos')
def investigacion():
    if request.method == 'POST':
        conn = connect_to_db()
        cur = conn.cursor()

        titulo = request.form['titulo']
        descripcion = request.form['descripcion']
        palabras_clave = request.form['palabras_clave']
        competencias = request.form['competencias']
        enlace_git = request.form.get('enlace_git', '')
        enlace_drive = request.form.get('enlace_drive', '')
        fecha_subida = request.form['fecha_subida']
        fecha_finalizacion = request.form['fecha_finalizacion']
        archivo = request.files['archivo']
        archivo_binario = archivo.read()

        autores = request.form.getlist('autores')
        categorias_seleccionadas = request.form.getlist('categorias')

        try:
            cur.execute('''
                INSERT INTO documentos (
                    titulo, descripcion, palabrasclave, archivo_pdf,
                    competencias, enlace_git, enlace_drive, fecha_subida, fecha_finalizacion
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (titulo, descripcion, palabras_clave, archivo_binario,
                  competencias, enlace_git, enlace_drive, fecha_subida, fecha_finalizacion))

            documento_id = cur.lastrowid  # ← CORRECTO

            for autor_id in autores:
                try:
                    autor_id = int(autor_id)
                    cur.execute('SELECT id FROM usuarios WHERE id = %s', (autor_id,))
                    if cur.fetchone():
                        cur.execute('INSERT INTO documento_autor (documento_id, usuario_id) VALUES (%s, %s)', (documento_id, autor_id))
                except ValueError:
                    pass

            for categoria_id in categorias_seleccionadas:
                try:
                    categoria_id = int(categoria_id)
                    cur.execute('SELECT id FROM categorias WHERE id = %s', (categoria_id,))
                    if cur.fetchone():
                        cur.execute('INSERT INTO documento_categoria (documento_id, categoria_id) VALUES (%s, %s)', (documento_id, categoria_id))
                except ValueError:
                    pass

            conn.commit()
            flash('Proyecto de investigación subido exitosamente.')
        except Exception as e:
            conn.rollback()
            flash(f'Error al subir proyecto: {e}')
        finally:
            cur.close()
            conn.close()

        return redirect(url_for('investigacion'))

    # GET: cargar datos para el formulario y lista de proyectos
    conn = connect_to_db()
    cur = conn.cursor()

    cur.execute('''
        SELECT d.id, d.titulo, d.competencias, d.fecha_subida, d.fecha_finalizacion,
               GROUP_CONCAT(DISTINCT CONCAT(u.nombre, ' ', u.apellido) SEPARATOR ', ') AS autores,
               GROUP_CONCAT(DISTINCT c.nombre SEPARATOR ', ') AS categorias
        FROM documentos d
        LEFT JOIN documento_autor da ON d.id = da.documento_id
        LEFT JOIN usuarios u ON da.usuario_id = u.id
        LEFT JOIN documento_categoria dc ON d.id = dc.documento_id
        LEFT JOIN categorias c ON dc.categoria_id = c.id
        GROUP BY d.id
        ORDER BY d.fecha_subida DESC
    ''')
    documentos = cur.fetchall()

    cur.execute('SELECT id, nombre, apellido FROM usuarios WHERE nombre IS NOT NULL AND apellido IS NOT NULL')
    autores = cur.fetchall()

    cur.execute('SELECT id, nombre FROM categorias')
    categorias = cur.fetchall()

    cur.close()
    conn.close()
    usuario = session.get('usuario', None)
    return render_template('investigacion.html', documentos=documentos, autores=autores, categorias=categorias, usuario=usuario)

# ------------------ VER DETALLE DE PROYECTO INVESTIGACION ------------------
@app.route('/proyecto_investigacion/<int:proyecto_id>')
def ver_proyecto_investigacion(proyecto_id):
    conn = connect_to_db()
    cur = conn.cursor()

    # Obtener el proyecto
    cur.execute("SELECT * FROM documentos WHERE id = %s", (proyecto_id,))
    proyecto = cur.fetchone()

    if not proyecto:
        cur.close()
        conn.close()
        return "Proyecto no encontrado", 404

    # Autores
    cur.execute('''
        SELECT u.nombre, u.apellido
        FROM documento_autor da
        JOIN usuarios u ON da.usuario_id = u.id
        WHERE da.documento_id = %s
    ''', (proyecto_id,))
    rows = cur.fetchall()
    autores = [f"{r['nombre'] or 'Nombre'} {r['apellido'] or 'Apellido'}" for r in rows]
    proyecto['autores'] = ', '.join(autores) if autores else 'N/A'

    # Categorías
    cur.execute('''
        SELECT c.nombre
        FROM documento_categoria dc
        JOIN categorias c ON dc.categoria_id = c.id
        WHERE dc.documento_id = %s
    ''', (proyecto_id,))
    categorias = [row['nombre'] or 'Categoría' for row in cur.fetchall()]
    proyecto['categorias'] = ', '.join(categorias) if categorias else 'N/A'

    # Visualización
    if 'usuario' in session:
        cur.execute(
            "INSERT INTO visualizaciones (documento_id, usuario_id) VALUES (%s, %s)",
            (proyecto_id, session['usuario']['id'])
        )
        conn.commit()

    cur.close()
    conn.close()

    return render_template('ver_proyecto_investigacion.html', proyecto=proyecto)

#--------------------- DESCARGAR PROYECTO INVESTIGACION DESDE BLOD -----------------
@app.route("/descargar_pdf_investigacion/<int:id>")
@tiene_permiso('descargar_documentos')  # <-- Esta línea agrega la protección por permisos
def descargar_pdf_investigacion(id):
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute("SELECT archivo_pdf FROM documentos WHERE id = %s", (id,))
    resultado = cur.fetchone()
    cur.close()
    conn.close()

    if resultado and resultado['archivo_pdf']:
        pdf_data = resultado['archivo_pdf']
        return send_file(
            io.BytesIO(pdf_data),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'investigacion_{id}.pdf'
        )
    else:
        return "Documento no encontrado", 404

# ------------------ VER PDF INVESTIGACION ------------------
@app.route("/ver_pdf_investigacion/<int:id>")
@tiene_permiso('ver_documentos')  # <-- Esta línea agrega la protección por permisos
def ver_pdf_investigacion(id):
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute("SELECT archivo_pdf FROM documentos WHERE id = %s", (id,))
    resultado = cur.fetchone()
    cur.close()
    conn.close()

    if resultado and resultado['archivo_pdf']:
        pdf_data = resultado['archivo_pdf']
        return send_file(
            io.BytesIO(pdf_data),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'investigacion_{id}.pdf'
        )
    else:
        return "Documento no encontrado", 404

# ------------------ ELIMINAR INVESTIGACION ------------------
@app.route('/eliminar_investigacion/<int:proyecto_id>', methods=['POST'])
@tiene_permiso('eliminar_documentos')
def eliminar_investigacion(proyecto_id):
    conn = connect_to_db()
    cur = conn.cursor()

    try:
        # Relaciones primero
        cur.execute('DELETE FROM documento_autor WHERE documento_id = %s', (proyecto_id,))
        cur.execute('DELETE FROM documento_categoria WHERE documento_id = %s', (proyecto_id,))
        cur.execute('DELETE FROM visualizaciones WHERE documento_id = %s', (proyecto_id,))

        # Documento
        cur.execute('DELETE FROM documentos WHERE id = %s', (proyecto_id,))

        conn.commit()
        flash('Investigación eliminada correctamente.')
    except Exception as e:
        conn.rollback()
        flash(f'Error al eliminar investigación: {e}')
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('investigacion'))
#--------------------- FIN DE TODAS LAS RUTAS DE INVESTIGACION -----------------

# ------------------ SUBIR / VER EMPRENDIMIENTOS ------------------
@app.route('/emprendimiento', methods=['GET', 'POST'])
@tiene_permiso('subir_documentos')
def emprendimiento():
    if request.method == 'POST':
        conn = connect_to_db()
        cur = conn.cursor()

        titulo = request.form['titulo']
        descripcion = request.form['descripcion']
        palabras_clave = request.form['palabras_clave']
        competencias = request.form['competencias']
        enlace_git = request.form.get('enlace_git', '')
        enlace_drive = request.form.get('enlace_drive', '')
        fecha_subida = request.form['fecha_subida']
        fecha_finalizacion = request.form['fecha_finalizacion']
        archivo = request.files['archivo']
        archivo_pdf = archivo.read()

        autores = request.form.getlist('autores')
        categorias_seleccionadas = request.form.getlist('categorias')

        try:
            cur.execute('''
                INSERT INTO documentos (
                    titulo, descripcion, palabrasclave, archivo_pdf,
                    competencias, enlace_git, enlace_drive, fecha_subida, fecha_finalizacion
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (titulo, descripcion, palabras_clave, archivo_pdf,
                  competencias, enlace_git, enlace_drive, fecha_subida, fecha_finalizacion))

            documento_id = cur.lastrowid

            for autor_id in autores:
                try:
                    autor_id = int(autor_id)
                    cur.execute('SELECT id FROM usuarios WHERE id = %s', (autor_id,))
                    if cur.fetchone():
                        cur.execute('INSERT INTO documento_autor (documento_id, usuario_id) VALUES (%s, %s)', (documento_id, autor_id))
                except ValueError:
                    pass

            for categoria_id in categorias_seleccionadas:
                try:
                    categoria_id = int(categoria_id)
                    cur.execute('SELECT id FROM categorias WHERE id = %s', (categoria_id,))
                    if cur.fetchone():
                        cur.execute('INSERT INTO documento_categoria (documento_id, categoria_id) VALUES (%s, %s)', (documento_id, categoria_id))
                except ValueError:
                    pass

            conn.commit()
            flash('Proyecto de emprendimiento subido exitosamente.')
        except Exception as e:
            conn.rollback()
            flash(f'Error al subir proyecto: {e}')
        finally:
            cur.close()
            conn.close()

        return redirect(url_for('emprendimiento'))

    # GET: mostrar formulario
    conn = connect_to_db()
    cur = conn.cursor()

    cur.execute('SELECT id, nombre, apellido FROM usuarios WHERE nombre IS NOT NULL AND apellido IS NOT NULL')
    autores = cur.fetchall()

    cur.execute('SELECT id, nombre FROM categorias')
    categorias = cur.fetchall()

    cur.execute('''
        SELECT d.id, d.titulo, d.competencias, d.fecha_subida, d.fecha_finalizacion,
               GROUP_CONCAT(DISTINCT CONCAT(u.nombre, ' ', u.apellido) SEPARATOR ', ') AS autores,
               GROUP_CONCAT(DISTINCT c.nombre SEPARATOR ', ') AS categorias
        FROM documentos d
        LEFT JOIN documento_autor da ON d.id = da.documento_id
        LEFT JOIN usuarios u ON da.usuario_id = u.id
        LEFT JOIN documento_categoria dc ON d.id = dc.documento_id
        LEFT JOIN categorias c ON dc.categoria_id = c.id
        GROUP BY d.id
        ORDER BY d.fecha_subida DESC
    ''')
    documentos = cur.fetchall()

    cur.close()
    conn.close()
    usuario = session.get('usuario', None)
    return render_template('emprendimiento.html', autores=autores, categorias=categorias, documentos=documentos, usuario=usuario)

# ------------------ VER DETALLE DE EMPRENDIMIENTO ------------------
@app.route('/proyecto_emprendimiento/<int:proyecto_id>')
def ver_proyecto_emprendimiento(proyecto_id):
    conn = connect_to_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM documentos WHERE id = %s", (proyecto_id,))
    proyecto = cur.fetchone()

    if not proyecto:
        cur.close()
        conn.close()
        return "Proyecto no encontrado", 404

    cur.execute('''
        SELECT u.nombre, u.apellido
        FROM documento_autor da
        JOIN usuarios u ON da.usuario_id = u.id
        WHERE da.documento_id = %s
    ''', (proyecto_id,))
    rows = cur.fetchall()
    autores = [f"{r['nombre'] or 'Nombre'} {r['apellido'] or 'Apellido'}" for r in rows]
    proyecto['autores'] = ', '.join(autores) if autores else 'N/A'

    cur.execute('''
        SELECT c.nombre
        FROM documento_categoria dc
        JOIN categorias c ON dc.categoria_id = c.id
        WHERE dc.documento_id = %s
    ''', (proyecto_id,))
    categorias = [row['nombre'] or 'Categoría' for row in cur.fetchall()]
    proyecto['categorias'] = ', '.join(categorias) if categorias else 'N/A'

    if 'usuario' in session:
        cur.execute(
            "INSERT INTO visualizaciones_emprendimiento (emprendimiento_id, usuario_id) VALUES (%s, %s)",
            (proyecto_id, session['usuario']['id'])
        )
        conn.commit()

    cur.close()
    conn.close()

    return render_template('ver_proyecto_emprendimiento.html', proyecto=proyecto)

# ------------------ DESCARGAR PDF EMPRENDIMIENTO ------------------
@app.route("/descargar_pdf_emprendimiento/<int:id>")    
@tiene_permiso('descargar_documentos')
def descargar_pdf_emprendimiento(id):
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute("SELECT archivo_pdf FROM documentos WHERE id = %s", (id,))
    resultado = cur.fetchone()
    cur.close()
    conn.close()

    if resultado and resultado['archivo_pdf']:
        pdf_data = resultado['archivo_pdf']
        return send_file(
            io.BytesIO(pdf_data),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'emprendimiento_{id}.pdf'
        )
    else:
        return "Documento no encontrado", 404

# ------------------ VER PDF EMPRENDIMIENTO ------------------
@app.route("/ver_pdf_emprendimiento/<int:id>")
@tiene_permiso('ver_documentos')
def ver_pdf_emprendimiento(id):
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute("SELECT archivo_pdf FROM documentos WHERE id = %s", (id,))
    resultado = cur.fetchone()
    cur.close()
    conn.close()

    if resultado and resultado['archivo_pdf']:
        pdf_data = resultado['archivo_pdf']
        return send_file(
            io.BytesIO(pdf_data),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'emprendimiento_{id}.pdf'
        )
    else:
        return "Documento no encontrado", 404

# ------------------ ELIMINAR EMPRENDIMIENTO ------------------
@app.route('/eliminar_emprendimiento/<int:proyecto_id>', methods=['POST'])
@tiene_permiso('eliminar_documentos')
def eliminar_emprendimiento(proyecto_id):
    conn = connect_to_db()
    cur = conn.cursor()

    try:
        cur.execute('DELETE FROM documento_autor WHERE documento_id = %s', (proyecto_id,))
        cur.execute('DELETE FROM documento_categoria WHERE documento_id = %s', (proyecto_id,))
        cur.execute('DELETE FROM visualizaciones WHERE documento_id = %s', (proyecto_id,))
        cur.execute('DELETE FROM documentos WHERE id = %s', (proyecto_id,))
        conn.commit()
        flash('Emprendimiento eliminado correctamente.')
    except Exception as e:
        conn.rollback()
        flash(f'Error al eliminar emprendimiento: {e}')
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('emprendimiento'))

#------------------ SUBIR SOFTWARE ------------------
@app.route('/software', methods=['GET', 'POST'])
@tiene_permiso('subir_documentos')
def software():
    if request.method == 'POST':
        conn = connect_to_db()
        cur = conn.cursor()

        titulo = request.form['titulo']
        descripcion = request.form['descripcion']
        palabras_clave = request.form['palabras_clave']
        competencias = request.form['competencias']
        enlace_git = request.form.get('enlace_git', '')
        enlace_drive = request.form.get('enlace_drive', '')
        fecha_subida = request.form['fecha_subida']
        fecha_finalizacion = request.form['fecha_finalizacion']
        archivo = request.files['archivo']
        archivo_pdf = archivo.read()

        autores = request.form.getlist('autores')
        categorias_seleccionadas = request.form.getlist('categorias')

        try:
            cur.execute('''
                INSERT INTO documentos (
                    titulo, descripcion, palabrasclave, archivo_pdf,
                    competencias, enlace_git, enlace_drive, fecha_subida, fecha_finalizacion
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (titulo, descripcion, palabras_clave, archivo_pdf,
                  competencias, enlace_git, enlace_drive, fecha_subida, fecha_finalizacion))

            documento_id = cur.lastrowid

            for autor_id in autores:
                try:
                    autor_id = int(autor_id)
                    cur.execute('SELECT id FROM usuarios WHERE id = %s', (autor_id,))
                    if cur.fetchone():
                        cur.execute('INSERT INTO documento_autor (documento_id, usuario_id) VALUES (%s, %s)', (documento_id, autor_id))
                except ValueError:
                    pass

            for categoria_id in categorias_seleccionadas:
                try:
                    categoria_id = int(categoria_id)
                    cur.execute('SELECT id FROM categorias WHERE id = %s', (categoria_id,))
                    if cur.fetchone():
                        cur.execute('INSERT INTO documento_categoria (documento_id, categoria_id) VALUES (%s, %s)', (documento_id, categoria_id))
                except ValueError:
                    pass

            conn.commit()
            flash('Proyecto subido exitosamente.')
        except Exception as e:
            conn.rollback()
            flash(f'Error al subir proyecto: {e}')
        finally:
            cur.close()
            conn.close()

        return redirect(url_for('software'))

    # GET: cargar formulario y documentos
    conn = connect_to_db()
    cur = conn.cursor()

    cur.execute('SELECT id, nombre, apellido FROM usuarios WHERE nombre IS NOT NULL AND apellido IS NOT NULL')
    autores = cur.fetchall()

    cur.execute('SELECT id, nombre FROM categorias')
    categorias = cur.fetchall()

    cur.execute('''
        SELECT d.id, d.titulo, d.competencias, d.fecha_subida, d.fecha_finalizacion,
               GROUP_CONCAT(DISTINCT CONCAT(u.nombre, ' ', u.apellido) SEPARATOR ', ') AS autores,
               GROUP_CONCAT(DISTINCT c.nombre SEPARATOR ', ') AS categorias
        FROM documentos d
        LEFT JOIN documento_autor da ON d.id = da.documento_id
        LEFT JOIN usuarios u ON da.usuario_id = u.id
        LEFT JOIN documento_categoria dc ON d.id = dc.documento_id
        LEFT JOIN categorias c ON dc.categoria_id = c.id
        GROUP BY d.id
        ORDER BY d.fecha_subida DESC
    ''')
    documentos = cur.fetchall()

    cur.close()
    conn.close()
    usuario = session.get('usuario', None)
    return render_template('software.html', autores=autores, categorias=categorias, documentos=documentos, usuario=usuario)

# ------------------ VER DETALLE DE PROYECTO ------------------
@app.route('/ver_software/<int:software_id>')
def ver_software(software_id):
    conn = connect_to_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM documentos WHERE id = %s", (software_id,))
    software = cur.fetchone()

    if not software:
        cur.close()
        conn.close()
        return "Proyecto no encontrado", 404

    cur.execute('''
        SELECT u.nombre, u.apellido
        FROM documento_autor da
        JOIN usuarios u ON da.usuario_id = u.id
        WHERE da.documento_id = %s
    ''', (software_id,))
    rows = cur.fetchall()
    autores = [f"{r['nombre'] or 'Nombre'} {r['apellido'] or 'Apellido'}" for r in rows]
    software['autores'] = ', '.join(autores) if autores else 'N/A'

    cur.execute('''
        SELECT c.nombre
        FROM documento_categoria dc
        JOIN categorias c ON dc.categoria_id = c.id
        WHERE dc.documento_id = %s
    ''', (software_id,))
    categorias = [row['nombre'] or 'Categoría' for row in cur.fetchall()]
    software['categorias'] = ', '.join(categorias) if categorias else 'N/A'

    if 'usuario' in session:
        cur.execute(
            "INSERT INTO visualizaciones (documento_id, usuario_id) VALUES (%s, %s)",
            (software_id, session['usuario']['id'])
        )
        conn.commit()

    cur.close()
    conn.close()

    return render_template('ver_proyecto.html', proyecto=software)

# ------------------ DESCARGAR PDF PROYECTO ------------------
@app.route("/descargar_pdf_software/<int:id>")
@tiene_permiso('descargar_documentos')
def descargar_pdf_software(id):
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute("SELECT archivo_pdf FROM documentos WHERE id = %s", (id,))
    resultado = cur.fetchone()
    cur.close()
    conn.close()

    if resultado and resultado['archivo_pdf']:
        pdf_data = resultado['archivo_pdf']
        return send_file(
            io.BytesIO(pdf_data),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'software_{id}.pdf'
        )
    else:
        return "Documento no encontrado", 404

# ------------------ VER PDF PROYECTO ------------------
@app.route("/ver_pdf_software/<int:id>")
@tiene_permiso('ver_documentos')
def ver_pdf_software(id):
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute("SELECT archivo_pdf FROM documentos WHERE id = %s", (id,))
    resultado = cur.fetchone()
    cur.close()
    conn.close()

    if resultado and resultado['archivo_pdf']:
        pdf_data = resultado['archivo_pdf']
        return send_file(
            io.BytesIO(pdf_data),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'software_{id}.pdf'
        )
    else:
        return "Documento no encontrado", 404

# ------------------ ELIMINAR PROYECTO ------------------
@app.route('/eliminar_software/<int:software_id>', methods=['POST'])
@tiene_permiso('eliminar_documentos')
def eliminar_software(software_id):
    conn = connect_to_db()
    cur = conn.cursor()

    try:
        cur.execute('DELETE FROM documento_autor WHERE documento_id = %s', (software_id,))
        cur.execute('DELETE FROM documento_categoria WHERE documento_id = %s', (software_id,))
        cur.execute('DELETE FROM visualizaciones WHERE documento_id = %s', (software_id,))
        cur.execute('DELETE FROM documentos WHERE id = %s', (software_id,))
        conn.commit()
        flash('Software eliminado correctamente.')
    except Exception as e:
        conn.rollback()
        flash(f'Error al eliminar software: {e}')
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('software'))



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
