from gevent import monkey
monkey.patch_all()

import os
import base64
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# Almacenamiento en memoria (se borra si se reinicia Render)
ROOM_PASSWORDS = {"general": ""} 
# Formato: {"sid_del_usuario": ["sala1", "sala2"]}
AUTHORIZED_USERS = {}

@socketio.on('connect')
def handle_connect():
    AUTHORIZED_USERS[request.sid] = ["general"]
    print(f"Cliente conectado: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in AUTHORIZED_USERS:
        del AUTHORIZED_USERS[request.sid]

@socketio.on('create_room')
def handle_create(data):
    room = data.get('room').lower()
    password = data.get('password', '')
    if room:
        ROOM_PASSWORDS[room] = password
        # El creador queda autorizado automáticamente
        if request.sid in AUTHORIZED_USERS:
            AUTHORIZED_USERS[request.sid].append(room)
        join_room(room)
        emit('join_success', {'room': room})
        # Avisar a todos que hay una sala nueva
        emit('new_room_available', {'room': room}, broadcast=True)

@socketio.on('join')
def handle_join(data):
    room = data.get('room', 'general')
    password = data.get('password', '')
    
    # Validar contraseña
    if room in ROOM_PASSWORDS and ROOM_PASSWORDS[room] != "":
        if ROOM_PASSWORDS[room] == password:
            if room not in AUTHORIZED_USERS[request.sid]:
                AUTHORIZED_USERS[request.sid].append(room)
        else:
            emit('error_msg', {'msg': "Contraseña incorrecta"})
            return

    join_room(room)
    if room not in AUTHORIZED_USERS.get(request.sid, []):
        AUTHORIZED_USERS[request.sid].append(room)
    emit('join_success', {'room': room})

@socketio.on('message')
def handle_message(data):
    room = data.get('room', 'general')
    msg = data.get('msg')
    
    # SEGURIDAD: Solo reenviar si el usuario está autorizado para esa sala
    if room in AUTHORIZED_USERS.get(request.sid, []):
        emit('message', msg, room=room, include_self=False)
    else:
        emit('error_msg', {'msg': "No tienes permiso para escribir aquí"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
