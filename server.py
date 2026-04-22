import os
from flask import Flask
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Diccionario para guardar contraseñas de salas: {nombre_sala: password}
rooms_db = {"general": None}

# Carpeta para logs
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def save_log(room, message):
    with open(f"{LOG_DIR}/{room}.txt", "a", encoding="utf-8") as f:
        f.write(message + "\n")

@socketio.on('create_room')
def handle_create(data):
    room = data['room']
    password = data.get('password')
    rooms_db[room] = password
    emit('room_list', list(rooms_db.keys()), broadcast=True)

@socketio.on('join')
def on_join(data):
    room = data['room']
    password = data.get('password')
    
    if rooms_db.get(room) == password:
        join_room(room)
        emit('status', {'msg': f"Usuario unido a {room}"}, room=room)
    else:
        emit('error', {'msg': "Contraseña incorrecta"})

@socketio.on('message')
def handle_message(data):
    room = data.get('room', 'general')
    msg_encrypted = data['msg'] # Viene cifrado desde el cliente
    emit('message', msg_encrypted, room=room, include_self=False)
    save_log(room, f"Encrypted: {msg_encrypted}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
