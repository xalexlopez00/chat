from gevent import monkey
monkey.patch_all()
import os, time
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, disconnect

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', ping_timeout=30)

# DB VOLÁTIL
ROOMS = {"general": {"pass": "", "temp": False, "history": []}}
USERS = {} 

def sync_all():
    """Sincronización forzada de todo el ecosistema"""
    # Para Usuarios: Lista de salas
    rooms_meta = {n: {"locked": bool(i['pass']), "temp": i['temp']} for n, i in ROOMS.items()}
    socketio.emit('update_rooms', rooms_meta)
    # Para Admin: Lista detallada de usuarios
    socketio.emit('admin_sync_users', USERS)

@socketio.on('register_user')
def handle_reg(data):
    nick = data.get('nickname', 'Anonymous')
    USERS[request.sid] = {
        'nickname': nick,
        'ip': request.remote_addr,
        'sid': request.sid,
        'joined': time.strftime('%H:%M:%S')
    }
    join_room("general")
    sync_all()

@socketio.on('create_room')
def handle_create(data):
    name = data.get('room', '').lower().strip()
    if name and name not in ROOMS:
        ROOMS[name] = {
            "pass": data.get('password', ''),
            "temp": data.get('temp', False),
            "history": []
        }
        sync_all()

@socketio.on('join')
def handle_join(data):
    room, pw, nick = data.get('room'), data.get('password'), data.get('nickname')
    if room in ROOMS:
        # BYPASS ADMIN: Si el nick es Admin, entra directo
        if ROOMS[room]['pass'] and nick != "Admin":
            if ROOMS[room]['pass'] != pw:
                emit('error_msg', {'msg': "🔒 Clave incorrecta"})
                return
        join_room(room)
        # Enviar historial al entrar (si no es temporal)
        hist = [] if ROOMS[room]['temp'] else ROOMS[room]['history']
        emit('room_joined', {'room': room, 'history': hist})

@socketio.on('message')
def handle_msg(data):
    room, msg = data.get('room'), data.get('msg')
    # Reenvío a la sala (excepto al que envía para evitar duplicados en UI)
    emit('new_message', {'msg': msg, 'room': room}, room=room, include_self=False)
    # Guardar si no es efímero
    if room in ROOMS and not ROOMS[room]['temp']:
        ROOMS[room]['history'].append({'msg': msg})
        if len(ROOMS[room]['history']) > 50: ROOMS[room]['history'].pop(0)

@socketio.on('admin_cmd')
def handle_admin(data):
    # Verificación de capa 7: solo el socket con nick Admin tiene poder
    if USERS.get(request.sid, {}).get('nickname') == "Admin":
        action, target = data.get('action'), data.get('target_sid')
        if action == "kick":
            socketio.emit('error_msg', {'msg': "Expulsado por Admin"}, room=target)
            disconnect(target)
        elif action == "broadcast":
            emit('system_alert', {'msg': data.get('msg')}, broadcast=True)

@socketio.on('disconnect')
def handle_disc():
    if request.sid in USERS: del USERS[request.sid]
    sync_all()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
