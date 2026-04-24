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
# Permitir CORS y usar gevent para evitar cuelgues en Render
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- CONFIGURACIÓN SEGURA ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID") 
CATEGORY_NAME = "CHAT_GHOST"

# 1. Función para cifrar Backups y Discord (Contraseña: chats123)
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
            channel = discord_api("POST", f"/guilds/{GUILD_ID}/channels", {"name": channel_name, "type": 0, "parent_id": category['id']})
        return channel['id']
    except: return None

# Memoria del servidor
ROOMS = {"general": {"history": [], "temp": False, "pass": "", "users": set(), "msg_count": 0, "owner": "SISTEMA"}}

def sync_rooms():
    # Sincroniza estados de salas
    data = {n: {"temp": i["temp"], "locked": bool(i["pass"]), "count": len(i["users"])} for n, i in ROOMS.items()}
    socketio.emit('update_rooms', data)

@socketio.on('register_user')
def handle_reg(data):
    join_room("general")
    ROOMS["general"]["users"].add(request.sid)
    sync_rooms()
    emit('room_joined', {'room': 'general', 'history': ROOMS['general']['history']})

@socketio.on('disconnect')
def handle_disconnect():
    """Limpiar al usuario de todas las salas al desconectarse"""
    for room in ROOMS.values():
        room["users"].discard(request.sid)
    sync_rooms()

@socketio.on('create_room')
def handle_create(data):
    name = data.get('room', '').lower().strip().replace(" ", "_")
    if name and name not in ROOMS:
        ROOMS[name] = {"history": [], "temp": data.get('temp', False), "pass": data.get('password', ""), "users": set(), "msg_count": 0, "owner": request.sid}
        sync_rooms()

@socketio.on('join')
def handle_join(data):
    room, password = data.get('room'), data.get('password', "")
    if room in ROOMS:
        if ROOMS[room]["pass"] and ROOMS[room]["pass"] != password:
            emit('error_msg', {'msg': 'Clave incorrecta'})
            return
        if data.get('old_room') in ROOMS:
            leave_room(data['old_room'])
            ROOMS[data['old_room']]["users"].discard(request.sid)
        join_room(room)
        ROOMS[room]["users"].add(request.sid)
        sync_rooms()
        emit('room_joined', {'room': room, 'history': ROOMS[room]['history']})

# --- CORRECCIÓN DEFINITIVA DE MENSAJES ---
@socketio.on('message')
def handle_msg(data):
    room = data.get('room')
    if room in ROOMS:
        if not ROOMS[room]['temp']:
            ROOMS[room]['history'].append(data)
            ROOMS[room]['msg_count'] += 1
            if len(ROOMS[room]['history']) > 100: ROOMS[room]['history'].pop(0)
        
        # EL CAMBIO:include_self=False. No te devolvemos tu propio mensaje.
        emit('new_message', data, room=room, include_self=False)
        socketio.start_background_task(process_discord_integration, room, data)

@socketio.on('close_room')
def handle_close(data):
    room = data.get('room')
    if room in ROOMS and room != "general":
        if ROOMS[room]['owner'] == request.sid:
            emit('room_closed', {'room': room}, room=room)
            del ROOMS[room]
            sync_rooms()

def process_discord_integration(room, data):
    if room not in ROOMS: return
    channel_id = setup_discord_channel(room)
    if not channel_id: return
    raw_log = f"{data['user']}: {data['msg']}"
    discord_cipher_text = encrypt_backup(raw_log).decode() 
    discord_api("POST", f"/channels/{channel_id}/messages", {"content": f"🔒 **GHOST_PACKET:** `{discord_cipher_text}`"})
    if ROOMS.get(room) and ROOMS[room]['msg_count'] >= 100:
        try:
            content = "\n".join([f"{m['user']}: {m['msg']}" for m in ROOMS[room]['history']])
            enc_data = encrypt_backup(content) 
            files = {'file': ('registro_cifrado.txt', enc_data)}
            discord_api("POST", f"/channels/{channel_id}/messages", data={"content": "📦 **BACKUP GENERADO (AES-256)**\nPassword: `chats123`"}, files=files)
            if room in ROOMS: ROOMS[room]['msg_count'] = 0 
        except: pass

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
