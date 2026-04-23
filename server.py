from gevent import monkey
monkey.patch_all()
import os
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
# Configuración para detectar desconexiones en 15 segundos
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', 
                    ping_timeout=15, ping_interval=5)

# Estructura: { "nombre": {"history": [], "temp": bool, "pass": str, "users": set()} }
ROOMS = {"general": {"history": [], "temp": False, "pass": "", "users": set()}}

def sync_rooms():
    """Envía la lista de salas y usuarios activos a todos los clientes"""
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
        # Validación de contraseña
        if ROOMS[room]["pass"] and pw != ROOMS[room]["pass"]:
            emit('error_msg', {'msg': "🔒 Contraseña incorrecta"})
            return
            
        # Salida limpia de la sala anterior
        if old_room and old_room in ROOMS:
            leave_room(old_room)
            if request.sid in ROOMS[old_room]["users"]:
                ROOMS[old_room]["users"].remove(request.sid)
        
        join_room(room)
        ROOMS[room]["users"].add(request.sid)
        sync_rooms()
        
        # Si es temporal, no enviamos historial
        hist = [] if ROOMS[room]["temp"] else ROOMS[room]["history"]
        emit('room_joined', {'room': room, 'history': hist})

@socketio.on('message')
def handle_msg(data):
    room = data.get('room')
    if room in ROOMS:
        # Solo guardar si NO es temporal
        if not ROOMS[room]['temp']:
            ROOMS[room]['history'].append(data)
            if len(ROOMS[room]['history']) > 50: ROOMS[room]['history'].pop(0)
        
        emit('new_message', data, room=room, include_self=False)

@socketio.on('disconnect')
def handle_disc():
    """Limpieza de 'fantasmas' al cerrar la app"""
    for room_data in ROOMS.values():
        if request.sid in room_data["users"]:
            room_data["users"].remove(request.sid)
    sync_rooms()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
