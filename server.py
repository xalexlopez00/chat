from gevent import monkey
monkey.patch_all()
import os, time
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, disconnect

app = Flask(__name__)
# Configuración optimizada para evitar micro-cortes en Render
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', 
                    ping_timeout=15, ping_interval=5)

# CORE DATA
ROOMS = {"general": {"pass": "", "temp": False, "history": []}}
USERS = {} # { sid: {profile_data} }

def broadcast_sync():
    """Sincronización masiva de estado para Clientes y Admin"""
    rooms_summary = {n: {"locked": bool(i['pass']), "temp": i['temp']} 
                    for n, i in ROOMS.items()}
    socketio.emit('global_sync', {
        'rooms': rooms_summary,
        'active_users': len(USERS)
    })
    socketio.emit('admin_user_table', USERS)

@socketio.on('register_user')
def on_register(data):
    nick = data.get('nickname', 'User')
    USERS[request.sid] = {
        'nickname': nick,
        'ip': request.remote_addr,
        'sid': request.sid,
        'joined': time.strftime('%H:%M:%S'),
        'browser': request.headers.get('User-Agent', 'Unknown')[:50]
    }
    join_room("general")
    print(f"[AUTH] {nick} sincronizado.")
    broadcast_sync()

@socketio.on('create_room')
def on_create(data):
    name = data.get('room', '').lower().strip()
    if name and name not in ROOMS:
        ROOMS[name] = {
            "pass": data.get('password', ''),
            "temp": data.get('temp', False),
            "history": []
        }
        broadcast_sync()

@socketio.on('join')
def on_join(data):
    room, pw, nick = data.get('room'), data.get('password'), data.get('nickname')
    if room in ROOMS:
        target = ROOMS[room]
        # Bypass Maestro para el Admin
        if target["pass"] and nick != "Admin" and target["pass"] != pw:
            emit('server_error', {'msg': "Acceso denegado: Clave incorrecta."})
            return
        
        join_room(room)
        emit('room_ready', {
            'room': room,
            'is_temp': target['temp'],
            'history': [] if target['temp'] else target['history']
        })

@socketio.on('message')
def on_message(data):
    room, msg = data.get('room'), data.get('msg')
    # Reenvío encriptado
    emit('new_msg', {'msg': msg, 'room': room}, room=room, include_self=False)
    # Persistencia selectiva
    if room in ROOMS and not ROOMS[room]['temp']:
        ROOMS[room]['history'].append({'msg': msg})
        if len(ROOMS[room]['history']) > 100: ROOMS[room]['history'].pop(0)

@socketio.on('admin_execute')
def on_admin(data):
    # Verificación de identidad Admin
    if USERS.get(request.sid, {}).get('nickname') == "Admin":
        action, target = data.get('action'), data.get('target_sid')
        if action == "kick":
            socketio.emit('server_error', {'msg': "Expulsado por el Admin."}, room=target)
            disconnect(target)
        elif action == "broadcast":
            emit('global_alert', {'msg': data.get('msg')}, broadcast=True)

@socketio.on('disconnect')
def on_disconnect():
    if request.sid in USERS: del USERS[request.sid]
    broadcast_sync()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
