"""
PlayerCog: Cog for controlling the music player.
"""

from asyncio import TimeoutError as AsyncioTimeoutError
from typing import TYPE_CHECKING, Any, Generator, List, Optional

from mafic import PlayerNotConnected
from nextcord import (Color, Forbidden, Guild, HTTPException, Interaction,
                      Member, SlashOption, VoiceState, slash_command)
from nextcord.abc import Messageable
from nextcord.ext import application_checks
from nextcord.ext.commands import Cog
from requests import HTTPError

from dataclass.custom_embed import CustomEmbed
from utils.constants import RELEASE, SPOTIFY_403_ERR_MSG
from utils.embeds import create_error_embed, create_success_embed
from utils.exceptions import (EmptyQueueError, EndOfQueueError, JockeyError,
                              JockeyException, SpotifyNoResultsError)
from utils.logger import create_logger
from utils.paginator import Paginator, list_chunks
from utils.player_checks import check_mutual_voice
from views.spotify_dropdown import SpotifyDropdownView

from .jockey import Jockey

if TYPE_CHECKING:
    from dataclass.queue_item import QueueItem
    from utils.blanco import BlancoBot


class PlayerCog(Cog):
    """
    Cog for creating, controlling, and destroying music players for guilds.
    """
    def __init__(self, bot: 'BlancoBot'):
        """
        Constructor for PlayerCog.
        """
        self._bot = bot
        self._logger = create_logger(self.__class__.__name__)

        # Initialize Lavalink client instance
        if not bot.pool_initialized:
            bot.loop.create_task(bot.init_pool())

        self._logger.info('Loaded PlayerCog')

    @Cog.listener()
    async def on_voice_state_update(self, member: Member, before: VoiceState, after: VoiceState):
        """
        Called every time the voice state of a member changes.
        In this cog, we use it to check if the bot is left alone in a voice channel,
        or if the bot has been server-undeafened.
        """
        # Get the player for this guild from cache
        jockey: Jockey = member.guild.voice_client # type: ignore
        if jockey is not None:
            # Stop playing if we're left alone
            if (hasattr(jockey.channel, 'members') and
                len(jockey.channel.members) == 1 and # type: ignore
                jockey.channel.members[0].id == member.guild.me.id and # type: ignore
                after.channel is None):
                return await self._disconnect(jockey=jockey, reason='You left me alone :(')

            # Did we get server undeafened?
            if member.id == member.guild.me.id and before.deaf and not after.deaf:
                await self._deafen(
                    member.guild.me,
                    was_deafened=True,
                    channel=jockey.status_channel
                )

    async def _get_jockey(self, itx: Interaction) -> Jockey:
        """
        Gets the Jockey instance for the specified guild.
        """
        jockey: Jockey = itx.guild.voice_client # type: ignore
        if jockey is None:
            if not itx.response.is_done():
                await itx.followup.send(embed=create_error_embed('Not connected to voice'))
            raise RuntimeError('Attempted to access nonexistent jockey')

        return jockey

    async def _deafen(
        self,
        bot_user: Member,
        was_deafened: bool = False,
        channel: Optional[Messageable] = None
    ):
        """
        Attempt to deafen the bot user.

        :param bot_user: The bot user to deafen. Should be an instance of nextcord.Member.
        :param was_deafened: Whether the bot user was previously deafened.
        :param channel: The Messageable channel to send the error message to.
        """
        # Check if we're already deafened
        if not was_deafened and bot_user.voice is not None and bot_user.voice.deaf:
            return

        if bot_user.guild_permissions.deafen_members:
            try:
                await bot_user.edit(deafen=True)
            except Forbidden:
                pass

        # Send message
        if channel is not None and hasattr(channel, 'send'):
            err = 'Please server deafen me.'
            if was_deafened:
                err = 'Please do not undeafen me.'

            try:
                await channel.send(embed=create_error_embed(
                    message=f'{err} Deafening helps save server resources.'
                ))
            except (Forbidden, HTTPException):
                self._logger.error('Unable to send deafen message in guild %d', bot_user.guild.id)

    async def _disconnect(
        self,
        jockey: Optional[Jockey] = None,
        itx: Optional[Interaction] = None,
        reason: Optional[str] = None
    ):
        # Destroy jockey instance
        if jockey is None:
            if itx is None:
                raise ValueError('[player::_disconnect] Either jockey or itx must be specified')
            jockey = await self._get_jockey(itx)

        try:
            await jockey.stop()
        except PlayerNotConnected:
            self._logger.warning('Attempted to disconnect disconnected Jockey')
        await jockey.disconnect()

        # Send disconnection message
        embed = CustomEmbed(
            title=':wave:｜Disconnected from voice',
            description=reason,
            footer=f'Blanco release {RELEASE}'
        ).get()

        # Try to send disconnection message
        try:
            if itx is not None:
                await itx.followup.send(embed=embed)
            else:
                guild_id = jockey.guild.id
                channel = self._bot.get_status_channel(guild_id)
                if channel is not None:
                    await channel.send(embed=embed)
        except (Forbidden, HTTPException):
            self._logger.error('Unable to send disconnect message in guild %d', jockey.guild.id)

        # Dispatch disconnect event
        self._bot.dispatch('jockey_disconnect', jockey)

    @slash_command(name='jump')
    @application_checks.check(check_mutual_voice)
    async def jump(
        self,
        itx: Interaction,
        position: int = SlashOption(description='Position to jump to', required=True)
    ):
        """
        Jumps to the specified position in the queue.
        """
        jockey = await self._get_jockey(itx)

        # First check if the value is within range
        if position < 1 or position > len(jockey.queue):
            await itx.response.send_message(
                f'Specify a number from 1 to {str(len(jockey.queue))}.',
                ephemeral=True
            )
            return

        # Dispatch to jockey
        await itx.response.defer()
        try:
            await jockey.skip(index=position - 1, auto=False)
        except JockeyError as err:
            await itx.followup.send(embed=create_error_embed(str(err)))
        else:
            await itx.followup.send(embed=create_success_embed(f'Jumped to track {str(position)}'))

    @slash_command(name='loop')
    @application_checks.check(check_mutual_voice)
    async def loop(self, itx: Interaction):
        """
        Loops the current track.
        """
        jockey = await self._get_jockey(itx)
        if not jockey.queue_manager.is_looping_one:
            jockey.queue_manager.is_looping_one = True

            # Update now playing message
            await jockey.update_now_playing()

        return await itx.response.send_message(embed=create_success_embed('Looping current track'))

    @slash_command(name='loopall')
    @application_checks.check(check_mutual_voice)
    async def loopall(self, itx: Interaction):
        """
        Loops the whole queue.
        """
        jockey = await self._get_jockey(itx)
        if not jockey.queue_manager.is_looping_all:
            jockey.queue_manager.is_looping_all = True

            # Update now playing message
            await jockey.update_now_playing()

        return await itx.response.send_message(embed=create_success_embed('Looping entire queue'))

    @slash_command(name='nowplaying')
    @application_checks.check(check_mutual_voice)
    async def now_playing(self, itx: Interaction):
        """
        Displays the currently playing track.
        """
        await itx.response.defer(ephemeral=True)
        jockey = await self._get_jockey(itx)
        embed = jockey.now_playing()
        await itx.followup.send(embed=embed)

    @slash_command(name='pause')
    @application_checks.check(check_mutual_voice)
    async def pause(self, itx: Interaction, quiet: bool = False):
        """
        Pauses the current track.
        """
        if not quiet:
            await itx.response.defer()

        # Dispatch to jockey
        jockey = await self._get_jockey(itx)
        await jockey.pause()

        if not quiet:
            await itx.followup.send(embed=create_success_embed('Paused'), delete_after=5.0)

    @slash_command(name='play')
    @application_checks.check(check_mutual_voice)
    async def play(
        self,
        itx: Interaction,
        query: str = SlashOption(description='Query string or URL', required=True)
    ):
        """
        Play a song from a search query or a URL.
        If you want to unpause a paused player, use /unpause instead.
        """
        if (not isinstance(itx.user, Member) or not itx.user.voice or
            not itx.user.voice.channel or not isinstance(itx.guild, Guild)):
            return await itx.response.send_message(embed=create_error_embed(
                message='Connect to a server voice channel to use this command.'
            ), ephemeral=True)

        # Set status channel
        guild_id = itx.guild.id
        channel = itx.channel
        if not isinstance(channel, Messageable):
            raise RuntimeError('[player::play] itx.channel is not Messageable')
        self._bot.set_status_channel(guild_id, channel)

        # Check if Lavalink is ready
        if not self._bot.pool_initialized or len(self._bot.pool.nodes) == 0:
            return await itx.response.send_message(embed=create_error_embed(
                message='No Lavalink nodes available. Try again later.'
            ))

        # Connect to voice
        await itx.response.defer()
        voice_channel = itx.user.voice.channel
        if itx.guild.voice_client is None:
            try:
                await voice_channel.connect(cls=Jockey) # type: ignore
                await voice_channel.guild.change_voice_state(
                    channel=voice_channel,
                    self_deaf=True
                )
                await self._deafen(itx.guild.me, channel=channel)
            except AsyncioTimeoutError:
                return await itx.followup.send(embed=create_error_embed(
                    message='Timed out while connecting to voice. Try again later.'
                ))

        # Dispatch to jockey
        jockey = await self._get_jockey(itx)
        try:
            track_name = await jockey.play_impl(query, itx.user.id)
        except JockeyError as err:
            # Disconnect if we're not playing anything
            if not jockey.playing:
                return await self._disconnect(itx=itx, reason=f'Error: `{err}`')

            return await itx.followup.send(embed=create_error_embed(str(err)))
        except JockeyException as exc:
            return await itx.followup.send(embed=create_error_embed(str(exc)))

        body = [f'{track_name}\n']

        # Add Last.fm integration promo if enabled
        assert self._bot.config is not None
        if (self._bot.config.base_url is not None and
            self._bot.config.lastfm_api_key is not None and
            self._bot.config.lastfm_shared_secret is not None):
            # Check if the user has connected their Last.fm account
            if self._bot.database.get_lastfm_credentials(itx.user.id) is not None:
                body.append(f':handshake: {itx.user.mention} is scrobbling to Last.fm!')
            body.append(
                f':sparkles: [Link Last.fm]({self._bot.config.base_url}) to scrobble as you listen'
            )

        # Update now playing message
        await jockey.update_now_playing()

        embed = create_success_embed(
            title='Added to queue',
            body='\n'.join(body),
        )
        return await itx.followup.send(embed=embed.set_footer(text=f'Blanco release {RELEASE}'))

    @slash_command(name='playlists')
    async def playlist(self, itx: Interaction):
        """
        Pick a Spotify playlist from your library to play.
        """
        if itx.user is None:
            return
        await itx.response.defer()

        # Get Spotify client
        try:
            spotify = self._bot.get_spotify_client(itx.user.id)
            if spotify is None:
                raise ValueError('You are not connected to Spotify.')
        except ValueError as err:
            return await itx.followup.send(
                embed=create_error_embed(err.args[0]),
                ephemeral=True
            )

        # Get the user's playlists
        try:
            playlists = spotify.get_user_playlists()
        except HTTPError as err:
            if err.response is not None and err.response.status_code == 403:
                return await itx.followup.send(embed=create_error_embed(
                    message=SPOTIFY_403_ERR_MSG.format('get your playlists')
                ), ephemeral=True)
            raise
        if len(playlists) == 0:
            return await itx.followup.send(embed=create_error_embed(
                message='You have no playlists.'
            ), ephemeral=True)

        # Create dropdown
        view = SpotifyDropdownView(self._bot, playlists, itx.user.id, 'playlist')
        await itx.followup.send(embed=create_success_embed(
            title='Pick a playlist',
            body='Select a playlist from the dropdown below.'
        ), view=view, delete_after=60.0)

    @slash_command(name='previous')
    @application_checks.check(check_mutual_voice)
    async def previous(self, itx: Interaction):
        """
        Skip to the previous song.
        """
        # Dispatch to jockey
        await itx.response.defer()
        jockey = await self._get_jockey(itx)
        try:
            await jockey.skip(forward=False, auto=False)
        except EndOfQueueError as err:
            embed = create_error_embed(f'Unable to rewind: {err.args[0]}')
            await itx.followup.send(embed=embed)

    @slash_command(name='queue')
    @application_checks.check(check_mutual_voice)
    async def queue(self, itx: Interaction):
        """
        Displays the current queue.
        """
        if itx.guild is None:
            raise RuntimeError('[player::queue] itx.guild is None')
        await itx.response.defer()

        # Get jockey
        jockey = await self._get_jockey(itx)
        if len(jockey.queue) == 0:
            await itx.followup.send(embed=create_error_embed('Queue is empty'))
            return

        # Show loop status
        embed_header = [f'{len(jockey.queue)} total']
        if jockey.queue_manager.is_looping_all:
            embed_header.append(':repeat: Looping entire queue (`/unloopall` to disable)')

        # Show shuffle status
        queue = jockey.queue_manager.shuffled_queue
        current = jockey.queue_manager.current_shuffled_index
        if jockey.queue_manager.is_shuffling:
            embed_header.append(
                ':twisted_rightwards_arrows: Shuffling queue  (`/unshuffle` to disable)'
            )

        # Show queue in chunks of 10 per page
        pages = []
        homepage = 0
        count = 1
        prefix_len = len(str(len(jockey.queue)))
        for i, chunk in enumerate(list_chunks(queue)):
            chunk_tracks = []

            # Create page content
            track: 'QueueItem'
            for track in chunk:
                title, artist = track.get_details()

                # Pad index with spaces if necessary
                index = str(count)
                while len(index) < prefix_len:
                    index = ' ' + index

                # Is this the current track?
                line_prefix = '  '
                if count - 1 == current:
                    line_prefix = '> '
                    homepage = i

                # Create item line
                line_prefix = '> ' if count - 1 == current else '  '
                line = f'{line_prefix} {index} :: {title} - {artist}'

                # Truncate line if necessary
                if len(line) > 50:
                    line = line[:47] + '...'
                else:
                    line = f'{line:50.50}'
                chunk_tracks.append(line)
                count += 1

            # Create page
            tracks = '\n'.join(chunk_tracks)
            embed_body = embed_header + [f'```asciidoc\n{tracks}```']
            embed = CustomEmbed(
                title=f'Queue for {itx.guild.name}',
                description='\n'.join(embed_body),
                color=Color.lighter_gray()
            )
            pages.append(embed.get())

        # Run paginator
        paginator = Paginator(itx)
        return await paginator.run(pages, start=homepage)

    @slash_command(name='remove')
    @application_checks.check(check_mutual_voice)
    async def remove(
        self,
        itx: Interaction,
        position: int = SlashOption(
            description='Position to remove',
            required=True
        )
    ):
        """
        Remove a track from queue.
        """
        jockey = await self._get_jockey(itx)
        if position < 1 or position > jockey.queue_size:
            return await itx.response.send_message(embed=create_error_embed(
                message=f'Specify a number from 1 to {str(jockey.queue_size)}.'
            ), ephemeral=True)
        if position - 1 == jockey.queue_manager.current_index:
            return await itx.response.send_message(embed=create_error_embed(
                message='You cannot remove the currently playing track.'
            ), ephemeral=True)

        # Dispatch to jockey
        await itx.response.defer()
        title, artist = await jockey.remove(index=position - 1)
        await itx.followup.send(embed=create_success_embed(
            title='Removed from queue',
            body=f'**{title}**\n{artist}'
        ))

        # Update now playing message
        await jockey.update_now_playing()

    @slash_command(name='search')
    async def search(
        self,
        itx: Interaction,
        search_type: str = SlashOption(
            description='Search type',
            required=True,
            choices=['track', 'playlist', 'album', 'artist']
        ),
        query: str = SlashOption(description='Query string', required=True)
    ):
        """
        Search Spotify's catalog for tracks to play.
        """
        if itx.user is None:
            return
        await itx.response.defer()

        # Search catalog
        try:
            results = self._bot.spotify.search(query, search_type)
        except SpotifyNoResultsError:
            return await itx.followup.send(embed=create_error_embed(
                message=f'No results found for `{query}`.'
            ), ephemeral=True)

        # Create dropdown
        view = SpotifyDropdownView(self._bot, results, itx.user.id, search_type)
        await itx.followup.send(embed=create_success_embed(
            title=f'Results for `{query}`',
            body='Select a result to play from the dropdown below.'
        ), view=view, delete_after=60.0)

    @slash_command(name='shuffle')
    @application_checks.check(check_mutual_voice)
    async def shuffle(self, itx: Interaction, quiet: bool = False):
        """
        Shuffle the current playlist.
        If you want to unshuffle the current queue, use /unshuffle instead.
        """
        if not quiet:
            await itx.response.defer()

        # Dispatch to jockey
        jockey = await self._get_jockey(itx)
        try:
            jockey.queue_manager.shuffle()
        except EmptyQueueError as err:
            if not quiet:
                await itx.followup.send(embed=create_error_embed(str(err.args[0])))
        else:
            # Update now playing message
            await jockey.update_now_playing()

            if not quiet:
                await itx.followup.send(
                    embed=create_success_embed(f'{len(jockey.queue)} tracks shuffled')
                )

    @slash_command(name='skip')
    @application_checks.check(check_mutual_voice)
    async def skip(self, itx: Interaction):
        """
        Skip the current song.
        """
        # Dispatch to jockey
        await itx.response.defer(ephemeral=True)
        jockey = await self._get_jockey(itx)
        try:
            await jockey.skip(auto=False)
        except EndOfQueueError as err:
            embed = create_error_embed(f'Unable to skip: {err.args[0]}')
            await itx.followup.send(embed=embed)

    @slash_command(name='stop')
    @application_checks.check(check_mutual_voice)
    async def stop(self, itx: Interaction):
        """
        Stops the current song and disconnects from voice.
        """
        if not isinstance(itx.user, Member):
            raise RuntimeError('[player::stop] itx.user is not a Member')
        await itx.response.defer()
        await self._disconnect(itx=itx, reason=f'Stopped by <@{itx.user.id}>')

    @slash_command(name='unloop')
    @application_checks.check(check_mutual_voice)
    async def unloop(self, itx: Interaction):
        """
        Stops looping the current track.
        """
        # Dispatch to jockey
        jockey = await self._get_jockey(itx)
        if jockey.queue_manager.is_looping_one:
            jockey.queue_manager.is_looping_one = False

            # Update now playing message
            await jockey.update_now_playing()

        return await itx.response.send_message(
            embed=create_success_embed('Not looping current track')
        )

    @slash_command(name='unloopall')
    @application_checks.check(check_mutual_voice)
    async def unloopall(self, itx: Interaction):
        """
        Stops looping the whole queue.
        """
        # Dispatch to jockey
        jockey = await self._get_jockey(itx)
        if jockey.queue_manager.is_looping_all:
            jockey.queue_manager.is_looping_all = False

            # Update now playing message
            await jockey.update_now_playing()

        return await itx.response.send_message(
            embed=create_success_embed('Not looping entire queue')
        )

    @slash_command(name='unpause')
    @application_checks.check(check_mutual_voice)
    async def unpause(self, itx: Interaction, quiet: bool = False):
        """
        Unpauses the current track.
        """
        if not quiet:
            await itx.response.defer()

        # Dispatch to jockey
        jockey = await self._get_jockey(itx)
        await jockey.resume()

        if not quiet:
            await itx.followup.send(embed=create_success_embed('Unpaused'), delete_after=5.0)

    @slash_command(name='unshuffle')
    @application_checks.check(check_mutual_voice)
    async def unshuffle(self, itx: Interaction, quiet: bool = False):
        """
        Unshuffle the current playlist.
        """
        if not quiet:
            await itx.response.defer()

        # Dispatch to jockey
        jockey = await self._get_jockey(itx)
        if jockey.queue_manager.is_shuffling:
            jockey.queue_manager.unshuffle()
            if not quiet:
                return await itx.followup.send(embed=create_success_embed('Unshuffled'))

            # Update now playing message
            await jockey.update_now_playing()

        if not quiet:
            return await itx.followup.send(
                embed=create_error_embed('Current queue is not shuffled')
            )

    @slash_command(name='volume')
    @application_checks.check(check_mutual_voice)
    async def volume(
        self,
        itx: Interaction,
        volume: Optional[int] = SlashOption(
            description='Volume level. Leave empty to print current volume.',
            required=False,
            min_value=0,
            max_value=1000
        )
    ):
        """
        Sets the volume level.
        """
        jockey = await self._get_jockey(itx)

        # Is the volume argument empty?
        if not volume:
            # Print current volume
            return await itx.response.send_message(
                f'The volume is set to {jockey.volume}.',
                ephemeral=True
            )

        # Dispatch to jockey
        await itx.response.defer()
        await jockey.set_volume(volume)
        await itx.followup.send(embed=create_success_embed(f'Volume set to {volume}'))

        # Update now playing message
        await jockey.update_now_playing()
