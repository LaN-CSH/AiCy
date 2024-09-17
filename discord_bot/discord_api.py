from dotenv import load_dotenv
import discord
import os
from ai_core.openai import chatgpt_response


load_dotenv()

discord_token = os.getenv('TOKEN')

class MyClient(discord.Client):
    async def on_ready(self):
        print("Successfully logged in as: ", self.user)

    async def on_message(self, message):
        print(message.content)
        if message.author == self.user:
            return
        command, user_message = None, None

        for text in ['/ai', '야', '월피티']:
            if message.content.startswith(text):
                command=message.content.split(' ')[0]
                user_message=message.content.replace(text,'')
                print(command, user_message)
        if command == '/ai' or command == '야' or command == '월피티':
            bot_response = chatgpt_response(prompt=user_message)
            await message.channel.send(f"{bot_response}")

intents = discord.Intents.default()
intents.message_content = True

client = MyClient(intents=intents)