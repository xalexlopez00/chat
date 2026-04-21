import os
from flask import Flask
from flask_socketio import SocketIO, emit

# Creamos la app de Flask necesaria para que Render la reconozca
app = Flask(__name__)
# Usamos SocketIO para manejar el chat por WebSockets
socketio = SocketIO(app, cors_allowed_origins="*")

@socketio.on('message')
def handle_message(encrypted_data):
    """
    Recibe el mensaje cifrado de un cliente y lo 
    reenvía a todos los demás conectados.
    """
    print("Mensaje cifrado recibido y reenviado.")
    emit('message', encrypted_data, broadcast=True, include_self=False)

@app.route('/')
def health_check():
    """Ruta necesaria para que Render sepa que el servidor está online"""
    return "Servidor de Chat Cifrado Online", 200

if __name__ == '__main__':
    # Render asigna el puerto mediante la variable de entorno PORT
    # Si no existe (local), usa el 5000
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
