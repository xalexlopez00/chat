import os
from flask import Flask
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    emit('status', {'msg': f"Alguien entró a la sala: {room}"}, room=room)

@socketio.on('message')
def handle_message(data):
    # data ahora debe incluir: {'msg': encrypted_data, 'room': room_name}
    room = data.get('room', 'general')
    emit('message', data['msg'], room=room, include_self=False)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
