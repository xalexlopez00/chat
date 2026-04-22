from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# ESTRUCTURA PROFESIONAL DE DATOS
# ROOMS: { 'nombre': {'pass': str, 'temp': bool, 'history': list} }
ROOMS = {
    "general": {"pass": "", "temp": False, "history": []}
}
# AUTH: { sid: [salas_donde_ha_entrado] }
AUTH_LOG = {}

@socketio.on('connect')
def on_connect():
    AUTH_LOG[request.sid] = ["general"]
    join_room("general")

@socketio.on('create_room')
def on_create(data):
    name = data.get('room', '').lower().strip()
    password = data.get('password', '')
    is_temp = data.get('temp', False)
    
    if name and name not in ROOMS:
        ROOMS[name] = {
            "pass": password,
            "temp": is_temp,
            "history": []
        }
        AUTH_LOG[request.sid].append(name)
        join_room(name)
        
        # Confirmación con metadatos
        emit('join_success', {
            'room': name, 
            'temp': is_temp, 
            'history': []
        })
        # Notificación global de nueva sala
        emit('new_room_available', {
            'room': name, 
            'has_pass': bool(password)
        }, broadcast=True)

@socketio.on('join')
def on_join(data):
    room = data.get('room', 'general')
    password = data.get('password', '')
    nickname = data.get('nickname', '')
    
    if room not in ROOMS:
        emit('error_msg', {'msg': "La sala no existe"})
        return

    # Validación Maestra
    target = ROOMS[room]
    if target["pass"] and nickname != "Admin":
        if target["pass"] != password:
            emit('error_msg', {'msg': "Acceso denegado: Clave incorrecta"})
            return

    join_room(room)
    if room not in AUTH_LOG[request.sid]:
        AUTH_LOG[request.sid].append(room)
    
    # Enviar historial solo si no es temporal
    history_to_send = [] if target["temp"] else target["history"]
    emit('join_success', {
        'room': room, 
        'temp': target["temp"], 
        'history': history_to_send
    })

@socketio.on('message')
def on_message(data):
    room = data.get('room', 'general')
    msg = data.get('msg')
    
    if room in AUTH_LOG.get(request.sid, []):
        # Reenvío a la sala
        emit('message', {'msg': msg, 'room': room}, room=room, include_self=False)
        
        # Guardado en memoria volátil (Historial de sesión)
        if not ROOMS[room]["temp"]:
            ROOMS[room]["history"].append({'msg': msg})
            # Limitar historial a los últimos 100 para eficiencia
            if len(ROOMS[room]["history"]) > 100:
                ROOMS[room]["history"].pop(0)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
