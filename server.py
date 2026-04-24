from gevent import monkey
monkey.patch_all()

import os
import requests
import base64
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

ROOMS = {"general": {"history": [], "temp": False, "pass": "", "users": set(), "msg_count": 0, "owner": "SISTEMA"}}

def sync_rooms():
    data = {n: {"temp": i["temp"], "locked": bool(i["pass"]), "count": len(i["users"])} for n, i in ROOMS.items()}
    socketio.emit('update_rooms', data)

@socketio.on('register_user')
def handle_reg(data):
    join_room("general")
    ROOMS["general"]["users"].add(request.sid)
    sync_rooms()
    emit('room_joined', {'room': 'general', 'history': ROOMS['general']['history']})

@socketio.on('create_room')
def handle_create(data):
    name = data.get('room', '').lower().strip().replace(" ", "_")
    if name and name not in ROOMS:
        ROOMS[name] = {
            "history": [], "temp": data.get('temp', False), 
            "pass": data.get('password', ""), "users": set(), 
            "msg_count": 0, "owner": request.sid 
        }
        sync_rooms()

@socketio.on('join')
def handle_join(data):
    room = data.get('room')
    old_room = data.get('old_room')
    password = data.get('password', "")
    if room in ROOMS:
        if ROOMS[room]["pass"] and ROOMS[room]["pass"] != password:
            emit('error_msg', {'msg': 'Clave incorrecta'})
            return
        if old_room and old_room in ROOMS:
            leave_room(old_room)
            ROOMS[old_room]["users"].discard(request.sid)
        join_room(room)
        ROOMS[room]["users"].add(request.sid)
        sync_rooms()
        emit('room_joined', {'room': room, 'history': ROOMS[room]['history']})

@socketio.on('message')
def handle_msg(data):
    room = data.get('room')
    if room in ROOMS:
        if not ROOMS[room]['temp']:
            ROOMS[room]['history'].append(data)
            if len(ROOMS[room]['history']) > 100: ROOMS[room]['history'].pop(0)
        # include_self=False evita el duplicado
        emit('new_message', data, room=room, include_self=False)

@socketio.on('close_room')
def handle_close(data):
    room = data.get('room')
    if room in ROOMS and room != "general":
        if ROOMS[room]['owner'] == request.sid:
            emit('room_closed', {'room': room}, room=room)
            del ROOMS[room]
            sync_rooms()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
