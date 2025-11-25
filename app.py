# app.py
from http import HTTPStatus
from functools import wraps
import datetime

from flask import Flask, jsonify, request, make_response
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

# Firebase Admin
import firebase_admin
from firebase_admin import credentials, auth, firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

# Cloudinary
import cloudinary
import cloudinary.uploader
import cloudinary.api

# JWT propio (PyJWT)
import jwt

# ============================================================
#   CONFIGURACIÓN INICIAL
# ============================================================
app = Flask(__name__)

# CORS: permitir credenciales desde Angular (localhost:4200)
CORS(
    app,
    supports_credentials=True,
    origins=["http://localhost:4200"]
)

# --- Cloudinary ---
cloudinary.config(
    cloud_name="dgbrhunlv",
    api_key="841378259651323",
    api_secret="mKLpjFMFuJeI7Nlmj8t6gyQCEW8",
    secure=True
)

# --- Firebase Admin ---
cred = credentials.Certificate("valandtickets-firebase-adminsdk.json")
firebase_admin.initialize_app(cred)
firestore_db = firestore.client()

# --- JWT propio ---
JWT_SECRET_KEY = "clave-secreta-super-segura"
JWT_ALGORITHM = "HS256"
JWT_EXP_HOURS = 2


# ============================================================
#   HELPERS JWT / AUTH
# ============================================================

def create_jwt(email: str) -> str:
    """Crea un JWT con subject = email y expiración en 2 horas."""
    now = datetime.datetime.now(datetime.UTC)

    payload = {
        "sub": email,
        "iat": now,
        "exp": now + datetime.timedelta(hours=JWT_EXP_HOURS),
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    # PyJWT puede devolver str o bytes según versión
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token

def decode_jwt(token: str):
    return jwt.decode(
        token,
        JWT_SECRET_KEY,
        algorithms=[JWT_ALGORITHM]
    )

def get_token_from_request() -> str | None:
    """Busca el token en Authorization: Bearer ... o en cookie 'token'."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]

    cookie_token = request.cookies.get("token")
    if cookie_token:
        return cookie_token

    return None


def create_token_response(email: str, message: str):
    """
    Crea un JWT, lo devuelve en JSON y además lo setea en cookie httpOnly.
    Respuesta JSON: { mensaje, token, email }
    """
    token = create_jwt(email)
    resp = make_response(jsonify({
        "mensaje": message,
        "token": token,
        "email": email
    }), 200)

    # Cookie de desarrollo (para producción: secure=True, SameSite=None)
    resp.set_cookie(
        "token",
        value=token,
        httponly=True,
        secure=False,          # Cambiar a True en producción con HTTPS
        samesite="Lax",        # Para localhost va bien; para cross-site real usar "None"
        max_age=JWT_EXP_HOURS * 3600
    )
    return resp


def login_required(f):
    """Decorator simple basado en nuestro JWT (cookie o header)."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        token = get_token_from_request()
        if not token:
            return jsonify({"mensaje": "No hay token de autenticación"}), 401

        try:
            payload = decode_jwt(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"mensaje": "Token expirado"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"mensaje": "Token inválido"}), 401

        # Guardamos email del usuario en request
        request.user_email = payload.get("sub")
        if not request.user_email:
            return jsonify({"mensaje": "Token sin usuario"}), 401

        return f(*args, **kwargs)

    return wrapper


# ============================================================
#   REGISTRO DE USUARIO (Firestore)
#   Colección: users (doc id = email)
# ============================================================
@app.route('/users', methods=['POST'])
def register():
    data = request.get_json()

    name = data.get('name')
    lastname = data.get('lastname')
    email = data.get('email')
    password = data.get('password')
    address = data.get('address')
    phone = data.get('phone')

    if not all([name, lastname, email, password]):
        return jsonify({"mensaje": "Nombre, apellido, email y contraseña son obligatorios"}), 400

    users_ref = firestore_db.collection('users')
    user_doc_ref = users_ref.document(email)
    user_doc = user_doc_ref.get()

    if user_doc.exists:
        return jsonify({"mensaje": "El usuario ya existe"}), 400

    password_hasheada = generate_password_hash(password)

    user_data = {
        "name": name,
        "lastname": lastname,
        "email": email,
        "password": password_hasheada,
        "address": address or "",
        "phone": phone or "",
        "createdAt": SERVER_TIMESTAMP
    }

    user_doc_ref.set(user_data)

    return jsonify({"mensaje": "Usuario registrado con éxito"}), 201


# ============================================================
#   LOGIN NORMAL (email / contraseña) contra Firestore
# ============================================================
@app.post("/login")
def login():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"mensaje": "Email y contraseña son obligatorios"}), 400

    users_ref = firestore_db.collection("users")
    user_doc = users_ref.document(email).get()

    if not user_doc.exists:
        return jsonify({"mensaje": "Usuario no encontrado"}), 401

    user = user_doc.to_dict()

    if not check_password_hash(user.get("password", ""), password):
        return jsonify({"mensaje": "Contraseña incorrecta"}), 401

    # Devuelve JSON con token y también lo guarda en cookie
    return create_token_response(email, "Login exitoso")


