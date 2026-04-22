import eventlet
eventlet.monkey_patch()  # ¡IMPORTANTE! Debe ser la primera línea

import os
import base64
from flask import Flask
from flask_socketio import SocketIO, emit, join_room
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

app = Flask(__name__)

# Configuración de compatibilidad para protocolos antiguos y nuevos
# Esto permite que clientes con socketio 4.x conecten sin errores
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode='eventlet',
    manage_session=False
)

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
    try:
        file_path = f"{LOG_DIR}/{room}.txt"
        encrypted_data = fernet_logs.encrypt(message.encode())
        with open(file_path, "ab") as f:
            f.write(encrypted_data + b"\n")
    except Exception as e:
        print(f"Error guardando log: {e}")

# --- LÓGICA DEL CHAT ---

@socketio.on('join')
def on_join(data):
    room = data.get('room', 'general')
    join_room(room)
    save_encrypted_log(room, f"[SISTEMA] Usuario unido a la sala: {room}")

@socketio.on('message')
def handle_message(data):
    room = data.get('room', 'general')
    msg_client = data['msg'] 
    # Reenviar el mensaje cifrado a los demás en la sala
    emit('message', msg_client, room=room, include_self=False)
    # Guardar en el log del servidor (también cifrado)
    save_encrypted_log(room, f"CHAT_DATA: {msg_client}")

if __name__ == '__main__':
    # Render asigna el puerto automáticamente
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
