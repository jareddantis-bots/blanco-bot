from asyncio import sleep
from lavalink import add_event_hook
from lavalink.events import NodeConnectedEvent, NodeDisconnectedEvent, Event as LavalinkEvent
from nextcord import Interaction, Member, slash_command, SlashOption, VoiceState
from nextcord.abc import Messageable
from nextcord.ext import application_checks
from nextcord.ext.commands import Cog
from os import environ
from typing import Dict, get_args, Optional
from dataclass.custom_embed import CustomEmbed
from utils.database import Database
from utils.exceptions import EndOfQueueError
from utils.jockey import Jockey
from utils.lavalink import init_lavalink
from utils.lavalink_bot import LavalinkBot
from utils.lavalink_helpers import EventWithPlayer
from utils.player_checks import *
from utils.spotify_client import Spotify
from utils.string import human_readable_time


class PlayerCog(Cog):
    def __init__(self, bot: LavalinkBot, db: Database):
        self._bot = bot
        self._db = db
        
        # Spotify client
        self.spotify_client = Spotify()

        # Jockey instances
        self._jockeys: Dict[int, Jockey] = {}

        # Create Lavalink client instance
        if bot.lavalink == None:
            bot.lavalink = init_lavalink(bot.user.id)

        # Listen to Lavalink events
        add_event_hook(self.on_lavalink_event)

        print(f'Loaded cog: {self.__class__.__name__}')
    
    def cog_unload(self):
        """
        Cog unload handler.
        This removes any event hooks that were registered.
        """
        self._bot.lavalink._event_hooks.clear()
    
    @Cog.listener()
    async def on_voice_state_update(self, member: Member, before: VoiceState, after: VoiceState):
        # Stop playing if we're left alone
        voice_client = member.guild.voice_client
        if voice_client is not None and len(voice_client.channel.members) == 1 and after.channel is None:
            # Get the player for this guild from cache
            guild_id = voice_client.guild.id
            player = self.bot.lavalink.player_manager.get(guild_id)
            return await self._disconnect(guild_id, reason='You left me alone :(')

        # Only handle join events by this bot
        if before.channel is None and after.channel is not None and member.id == self._bot.user.id:
            # Get the player for this guild from cache
            guild_id = after.channel.guild.id
            player = self._bot.lavalink.player_manager.get(guild_id)

            # Inactivity check
            time = 0
            inactive_sec = int(environ['INACTIVE_SEC'])
            inactive_h, inactive_m, inactive_s = human_readable_time(inactive_sec * 1000)
            inactive_h = f'{inactive_h}h ' if inactive_h else ''
            inactive_m = f'{inactive_m}m ' if inactive_m else ''
            inactive_s = f'{inactive_s}s' if inactive_s else ''
            while True:
                await sleep(1)
                time = time + 1

                if player is not None:
                    if player.is_playing and not player.paused:
                        time = 0
                    if time == inactive_sec:
                        await self._disconnect(guild_id, reason=f'Inactive for {inactive_h}{inactive_m}{inactive_s}')
                    if not player.is_connected:
                        break
    
    async def on_lavalink_event(self, event: LavalinkEvent):
        if isinstance(event, NodeConnectedEvent):
            print('Connected to Lavalink node.')
        elif isinstance(event, NodeDisconnectedEvent):
            print('Disconnected from Lavalink node.')
        elif isinstance(event, get_args(EventWithPlayer)):
            # Dispatch event to appropriate jockey
            guild_id = int(event.player.guild_id)
            if guild_id in self._jockeys.keys():
                await self._jockeys[guild_id].handle_event(event)
    
    async def delete_jockey(self, guild: int) -> Optional[Messageable]:
        channel = None
        if guild in self._jockeys:
            channel = await self._jockeys[guild].destroy()
            del self._jockeys[guild]
        
        return channel

    def get_jockey(self, guild: int, channel: Optional[Messageable] = None) -> Jockey:
        # Create jockey for guild if it doesn't exist yet
        if guild not in self._jockeys:
            # Ensure that we have a valid channel
            if channel is None:
                raise RuntimeError('No channel provided for jockey creation.')

            self._jockeys[guild] = Jockey(
                guild=guild,
                db=self._db,
                bot=self._bot,
                player=self._bot.lavalink.player_manager.create(guild),
                spotify=self.spotify_client,
                channel=channel
            )

        return self._jockeys[guild]
    
    async def _disconnect(self, guild_id: int, reason: Optional[str] = None):
        # Destroy jockey and player instances
        channel = await self.delete_jockey(guild_id)

        # Send disconnection message
        if channel is not None:
            await channel.send(embed=CustomEmbed(
                title=':wave:｜Disconnected from voice',
                description=reason
            ).get())

    @slash_command(name='play')
    @application_checks.check(check_mutual_voice)
    async def play(self, itx: Interaction, query: Optional[str] = SlashOption(description='Query string or URL', required=True)):
        """
        Play a song from a search query or a URL.
        """
        # Dispatch to jockey
        await itx.response.defer()
        jockey = self.get_jockey(itx.guild_id, itx.channel)
        await jockey.play(itx, query)
    
    @slash_command(name='previous')
    @application_checks.check(check_mutual_voice)
    async def previous(self, itx: Interaction):
        """
        Skip to the previous song.
        """
        # Dispatch to jockey
        await itx.response.defer()
        jockey = self.get_jockey(itx.guild_id, itx.channel)
        await jockey.skip(itx, forward=False)
    
    @slash_command(name='skip')
    @application_checks.check(check_mutual_voice)
    async def skip(self, itx: Interaction):
        """
        Skip the current song.
        """
        # Dispatch to jockey
        await itx.response.defer(ephemeral=True)
        jockey = self.get_jockey(itx.guild_id, itx.channel)
        try:
            await jockey.skip(itx)
        except EndOfQueueError:
            # Disconnect from voice
            await self._disconnect(itx.guild_id, reason='Reached the end of the queue')
