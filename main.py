import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('VOICE_CHANNEL_ID'))
STREAM_URL = os.getenv('STREAM_URL')

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
class MusicBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.voice_client = None
        self.current_song = "Unknown"

    async def setup_hook(self):
        await self.tree.sync()

client = MusicBot()

def parse_icy(response):
    # Parse ICY metadata from HTTP response
    if 'icy-metaint' in response.headers:
        metaint = int(response.headers['icy-metaint'])
        for _ in range(20):  # Read first 20 metadata blocks
            response.raw.read(metaint)  # Skip audio data
            length = response.raw.read(1)
            if length:
                length = ord(length) * 16
                if length > 0:
                    metadata = response.raw.read(length).decode('utf-8', errors='ignore')
                    if 'StreamTitle=' in metadata:
                        title = metadata.split('StreamTitle=')[1].split(';')[0].strip("'")
                        return title
    return "Unknown"

async def update_presence():
    # Update bot's status with current song
    while True:
        try:
            await client.change_presence(activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=client.current_song
            ))
        except Exception as e:
            print(f"Error updating presence: {e}")
        await asyncio.sleep(5)

async def get_stream_title():
    # Get current song title from ICY metadata
    while True:
        try:
            response = requests.get(STREAM_URL, headers={'Icy-MetaData': '1'}, stream=True)
            title = parse_icy(response)
            if title != client.current_song:
                client.current_song = title
        except Exception as e:
            print(f"Error getting stream title: {e}")
            client.current_song = "Unknown"
        await asyncio.sleep(5)

async def play_stream(voice_channel):
    # Play audio stream in voice channel
    try:
        if client.voice_client and client.voice_client.is_connected():
            await client.voice_client.disconnect()
        
        client.voice_client = await voice_channel.connect()
        client.voice_client.play(
            discord.FFmpegPCMAudio(
                STREAM_URL,
                before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
            ),
            after=lambda e: print(f'Player error: {e}') if e else None
        )
    except Exception as e:
        print(f"Error playing stream: {e}")
        raise e

@client.event
async def on_ready():
    # Bot startup logic
    print(f'{client.user} connected to Discord!')
    
    # Start background tasks
    client.loop.create_task(update_presence())
    client.loop.create_task(get_stream_title())
    
    # Auto-join configured voice channel
    try:
        channel = client.get_channel(CHANNEL_ID)
        if channel:
            await play_stream(channel)
    except Exception as e:
        print(f"Error auto-joining channel: {e}")

@client.tree.command(name="join", description="Join your current voice channel")
async def join(interaction: discord.Interaction):
    # Join command
    try:
        if not interaction.user.voice:
            await interaction.response.send_message("You need to be in a voice channel first!")
            return
        
        channel = interaction.user.voice.channel
        await play_stream(channel)
        await interaction.response.send_message(f'Joined {channel.name}!')
    except Exception as e:
        await interaction.response.send_message(f"Error: {str(e)}")

@client.tree.command(name="reload", description="Reload the audio stream")
async def reload(interaction: discord.Interaction):
    # Reload command
    try:
        if client.voice_client and client.voice_client.is_connected():
            channel = client.voice_client.channel
            await client.voice_client.disconnect()
            await play_stream(channel)
            await interaction.response.send_message('Stream reloaded!')
        else:
            await interaction.response.send_message('Not connected to a voice channel!')
    except Exception as e:
        await interaction.response.send_message(f'Error reloading stream: {str(e)}')

client.run(TOKEN)