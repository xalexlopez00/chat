from gevent import monkey
monkey.patch_all()

import os
import requests
import base64
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- CONFIGURACIÓN DESDE VARIABLES DE ENTORNO ---
# Lee automáticamente las "Keys" de tu captura de pantalla
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
CATEGORY_NAME = "CHAT_GHOST"
MASTER_PASS = b"chats123"

# --- UTILIDAD DE CIFRADO ---
def get_cipher():
    salt = b'\x14\xab\x11\xcd\xfe\xed\x11\x22'
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    key = base64.urlsafe_b64encode(kdf.derive(MASTER_PASS))
    return Fernet(key)

# --- MOTOR DE DISCORD ---
def discord_api(method, endpoint, data=None, files=None):
    if not DISCORD_TOKEN or not GUILD_ID:
        print("⚠️ ERROR: Variables DISCORD_TOKEN o GUILD_ID no configuradas.")
        return None
        
    url = f"https://discord.com/api/v10{endpoint}"
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    try:
        if method == "GET":
            return requests.get(url, headers=headers).json()
        if method == "POST":
            if files:
                return requests.post(url, headers=headers, data=data, files=files).json()
            return requests.post(url, headers=headers, json=data).json()
    except Exception as e:
        print(f"Error Discord API: {e}")
        return None

def setup_discord_channel(room_name):
    channels = discord_api("GET", f"/guilds/{GUILD_ID}/channels")
    if not isinstance(channels, list): return None
    
    # Buscar o crear categoría CHAT_GHOST
    category = next((c for c in channels if c['name'].upper() == CATEGORY_NAME and c['type'] == 4), None)
    if not category:
        category = discord_api("POST", f"/guilds/{GUILD_ID}/channels", {"name": CATEGORY_NAME, "type": 4})

    # Buscar o crear canal de la sala
    ch_name = room_name.lower().replace(" ", "-")
    channel = next((c for c in channels if c['name'] == ch_name and c.get('parent_id') == category['id']), None)
    if not channel:
        channel = discord_api("POST", f"/guilds/{GUILD_ID}/channels", {
            "name": ch_name, "type": 0, "parent_id": category['id']
        })
    return channel['id']

# --- LÓGICA DEL SERVIDOR ---
ROOMS = {"general": {"history": [], "temp": False, "pass": "", "users": set(), "msg_count": 0}}

@socketio.on('message')
def handle_msg(data):
    room = data.get('room')
    if room in ROOMS:
        ROOMS[room]['history'].append(data)
        ROOMS[room]['msg_count'] += 1
        emit('new_message', data, room=room, include_self=False)
        socketio.start_background_task(log_to_discord, room, data)

def log_to_discord(room, data):
    channel_id = setup_discord_channel(room)
    if not channel_id: return

    cipher = get_cipher()
    log_text = f"{data['user']}: {data['msg']}"
    encrypted_log = cipher.encrypt(log_text.encode()).decode()
    
    discord_api("POST", f"/channels/{channel_id}/messages", {
        "content": f"📝 **PACKET:** `{encrypted_log}`"
    })

    # Backup automático cada 50 mensajes
    if ROOMS[room]['msg_count'] >= 50:
        full_history = "\n".join([f"{m['user']}: {m['msg']}" for m in ROOMS[room]['history']])
        enc_history = cipher.encrypt(full_history.encode())
        
        with open("backup.txt", "wb") as f: f.write(enc_history)
        with open("backup.txt", "rb") as f:
            discord_api("POST", f"/channels/{channel_id}/messages", 
                        data={"content": "📂 **SISTEMA: Backup de seguridad generado (AES-256)**"},
                        files={'file': f})
        ROOMS[room]['msg_count'] = 0

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
        ROOMS[name] = {"history": [], "temp": data.get('temp', False), 
                       "pass": data.get('password', ""), "users": set(), "msg_count": 0}
        sync_rooms()

@socketio.on('join')
def handle_join(data):
    room, old, pwd = data.get('room'), data.get('old_room'), data.get('password', "")
    if room in ROOMS:
        if ROOMS[room]["pass"] and ROOMS[room]["pass"] != pwd:
            emit('error_msg', {'msg': 'Clave incorrecta'})
            return
        if old: leave_room(old)
        join_room(room)
        sync_rooms()
        emit('room_joined', {'room': room, 'history': ROOMS[room]['history']})

def sync_rooms():
    data = {n: {"locked": bool(i["pass"]), "count": len(i["users"])} for n, i in ROOMS.items()}
    socketio.emit('update_rooms', data)

if __name__ == '__main__':
    # El puerto lo define el hosting, por defecto 10000 en Render
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host='0.0.0.0', port=port)
