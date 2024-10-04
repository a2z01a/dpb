// Full code snippet including corrections
require('dotenv').config();

const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');
const { promisify } = require('util');
const execPromise = promisify(exec);
const { 
  createAudioPlayer, createAudioResource, AudioPlayerStatus, 
  VoiceConnectionStatus, joinVoiceChannel, entersState 
} = require('@discordjs/voice');
const { Client, GatewayIntentBits, EmbedBuilder } = require('discord.js');
const play = require('play-dl');
const bots = new Map();
const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
    GatewayIntentBits.GuildVoiceStates,
  ],
});

client.on('ready', function() {
  console.log('Bot is ready!');
  initializeBots();
});

client.on('messageCreate', async (message) => {
  if (message.channel.type !== 0) return; // 0 is the value for GUILD_TEXT
  
  const bot = Array.from(bots.values()).find(bot =>
    message.member && message.member.voice.channelId === bot.voiceChannelId
  );

  if (bot && message.content.startsWith(bot.prefix)) {
    await bot.handleCommand(message);
  }
});

function initializeBots() {
  const botConfigs = [
    { name: 'Trap Music Bot', voiceChannelId: '1291366977667076170' },
    // Add more bot configurations as needed
  ];

  botConfigs.forEach(config => {
    const bot = new MusicBot(client, config.name, config.voiceChannelId);
    bot.initialize();
    bots.set(config.voiceChannelId, bot);
  });
}

client.login(process.env.DISCORD_BOT_TOKEN);

class MusicBot {
  constructor(client, name, voiceChannelId) {
    this.client = client;
    this.name = name;
    this.voiceChannelId = voiceChannelId;
    this.prefix = '!';
    this.queue = [];
    this.currentIndex = 0;
    this.player = null;
    this.connection = null;
    this.isPaused = false;
    this.downloadQueue = [];
    this.isDownloading = false;
  }

  async initialize() {
    await this.joinVoiceChannel();
  }

  async sendStatusEmbed(message, title, description, color = '#0099ff') {
    const embed = new EmbedBuilder()
      .setColor(color)
      .setTitle(title)
      .setDescription(description)
      .setTimestamp();

    return await message.channel.send({ embeds: [embed] });
  }

  async joinVoiceChannel() {
    try {
      const channel = await this.client.channels.fetch(this.voiceChannelId);
      if (!channel || channel.type !== 2) { // 2 is the value for GUILD_VOICE
        throw new Error('Invalid voice channel');
      }

      this.connection = joinVoiceChannel({
        channelId: this.voiceChannelId,
        guildId: channel.guild.id,
        adapterCreator: channel.guild.voiceAdapterCreator,
      });

      await entersState(this.connection, VoiceConnectionStatus.Ready, 30_000);
      
      if (!this.player) {
        this.player = createAudioPlayer();
        this.connection.subscribe(this.player);

        this.player.on('error', (error) => {
          console.error('Playback error:', error.message);
          this.playSong().catch(console.error);
        });

        this.player.on(AudioPlayerStatus.Idle, () => {
          this.currentIndex++;
          if (this.currentIndex < this.queue.length) {
            this.playSong().catch(console.error);
          }
        });
      }

      setInterval(() => this.checkVoiceChannel(), 5000);

      console.log(`${this.name}: Successfully joined voice channel`);
      return this.connection;
    } catch (error) {
      console.error(`${this.name}: Error joining voice channel:`, error);
      return null;
    }
  }

  async checkVoiceChannel() {
    const channel = await this.client.channels.fetch(this.voiceChannelId);
    if (channel && channel.members.size === 1) {
      if (!this.isPaused) {
        this.player.pause();
        this.isPaused = true;
        console.log(`${this.name}: Paused playback due to empty voice channel`);
      }
    } else if (this.isPaused) {
      this.player.unpause();
      this.isPaused = false;
      console.log(`${this.name}: Resumed playback`);
    }
  }

