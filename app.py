from flask import Flask, request, jsonify
import oracledb
from datetime import datetime
import base64
import sys
import os

try:
    from Utils.constants import DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_SERVICE, WEB_SERVICE_HOST, WEB_SERVICE_PORT
except ImportError:
    # Fallback por si la ruta no es detectada, intentamos agregar el directorio actual
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from Utils.constants import DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_SERVICE, WEB_SERVICE_HOST, WEB_SERVICE_PORT

app = Flask(__name__)

class PrefixMiddleware(object):
    def __init__(self, app, prefix=''):
        self.app = app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        # Si la ruta empieza con el prefijo, lo quitamos para que Flask la reconozca
        if environ['PATH_INFO'].startswith(self.prefix):
            environ['PATH_INFO'] = environ['PATH_INFO'][len(self.prefix):]
            environ['SCRIPT_NAME'] = self.prefix
            return self.app(environ, start_response)
        else:
            # Si no tiene el prefijo, dejamos que pase (o devolvemos 404 si es estricto)
            return self.app(environ, start_response)

# IMPORTANTE: Reemplaza '/IClassSel_WebService' con el nombre EXACTO de tu carpeta/app en IIS
app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix='/IClassSel_WebService')

DB_CONFIG = {
    "user": DB_USER,
    "password": DB_PASSWORD,
    "dsn": f"{DB_HOST}:{DB_PORT}/{DB_SERVICE}"
}

def execute_query(sql, params=None, fetch_one=False):
    try:
        with oracledb.connect(**DB_CONFIG) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params or {})
                if fetch_one:
                    row = cursor.fetchone()
                    if row: # Validación extra por si devuelve None
                        # Convertir LOBs a texto/bytes automáticamente
                        row = list(row)
                        for i, col in enumerate(row):
                            if isinstance(col, oracledb.LOB):
                                row[i] = col.read()
                    return row
                else:
                    rows = cursor.fetchall()
                    # Procesamiento de LOBs para listas
                    processed_rows = []
                    for row in rows:
                        row_list = list(row)
                        for i, col in enumerate(row_list):
                            if isinstance(col, oracledb.LOB):
                                row_list[i] = col.read()
                        processed_rows.append(tuple(row_list))
                    return processed_rows
    except oracledb.Error as error:
        print(f"Error BD: {error}")
        return None

def execute_non_query(sql, params=None):
    try:
        with oracledb.connect(**DB_CONFIG) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params or {})
                connection.commit()
    except oracledb.Error as error:
        print(f"Error BD: {error}")

@app.route('/api/example', methods=['GET'])
def example():
    return jsonify({"message": "Hello, World! Oracle Configured."})

@app.route('/student/<username>', methods=['GET'])
def get_student(username):
    sql = "SELECT * FROM DOC_SDEL.ALUMNO WHERE USUARIO = :USUARIO"
    result = execute_query(sql, {"USUARIO": username}, fetch_one=True)
    return jsonify(result)

@app.route('/program/<program_id>', methods=['GET'])
def get_program(program_id):
    sql = "SELECT * FROM DOC_SDEL.REGISTRO_PROGRAMA WHERE ID_PROGRAMA = :PROGRAM_ID"
    result = execute_query(sql, {"PROGRAM_ID": program_id}, fetch_one=True)
    return jsonify(result)

@app.route('/docent/<program_id>', methods=['GET'])
def get_docent(program_id):
    sql = "SELECT * FROM DOC_SDEL.DOCENTE WHERE ID_PROGRAMA = :PROGRAM_ID"
    result = execute_query(sql, {"PROGRAM_ID": program_id}, fetch_one=True)
    return jsonify(result)

@app.route('/student_image', methods=['POST'])
def save_student_image():
    data = request.json
    sql = """
        UPDATE DOC_SDEL.ALUMNO
        SET FOTO_ALUMNO = :STUDENT_PHOTO, ASISTENCIA = :ASSISTANCE
        WHERE ID_ALUMNO = :STUDENT_ID
    """
    execute_non_query(sql, data)
    return '', 204

@app.route('/student_no_assistance', methods=['POST'])
def save_student_no_assistance():
    data = request.json
    sql = """
        UPDATE DOC_SDEL.ALUMNO
        SET ASISTENCIA = :ASSISTANCE
        WHERE ID_ALUMNO = :STUDENT_ID
    """
    execute_non_query(sql, data)
    return '', 204

@app.route('/event', methods=['POST'])
def save_event():
    data = request.json
    sql = """
        INSERT INTO DOC_SDEL.BITACORA_EVENTOS
        (ID_PROGRAMA, NOMBRE_ESTUDIANTE, APELLIDO_ESTUDIANTE, DESCRIPCION_EVENTO, HORA_EVENTO, CAPTURA_PRUEBA, ID_EVENTO, AVISO_USUARIO, ID_INSTITUCION)
        VALUES (:PROGRAM_ID, :STUDENT_NAME, :LASTNAME_STUDENT, :EVENT_DESCRIPTION, :TIME_EVENT, :CAPTURE_TEST, :ID_EVENT, :NOTICE_USER, :INSTITUTION_ID)
    """
    execute_non_query(sql, data)
    return '', 204

