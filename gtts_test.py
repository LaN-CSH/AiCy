import discord
import os
import asyncio
import yt_dlp
from dotenv import load_dotenv
from gtts import gTTS
from ai_core.openai import chatgpt_response
import json
import elevenlabs
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs
import requests

def run_bot():
    load_dotenv()
    TOKEN = os.getenv('TOKEN')
    EL_TOKEN = os.getenv('ELEVENLABS')
    aicy_voice1 = os.getenv('AICY_VOICEVOX_L')
    aicy_voice2 = os.getenv('AICY_VC_A')

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)
    el_client = ElevenLabs()
    queues = {}
    voice_clients = {}
    yt_dl_options = {"format": "bestaudio/best"}
    ytdl = yt_dlp.YoutubeDL(yt_dl_options)

    ffmpeg_options = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5','options': '-vn -filter:a "volume=0.25"'}

    @client.event
    async def on_ready():
        print(f'{client.user} is now jamming')

    @client.event
    async def on_message(message):
        if message.content.startswith("?play"):
            try:
                voice_client = await message.author.voice.channel.connect()
                voice_clients[voice_client.guild.id] = voice_client
            except Exception as e:
                print(e)

            try:
                url = message.content.split()[1]

                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))

                song = data['url']
                player = discord.FFmpegOpusAudio(song, **ffmpeg_options)

                voice_clients[message.guild.id].play(player)
            except Exception as e:
                print(e)

        if message.content.startswith("?test"):
            try:
                voice_client = await message.author.voice.channel.connect()
                voice_clients[voice_client.guild.id] = voice_client
            except Exception as e:
                print(e)

            try:
                # url = message.content.split()[1]

                loop = asyncio.get_event_loop()
                # data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
                text = "테스트입니다"
                myobj = gTTS(text=text, lang="ko", slow=False)
                myobj.save("tts-audio.mp3")
                # song = data['url']
                # player = discord.FFmpegOpusAudio("tts-audio.mp3", **ffmpeg_options)
                voice_clients[message.guild.id].play(discord.FFmpegPCMAudio(executable="C:/ffmpeg/ffmpeg.exe", source="tts-audio.mp3"))
                # voice_clients[message.guild.id].play(player)
            except Exception as e:
                print(e)
        
        # 말하게 하기
        if message.content.startswith("?ans"):
            try:
                voice_client = await message.author.voice.channel.connect()
                voice_clients[voice_client.guild.id] = voice_client
            except Exception as e:
                print(e)

            try:
                input_texts = message.content.split()[1:]
                input_text = " ".join(input_texts)

                loop = asyncio.get_event_loop()

                if os.path.exists("conv.json")==False:
                    print("conv.json does not exist")
                    conv = []
                else:
                    with open('conv.json', 'r') as file:
                        conv = json.load(file)
                    print(conv)
                # data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
                text, conv = chatgpt_response(input_text, conv)
                text = text.replace("*","")
                # Serializing json
                json_object = json.dumps(conv, ensure_ascii=False)
                
                # Writing to sample.json
                with open("conv.json", "w") as outfile:
                    outfile.write(json_object)
                
                # myobj = gTTS(text=text, lang="ko", slow=False)
                # myobj = client.text_to_speech.convert(
                #         voice_id="pMsXgVXv3BLzUgSXRplE",
                #         optimize_streaming_latency="0",
                #         output_format="mp3_22050_32",
                #         text=text,
                #         voice_settings=VoiceSettings(
                #             stability=0.1,
                #             similarity_boost=0.3,
                #             style=0.2,
                #         ),
                #     )
                CHUNK_SIZE = 1024
                url = "https://api.elevenlabs.io/v1/text-to-speech/edaoIXGiOsk7Opf9lAsF"

                headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": EL_TOKEN
                }

                data = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.3
                }
                }

                response = requests.post(url, json=data, headers=headers)
                with open('tts-audio.mp3', 'wb') as f:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                # myobj.save("tts-audio.mp3")
                # song = data['url']
                # player = discord.FFmpegOpusAudio("tts-audio.mp3", **ffmpeg_options)
                voice_clients[message.guild.id].play(discord.FFmpegPCMAudio(executable="C:/ffmpeg/ffmpeg.exe", source="tts-audio.mp3"))
                # voice_clients[message.guild.id].play(player)
            except Exception as e:
                print(e)


        if message.content.startswith("?pause"):
            try:
                voice_clients[message.guild.id].pause()
            except Exception as e:
                print(e)

        if message.content.startswith("?resume"):
            try:
                voice_clients[message.guild.id].resume()
            except Exception as e:
                print(e)

        if message.content.startswith("?stop"):
            try:
                voice_clients[message.guild.id].stop()
                await voice_clients[message.guild.id].disconnect()
            except Exception as e:
                print(e)

        if message.content.startswith("?reset"):
            if os.path.exists("conv.json"):
                os.remove("conv.json")
    client.run(TOKEN)
