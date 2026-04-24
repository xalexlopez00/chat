from gevent import monkey
monkey.patch_all()

import os
import requests
import json
import base64
import time
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

app = Flask(__name__)
# Importante: Permitir CORS y usar gevent para que no se cuelgue en Render
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- CONFIGURACIÓN ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID") 
CATEGORY_NAME = "CHAT_GHOST"

# Lógica para cifrar el archivo de backup (Contraseña fija para recuperación)
def encrypt_backup(text):
    salt = b'\x14\xab\x11\xcd\xfe\xed\x11\x22'
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    key = base64.urlsafe_b64encode(kdf.derive(b"chats123"))
    return Fernet(key).encrypt(text.encode())

def discord_api(method, endpoint, data=None, files=None):
    if not DISCORD_TOKEN: return None
    url = f"https://discord.com/api/v10{endpoint}"
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    if not files: headers["Content-Type"] = "application/json"
    
    try:
        if method == "GET": return requests.get(url, headers=headers, timeout=5).json()
        if method == "POST": 
            return requests.post(url, headers=headers, json=data, files=files, timeout=5).json()
    except Exception as e:
        print(f"Error Discord API: {e}")
        return None

def setup_discord_channel(room_name):
    if not GUILD_ID: return None
    try:
        channels = discord_api("GET", f"/guilds/{GUILD_ID}/channels")
        if not isinstance(channels, list): return None
        
        # 1. Buscar o crear categoría
        category = next((c for c in channels if c.get('name', '').upper() == CATEGORY_NAME), None)
        if not category:
            category = discord_api("POST", f"/guilds/{GUILD_ID}/channels", {"name": CATEGORY_NAME, "type": 4})

        # 2. Buscar o crear canal
        channel_name = room_name.lower().replace(" ", "_")
        channel = next((c for c in channels if c.get('name') == channel_name), None)
        
        if not channel:
            channel = discord_api("POST", f"/guilds/{GUILD_ID}/channels", {
                "name": channel_name, "type": 0, "parent_id": category['id']
            })
        return channel['id']
    except: return None

# Memoria del servidor (Volátil)
# Estructura: {nombre: {history: [], temp: bool, pass: str, users: set, msg_count: int}}
ROOMS = {"general": {"history": [], "temp": False, "pass": "", "users": set(), "msg_count": 0}}

def sync_rooms():
    # Enviamos solo la info necesaria al cliente
    data = {n: {"locked": bool(i["pass"]), "count": len(i["users"])} for n, i in ROOMS.items()}
    socketio.emit('update_rooms', data)

@socketio.on('connect')
def on_connect():
    sync_rooms()

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
        ROOMS[name] = {
            "history": [], 
            "temp": data.get('temp', False), 
            "pass": data.get('password', ""), 
            "users": set(), 
            "msg_count": 0
        }
        sync_rooms()

@socketio.on('join')
def handle_join(data):
    room = data.get('room')
    old_room = data.get('old_room')
    password = data.get('password', "")
    
    if room in ROOMS:
        # Validación de contraseña
        if ROOMS[room]["pass"] and ROOMS[room]["pass"] != password:
            emit('new_message', {'user': 'SISTEMA', 'msg': 'eN0rcmptZWRfa2V5...'}, room=request.sid) # Opcional: mensaje cifrado de error
            return
            
        if old_room and old_room in ROOMS:
            leave_room(old_room)
            ROOMS[old_room]["users"].discard(request.sid)
        
        join_room(room)
        ROOMS[room]["users"].add(request.sid)
        sync_rooms()
        # Enviar historial al entrar
        emit('room_joined', {'room': room, 'history': ROOMS[room]['history']})

@socketio.on('message')
def handle_msg(data):
    room = data.get('room')
    if room in ROOMS:
        # 1. Guardar en historial si NO es efímera
        if not ROOMS[room]['temp']:
            ROOMS[room]['history'].append(data)
            ROOMS[room]['msg_count'] += 1
            # Mantener máximo 100 mensajes en memoria RAM
            if len(ROOMS[room]['history']) > 100:
                ROOMS[room]['history'].pop(0)
        
        # 2. Reenviar a los demás (cifrado tal cual llega)
        emit('new_message', data, room=room, include_self=False)

        # 3. Notificar a Discord (en segundo plano)
        socketio.start_background_task(process_discord_integration, room, data)

def process_discord_integration(room, data):
    channel_id = setup_discord_channel(room)
    if not channel_id: return

    # Enviar mensaje normal a Discord
    discord_api("POST", f"/channels/{channel_id}/messages", {"content": f"**{data['user']}**: `{data['msg']}`"})

    # 4. Backup automático si llega a 100 mensajes nuevos
    if ROOMS[room]['msg_count'] >= 100:
        try:
            content = "\n".join([f"{m['user']}: {m['msg']}" for m in ROOMS[room]['history']])
            enc_data = encrypt_backup(content)
            
            # Subir archivo cifrado a Discord
            files = {'file': ('backup_cifrado.ghost', enc_data)}
            discord_api("POST", f"/channels/{channel_id}/messages", 
                        data={"content": "📦 **NIVEL DE SEGURIDAD MÁXIMO: Backup Cifrado Generado.**\nClave de recuperación: `chats123`"}, 
                        files=files)
            
            ROOMS[room]['msg_count'] = 0 # Reiniciar contador
        except Exception as e:
            print(f"Error en backup: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    socketio.run(app, host='0.0.0.0', port=port)
