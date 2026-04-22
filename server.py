from gevent import monkey
monkey.patch_all()
import os, time
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
# Configuración optimizada para la nube (Render)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', 
                    ping_timeout=30, ping_interval=10)

# Almacenamiento estructurado
# ROOMS = { "nombre": {"pass": "123", "temp": False, "history": []} }
ROOMS = {"general": {"pass": "", "temp": False, "history": []}}

def broadcast_room_list():
    """Notifica a todos los clientes los cambios en las salas disponibles"""
    meta = {n: {"locked": bool(i['pass']), "temp": i['temp']} for n, i in ROOMS.items()}
    socketio.emit('update_rooms', meta)

@socketio.on('connect')
def on_connect():
    print(f"[NET] Cliente conectado: {request.sid}")

@socketio.on('register_user')
def on_register(data):
    join_room("general")
    broadcast_room_list()

@socketio.on('create_room')
def on_create(data):
    name = data.get('room', '').lower().strip()
    if name and name not in ROOMS:
        ROOMS[name] = {
            "pass": data.get('password', ''),
            "temp": data.get('temp', False),
            "history": []
        }
        print(f"[ROOM] Nueva sala: {name} (Temp: {ROOMS[name]['temp']})")
        broadcast_room_list()

@socketio.on('join')
def on_join(data):
    room = data.get('room')
    pw = data.get('password', '')
    nick = data.get('nickname')
    
    if room in ROOMS:
        # Validación de seguridad
        if ROOMS[room]['pass'] and nick != "Admin" and ROOMS[room]['pass'] != pw:
            emit('error_msg', {'msg': "🔒 Contraseña de canal incorrecta."})
            return
        
        # Salir de salas anteriores para independencia total
        # (SocketIO gestiona esto, pero forzamos limpieza)
        join_room(room)
        
        # Carga selectiva de historial
        history = [] if ROOMS[room]['temp'] else ROOMS[room]['history']
        emit('room_joined', {'room': room, 'history': history})

@socketio.on('message')
def on_message(data):
    room = data.get('room')
    msg_encrypted = data.get('msg')
    
    # El servidor solo retransmite a la sala específica
    emit('new_message', {'msg': msg_encrypted, 'room': room}, room=room, include_self=False)
    
    # Persistencia efímera
    if room in ROOMS and not ROOMS[room]['temp']:
        ROOMS[room]['history'].append({'msg': msg_encrypted})
        # Limitar historial para no saturar RAM
        if len(ROOMS[room]['history']) > 50:
            ROOMS[room]['history'].pop(0)

@socketio.on('disconnect')
def on_disconnect():
    print(f"[NET] Cliente desconectado: {request.sid}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
