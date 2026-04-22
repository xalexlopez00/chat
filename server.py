from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

ROOM_PASSWORDS = {"general": ""} 
AUTHORIZED_USERS = {} # { sid: [lista_salas_autorizadas] }

@socketio.on('connect')
def handle_connect():
    AUTHORIZED_USERS[request.sid] = ["general"]
    join_room("general")

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
    
    es_admin = (nickname == "Admin")
    
    if room in ROOM_PASSWORDS and ROOM_PASSWORDS[room] != "" and not es_admin:
        if ROOM_PASSWORDS[room] != password:
            emit('error_msg', {'msg': "Contraseña incorrecta"})
            return

    join_room(room)
    if room not in AUTHORIZED_USERS[request.sid]:
        AUTHORIZED_USERS[request.sid].append(room)
    emit('join_success', {'room': room})

@socketio.on('leave')
def handle_leave(data):
    room = data.get('room')
    if room:
        leave_room(room)

@socketio.on('message')
def handle_message(data):
    room = data.get('room', 'general')
    msg = data.get('msg')
    # IMPORTANTE: El mensaje solo se emite a 'room=room'
    if room in AUTHORIZED_USERS.get(request.sid, []):
        emit('message', {'msg': msg, 'room': room}, room=room, include_self=False)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
