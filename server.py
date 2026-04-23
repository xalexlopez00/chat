from gevent import monkey
monkey.patch_all()
import os
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
# Configuración para evitar "fantasmas" y detectar cierres rápidos
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', 
                    ping_timeout=15, ping_interval=5)

ROOMS = {"general": {"history": [], "temp": False, "pass": "", "users": set()}}

def sync_rooms():
    data = {n: {
        "temp": i["temp"], 
        "locked": bool(i["pass"]), 
        "count": len(i["users"])
    } for n, i in ROOMS.items()}
    socketio.emit('update_rooms', data)

@socketio.on('register_user')
def handle_reg(data):
    join_room("general")
    ROOMS["general"]["users"].add(request.sid)
    sync_rooms()
    emit('room_joined', {'room': 'general', 'history': ROOMS['general']['history']})

@socketio.on('create_room')
def handle_create(data):
    name = data.get('room', '').lower().strip()
    if name and name not in ROOMS:
        ROOMS[name] = {
            "history": [], 
            "temp": data.get('temp', False), 
            "pass": data.get('password', ""), 
            "users": set()
        }
        sync_rooms()

@socketio.on('join')
def handle_join(data):
    room, pw, nick = data.get('room'), data.get('password', ""), data.get('nickname')
    old_room = data.get('old_room')
    
    if room in ROOMS:
        # Validación de contraseña
        if ROOMS[room]["pass"] and pw != ROOMS[room]["pass"]:
            emit('error_msg', {'msg': "Contraseña incorrecta"})
            return
            
        if old_room and request.sid in ROOMS[old_room]["users"]:
            leave_room(old_room)
            ROOMS[old_room]["users"].remove(request.sid)
        
        join_room(room)
        ROOMS[room]["users"].add(request.sid)
        sync_rooms()
        # Si es temporal, enviamos historial vacío siempre
        hist = [] if ROOMS[room]["temp"] else ROOMS[room]["history"]
        emit('room_joined', {'room': room, 'history': hist})

@socketio.on('message')
def handle_msg(data):
    room = data.get('room')
    if room in ROOMS:
        if not ROOMS[room]['temp']:
            ROOMS[room]['history'].append(data)
        emit('new_message', data, room=room, include_self=False)

@socketio.on('disconnect')
def handle_disc():
    for room in ROOMS.values():
        if request.sid in room["users"]:
            room["users"].remove(request.sid)
    sync_rooms()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
