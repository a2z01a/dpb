import discord
from discord.ext import commands
import asyncio
import config
import random

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await bot.change_presence(activity=discord.Game(name="🎵 Vibing to tunes"))
    for guild in bot.guilds:
        for voice_channel in guild.voice_channels:
            if voice_channel.id == config.VOICE_CHANNEL_ID:
                await bot.get_cog('Music').join_voice_channel(voice_channel)
                break

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        confused_responses = [
            "Huh? I didn't catch that. Try `!help` for a list of commands! 🤔",
            "Oops, that command doesn't ring a bell. Need `!help`? 🔍",
            "I'm scratching my virtual head here. Maybe you meant something else? 🤖",
        ]
        await ctx.send(random.choice(confused_responses))
    else:
        await ctx.send(f"Uh-oh, something went wrong: {str(error)} 😅")

@bot.command()
@commands.is_owner()
async def reload(ctx, extension):
    await bot.reload_extension(f'cogs.{extension}')
    await ctx.send(f"🔄 {extension} has been reloaded. Let's hope I didn't forget how to sing! 🎵")

async def load_extensions():
    await bot.load_extension('cogs.music')

asyncio.run(load_extensions())
bot.run(config.TOKEN)