  async handleCommand(message) {
    const args = message.content.slice(this.prefix.length).trim().split(/ +/);
    const command = args.shift().toLowerCase();

    switch (command) {
      case 'play':
        const songUrl = args[0];
        if (!songUrl) {
          return this.sendStatusEmbed(message, '❌ Invalid Command', 'Please provide a song URL or search term.', '#ff0000');
        }
        await this.addToQueue(message, songUrl);
        break;

      case 'playlist':
        const playlistUrl = args[0];
        if (!playlistUrl) {
          return this.sendStatusEmbed(message, '❌ Invalid Command', 'Please provide a playlist URL.', '#ff0000');
        }
        await this.loadPlaylist(message, playlistUrl);
        break;

      case 'skip':
        await this.skipSong(message);
        break;

      case 'queue':
        await this.showQueue(message);
        break;

      default:
        await this.sendStatusEmbed(message, '❓ Unknown Command', 'Available commands: play, playlist, skip, queue', '#ff9900');
    }
  }

  async addToQueue(message, query) {
    try {
      const { stdout } = await execPromise(`yt-dlp --get-title --get-id "${query}"`);
      const [title, videoId] = stdout.trim().split('\n');
      const song = {
        title: title,
        url: `https://www.youtube.com/watch?v=${videoId}`,
      };
      this.queue.push(song);
      this.downloadQueue.push(song);
      await this.sendStatusEmbed(message, '🎵 Added to Queue', `${song.title} has been added to the queue!`);
      
      if (this.queue.length === 1) {
        this.processDownloadQueue(message);
      }
    } catch (error) {
      console.error('Error adding song to queue:', error);
      await this.sendStatusEmbed(message, '❌ Error', 'Error adding song to queue. Please try again.', '#ff0000');
    }
  }

  async loadPlaylist(message, playlistUrl) {
    try {
      const statusEmbed = await this.sendStatusEmbed(message, '📋 Loading Playlist', 'Starting to load playlist...');

      const { stdout } = await execPromise(`yt-dlp --flat-playlist --get-title --get-id "${playlistUrl}"`);

      const videos = stdout.trim().split('\n').reduce((acc, line, index) => {
        if (index % 2 === 0) {
          acc.push({ title: line });
        } else {
          acc[acc.length - 1].url = `https://www.youtube.com/watch?v=${line}`;
        }
        return acc;
      }, []);

      for (let i = 0; i < videos.length; i++) {
        const video = videos[i];
        this.queue.push(video);
        this.downloadQueue.push(video);

        if (i % 10 === 0 || i === videos.length - 1) {
          await statusEmbed.edit({ embeds: [new EmbedBuilder()
            .setColor('#0099ff')
            .setTitle('📋 Loading Playlist')
            .setDescription(`Loaded ${i + 1}/${videos.length} songs...`)
            .setTimestamp()] });
        }
      }

      await statusEmbed.edit({ embeds: [new EmbedBuilder()
        .setColor('#00ff00')
        .setTitle('✅ Playlist Loaded')
        .setDescription(`Added ${videos.length} songs from playlist to queue.`)
        .setTimestamp()] });
      
      if (this.queue.length === videos.length) {
        this.processDownloadQueue(message);
      }
    } catch (error) {
      console.error('Error loading playlist:', error);
      await this.sendStatusEmbed(message, '❌ Error', 'Error loading playlist. Please try again.', '#ff0000');
    }
  }

  async processDownloadQueue(message) {
    if (this.isDownloading || this.downloadQueue.length === 0) return;

    this.isDownloading = true;
    const song = this.downloadQueue.shift();
    
    try {
      const statusEmbed = await this.sendStatusEmbed(message, '⏬ Downloading', `Downloading: ${song.title}`);

      await this.downloadSong(song, statusEmbed);
      if (this.player.state.status === AudioPlayerStatus.Idle) {
        this.playSong(message);
      }
    } catch (error) {
      console.error('Error downloading song:', error);
      await this.sendStatusEmbed(message, '❌ Download Error', `Failed to download: ${song.title}`, '#ff0000');
    } finally {
      this.isDownloading = false;
      this.processDownloadQueue(message);
    }
  }
  
