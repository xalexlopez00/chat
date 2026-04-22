import eventlet
eventlet.monkey_patch()  # Vital para que eventlet funcione bien

import os
import base64
from flask import Flask
from flask_socketio import SocketIO, emit, join_room
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

app = Flask(__name__)
# Usamos async_mode='eventlet' para máxima estabilidad en Render
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# --- CONFIGURACIÓN DE SEGURIDAD PARA LOGS ---
ADMIN_PASSWORD = "chats1234" 

def generar_llave_sifra(password: str):
    salt = b'\x14\xab\x11\xcd\xfe\xed\x11\x22'
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

fernet_logs = Fernet(generar_llave_sifra(ADMIN_PASSWORD))

LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def save_encrypted_log(room, message):
    file_path = f"{LOG_DIR}/{room}.txt"
    encrypted_data = fernet_logs.encrypt(message.encode())
    with open(file_path, "ab") as f:
        f.write(encrypted_data + b"\n")

# --- LÓGICA DE SALAS Y MENSAJES ---

@socketio.on('join')
def on_join(data):
    room = data.get('room', 'general')
    join_room(room)
    save_encrypted_log(room, f"[SISTEMA] Usuario unido a {room}")

@socketio.on('message')
def handle_message(data):
    room = data.get('room', 'general')
    msg_client = data['msg'] 
    # Reenviar a los demás en la misma sala
    emit('message', msg_client, room=room, include_self=False)
    save_encrypted_log(room, f"CHAT_DATA: {msg_client}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
