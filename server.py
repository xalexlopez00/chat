from gevent import monkey
monkey.patch_all()
import os
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
# Reducimos los tiempos de espera para detectar desconexiones rápido
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', 
                    ping_timeout=10, ping_interval=5)

ROOMS = {"general": {"history": [], "temp": False, "users": set()}}

def sync_rooms():
    data = {n: {"temp": i["temp"], "count": len(i["users"])} for n, i in ROOMS.items()}
    socketio.emit('update_rooms', data)

@socketio.on('register_user')
def handle_reg(data):
    nick = data.get('nickname', 'Anónimo')
    join_room("general")
    ROOMS["general"]["users"].add(request.sid)
    sync_rooms()
    emit('room_joined', {'room': 'general', 'history': ROOMS['general']['history']})

@socketio.on('create_room')
def handle_create(data):
    name = data.get('room', '').lower().strip()
    if name and name not in ROOMS:
        ROOMS[name] = {"history": [], "temp": data.get('temp', False), "users": set()}
        sync_rooms()

@socketio.on('join')
def handle_join(data):
    room = data.get('room')
    old_room = data.get('old_room', 'general')
    if room in ROOMS:
        leave_room(old_room)
        if request.sid in ROOMS[old_room]["users"]:
            ROOMS[old_room]["users"].remove(request.sid)
        
        join_room(room)
        ROOMS[room]["users"].add(request.sid)
        sync_rooms()
        emit('room_joined', {'room': room, 'history': ROOMS[room]['history']})

@socketio.on('message')
def handle_msg(data):
    room = data.get('room', 'general')
    if room in ROOMS:
        if not ROOMS[room]['temp']:
            ROOMS[room]['history'].append(data)
        emit('new_message', data, room=room, include_self=False)

@socketio.on('disconnect')
def handle_disc():
    # Limpieza total de fantasmas al cerrar app
    for room in ROOMS.values():
        if request.sid in room["users"]:
            room["users"].remove(request.sid)
    sync_rooms()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
