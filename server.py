from gevent import monkey
monkey.patch_all()
import os
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

ROOMS = {"general": {"pass": "", "temp": False, "history": []}}
USERS = {} 

@socketio.on('connect')
def on_connect():
    pass # Esperamos al registro formal

@socketio.on('register_user')
def on_register(data):
    nick = data.get('nickname', 'User')
    USERS[request.sid] = {'nickname': nick, 'ip': request.remote_addr}
    join_room("general")
    emit('admin_user_sync', USERS, broadcast=True)
    # Enviamos las salas existentes al nuevo usuario
    for r_name, r_info in ROOMS.items():
        emit('new_room_available', {'room': r_name, 'has_pass': bool(r_info['pass'])})

@socketio.on('disconnect')
def on_disconnect():
    if request.sid in USERS:
        del USERS[request.sid]
    emit('admin_user_sync', USERS, broadcast=True)

@socketio.on('create_room')
def on_create(data):
    name = data.get('room', '').lower().strip()
    if name and name not in ROOMS:
        ROOMS[name] = {"pass": data.get('password', ''), "temp": data.get('temp', False), "history": []}
        emit('new_room_available', {'room': name, 'has_pass': bool(ROOMS[name]['pass'])}, broadcast=True)
        # El creador se une automáticamente
        join_room(name)
        emit('join_success', {'room': name, 'temp': ROOMS[name]['temp'], 'history': []})

@socketio.on('join')
def on_join(data):
    room = data.get('room', 'general')
    nick = data.get('nickname', '')
    if room in ROOMS:
        if ROOMS[room]['pass'] and nick != "Admin" and ROOMS[room]['pass'] != data.get('password'):
            emit('error_msg', {'msg': "Clave incorrecta"})
            return
        join_room(room)
        hist = [] if ROOMS[room]['temp'] else ROOMS[room]['history']
        emit('join_success', {'room': room, 'temp': ROOMS[room]['temp'], 'history': hist})

@socketio.on('message')
def on_message(data):
    room = data.get('room', 'general')
    msg = data.get('msg')
    emit('message', {'msg': msg, 'room': room}, room=room, include_self=False)
    if room in ROOMS and not ROOMS[room]['temp']:
        ROOMS[room]['history'].append({'msg': msg})
        if len(ROOMS[room]['history']) > 100: ROOMS[room]['history'].pop(0)

@socketio.on('admin_action')
def on_admin(data):
    if USERS.get(request.sid, {}).get('nickname') == "Admin":
        if data.get('action') == "kick": disconnect(data.get('target_sid'))
        elif data.get('action') == "alert": emit('broadcast_alert', {'msg': data.get('msg')}, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
