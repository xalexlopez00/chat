from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# BASE DE DATOS EN MEMORIA
# ROOMS: { 'nombre': {'pass': str, 'temp': bool, 'history': list} }
ROOMS = {"general": {"pass": "", "temp": False, "history": []}}
USERS = {} # { sid: nickname }
BANNED_IPS = []

@socketio.on('connect')
def on_connect():
    if request.remote_addr in BANNED_IPS:
        return False
    join_room("general")

@socketio.on('register_user')
def on_register(data):
    nick = data.get('nickname', 'Anónimo')
    USERS[request.sid] = nick
    emit('admin_update_users', USERS, broadcast=True)

@socketio.on('disconnect')
def on_disconnect():
    if request.sid in USERS:
        del USERS[request.sid]
    emit('admin_update_users', USERS, broadcast=True)

@socketio.on('create_room')
def on_create(data):
    name = data.get('room', '').lower().strip()
    password = data.get('password', '')
    is_temp = data.get('temp', False)
    
    if name and name not in ROOMS:
        ROOMS[name] = {"pass": password, "temp": is_temp, "history": []}
        join_room(name)
        emit('join_success', {'room': name, 'temp': is_temp, 'history': []})
        emit('new_room_available', {'room': name, 'has_pass': bool(password)}, broadcast=True)

@socketio.on('join')
def on_join(data):
    room = data.get('room', 'general')
    password = data.get('password', '')
    nickname = data.get('nickname', '')
    
    if room not in ROOMS: return

    # Bypass para Admin o validación de password
    target = ROOMS[room]
    if target["pass"] and nickname != "Admin":
        if target["pass"] != password:
            emit('error_msg', {'msg': "Clave incorrecta"})
            return

    join_room(room)
    history = [] if target["temp"] else target["history"]
    emit('join_success', {'room': room, 'temp': target["temp"], 'history': history})

@socketio.on('message')
def on_message(data):
    room = data.get('room', 'general')
    msg = data.get('msg')
    
    # Reenviar mensaje
    emit('message', {'msg': msg, 'room': room}, room=room, include_self=False)
    
    # Guardar en historial si no es temporal
    if room in ROOMS and not ROOMS[room]["temp"]:
        ROOMS[room]["history"].append({'msg': msg})
        if len(ROOMS[room]["history"]) > 100: ROOMS[room]["history"].pop(0)

# COMANDOS DE ADMIN
@socketio.on('admin_command')
def on_admin_cmd(data):
    if USERS.get(request.sid) != "Admin": return
    
    cmd = data.get('cmd')
    target_sid = data.get('target_sid')
    
    if cmd == "kick":
        socketio.emit('admin_alert', {'msg': "Has sido expulsado por el Admin"}, room=target_sid)
        disconnect(target_sid)
    elif cmd == "alert":
        emit('admin_alert', {'msg': data.get('msg')}, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
