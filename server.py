from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# ESTRUCTURA DE DATOS GLOBAL
# ROOMS: { 'nombre': {'pass': str, 'temp': bool, 'history': list} }
ROOMS = {"general": {"pass": "", "temp": False, "history": []}}
USERS = {} # { sid: {'nickname': str, 'ip': str} }

@socketio.on('connect')
def on_connect():
    # El usuario se une a una sala de espera hasta que se registre
    join_room("waiting_room")

@socketio.on('register_user')
def on_register(data):
    nick = data.get('nickname', 'User')
    USERS[request.sid] = {'nickname': nick, 'ip': request.remote_addr}
    leave_room("waiting_room")
    join_room("general")
    # Notificar a los admins sobre la actualización de la lista
    emit('admin_user_sync', USERS, broadcast=True)

@socketio.on('disconnect')
def on_disconnect():
    if request.sid in USERS:
        del USERS[request.sid]
    emit('admin_user_sync', USERS, broadcast=True)

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

    target = ROOMS[room]
    # Bypass: Si el usuario es 'Admin', no se valida contraseña
    if target["pass"] and nickname != "Admin":
        if target["pass"] != password:
            emit('error_msg', {'msg': "Acceso denegado: Clave incorrecta"})
            return

    join_room(room)
    # Si la sala es temporal, enviamos historial vacío
    history = [] if target["temp"] else target["history"]
    emit('join_success', {'room': room, 'temp': target["temp"], 'history': history})

@socketio.on('message')
def on_message(data):
    room = data.get('room', 'general')
    msg = data.get('msg') # Viene cifrado desde el cliente
    
    # Emitir a los demás en la sala
    emit('message', {'msg': msg, 'room': room}, room=room, include_self=False)
    
    # Almacenar en historial si no es temporal (Máximo 100 mensajes)
    if room in ROOMS and not ROOMS[room]["temp"]:
        ROOMS[room]["history"].append({'msg': msg})
        if len(ROOMS[room]["history"]) > 100:
            ROOMS[room]["history"].pop(0)

# MODULO DE COMANDOS MAESTROS (Solo para Admin)
@socketio.on('admin_action')
def on_admin_action(data):
    if USERS.get(request.sid, {}).get('nickname') != "Admin": return
    
    action = data.get('action')
    target_sid = data.get('target_sid')
    
    if action == "kick":
        emit('broadcast_alert', {'msg': "SISTEMA: Un usuario ha sido expulsado."}, broadcast=True)
        disconnect(target_sid)
    elif action == "alert":
        emit('broadcast_alert', {'msg': f"AVISO GLOBAL: {data.get('msg')}"}, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
