import os
import time
import base64
import asyncio
import logging
import threading
from flask import Flask
from flask_socketio import SocketIO, emit, join_room
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.fernet import Fernet
import discord

# --- CONFIGURACIÓN DESDE ENTORNO ---
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')
try:
    GUILD_ID = int(os.environ.get('GUILD_ID', 0))
except:
    GUILD_ID = 0

CIFRA_PASS = os.environ.get('CIFRA_PASS', 'chats123')
CATEGORY_NAME = "GHOST-ARCHIVES"

# Configuración de Logs para ver errores en Render
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GHOST_SERVER")

def get_cipher():
    salt = b'\x14\xab\x11\xcd\xfe\xed\x11\x22'
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    key = base64.urlsafe_b64encode(kdf.derive(CIFRA_PASS.encode()))
    return Fernet(key)

cipher = get_cipher()
app = Flask(__name__)
# IMPORTANTE: cors_allowed_origins="*" permite que tu App conecte desde tu PC
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')
client = discord.Client(intents=discord.Intents.all())
NUCLEO_DATA = {}

async def get_secure_channel(room_name):
    guild = client.get_guild(GUILD_ID)
    if not guild: 
        logger.error(f"No se encontró el servidor {GUILD_ID}")
        return None
    
    cat = discord.utils.get(guild.categories, name=CATEGORY_NAME)
    if not cat: cat = await guild.create_category(CATEGORY_NAME)
    
    chan = discord.utils.get(cat.text_channels, name=room_name.lower())
    if not chan:
        chan = await guild.create_text_channel(room_name.lower(), category=cat)
    return chan.id

@socketio.on('register_user')
def on_reg(data):
    emit('update_rooms', {n: {"locked": False} for n in NUCLEO_DATA})

@socketio.on('create_room')
def on_create(data):
    room = data.get('room', '').lower().strip().replace(" ", "_")
    if room and room not in NUCLEO_DATA:
        # Esto crea el canal en Discord en segundo plano
        future = asyncio.run_coroutine_threadsafe(get_secure_channel(room), client.loop)
        try:
            d_id = future.result(timeout=15)
            if d_id:
                NUCLEO_DATA[room] = {'discord_id': d_id, 'history': []}
                socketio.emit('update_rooms', {n: {"locked": False} for n in NUCLEO_DATA})
        except Exception as e:
            logger.error(f"Error creando sala: {e}")

@socketio.on('join')
def on_join(data):
    room = data.get('room')
    if room in NUCLEO_DATA:
        join_room(room)
        emit('room_joined', {'room': room, 'history': NUCLEO_DATA[room]['history']})

@socketio.on('message')
def on_message(data):
    room = data.get('room')
    if room in NUCLEO_DATA:
        # Guardamos en el historial (máximo 50 mensajes)
        NUCLEO_DATA[room]['history'].append(data)
        if len(NUCLEO_DATA[room]['history']) > 50: NUCLEO_DATA[room]['history'].pop(0)
        emit('new_message', data, room=room, include_self=False)

def start_discord():
    if DISCORD_TOKEN:
        try:
            client.run(DISCORD_TOKEN)
        except Exception as e:
            logger.error(f"Error en el Bot de Discord: {e}")

if __name__ == '__main__':
    threading.Thread(target=start_discord, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
