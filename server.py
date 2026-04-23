import os
import time
import base64
import asyncio
import logging
import threading
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.fernet import Fernet
import discord

# --- CONFIGURACIÓN ---
DISCORD_TOKEN = "TU_TOKEN_AQUÍ"
GUILD_ID = 123456789  # ID de tu servidor de Discord
CATEGORY_NAME = "chatapp"
CIFRA_PASS = "chats123"
MSG_LIMIT = 100

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GHOST_CORE")

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")
client = discord.Client(intents=discord.Intents.all())

ROOMS_MANAGER = {}

# --- LÓGICA SIFRA V7 ---
def generar_llave_sifra(password: str):
    salt = b'\x14\xab\x11\xcd\xfe\xed\x11\x22'
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

cipher_suite = Fernet(generar_llave_sifra(CIFRA_PASS))

# --- DISCORD LOGIC ---
async def setup_channel(room_name):
    guild = client.get_guild(GUILD_ID)
    cat = discord.utils.get(guild.categories, name=CATEGORY_NAME) or await guild.create_category(CATEGORY_NAME)
    chan = discord.utils.get(cat.text_channels, name=room_name.lower()) or await guild.create_text_channel(room_name.lower(), category=cat)
    return chan.id

async def send_vault(room_name, messages):
    channel = client.get_channel(ROOMS_MANAGER[room_name]['discord_id'])
    raw_text = f"SALA: {room_name}\n" + "\n".join([f"[{time.ctime()}] {m['user']}: {m['msg']}" for m in messages])
    encrypted = cipher_suite.encrypt(raw_text.encode())
    
    fname = f"vault_{room_name}_{int(time.time())}.txt"
    with open(fname, "wb") as f: f.write(encrypted)
    await channel.send(content=f"📦 **BÓVEDA SIFRA V7 SELLADA** (100 msgs)", file=discord.File(fname))
    os.remove(fname)

# --- SOCKET EVENTS ---
@socketio.on('create_room')
def on_create(data):
    room = data.get('room', '').lower().strip()
    if room and room not in ROOMS_MANAGER:
        fut = asyncio.run_coroutine_threadsafe(setup_channel(room), client.loop)
        ROOMS_MANAGER[room] = {'count': 0, 'discord_id': fut.result(), 'buffer': [], 'history': []}
        socketio.emit('update_rooms', {n: {"locked": False} for n in ROOMS_MANAGER})

@socketio.on('message')
def on_msg(data):
    r = data.get('room')
    if r in ROOMS_MANAGER:
        ROOMS_MANAGER[r]['buffer'].append(data)
        ROOMS_MANAGER[r]['count'] += 1
        if ROOMS_MANAGER[r]['count'] >= MSG_LIMIT:
            batch = ROOMS_MANAGER[r]['buffer'].copy()
            ROOMS_MANAGER[r]['buffer'] = []
            ROOMS_MANAGER[r]['count'] = 0
            asyncio.run_coroutine_threadsafe(send_vault(r, batch), client.loop)
        emit('new_message', data, room=r, include_self=False)

@socketio.on('join')
def on_join(data):
    join_room(data['room'])
    emit('room_joined', {'room': data['room'], 'history': []})

if __name__ == '__main__':
    threading.Thread(target=lambda: client.run(DISCORD_TOKEN), daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
