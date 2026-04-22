from gevent import monkey
monkey.patch_all()
import os, time
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, disconnect

app = Flask(__name__)
# Configuración optimizada para evitar desconexiones en Render
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', 
                    ping_timeout=30, ping_interval=10)

# ESTRUCTURA DE DATOS PRO
ROOMS = {"general": {"pass": "", "temp": False, "history": []}}
USERS = {} 

def broadcast_sync():
    """Sincronización masiva de perfiles y salas"""
    rooms_meta = {n: {"locked": bool(i['pass']), "temp": i['temp']} for n, i in ROOMS.items()}
    socketio.emit('update_rooms', rooms_meta)
    socketio.emit('admin_sync_users', USERS)

@socketio.on('register_user')
def handle_reg(data):
    nick = data.get('nickname', 'Anonymous')
    USERS[request.sid] = {
        'nickname': nick,
        'ip': request.remote_addr,
        'sid': request.sid,
        'joined': time.strftime('%H:%M:%S'),
        'status': 'Online'
    }
    join_room("general")
    broadcast_sync()

@socketio.on('join')
def handle_join(data):
    room, pw, nick = data.get('room'), data.get('password'), data.get('nickname')
    if room in ROOMS:
        # BYPASS MAESTRO: El admin no necesita contraseña
        if ROOMS[room]['pass'] and nick != "Admin" and ROOMS[room]['pass'] != pw:
            emit('error_msg', {'msg': "🔒 Acceso denegado: Clave incorrecta"})
            return
        join_room(room)
        emit('room_joined', {'room': room, 'history': [] if ROOMS[room]['temp'] else ROOMS[room]['history']})

@socketio.on('message')
def handle_msg(data):
    room, msg = data.get('room'), data.get('msg')
    emit('new_message', {'msg': msg, 'room': room}, room=room, include_self=False)
    if room in ROOMS and not ROOMS[room]['temp']:
        ROOMS[room]['history'].append({'msg': msg})
        if len(ROOMS[room]['history']) > 50: ROOMS[room]['history'].pop(0)

@socketio.on('admin_cmd')
def handle_admin(data):
    # Verificación de identidad Admin en el servidor
    if USERS.get(request.sid, {}).get('nickname') == "Admin":
        action, target = data.get('action'), data.get('target_sid')
        if action == "kick":
            socketio.emit('error_msg', {'msg': "Expulsado por la administración."}, room=target)
            disconnect(target)
        elif action == "broadcast":
            emit('system_alert', {'msg': data.get('msg')}, broadcast=True)

@socketio.on('disconnect')
def handle_disc():
    if request.sid in USERS: del USERS[request.sid]
    broadcast_sync()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
