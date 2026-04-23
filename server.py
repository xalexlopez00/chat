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

# ==========================================
# CONFIGURACIÓN MAESTRA (EDITAR AQUÍ)
# ==========================================
DISCORD_TOKEN = "TU_TOKEN_BOT_AQUI"
GUILD_ID = 123456789012345678  # Tu ID de Servidor
CATEGORY_NAME = "GHOST-ARCHIVES"
CIFRA_PASS = "chats123"        # Llave maestra para los .txt
MSG_LIMIT = 100               # Cada cuántos mensajes se crea un archivo

# Configuración de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("GHOST_SERVER")

# ==========================================
# MOTOR CRIPTOGRÁFICO (SIFRA V7 COMPATIBLE)
# ==========================================
def get_cipher():
    salt = b'\x14\xab\x11\xcd\xfe\xed\x11\x22'
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    key = base64.urlsafe_b64encode(kdf.derive(CIFRA_PASS.encode()))
    return Fernet(key)

cipher = get_cipher()

# ==========================================
# INICIALIZACIÓN
# ==========================================
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')
client = discord.Client(intents=discord.Intents.all())

# Memoria Volátil (Se limpia al reiniciar para máxima privacidad)
# Estructura: { 'sala': {'discord_id': int, 'buffer': [], 'history': []} }
NUCLEO_DATA = {}

# ==========================================
# LÓGICA DE DISCORD (HILO ASÍNCRONO)
# ==========================================
async def get_secure_channel(room_name):
    """Asegura que exista la categoría y el canal en Discord."""
    guild = client.get_guild(GUILD_ID)
    if not guild: return None

    cat = discord.utils.get(guild.categories, name=CATEGORY_NAME)
    if not cat: cat = await guild.create_category(CATEGORY_NAME)

    chan = discord.utils.get(cat.text_channels, name=room_name.lower())
    if not chan:
        chan = await guild.create_text_channel(room_name.lower(), category=cat)
        await chan.send(f"🛡️ **NODO ESTABLECIDO**: #{room_name.upper()}\nEsperando flujo de datos cifrados...")
    
    return chan.id

async def upload_to_vault(room_name, messages):
    """Cifra y sube el bloque de mensajes a Discord."""
    chan_id = NUCLEO_DATA[room_name]['discord_id']
    channel = client.get_channel(chan_id)
    if not channel: return

    # Formateo del log
    content = f"--- INFORME GHOST | NODO: {room_name.upper()} ---\n"
    content += f"CAPTURADO: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    for m in messages:
        content += f"[{time.strftime('%H:%M:%S')}] {m['user']}: {m['msg']}\n"

    # Cifrado de capa de transporte
    encrypted_data = cipher.encrypt(content.encode())
    
    filename = f"vault_{room_name}_{int(time.time())}.txt"
    with open(filename, "wb") as f:
        f.write(encrypted_data)

    await channel.send(
        content=f"📦 **BÓVEDA GENERADA**\nContiene {MSG_LIMIT} mensajes cifrados con SIFRA V7.",
        file=discord.File(filename)
    )
    os.remove(filename)
    logger.info(f"Vóveda enviada con éxito para #{room_name}")

# ==========================================
# EVENTOS DE COMUNICACIÓN (SOCKET.IO)
# ==========================================
@socketio.on('register_user')
def on_reg(data):
    logger.info(f"Usuario {data.get('nickname')} ha entrado en la red.")
    # Sincronizar salas existentes con el nuevo usuario
    emit('update_rooms', {n: {"locked": False} for n in NUCLEO_DATA})

@socketio.on('create_room')
def on_create(data):
    room = data.get('room', '').lower().strip().replace(" ", "_")
    if room and room not in NUCLEO_DATA:
        # Programar tarea en el loop de Discord
        future = asyncio.run_coroutine_threadsafe(get_secure_channel(room), client.loop)
        try:
            d_id = future.result(timeout=15)
            NUCLEO_DATA[room] = {
                'discord_id': d_id,
                'buffer': [],
                'history': []
            }
            socketio.emit('update_rooms', {n: {"locked": False} for n in NUCLEO_DATA})
            logger.info(f"Sala #{room} activada y vinculada a Discord.")
        except Exception as e:
            logger.error(f"Error al vincular sala con Discord: {e}")

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
        # Guardar en RAM (historial corto)
        NUCLEO_DATA[room]['history'].append(data)
        if len(NUCLEO_DATA[room]['history']) > 40: NUCLEO_DATA[room]['history'].pop(0)

        # Guardar en Buffer (para el .txt de 100 mensajes)
        NUCLEO_DATA[room]['buffer'].append(data)
        
        if len(NUCLEO_DATA[room]['buffer']) >= MSG_LIMIT:
            batch = NUCLEO_DATA[room]['buffer'].copy()
            NUCLEO_DATA[room]['buffer'] = []
            asyncio.run_coroutine_threadsafe(upload_to_vault(room, batch), client.loop)

        emit('new_message', data, room=room, include_self=False)

# ==========================================
# LANZAMIENTO (SISTEMA DUAL)
# ==========================================
def start_discord():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client.run(DISCORD_TOKEN)

if __name__ == '__main__':
    # Hilo para el Bot de Discord
    threading.Thread(target=start_discord, daemon=True).start()
    
    # Servidor Flask-SocketIO (Optimizado para Render con gevent)
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Servidor Maestro GHOST activo en puerto {port}")
    socketio.run(app, host='0.0.0.0', port=port)
