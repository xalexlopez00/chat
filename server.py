import os
from flask import Flask
from flask_socketio import SocketIO, emit

app = Flask(__name__)
# Permitimos que cualquier cliente se conecte
socketio = SocketIO(app, cors_allowed_origins="*")

@app.route('/')
def index():
    return "Servidor de Chat Cifrado Activo", 200

@socketio.on('message')
def handle_message(data):
    # Reenvía el mensaje cifrado a todos excepto al que lo envió
    emit('message', data, broadcast=True, include_self=False)

if __name__ == '__main__':
    # Render usa la variable PORT
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
