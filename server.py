from gevent import monkey
monkey.patch_all()  # Crucial: Debe ser la primera línea

import os
import base64
from flask import Flask
from flask_socketio import SocketIO, emit, join_room, leave_room
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

app = Flask(__name__)
# Configuración optimizada para Render con gevent
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- CONFIGURACIÓN DE SEGURIDAD PARA LOGS ---
# Esta clave cifra los archivos físicos en el servidor
ADMIN_PASSWORD = "chats1234" 

def generar_llave_admin(password: str):
    salt = b'\x14\xab\x11\xcd\xfe\xed\x11\x22' # Salt estático
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

cipher_admin = Fernet(generar_llave_admin(ADMIN_PASSWORD))

# Crear carpeta de logs si no existe
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def save_log(room, message):
    """Guarda el mensaje cifrado en un archivo .txt por sala"""
    try:
        file_path = f"{LOG_DIR}/{room}.txt"
        # Ciframos el mensaje (que ya viene cifrado del cliente) con la llave de Admin
        encrypted_data = cipher_admin.encrypt(message.encode())
        with open(file_path, "ab") as f:
            f.write(encrypted_data + b"\n")
    except Exception as e:
        print(f"Error guardando log: {e}")

# --- RUTAS Y EVENTOS ---

@app.route('/')
def index():
    return "Servidor de Chat Cifrado Activo"

@socketio.on('join')
def handle_join(data):
    room = data.get('room', 'general')
    join_room(room)
    save_log(room, f"[SISTEMA] Usuario entró en sala: {room}")
    print(f"Usuario unido a: {room}")

@socketio.on('leave')
def handle_leave(data):
    room = data.get('room', 'general')
    leave_room(room)
    save_log(room, f"[SISTEMA] Usuario salió de la sala: {room}")
    print(f"Usuario salió de: {room}")

@socketio.on('message')
def handle_message(data):
    room = data.get('room', 'general')
    msg = data.get('msg')
    # Reenviar el mensaje a todos los de la sala (excepto al emisor)
    emit('message', msg, room=room, include_self=False)
    # Guardar en el log cifrado
    save_log(room, f"MSG_DATA: {msg}")

if __name__ == '__main__':
    # Render asigna el puerto mediante la variable de entorno PORT
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
