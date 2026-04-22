from gevent import monkey
monkey.patch_all()
import os
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect

app = Flask(__name__)
# Configuración de reconexión optimizada
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', ping_timeout=10, ping_interval=5)

# STORAGE DE SISTEMA
ROOMS = {"general": {"pass": "", "temp": False, "history": []}}
USERS = {} 

def broadcast_system_update():
    """Sincroniza el estado global de salas y usuarios en toda la red"""
    # Meta-datos de salas (para la barra lateral de los usuarios)
    rooms_meta = {name: {"has_pass": bool(info['pass']), "is_temp": info['temp']} 
                 for name, info in ROOMS.items()}
    socketio.emit('server_state_update', {
        'rooms': rooms_meta,
        'user_count': len(USERS)
    })
    # Datos sensibles (solo para el panel de Admin)
    socketio.emit('admin_sync_users', USERS)

@socketio.on('register_user')
def handle_registration(data):
    nick = data.get('nickname', 'Anonymous')
    USERS[request.sid] = {
        'nickname': nick,
        'ip': request.remote_addr,
        'connected_at': os.times()[4]
    }
    join_room("general")
    print(f"[AUTH] {nick} ha ingresado al sistema.")
    broadcast_system_update()
    emit('registration_confirmed', {'room': 'general'})

@socketio.on('create_room')
def handle_create_room(data):
    name = data.get('room', '').lower().strip()
    if name and name not in ROOMS:
        ROOMS[name] = {
            "pass": data.get('password', ''),
            "temp": data.get('temp', False),
            "history": []
        }
        print(f"[SYSTEM] Nueva sala desplegada: {name}")
        broadcast_system_update()
        # El creador se mueve a la sala
        handle_join_room({'room': name, 'password': data.get('password'), 'nickname': data.get('nickname')})

@socketio.on('join')
def handle_join_room(data):
    room = data.get('room', 'general')
    password = data.get('password', '')
    nickname = data.get('nickname', '')
    
    if room in ROOMS:
        target = ROOMS[room]
        # Regla de Oro: Admin tiene acceso total
        if target["pass"] and nickname != "Admin":
            if target["pass"] != password:
                emit('error_notification', {'msg': "Credenciales de sala inválidas"})
                return
        
        # Salir de la sala anterior (si no es general)
        leave_room(request.sid) # Limpia salas anteriores
        join_room(room)
        
        history = [] if target["temp"] else target["history"]
        emit('room_access_granted', {
            'room': room,
            'temp': target["temp"],
            'history': history
        })

@socketio.on('message')
def handle_message(data):
    room = data.get('room', 'general')
    msg = data.get('msg')
    
    # Broadcast a la sala
    emit('new_message', {'msg': msg, 'room': room}, room=room, include_self=False)
    
    # Persistencia en RAM (Buffer de 100 mensajes)
    if room in ROOMS and not ROOMS[room]["temp"]:
        ROOMS[room]["history"].append({'msg': msg})
        if len(ROOMS[room]["history"]) > 100:
            ROOMS[room]["history"].pop(0)

@socketio.on('admin_cmd')
def handle_admin_action(data):
    # Seguridad de Capa 7: Verificar si es el Admin
    if USERS.get(request.sid, {}).get('nickname') == "Admin":
        action = data.get('action')
        if action == "kick":
            target = data.get('target_sid')
            socketio.emit('error_notification', {'msg': "Desconectado por el Administrador"}, room=target)
            disconnect(target)
        elif action == "broadcast":
            emit('global_alert', {'msg': data.get('msg')}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in USERS:
        del USERS[request.sid]
    broadcast_system_update()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
