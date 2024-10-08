﻿import discord
from discord.ext import commands
import asyncio
import os
import random
from pytube import YouTube
from youtubesearchpython import VideosSearch

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = []
        self.current_index = 0
        self.voice_client = None
        self.is_playing = False
        self.download_queue = asyncio.Queue()
        self.download_task = None

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

    @commands.command(aliases=['s'])  # Short form !s
    async def search(self, ctx, *, query):
        videosSearch = VideosSearch(query, limit=5)
        results = videosSearch.result()

        if not results['result']:
            await ctx.send("No results found.")
            return

        embed = discord.Embed(title="Search Results", color=discord.Color.blue())
        for i, video in enumerate(results['result'], 1):
            duration = video['duration']
            embed.add_field(name=f"{i}. {video['title']}", value=f"Duration: {duration}", inline=False)

        message = await ctx.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit() and 1 <= int(m.content) <= 5

        try:
            response = await self.bot.wait_for('message', check=check, timeout=30.0)
            selected = results['result'][int(response.content) - 1]
            await self.play(ctx, query=selected['link'])
        except asyncio.TimeoutError:
            await ctx.send("Search timed out.")
        finally:
            await message.delete()
    
    @commands.command(aliases=['p'])  # Allow short form like !p
    async def play(self, ctx, *, query):
        if not ctx.author.voice:
            await ctx.send("You need to be in a voice channel to use this command!")
            return

        if not self.voice_client:
            await self.join_voice_channel(ctx.author.voice.channel)

        if not query.startswith('http'):
            await self.search(ctx, query=query)
            return

        async with ctx.typing():
            song_info = await self.get_song_info(query)
            if song_info:
                self.queue.append(song_info)
                await self.download_queue.put(song_info)

                embed = discord.Embed(
                    title="🎵 Added to Queue", 
                    description=f"**{song_info['title']}**", 
                    color=discord.Color.green()
                )
                embed.set_footer(
                    text=f"Requested by {ctx.author.display_name}", 
                    icon_url=ctx.author.avatar.url
                )
                await ctx.send(embed=embed)

                if not self.is_playing:
                    await self.play_next()
                if not self.download_task:
                    self.download_task = asyncio.create_task(self.download_songs())
            else:
                await ctx.send("😕 Oops! I couldn't find that song or there was an error. Please try again.")

    @commands.command(aliases=['pl'])  # Short form !pl
    async def playlist(self, ctx, *, playlist_url):
        # Simulate fetching playlist songs (you need a separate method to handle playlists)
        playlist_songs = await self.get_playlist_songs(playlist_url)
        if not playlist_songs:
            await ctx.send("Couldn't fetch playlist. Please try a different one.")
            return

        for song in playlist_songs:
            self.queue.append(song)
            await self.download_queue.put(song)

        await ctx.send(f"Added {len(playlist_songs)} songs from the playlist to the queue!" )
    
        if not self.is_playing:
            await self.play_next()
        if not self.download_task:
            self.download_task = asyncio.create_task(self.download_songs())
            
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

    async def get_song_info(self, url):
        try:
            yt = YouTube(url)
            return {
                'title': yt.title,
                'url': url,
                'duration': yt.length
            }
        except Exception as e:
            # Log the error and URL causing the issue
            print(f"Error fetching video info from URL {url}: {e}")
            return None

    async def download_songs(self):
        while True:
            song = await self.download_queue.get()
            file_name = f"{song['title']}.mp3"
            try:
                yt = YouTube(song['url'])
                audio_stream = yt.streams.filter(only_audio=True).first()
                audio_stream.download(filename=file_name)
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