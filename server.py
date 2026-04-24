from gevent import monkey
monkey.patch_all()
import os
import requests
import json
from flask import Flask, request, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room

# Para el cifrado del backup TXT
from cryptography.fernet import Fernet
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- CONFIGURACIÓN DISCORD ---
# Necesitas un TOKEN de Bot de Discord para crear canales (No solo webhook)
DISCORD_TOKEN = "TU_BOT_TOKEN_AQUI" 
GUILD_ID = "TU_SERVER_ID_AQUI"
CATEGORY_NAME = "CHAT_GHOST"

# Función para cifrar el archivo de backup (contraseña: chats123)
def encrypt_backup(text):
    salt = b'\x14\xab\x11\xcd\xfe\xed\x11\x22'
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    key = base64.urlsafe_b64encode(kdf.derive(b"chats123"))
    return Fernet(key).encrypt(text.encode())

def discord_api(method, endpoint, data=None):
    url = f"https://discord.com/api/v10{endpoint}"
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}", "Content-Type": "application/json"}
    if method == "GET": return requests.get(url, headers=headers).json()
    return requests.post(url, headers=headers, json=data).json()

def setup_discord_channel(room_name):
    """ Crea la categoría y el canal si no existen """
    try:
        channels = discord_api("GET", f"/guilds/{GUILD_ID}/channels")
        category_id = next((c['id'] for c in channels if c['name'].upper() == CATEGORY_NAME), None)
        
        if not category_id:
            cat = discord_api("POST", f"/guilds/{GUILD_ID}/channels", {"name": CATEGORY_NAME, "type": 4})
            category_id = cat['id']

        channel = next((c for c in channels if c['name'] == room_name.lower()), None)
        if not channel:
            new_ch = discord_api("POST", f"/guilds/{GUILD_ID}/channels", {
                "name": room_name.lower(),
                "type": 0,
                "parent_id": category_id
            })
            return new_ch['id']
        return channel['id']
    except: return None

# Almacén de salas
ROOMS = {"general": {"history": [], "temp": False, "pass": "", "users": set(), "msg_count": 0}}

@socketio.on('message')
def handle_msg(data):
    room = data.get('room')
    if room in ROOMS:
        ROOMS[room]['history'].append(data)
        ROOMS[room]['msg_count'] += 1
        
        # Enviar a Discord (Normal)
        channel_id = setup_discord_channel(room)
        if channel_id:
            content = f"**{data['user']}**: `{data['msg']}`"
            discord_api("POST", f"/channels/{channel_id}/messages", {"content": content})

        # BACKUP CADA 100 MENSAJES
        if ROOMS[room]['msg_count'] >= 100:
            full_text = "\n".join([f"{m['user']}: {m['msg']}" for m in ROOMS[room]['history']])
            encrypted_data = encrypt_backup(full_text)
            
            with open("backup.txt", "wb") as f:
                f.write(encrypted_data)
            
            # Enviar archivo a Discord
            files = {'file': ('backup_cifrado.txt', open('backup.txt', 'rb'))}
            requests.post(f"https://discord.com/api/v10/channels/{channel_id}/messages", 
                          headers={"Authorization": f"Bot {DISCORD_TOKEN}"}, 
                          files=files, data={"content": "📦 **BACKUP 100 MSGS - CIFRADO (chats123)**"})
            
            ROOMS[room]['msg_count'] = 0 # Reiniciar contador

        emit('new_message', data, room=room, include_self=False)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
