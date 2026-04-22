from gevent import monkey
monkey.patch_all()

import os
from flask import Flask
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# Diccionario para guardar las contraseñas de las salas en memoria
# Formato: {"nombre_sala": "contraseña"}
ROOM_PASSWORDS = {
    "general": "", # Sala libre
    "vip": "1234"  # Sala con contraseña predeterminada
}

@socketio.on('join')
def handle_join(data):
    room = data.get('room', 'general')
    password = data.get('password', '')
    
    # Si la sala tiene contraseña y es incorrecta, rebotar al usuario
    if room in ROOM_PASSWORDS and ROOM_PASSWORDS[room] != "" and ROOM_PASSWORDS[room] != password:
        emit('error_msg', {'msg': f"Contraseña incorrecta para la sala {room}"})
        return

    join_room(room)
    emit('join_success', {'room': room})
    print(f"Usuario unido a: {room}")

@socketio.on('create_room')
def handle_create(data):
    room = data.get('room').lower()
    password = data.get('password', '')
    if room:
        ROOM_PASSWORDS[room] = password
        print(f"Nueva sala creada: {room} con clave: {password}")
        emit('room_created', {'room': room})

# ... (El resto de funciones message y leave igual que antes)
