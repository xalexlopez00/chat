import socket
import threading
import time

# --- CONFIGURACIÓN DEL CHAT ---
CHAT_PORT = 5555
DISCOVERY_PORT = 5556

def discovery_beacon():
    """Envía un paquete UDP cada 2 segundos anunciando el servidor"""
    broadcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    broadcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    print(f"Anunciando servidor en el puerto UDP {DISCOVERY_PORT}...")
    while True:
        # Enviamos un mensaje identificador
        broadcast_sock.sendto(b"CHAT_SERVER_HERE", ('<broadcast>', DISCOVERY_PORT))
        time.sleep(2)

# --- LÓGICA DEL SERVIDOR DE CHAT (Igual que antes) ---
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(('0.0.0.0', CHAT_PORT))
server.listen()
clients = []

def broadcast(message, _client):
    for client in clients:
        if client != _client:
            client.send(message)

def handle_client(client):
    while True:
        try:
            message = client.recv(1024)
            if not message: break
            broadcast(message, client)
        except:
            if client in clients: clients.remove(client)
            client.close()
            break

# Lanzar el anuncio automático en un hilo aparte
threading.Thread(target=discovery_beacon, daemon=True).start()

print(f"Servidor de Chat iniciado en puerto {CHAT_PORT}...")
while True:
    client, addr = server.accept()
    clients.append(client)
    threading.Thread(target=handle_client, args=(client,)).start()