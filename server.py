from gevent import monkey
monkey.patch_all()

import os
import base64
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- CONFIGURACIÓN ---
ADMIN_LOG_PASS = "chats1234" # Para el panel de descifrado
ROOM_PASSWORDS = {"general": ""} 
AUTHORIZED_USERS = {} # { sid: [salas_autorizadas] }

def generar_llave_admin(password: str):
    salt = b'\x14\xab\x11\xcd\xfe\xed\x11\x22'
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

cipher_admin = Fernet(generar_llave_admin(ADMIN_LOG_PASS))

LOG_DIR = "logs"
if not os.path.exists(LOG_DIR): os.makedirs(LOG_DIR)

def save_log(room, message):
    try:
        file_path = f"{LOG_DIR}/{room}.txt"
        encrypted_data = cipher_admin.encrypt(message.encode())
        with open(file_path, "ab") as f:
            f.write(encrypted_data + b"\n")
    except: pass

@socketio.on('connect')
def handle_connect():
    AUTHORIZED_USERS[request.sid] = ["general"]

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in AUTHORIZED_USERS: del AUTHORIZED_USERS[request.sid]

@socketio.on('create_room')
def handle_create(data):
    room = data.get('room').lower()
    password = data.get('password', '')
    if room:
        ROOM_PASSWORDS[room] = password
        if request.sid in AUTHORIZED_USERS: AUTHORIZED_USERS[request.sid].append(room)
        join_room(room)
        emit('join_success', {'room': room})
        emit('new_room_available', {'room': room}, broadcast=True)

@socketio.on('join')
def handle_join(data):
    room = data.get('room', 'general')
    password = data.get('password', '')
    nickname = data.get('nickname', '')
    
    # Lógica de Super-Usuario
    es_admin = (nickname == "Admin")
    
    if room in ROOM_PASSWORDS and ROOM_PASSWORDS[room] != "" and not es_admin:
        if ROOM_PASSWORDS[room] != password:
            emit('error_msg', {'msg': "Contraseña incorrecta"})
            return

    join_room(room)
    if room not in AUTHORIZED_USERS[request.sid]:
        AUTHORIZED_USERS[request.sid].append(room)
    emit('join_success', {'room': room})

@socketio.on('message')
def handle_message(data):
    room = data.get('room', 'general')
    msg = data.get('msg')
    if room in AUTHORIZED_USERS.get(request.sid, []):
        emit('message', msg, room=room, include_self=False)
        save_log(room, f"DATA: {msg}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
