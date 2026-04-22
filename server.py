import os
import base64
from flask import Flask
from flask_socketio import SocketIO, emit, join_room, leave_room
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# --- CONFIGURACIÓN DE SEGURIDAD PARA LOGS (SIFRA COMPATIBLE) ---
# Cambia esta contraseña por la que quieras usar en SIFRA para abrir los logs
ADMIN_PASSWORD = "chats1234" 

def generar_llave_sifra(password: str):
    salt = b'\x14\xab\x11\xcd\xfe\xed\x11\x22' # El mismo salt de tu programa
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

# Generamos el objeto de cifrado para los logs
fernet_logs = Fernet(generar_llave_sifra(ADMIN_PASSWORD))

LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def save_encrypted_log(room, message):
    file_path = f"{LOG_DIR}/{room}.txt"
    # Ciframos el mensaje con la lógica de SIFRA
    encrypted_data = fernet_logs.encrypt(message.encode())
    
    # Escribimos en modo binario 'ab' (append binary)
    with open(file_path, "ab") as f:
        f.write(encrypted_data + b"\n") # Añadimos un salto de línea binario

# --- LÓGICA DE SALAS Y MENSAJES ---

rooms_db = {"general": None}

@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    log_msg = f"[SISTEMA] Usuario unido a {room}"
    save_encrypted_log(room, log_msg)

@socketio.on('message')
def handle_message(data):
    room = data.get('room', 'general')
    msg_client = data['msg'] # Este ya viene cifrado por los clientes (AES de chat)
    
    # Reenviar a los demás
    emit('message', msg_client, room=room, include_self=False)
    
    # Guardar en log (doble cifrado: el del chat + el de SIFRA para el admin)
    save_encrypted_log(room, f"CHAT_DATA: {msg_client}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