@app.route('/programs_by_institution', methods=['GET'])
def get_programs_by_institution():
    institution_id = request.args.get('id_institucion')
    fecha_actual = request.args.get('fecha_actual')
    sql = """
        SELECT ID_PROGRAMA, NOMBRE_PROGRAMA, DESCRIPCION_PROGRAMA, RESTRICCION_RESOLUCION 
        FROM DOC_SDEL.REGISTRO_PROGRAMA 
        WHERE id_institucion = :id_institucion
        AND TO_DATE(:fecha_actual, 'DD-MM-YYYY HH:MI:SS PM') BETWEEN fecha_inicio AND fecha_fin
    """
    params = {
        "id_institucion": institution_id,
        "fecha_actual": fecha_actual
    }
    result = execute_query(sql, params)
    return jsonify(result)

@app.route('/configuracion_programa/<id_programa>', methods=['GET'])
def cargar_configuracion_programa(id_programa):
    query = """
        SELECT TIPO_PROGRAMA, RETROCESO 
        FROM DOC_SDEL.PROGRAMA_CONFIGURACION 
        WHERE id_programa = :id_programa
    """
    result = execute_query(query, {'id_programa': id_programa}, fetch_one=True)
    return jsonify(result)

@app.route('/preguntas', methods=['GET'])
def cargar_preguntas():
    id_institucion = request.args.get('id_institucion')
    id_programa = request.args.get('id_programa')
    query = """
        SELECT ID_PROGRAMA_PREGUNTA, pregunta_descripcion, tipo_pregunta, pregunta_imagen
        FROM DOC_SDEL.PROGRAMA_PREGUNTAS
        WHERE id_institucion = :id_institucion AND id_programa = :id_programa
    """
    params = {'id_institucion': id_institucion, 'id_programa': id_programa}
    result = execute_query(query, params)
    
    preguntas = []
    for row in result:
        pregunta_imagen = None
        if row[3] is not None:
            pregunta_imagen = base64.b64encode(row[3]).decode('utf-8')
        
        pregunta = {
            'ID_PROGRAMA_PREGUNTA': row[0],
            'pregunta_descripcion': row[1],
            'tipo_pregunta': row[2],
            'pregunta_imagen': pregunta_imagen
        }
        preguntas.append(pregunta)
    
    return jsonify(preguntas)

@app.route('/respuestas', methods=['GET'])
def cargar_respuestas():
    id_institucion = request.args.get('id_institucion')
    id_programa = request.args.get('id_programa')
    id_pregunta = request.args.get('id_pregunta')
    query = """
        SELECT ID_PROGRAMA_RESPUESTA, respuesta 
        FROM DOC_SDEL.PROGRAMA_RESPUESTAS
        WHERE id_institucion = :id_institucion 
          AND id_programa = :id_programa 
          AND id_programa_pregunta = :id_pregunta
    """
    params = {
        'id_institucion': id_institucion,
        'id_programa': id_programa,
        'id_pregunta': id_pregunta
    }
    result = execute_query(query, params)
    return jsonify(result)

@app.route('/programas/<id_institucion>', methods=['GET'])
def cargar_programas(id_institucion):
    fecha_actual = datetime.now().strftime('%d-%m-%Y %I:%M:%S %p')
    query = """
        SELECT ID_PROGRAMA, NOMBRE_PROGRAMA, DESCRIPCION_PROGRAMA, RESTRICCION_RESOLUCION 
        FROM DOC_SDEL.REGISTRO_PROGRAMA 
        WHERE id_institucion = :id_institucion
          AND TO_DATE(:fecha_actual, 'DD-MM-YYYY HH:MI:SS PM') 
              BETWEEN fecha_inicio AND fecha_fin
    """
    params = {'id_institucion': id_institucion, 'fecha_actual': fecha_actual}
    result = execute_query(query, params)
    return jsonify(result)

@app.route('/guardar_respuesta', methods=['POST'])
def guardar_respuesta():
    data = request.json

    sql = """
        INSERT INTO DOC_SDEL.SEL_PREGUNTA_UNICA_MULTIPLE (
            ID_INSTITUCION,
            ID_PROGRAMA,
            ID_ALUMNO,
            ID_PREGUNTA,
            TIPO_PREGUNTA,
            RESPUESTA,
            RESPUESTAS_MULTIPLES,
            PREGUNTA_DESCRIPCION,
            CALIFICACION_ALUMNO,
            CALIFICACION_PREGUNTA
        ) VALUES (
            :ID_INSTITUCION,
            :ID_PROGRAMA,
            :ID_ALUMNO,
            :ID_PREGUNTA,
            :TIPO_PREGUNTA,
            :RESPUESTA,
            :RESPUESTAS_MULTIPLES,
            :PREGUNTA_DESCRIPCION,
            :CALIFICACION_ALUMNO,
            :CALIFICACION_PREGUNTA
        )
    """
    execute_non_query(sql, data)
    return jsonify({"message": "Respuesta guardada correctamente"}), 201

def run_api():
    app.run(debug=False, use_reloader=False, host=WEB_SERVICE_HOST, port=WEB_SERVICE_PORT)

if __name__ == '__main__':
    run_api()
