from gevent import monkey
monkey.patch_all()

import os
import base64
from flask import Flask
from flask_socketio import SocketIO, emit, join_room, leave_room
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- CONFIGURACIÓN DE CIFRADO DE LOGS ---
# Esta es la llave para que solo el Admin Panel pueda leerlos
ADMIN_PASSWORD = "chats1234" 

def generar_llave_admin(password: str):
    salt = b'\x14\xab\x11\xcd\xfe\xed\x11\x22' # Salt estático para que la llave no cambie
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

cipher_admin = Fernet(generar_llave_admin(ADMIN_PASSWORD))

LOG_DIR = "logs"
if not os.path.exists(LOG_DIR): os.makedirs(LOG_DIR)

def save_log(room, message):
    file_path = f"{LOG_DIR}/{room}.txt"
    # El mensaje llega ya cifrado por los clientes, pero lo ciframos OTRA VEZ con la llave admin
    # Así, si alguien hackea Render, no puede leer nada sin la clave 'chats1234'
    encrypted_log = cipher_admin.encrypt(message.encode())
    with open(file_path, "ab") as f:
        f.write(encrypted_log + b"\n")

# --- EVENTOS ---

@socketio.on('join')
def on_join(data):
    room = data.get('room', 'general')
    join_room(room)
    save_log(room, f"[SISTEMA] Usuario conectado a sala: {room}")

@socketio.on('message')
def handle_message(data):
    room = data.get('room', 'general')
    msg = data.get('msg')
    emit('message', msg, room=room, include_self=False)
    save_log(room, f"DATA: {msg}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
