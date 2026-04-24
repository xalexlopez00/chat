from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
# Configuración para Render/Despliegue
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# Memoria volátil de salas
ROOMS = {"general": {"history": [], "users": set()}}

@socketio.on('register_user')
def handle_reg(data):
    join_room("general")
    ROOMS["general"]["users"].add(request.sid)
    emit('room_joined', {'room': 'general', 'history': ROOMS['general']['history']})

@socketio.on('message')
def handle_msg(data):
    room = data.get('room')
    if room in ROOMS:
        # Guardar mensaje en el historial del servidor (máximo 50)
        ROOMS[room]['history'].append(data)
        if len(ROOMS[room]['history']) > 50:
            ROOMS[room]['history'].pop(0)
        
        # REENVÍO CRÍTICO: include_self=False evita el bucle de "SISTEMA: Tú"
        emit('new_message', data, room=room, include_self=False)

@socketio.on('join')
def handle_join(data):
    room = data.get('room')
    old = data.get('old_room')
    if room in ROOMS:
        if old: leave_room(old)
        join_room(room)
        emit('room_joined', {'room': room, 'history': ROOMS[room]['history']})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    socketio.run(app, host='0.0.0.0', port=port)
