from gevent import monkey
monkey.patch_all()
import os
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room, close_room

app = Flask(__name__)
# Configuración para detección rápida de desconexiones
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', 
                    ping_timeout=15, ping_interval=5)

# ROOMS = { "nombre": {"history": [], "temp": bool, "pass": str, "users": set()} }
ROOMS = {"general": {"history": [], "temp": False, "pass": "", "users": set()}}

def sync_rooms():
    """Envía a todos los clientes la lista actualizada de salas y ocupación"""
    data = {n: {
        "temp": i["temp"], 
        "locked": bool(i["pass"]), 
        "count": len(i["users"])
    } for n, i in ROOMS.items()}
    socketio.emit('update_rooms', data)

@socketio.on('register_user')
def handle_reg(data):
    join_room("general")
    ROOMS["general"]["users"].add(request.sid)
    sync_rooms()
    emit('room_joined', {'room': 'general', 'history': ROOMS['general']['history']})

@socketio.on('create_room')
def handle_create(data):
    name = data.get('room', '').lower().strip()
    if name and name not in ROOMS:
        ROOMS[name] = {
            "history": [], 
            "temp": data.get('temp', False), 
            "pass": data.get('password', ""), 
            "users": set()
        }
        sync_rooms()

@socketio.on('join')
def handle_join(data):
    room = data.get('room')
    pw = data.get('password', "")
    old_room = data.get('old_room')
    
    if room in ROOMS:
        # Validar contraseña si la sala tiene una
        if ROOMS[room]["pass"] and pw != ROOMS[room]["pass"]:
            emit('error_msg', {'msg': "🔒 Contraseña incorrecta"})
            return
            
        # Salir de la sala anterior limpiamente
        if old_room and old_room in ROOMS:
            leave_room(old_room)
            if request.sid in ROOMS[old_room]["users"]:
                ROOMS[old_room]["users"].remove(request.sid)
        
        join_room(room)
        ROOMS[room]["users"].add(request.sid)
        sync_rooms()
        
        # Si la sala es temporal, el historial enviado siempre es vacío
        hist = [] if ROOMS[room]["temp"] else ROOMS[room]["history"]
        emit('room_joined', {'room': room, 'history': hist})

@socketio.on('message')
def handle_msg(data):
    room = data.get('room')
    if room in ROOMS:
        # Solo guardar si la sala NO es temporal
        if not ROOMS[room]['temp']:
            ROOMS[room]['history'].append(data)
            if len(ROOMS[room]['history']) > 50: ROOMS[room]['history'].pop(0)
        
        emit('new_message', data, room=room, include_self=False)

@socketio.on('disconnect')
def handle_disc():
    """Elimina al usuario de cualquier sala para evitar 'fantasmas'"""
    for room_name, room_data in ROOMS.items():
        if request.sid in room_data["users"]:
            room_data["users"].remove(request.sid)
    sync_rooms()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
