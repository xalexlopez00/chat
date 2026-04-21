import os
from flask import Flask
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room) # Esto mete al usuario en la sala específica

@socketio.on('leave')
def on_leave(data):
    room = data['room']
    leave_room(room) # Esto lo saca

@socketio.on('message')
def handle_message(data):
    # data trae el mensaje cifrado y el nombre de la sala
    room = data.get('room', 'general')
    emit('message', data['msg'], room=room, include_self=False)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
