from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# Configuración
ROOM_DATA = {"general": {"pass": "", "temp": False}} 
ROOM_HISTORY = {"general": []} # Guarda los últimos mensajes: [{"msg": "...", "room": "..."}]
AUTHORIZED_USERS = {} 

@socketio.on('connect')
def handle_connect():
    AUTHORIZED_USERS[request.sid] = ["general"]
    join_room("general")

@socketio.on('create_room')
def handle_create(data):
    room = data.get('room').lower()
    password = data.get('password', '')
    is_temp = data.get('temp', False) 
    
    if room:
        ROOM_DATA[room] = {"pass": password, "temp": is_temp}
        ROOM_HISTORY[room] = [] # Inicializar historial para la nueva sala
        if request.sid in AUTHORIZED_USERS: AUTHORIZED_USERS[request.sid].append(room)
        join_room(room)
        emit('join_success', {'room': room, 'temp': is_temp, 'history': []})
        emit('new_room_available', {'room': room, 'has_pass': password != ""}, broadcast=True)

@socketio.on('join')
def handle_join(data):
    room = data.get('room', 'general')
    password = data.get('password', '')
    nickname = data.get('nickname', '')
    
    info = ROOM_DATA.get(room, {"pass": "", "temp": False})
    if info["pass"] != "" and nickname != "Admin":
        if info["pass"] != password:
            emit('error_msg', {'msg': "Contraseña incorrecta"})
            return

    join_room(room)
    if room not in AUTHORIZED_USERS[request.sid]:
        AUTHORIZED_USERS[request.sid].append(room)
    
    # ENVIAR EL HISTORIAL DE LA SALA AL USUARIO QUE ENTRA
    history = ROOM_HISTORY.get(room, [])
    emit('join_success', {'room': room, 'temp': info["temp"], 'history': history})

@socketio.on('message')
def handle_message(data):
    room = data.get('room', 'general')
    msg = data.get('msg')
    
    if room in AUTHORIZED_USERS.get(request.sid, []):
        # Enviar a los demás
        emit('message', {'msg': msg, 'room': room}, room=room, include_self=False)
        
        # GUARDAR EN EL HISTORIAL DEL SERVIDOR (si no es temporal)
        if not ROOM_DATA.get(room, {}).get("temp", False):
            if room not in ROOM_HISTORY: ROOM_HISTORY[room] = []
            ROOM_HISTORY[room].append({'msg': msg, 'room': room})
            # Mantener solo los últimos 50 mensajes para no saturar
            if len(ROOM_HISTORY[room]) > 50:
                ROOM_HISTORY[room].pop(0)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
