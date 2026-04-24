from gevent import monkey
monkey.patch_all()
import os
import requests
import json
import base64
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- CONFIGURACIÓN SEGURA (LEER DESDE RENDER) ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID") 
CATEGORY_NAME = "CHAT_GHOST"

# Lógica para cifrar el archivo de backup (contraseña: chats123)
def encrypt_backup(text):
    salt = b'\x14\xab\x11\xcd\xfe\xed\x11\x22'
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    key = base64.urlsafe_b64encode(kdf.derive(b"chats123"))
    return Fernet(key).encrypt(text.encode())

def discord_api(method, endpoint, data=None):
    if not DISCORD_TOKEN: return None
    url = f"https://discord.com/api/v10{endpoint}"
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}", "Content-Type": "application/json"}
    try:
        if method == "GET": return requests.get(url, headers=headers).json()
        return requests.post(url, headers=headers, json=data).json()
    except: return None

def setup_discord_channel(room_name):
    if not GUILD_ID: return None
    try:
        channels = discord_api("GET", f"/guilds/{GUILD_ID}/channels")
        if not isinstance(channels, list): return None
        
        category = next((c for c in channels if str(c.get('name', '')).upper() == CATEGORY_NAME), None)
        if not category:
            category = discord_api("POST", f"/guilds/{GUILD_ID}/channels", {"name": CATEGORY_NAME, "type": 4})

        channel_name = room_name.lower().replace(" ", "_")
        channel = next((c for c in channels if c.get('name') == channel_name), None)
        
        if not channel:
            channel = discord_api("POST", f"/guilds/{GUILD_ID}/channels", {
                "name": channel_name, "type": 0, "parent_id": category['id']
            })
        return channel['id']
    except: return None

# Memoria del servidor
ROOMS = {"general": {"history": [], "temp": False, "pass": "", "users": set(), "msg_count": 0}}

def sync_rooms():
    data = {n: {"temp": i["temp"], "locked": bool(i["pass"]), "count": len(i["users"])} for n, i in ROOMS.items()}
    socketio.emit('update_rooms', data)

@socketio.on('register_user')
def handle_reg(data):
    join_room("general")
    ROOMS["general"]["users"].add(request.sid)
    sync_rooms()
    emit('room_joined', {'room': 'general', 'history': ROOMS['general']['history']})

@socketio.on('create_room')
def handle_create(data):
    name = data.get('room', '').lower().strip().replace(" ", "_")
    if name and name not in ROOMS:
        ROOMS[name] = {"history": [], "temp": data.get('temp', False), "pass": data.get('password', ""), "users": set(), "msg_count": 0}
        sync_rooms()

@socketio.on('join')
def handle_join(data):
    room = data.get('room')
    old_room = data.get('old_room')
    password = data.get('password', "")
    if room in ROOMS:
        if ROOMS[room]["pass"] and ROOMS[room]["pass"] != password:
            emit('error_msg', {'msg': 'Clave incorrecta'})
            return
        if old_room and old_room in ROOMS:
            leave_room(old_room)
            ROOMS[old_room]["users"].discard(request.sid)
        join_room(room)
        ROOMS[room]["users"].add(request.sid)
        sync_rooms()
        emit('room_joined', {'room': room, 'history': ROOMS[room]['history']})

@socketio.on('message')
def handle_msg(data):
    room = data.get('room')
    if room in ROOMS:
        # Guardar en historial si no es efímera
        if not ROOMS[room]['temp']:
            ROOMS[room]['history'].append(data)
            ROOMS[room]['msg_count'] += 1
        
        # Enviar mensaje a Discord
        channel_id = setup_discord_channel(room)
        if channel_id:
            discord_api("POST", f"/channels/{channel_id}/messages", {"content": f"**{data['user']}**: `{data['msg']}`"})

        # Backup automático cada 100 mensajes
        if ROOMS[room]['msg_count'] >= 100:
            content = "\n".join([f"{m['user']}: {m['msg']}" for m in ROOMS[room]['history']])
            enc_data = encrypt_backup(content)
            requests.post(f"https://discord.com/api/v10/channels/{channel_id}/messages", 
                          headers={"Authorization": f"Bot {DISCORD_TOKEN}"}, 
                          files={'file': ('backup_cifrado.txt', enc_data)},
                          data={"content": "📦 **BACKUP GENERADO (Clave: chats123)**"})
            ROOMS[room]['msg_count'] = 0
            
        emit('new_message', data, room=room, include_self=False)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
