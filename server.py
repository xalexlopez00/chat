from gevent import monkey
monkey.patch_all()
import os
import time
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, disconnect

app = Flask(__name__)
# Configuración de alto rendimiento: Pings frecuentes para que Render no mate la conexión
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', 
                    ping_timeout=25, ping_interval=10)

# --- BASE DE DATOS EN MEMORIA ---
ROOMS = {"general": {"pass": "", "temp": False, "history": []}}
USERS = {} # Estructura: { sid: { nickname, ip, sid, joined, last_active } }

def broadcast_system_state():
    """Sincroniza salas con usuarios y la tabla maestra con el Admin"""
    # 1. Metadatos de salas para los clientes (Público)
    rooms_meta = {n: {"locked": bool(i['pass']), "temp": i['temp']} 
                 for n, i in ROOMS.items()}
    socketio.emit('server_sync', {
        'rooms': rooms_meta, 
        'user_count': len(USERS)
    })
    
    # 2. Diccionario completo de usuarios para el Admin (Privado)
    socketio.emit('admin_user_list', USERS)

@socketio.on('connect')
def handle_connect():
    print(f"[DEBUG] Conexión física establecida: {request.sid}")

@socketio.on('register_user')
def handle_register(data):
    nick = data.get('nickname', 'User')
    # Guardamos el perfil completo del usuario
    USERS[request.sid] = {
        'nickname': nick,
        'ip': request.remote_addr,
        'sid': request.sid,
        'joined': time.strftime('%H:%M:%S'),
        'status': 'Online'
    }
    join_room("general")
    print(f"[AUTH] {nick} se ha registrado con éxito.")
    broadcast_system_state()

@socketio.on('create_room')
def handle_create(data):
    name = data.get('room', '').lower().strip()
    if name and name not in ROOMS:
        ROOMS[name] = {
            "pass": data.get('password', ''),
            "temp": data.get('temp', False),
            "history": []
        }
        print(f"[ROOM] Sala '{name}' creada.")
        broadcast_system_state()

@socketio.on('join')
def handle_join(data):
    room = data.get('room', 'general')
    pw = data.get('password', '')
    nick = data.get('nickname', '')
    
    if room in ROOMS:
        target = ROOMS[room]
        # BYPASS DE ADMIN: El Admin entra a cualquier sala sin pass
        if target['pass'] and nick != "Admin":
            if target['pass'] != pw:
                emit('server_error', {'msg': "Contraseña incorrecta."})
                return
        
        join_room(room)
        # Enviar historial solo si la sala no es temporal
        history = [] if target['temp'] else target['history']
        emit('room_ready', {
            'room': room,
            'is_temp': target['temp'],
            'history': history
        })

@socketio.on('message')
def handle_message(data):
    room = data.get('room', 'general')
    msg = data.get('msg') # El mensaje ya viene encriptado desde el cliente
    
    # Reenviar a todos en la sala
    emit('new_msg', {'msg': msg, 'room': room}, room=room, include_self=False)
    
    # Guardar en historial si la sala es permanente
    if room in ROOMS and not ROOMS[room]['temp']:
        ROOMS[room]['history'].append({'msg': msg})
        # Mantener historial corto para no saturar la RAM de Render
        if len(ROOMS[room]['history']) > 50:
            ROOMS[room]['history'].pop(0)

@socketio.on('admin_action')
def handle_admin(data):
    # Verificación de Seguridad: Solo el socket con nick 'Admin' puede mandar esto
    if USERS.get(request.sid, {}).get('nickname') == "Admin":
        action = data.get('action')
        target_sid = data.get('target_sid')
        
        if action == "kick" and target_sid in USERS:
            print(f"[ADMIN] Expulsando a {USERS[target_sid]['nickname']}")
            socketio.emit('server_error', {'msg': "Has sido expulsado por el Admin."}, room=target_sid)
            disconnect(target_sid)
            
        elif action == "broadcast":
            print(f"[ADMIN] Alerta global: {data.get('msg')}")
            emit('alert', {'msg': data.get('msg')}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in USERS:
        print(f"[QUIT] {USERS[request.sid]['nickname']} se ha desconectado.")
        del USERS[request.sid]
    broadcast_system_state()

if __name__ == '__main__':
    # Render usa la variable de entorno PORT
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
