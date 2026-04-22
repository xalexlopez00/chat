from gevent import monkey
monkey.patch_all()
import os
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, disconnect

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# DB VOLÁTIL
ROOMS = {"general": {"pass": "", "temp": False, "history": []}}
USERS = {} # { sid: {'nickname': str, 'ip': str} }

def sync_admins():
    """Envía la lista de usuarios actualizada a todos los conectados"""
    socketio.emit('admin_user_sync', USERS)

@socketio.on('register_user')
def on_register(data):
    nick = data.get('nickname', 'User')
    # Guardamos datos del usuario
    USERS[request.sid] = {
        'nickname': nick, 
        'ip': request.remote_addr,
        'sid': request.sid
    }
    join_room("general")
    # Sincronización inmediata
    sync_admins()
    # Enviar salas existentes al nuevo
    for r_name, r_info in ROOMS.items():
        emit('new_room_available', {'room': r_name, 'has_pass': bool(r_info['pass'])})

@socketio.on('disconnect')
def on_disconnect():
    if request.sid in USERS:
        print(f"Usuario desconectado: {USERS[request.sid]['nickname']}")
        del USERS[request.sid]
    sync_admins() # Actualizar lista del admin al instante

@socketio.on('admin_action')
def on_admin(data):
    # Verificación de seguridad: solo el Admin real puede ejecutar esto
    if USERS.get(request.sid, {}).get('nickname') == "Admin":
        action = data.get('action')
        target = data.get('target_sid')
        if action == "kick" and target in USERS:
            socketio.emit('broadcast_alert', {'msg': f"Usuario {USERS[target]['nickname']} expulsado."}, broadcast=True)
            disconnect(target)
        elif action == "alert":
            emit('broadcast_alert', {'msg': data.get('msg')}, broadcast=True)

# ... (Mantener el resto de funciones de join, message y create_room igual)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