# ============================================================
#   LOGIN CON GOOGLE (Firebase Auth + Firestore)
# ============================================================
@app.post("/login/google")
def login_google():
    data = request.get_json() or {}
    id_token = data.get("idToken")

    if not id_token:
        return jsonify({"mensaje": "Token de Google no recibido"}), 400

    try:
        decoded = auth.verify_id_token(id_token)
    except Exception as e:
        print("ERROR LOGIN GOOGLE:", e)
        return jsonify({"mensaje": "Token de Google inválido", "error": str(e)}), 401

    email = decoded.get("email")
    if not email:
        return jsonify({"mensaje": "No se pudo obtener el email desde Google"}), 400

    users_ref = firestore_db.collection("users")
    user_doc = users_ref.document(email).get()

    # Si no existe el usuario, lo creamos automáticamente
    if not user_doc.exists:
        uid = decoded.get("uid", "")
        password_hasheada = generate_password_hash(uid or "google_user")

        user_data = {
            "name": decoded.get("name", "Usuario Google"),
            "lastname": decoded.get("family_name", ""),
            "email": email,
            "password": password_hasheada,
            "address": "",
            "phone": "",
            "provider": "google",
            "createdAt": SERVER_TIMESTAMP
        }
        users_ref.document(email).set(user_data)

    # Devuelve JSON con token y lo guarda en cookie
    return create_token_response(email, "Login con Google exitoso")


# ============================================================
#   PERFIL AUTENTICADO (lee usuario desde Firestore)
# ============================================================
@app.route('/api/perfil', methods=['GET'])
@login_required
def perfil():
    email = getattr(request, "user_email", None)
    if not email:
        return jsonify({"mensaje": "No se pudo obtener el usuario del token"}), 401

    users_ref = firestore_db.collection('users')
    user_doc = users_ref.document(email).get()

    if not user_doc.exists:
        return jsonify({"mensaje": "Usuario no encontrado"}), 404

    user_data = user_doc.to_dict()
    # No devolvemos el hash de la contraseña
    user_data.pop('password', None)

    return jsonify({
        "mensaje": f"Bienvenido {email}",
        "usuario": user_data
    }), 200


# ============================================================
#   CREAR EVENTO (Firestore)
#   Colección: events
# ============================================================
@app.route('/events', methods=['POST'])
def add_event():
    if not request.is_json:
        return jsonify({"error": "El cuerpo debe ser JSON"}), HTTPStatus.BAD_REQUEST

    data = request.get_json()

    required_fields = [
        'title', 'datec', 'category', 'day', 'month',
        'date', 'year', 'site', 'city', 'price'
    ]

    missing = [f for f in required_fields if f not in data]
    if missing:
        return jsonify({
            "error": "Faltan campos obligatorios",
            "missing": missing
        }), HTTPStatus.BAD_REQUEST

    try:
        doc_ref = firestore_db.collection('events').document()

        event_data = {
            "id": doc_ref.id,
            "title": data['title'],
            "datec": data['datec'],
            "category": data['category'],
            "day": data['day'],
            "month": data['month'],
            "date": data['date'],
            "year": data['year'],
            "site": data['site'],
            "image": data.get('image', 'default.png'),
            "city": data['city'],
            "banner": data.get('banner', ''),
            "tickets": data.get('tickets', '0'),
            "time": data.get('time', ''),
            "price": int(data['price']),
            "map": data.get('map', '')
        }

        doc_ref.set(event_data)

        return jsonify({
            "message": "Evento creado exitosamente",
            "event_id": doc_ref.id,
            "event": event_data
        }), HTTPStatus.CREATED

    except Exception as e:
        print("ERROR FIRESTORE (add_event):", e)
        return jsonify({"error": "No se pudo crear el evento", "details": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


# ============================================================
#   OBTENER TODOS LOS EVENTOS (Firestore)
# ============================================================
@app.route('/events', methods=['GET'])
def get_events():
    try:
        docs = firestore_db.collection('events').stream()
        events_list = [doc.to_dict() for doc in docs]
        return jsonify(events_list), 200

    except Exception as e:
        print("ERROR FIRESTORE (get_events):", e)
        return jsonify({"error": "No se pudieron obtener los eventos", "details": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


# ============================================================
#   OBTENER EVENTO POR ID (Firestore)
# ============================================================
@app.route('/events/<id>', methods=['GET'])
def get_event_by_id(id):
    try:
        doc = firestore_db.collection('events').document(id).get()

        if not doc.exists:
            return jsonify({"error": "Evento no encontrado"}), 404

        return jsonify(doc.to_dict()), 200

    except Exception as e:
        print("ERROR FIRESTORE (get_event_by_id):", e)
        return jsonify({"error": "Error obteniendo evento", "details": str(e)}), 500


# ============================================================
#   OBTENER EVENTOS POR CATEGORÍA (Firestore)
# ============================================================
@app.route('/categories/<category>', methods=['GET'])
def get_events_by_category(category):
    try:
        docs = firestore_db.collection('events').where("category", "==", category).stream()
        events_list = [doc.to_dict() for doc in docs]
        return jsonify(events_list), 200

    except Exception as e:
        print("ERROR FIRESTORE (get_events_by_category):", e)
        return jsonify({"error": "No se pudieron obtener eventos por categoría", "details": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


# ============================================================
#   SUBIR IMAGEN A CLOUDINARY
# ============================================================
@app.route('/upload-image', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return jsonify({"error": "No se recibió ningún archivo"}), 400

    file = request.files['file']

    try:
        result = cloudinary.uploader.upload(
            file,
            folder="valand/events"
        )

        url = result.get("secure_url")

        return jsonify({"url": url}), 200

    except Exception as e:
        print("ERROR CLOUDINARY:", e)
        return jsonify({"error": "Error al subir la imagen", "details": str(e)}), 500


# ============================================================
#   INICIO DEL SERVIDOR
# ============================================================
if __name__ == '__main__':
    app.run(debug=True)