  async downloadSong(song, statusEmbed) {
    return new Promise((resolve, reject) => {
      const outputFile = path.join(__dirname, `${Date.now()}.%(ext)s`);
      const command = `yt-dlp --no-playlist --extract-audio --audio-format mp3 --audio-quality 0 --output "${outputFile}" "${song.url}"`;
      
      const process = exec(command);
      let progress = 0;

      process.stderr.on('data', (data) => {
        const match = data.match(/(\d+\.\d+)%/);
        if (match) {
          const newProgress = parseFloat(match[1]);
          if (newProgress > progress + 10) {
            progress = newProgress;
            statusEmbed.edit({ embeds: [new EmbedBuilder()
              .setColor('#0099ff')
              .setTitle('⏬ Downloading')
              .setDescription(`Downloading: ${song.title}\nProgress: ${progress.toFixed(1)}%`)
              .setTimestamp()] });
          }
        }
      });

      process.on('exit', (code) => {
        if (code === 0) {
          const files = fs.readdirSync(__dirname);
          const audioFile = files.find(file => file.startsWith(path.basename(outputFile, path.extname(outputFile))));
          
          if (!audioFile) {
            reject(new Error('Audio file not found'));
            return;
          }
          
          song.filePath = path.join(__dirname, audioFile);
          statusEmbed.edit({ embeds: [new EmbedBuilder()
            .setColor('#00ff00')
            .setTitle('✅ Download Complete')
            .setDescription(`Successfully downloaded: ${song.title}`)
            .setTimestamp()] });
          resolve();
        } else {
          reject(new Error(`yt-dlp exited with code ${code}`));
        }
      });
    });
  }

  async skipSong(message) {
    if (this.queue.length > 0) {
      this.player.stop();
      await this.sendStatusEmbed(message, '⏭️ Skipped', 'Skipped to the next song.');
    } else {
      await this.sendStatusEmbed(message, '❌ Cannot Skip', 'No songs in the queue to skip.', '#ff0000');
    }
  }

  async showQueue(message) {
    if (this.queue.length === 0) {
      await this.sendStatusEmbed(message, '📭 Queue Empty', 'The queue is empty.');
    } else {
      const queueList = this.queue.map((song, index) =>
        `${index + 1}. ${song.title}`
      ).join('\n');
      await this.sendStatusEmbed(message, '📋 Current Queue', queueList);
    }
  }

  async playSong(message) {
    if (this.queue.length > 0 && this.currentIndex < this.queue.length) {
      const song = this.queue[this.currentIndex];
      
      if (!song.filePath) {
        await this.sendStatusEmbed(message, '⏳ Waiting', `Waiting for download: ${song.title}`);
        setTimeout(() => this.playSong(message), 1000);
        return;
      }

      try {
        const resource = createAudioResource(song.filePath);
        this.player.play(resource);
        await this.sendStatusEmbed(message, '🎶 Now Playing', `Now playing: ${song.title}`);
        
        this.player.once(AudioPlayerStatus.Idle, () => {
          fs.unlinkSync(song.filePath);
          this.currentIndex++;
          this.playSong(message);
        });
      } catch (error) {
        console.error('Error playing song:', error);
        await this.sendStatusEmbed(message, '❌ Playback Error', `Error playing: ${song.title}`, '#ff0000');
        this.currentIndex++;
        this.playSong(message);
      }
    } else {
      await this.sendStatusEmbed(message, '📭 Queue Empty', 'The queue is now empty. Add more songs!');
    }
  }
} // Closing brace for MusicBot class
