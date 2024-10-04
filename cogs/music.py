import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
import random
from youtube_search import YoutubeSearch
from googleapiclient.discovery import build
import config
import re

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = []
        self.current_index = 0
        self.voice_client = None
        self.is_playing = False
        self.download_queue = asyncio.Queue()
        self.download_task = None
        self.youtube = build("youtube", "v3", developerKey=config.YOUTUBE_API_KEY)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if self.voice_client and len(self.voice_client.channel.members) == 1:
            if self.is_playing:
                self.voice_client.pause()
                self.is_playing = False
                await self.voice_client.channel.send("Looks like everyone left... I'll take a quick break! ⏸️")
        elif self.voice_client and not self.is_playing and len(self.voice_client.channel.members) > 1:
            self.voice_client.resume()
            self.is_playing = True
            await self.voice_client.channel.send("Someone's back! Let's get this party started again! ▶️")

    async def join_voice_channel(self, channel):
        if self.voice_client:
            await self.voice_client.move_to(channel)
        else:
            self.voice_client = await channel.connect()
        await channel.send("🎤 I've arrived! Who's ready for some tunes? 🎶")

    

    @commands.command()
    async def search(self, ctx, *, query):
        search = YoutubeSearch(query, limit=5)
        results = search.result()['result']
    
        if not results:
            await ctx.send("No results found.")
            return

        embed = discord.Embed(title="Search Results", color=discord.Color.blue())
        for i, video in enumerate(results, 1):
            embed.add_field(name=f"{i}. {video['title']}", value=f"Duration: {video['duration']}", inline=False)

        message = await ctx.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit() and 1 <= int(m.content) <= 5

        try:
            response = await self.bot.wait_for('message', check=check, timeout=30.0)
            selected = results[int(response.content) - 1]
            await self.play(ctx, query=selected['link'])
        except asyncio.TimeoutError:
            await ctx.send("Search timed out.")
        finally:
            await message.delete()
    
    @commands.command()
    async def play(self, ctx, *, query):
        if not query.startswith('http'):
            await self.search(ctx, query=query)
            return
        async with ctx.typing():
            song_info = await self.get_song_info(query)
            if song_info:
                self.queue.append(song_info)
                await self.download_queue.put(song_info)
                embed = discord.Embed(title="🎵 Added to Queue", description=f"**{song_info['title']}**", color=discord.Color.green())
                embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.avatar.url)
                await ctx.send(embed=embed)
                if not self.is_playing:
                    await self.play_next()
                if not self.download_task:
                    self.download_task = asyncio.create_task(self.download_songs())
            else:
                await ctx.send("😕 Oops! I couldn't find that song or there was an error. Maybe try another?")

    @commands.command()
    async def skip(self, ctx):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
            skip_messages = [
                "Alright, moving on! ⏭️",
                "That song was so last minute ago. Next! 🎶",
                "Skippity skip skip! 🐰",
            ]
            await ctx.send(random.choice(skip_messages))
        else:
            await ctx.send("There's no song playing right now. How about requesting one? 🎵")

    @commands.command()
    async def queue(self, ctx):
        if not self.queue:
            await ctx.send("The queue is as empty as a concert hall on a Monday morning. 🏜️")
        else:
            embed = discord.Embed(title="🎶 Current Queue", color=discord.Color.blue())
            for i, song in enumerate(self.queue):
                embed.add_field(name=f"{i+1}. {song['title']}", value=f"Duration: {song['duration']//60}:{song['duration']%60:02d}", inline=False)
            await ctx.send(embed=embed)


    async def get_song_info(self, query):
        try:
            if not query.startswith('http'):
                search_response = self.youtube.search().list(
                    q=query,
                    type="video",
                    part="id,snippet",
                    maxResults=1
                ).execute()

                if not search_response['items']:
                    return None

                video_id = search_response['items'][0]['id']['videoId']
                url = f"https://www.youtube.com/watch?v={video_id}"
            else:
                url = query
                # Extract video ID from URL
                video_id = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
                if video_id:
                    video_id = video_id.group(1)
                else:
                    return None

            video_response = self.youtube.videos().list(
                part="snippet,contentDetails",
                id=video_id
            ).execute()

            if not video_response['items']:
                return None

            video_info = video_response['items'][0]
            return {
                'title': video_info['snippet']['title'],
                'url': url,
                'duration': self.parse_duration(video_info['contentDetails']['duration'])
            }
        except Exception as e:
            print(f"Error fetching video info: {e}")
            return None

    def parse_duration(self, duration):
        match = re.match(r'PT(\d+H)?(\d+M)?(\d+S)?', duration)
        hours = int(match.group(1)[:-1]) if match.group(1) else 0
        minutes = int(match.group(2)[:-1]) if match.group(2) else 0
        seconds = int(match.group(3)[:-1]) if match.group(3) else 0
        return hours * 3600 + minutes * 60 + seconds

    async def download_songs(self):
        while True:
            song = await self.download_queue.get()
            file_name = f"{song['title']}.mp3"
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': file_name,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    await self.bot.loop.run_in_executor(None, lambda: ydl.download([song['url']]))
                    song['file_path'] = file_name
                except Exception as e:
                    print(f"Error downloading {song['title']}: {e}")
            self.download_queue.task_done()

    async def play_next(self):
        if self.current_index < len(self.queue):
            song = self.queue[self.current_index]
            while 'file_path' not in song:
                await asyncio.sleep(1)
            source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(song['file_path']))
            self.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(self.song_finished(), self.bot.loop))
            self.is_playing = True
            self.current_index += 1
            
            embed = discord.Embed(title="🎵 Now Playing", description=f"**{song['title']}**", color=discord.Color.purple())
            embed.set_footer(text=f"Duration: {song['duration']//60}:{song['duration']%60:02d}")
            await self.voice_client.channel.send(embed=embed)
        else:
            self.is_playing = False
            await self.voice_client.channel.send("That's all folks! The queue is empty. Feel free to add more songs! 🎭")

    async def song_finished(self):
        os.remove(self.queue[self.current_index - 1]['file_path'])
        await self.play_next()

    @commands.command()
    async def pause(self, ctx):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            await ctx.send("Paused ⏸️ - I'll be here when you're ready to continue!")
        else:
            await ctx.send("There's nothing playing right now. It's quieter than a library in here! 🤫")

    @commands.command()
    async def resume(self, ctx):
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            await ctx.send("Resuming playback! Let's get this party started again! 🎉")
        else:
            await ctx.send("There's nothing to resume. How about we play something new? 🎵")

    @commands.command()
    async def stop(self, ctx):
        if self.voice_client:
            await self.voice_client.disconnect()
            self.voice_client = None
            self.is_playing = False
            self.queue.clear()
            self.current_index = 0
            await ctx.send("Alright, I'm heading out! Thanks for the tunes! 👋")
        else:
            await ctx.send("I'm not even in a voice channel. Did you miss me that much? 😉")

async def setup(bot):
    await bot.add_cog(Music(bot))