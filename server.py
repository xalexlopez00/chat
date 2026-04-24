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
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- CONFIGURACIÓN SEGURA ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID") 
CATEGORY_NAME = "CHAT_GHOST"

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

# Memoria del servidor (Añadido 'owner' a la estructura)
ROOMS = {"general": {"history": [], "temp": False, "pass": "", "users": set(), "msg_count": 0, "owner": "SISTEMA"}}

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
        ROOMS[name] = {
            "history": [], 
            "temp": data.get('temp', False), 
            "pass": data.get('password', ""), 
            "users": set(), 
            "msg_count": 0,
            "owner": request.sid # Guardamos el ID de quien la creó
        }
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
        if not ROOMS[room]['temp']:
            ROOMS[room]['history'].append(data)
            ROOMS[room]['msg_count'] += 1
            if len(ROOMS[room]['history']) > 100:
                ROOMS[room]['history'].pop(0)
        
        emit('new_message', data, room=room, include_self=False)
        socketio.start_background_task(process_discord_integration, room, data)

# --- NUEVA FUNCIÓN: CERRAR SALA ---
@socketio.on('close_room')
def handle_close(data):
    room = data.get('room')
    # Solo el dueño (owner) puede cerrar la sala y no puede cerrar la sala 'general'
    if room in ROOMS and room != "general":
        if ROOMS[room]['owner'] == request.sid:
            # Notificar a los usuarios para que salgan antes de borrar
            emit('room_closed', {'room': room}, room=room)
            # Borrar de memoria
            del ROOMS[room]
            sync_rooms()

def process_discord_integration(room, data):
    channel_id = setup_discord_channel(room)
    if not channel_id: return

    raw_log = f"{data['user']}: {data['msg']}"
    discord_cipher_text = encrypt_backup(raw_log).decode() 
    
    discord_api("POST", f"/channels/{channel_id}/messages", {
        "content": f"🔒 **GHOST_PACKET:** `{discord_cipher_text}`"
    })

    if ROOMS.get(room) and ROOMS[room]['msg_count'] >= 100:
        try:
            content = "\n".join([f"{m['user']}: {m['msg']}" for m in ROOMS[room]['history']])
            enc_data = encrypt_backup(content) 
            
            files = {'file': ('registro_cifrado.txt', enc_data)}
            discord_api("POST", f"/channels/{channel_id}/messages", 
                        data={"content": "📦 **BACKUP GENERADO (AES-256)**\nClave: `chats123`"},
                        files=files)
            
            ROOMS[room]['msg_count'] = 0 
        except Exception as e:
            print(f"Error en backup: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    socketio.run(app, host='0.0.0.0', port=port)
