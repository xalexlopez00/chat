from gevent import monkey
monkey.patch_all()
import os, time
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
# Configuración de latencia ultra-baja
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', 
                    ping_timeout=60, ping_interval=25)

# DATABASE EN MEMORIA (OPTIMIZADA)
STATE = {
    "rooms": {
        "general": {"pass": "", "temp": False, "history": [], "users": 0}
    },
    "clients": {} # sid: {nickname, room}
}

def sync_all():
    """Sincronización selectiva: Salas para todos, perfiles para Admin"""
    rooms_meta = {n: {"locked": bool(i['pass']), "temp": i['temp'], "active": i['users']} 
                 for n, i in STATE['rooms'].items()}
    socketio.emit('update_rooms', rooms_meta)

@socketio.on('register_user')
def handle_reg(data):
    nick = data.get('nickname', 'User')
    STATE['clients'][request.sid] = {'nickname': nick, 'room': 'general'}
    join_room('general')
    STATE['rooms']['general']['users'] += 1
    sync_all()

@socketio.on('create_room')
def handle_create(data):
    name = data.get('room', '').lower().strip()
    if name and name not in STATE['rooms']:
        STATE['rooms'][name] = {
            "pass": data.get('password', ''),
            "temp": data.get('temp', False),
            "history": [],
            "users": 0
        }
        sync_all()

@socketio.on('join')
def handle_join(data):
    new_room = data.get('room')
    pw = data.get('password', '')
    client = STATE['clients'].get(request.sid)
    
    if new_room in STATE['rooms'] and client:
        # Bypass de seguridad para el Admin
        if STATE['rooms'][new_room]['pass'] and client['nickname'] != "Admin":
            if STATE['rooms'][new_room]['pass'] != pw:
                emit('error_msg', {'msg': "🔒 Acceso Denegado"})
                return
        
        # Salir de la sala anterior
        old_room = client['room']
        STATE['rooms'][old_room]['users'] -= 1
        
        # Entrar a la nueva
        client['room'] = new_room
        join_room(new_room)
        STATE['rooms'][new_room]['users'] += 1
        
        hist = [] if STATE['rooms'][new_room]['temp'] else STATE['rooms'][new_room]['history']
        emit('room_joined', {'room': new_room, 'history': hist})
        sync_all()

@socketio.on('message')
def handle_msg(data):
    room = data.get('room')
    if room in STATE['rooms']:
        emit('new_message', data, room=room, include_self=False)
        if not STATE['rooms'][room]['temp']:
            STATE['rooms'][room]['history'].append(data)
            if len(STATE['rooms'][room]['history']) > 50: STATE['rooms'][room]['history'].pop(0)

@socketio.on('disconnect')
def handle_exit():
    if request.sid in STATE['clients']:
        room = STATE['clients'][request.sid]['room']
        if room in STATE['rooms']:
            STATE['rooms'][room]['users'] -= 1
        del STATE['clients'][request.sid]
        sync_all()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
