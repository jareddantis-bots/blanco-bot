"""
Music player class for Blanco. Subclass of mafic.Player.
"""

from asyncio import get_event_loop, sleep
from time import time
from typing import TYPE_CHECKING, List, Optional, Tuple

from mafic import Player, PlayerNotConnected
from nextcord import (Colour, Forbidden, HTTPException, Message, NotFound,
                      StageChannel, VoiceChannel)

from dataclass.custom_embed import CustomEmbed
from utils.constants import UNPAUSE_THRESHOLD
from utils.embeds import create_error_embed
from utils.exceptions import (EndOfQueueError, JockeyError, JockeyException,
                              LavalinkSearchError, SpotifyNoResultsError)
from utils.musicbrainz import annotate_track
from utils.time import human_readable_time
from views.now_playing import NowPlayingView

from .jockey_helpers import (find_lavalink_track, invalidate_lavalink_track,
                             parse_query)
from .queue import QueueManager

if TYPE_CHECKING:
    from mafic import Track
    from nextcord import Embed
    from nextcord.abc import Connectable, Messageable

    from dataclass.queue_item import QueueItem
    from utils.blanco import BlancoBot


class Jockey(Player['BlancoBot']):
    """
    Class that handles music playback for a single guild.
    Contains all the methods for music playback, along with a
    local instance of an in-memory database for fast queueing.
    """

    def __init__(self, client: 'BlancoBot', channel: 'Connectable'):
        super().__init__(client, channel)
        self._bot = client

        if not isinstance(channel, StageChannel) and not isinstance(channel, VoiceChannel):
            raise TypeError(f'Channel must be a voice channel, not {type(channel)}')

        # Database
        self._db = client.database
        client.database.init_guild(channel.guild.id)

        # Pause timestamp
        self._pause_ts: Optional[int] = None

        # Queue
        self._queue_mgr = QueueManager(channel.guild.id, client.database)

        # Volume
        self._volume = client.database.get_volume(channel.guild.id)

        # Logger
        self._logger = client.jockey_logger
        self._logger.info(
            'Using node `%s\' for %s',
            self.node.label,
            channel.guild.name
        )

    @property
    def playing(self) -> bool:
        """
        Returns whether the player is currently playing a track.
        """
        return self.current is not None

    @property
    def queue(self) -> List['QueueItem']:
        """
        Returns the player queue.
        """
        return self._queue_mgr.queue

    @property
    def queue_manager(self) -> QueueManager:
        """
        Returns the queue manager for the player.
        """
        return self._queue_mgr

    @property
    def queue_size(self) -> int:
        """
        Returns the player queue size.
        """
        return self._queue_mgr.size

    @property
    def status_channel(self) -> 'Messageable':
        """
        Returns the status channel for the player.
        """
        channel = self._bot.get_status_channel(self.guild.id)
        if channel is None:
            raise ValueError('Status channel has not been set')
        return channel

    @property
    def volume(self) -> int:
        """
        Returns the player volume.
        """
        return self._volume

    @volume.setter
    def volume(self, value: int):
        """
        Sets the player volume and saves it to the database.
        """
        self._volume = value
        self._db.set_volume(self.guild.id, value)

    async def _edit_np_controls(self, show_controls: bool = True):
        """
        Edits the now playing message to show or hide controls.
        """
        view = None
        if show_controls:
            view = NowPlayingView(self._bot, self)

        np_msg = await self._get_now_playing()
        if isinstance(np_msg, Message):
            try:
                await np_msg.edit(view=view)
            except (HTTPException, Forbidden) as exc:
                self._logger.warning(
                    'Could not edit now playing message for %s: %s',
                    self.guild.name,
                    exc
                )

    async def _enqueue(self, index: int, auto: bool = True):
        """
        Attempt to enqueue a track, for use with the skip() method.

        :param index: The index of the track to enqueue.
        :param auto: Whether this is an automatic enqueue, i.e. not part of a user's command.
        """
        try:
            track = self._queue_mgr.queue[index]
            await self._play(track)
        except PlayerNotConnected:
            if not auto:
                await self.status_channel.send(embed=create_error_embed(
                    'Attempted to skip while disconnected'
                ))
            raise JockeyError('Player is not connected')
        except JockeyError as err:
            self._logger.error('Failed to enqueue track: %s', err)
            raise

        # Scrobble if possible
        await self._scrobble(self._queue_mgr.current)

        # Update queue index
        self._queue_mgr.current_index = index

    async def _get_now_playing(self) -> Optional[Message]:
        np_msg_id = self._db.get_now_playing(self.guild.id)
        if np_msg_id != -1:
            try:
                np_msg = await self.status_channel.fetch_message(np_msg_id)
                return np_msg
            except (Forbidden, HTTPException, NotFound) as exc:
                self._logger.warning(
                    'Failed to fetch now playing message for %s: %s',
                    self.guild.name,
                    exc
                )

        return None

    async def _play(self, item: 'QueueItem', position: Optional[int] = None):
        if item.lavalink_track is None:
            try:
                assert self._bot.config is not None
                deezer_enabled = self._bot.config.lavalink_nodes[self.node.label].deezer
                item.lavalink_track = await find_lavalink_track(
                    self.node,
                    item,
                    deezer_enabled=deezer_enabled
                )
            except LavalinkSearchError as err:
                self._logger.critical('Failed to play `%s\'.', item.title)
                raise JockeyError(err.args[0]) from err

        # Play track
        has_retried = False
        while True:
            try:
                await self.play(
                    item.lavalink_track,
                    volume=self.volume,
                    start_time=position,
                    replace=True,
                    pause=False
                )
            except PlayerNotConnected as err:
                # If we've already retried, give up
                if has_retried:
                    raise JockeyError(err.args[0]) from err

                # Wait until we're connected
                wait_time = 0
                self._logger.warning(
                    'PlayerNotConnected raised while trying to play `%s\', retrying...',
                    item.title
                )
                while not self.connected:
                    if wait_time >= 10:
                        raise JockeyError('Timeout while waiting for player to connect') from err

                    # Print wait message only once
                    if wait_time == 0:
                        self._logger.debug('Waiting 10 sec for player to connect...')
                    await sleep(0.1)
                    wait_time += 0.1

                # Remove cached Lavalink track and try again
                invalidate_lavalink_track(item)
                has_retried = True
            else:
                # Clear pause timestamp for new track
                if position is None:
                    self._pause_ts = None

                break

        # Save start time for scrobbling
        item.start_time = int(time())

    async def _scrobble(self, item: 'QueueItem'):
        """
        Scrobbles a track in a separate thread.

        :param item: The track to scrobble.
        """
        get_event_loop().create_task(self._scrobble_impl(item))

    async def _scrobble_impl(self, item: 'QueueItem'):
        """
        Scrobbles a track for all users in the channel who have
        linked their Last.fm accounts.

        Called by _scrobble() in a separate thread.

        :param item: The track to scrobble.
        """
        if not isinstance(self.channel, VoiceChannel):
            return

        # Check if scrobbling is enabled
        assert self._bot.config is not None
        if not self._bot.config.lastfm_enabled:
            return

        # Check if track can be scrobbled
        time_now = int(time())
        try:
            duration = item.duration
            if item.lavalink_track is not None:
                duration = item.lavalink_track.length

            if item.start_time is not None and duration is not None:
                # Check if track is longer than 30 seconds
                if duration < 30000:
                    raise ValueError('Track is too short')

                # Check if enough time has passed (1/2 duration or 4 min, whichever is less)
                elapsed_ms = (time_now - item.start_time) * 1000
                if elapsed_ms < min(duration // 2, 240000):
                    raise ValueError('Not enough time has passed')
            else:
                # Default to current time for timestamp
                item.start_time = time_now
        except ValueError as err:
            self._logger.warning('Failed to scrobble `%s\': %s', item.title, err.args[0])
            return

        # Lookup MusicBrainz ID if needed
        if item.mbid is None:
            annotate_track(item)

        # Don't scrobble with no MBID and ISRC,
        # as the track probably isn't on Last.fm
        if item.mbid is None and item.isrc is None:
            self._logger.warning(
                'Not scrobbling `%s\': no MusicBrainz ID or ISRC',
                item.title
            )
            return

        # Scrobble for every user
        for member in self.channel.members:
            if not member.bot:
                scrobbler = self._bot.get_scrobbler(member.id)
                if scrobbler is not None:
                    scrobbler.scrobble(item)

    async def disconnect(self, *, force: bool = False):
        """
        Removes the controls from Now Playing, then disconnects.
        """
        # Get now playing message
        np_msg = await self._get_now_playing()
        if np_msg is not None:
            try:
                await np_msg.edit(view=None)
            except (HTTPException, Forbidden):
                self._logger.warning(
                    'Failed to remove now playing message for %s',
                    self.guild.name
                )

        # Disconnect
        await super().disconnect(force=force)

    def now_playing(self, current: Optional['Track'] = None) -> 'Embed':
        """
        Returns information about the currently playing track.

        :return: An instance of nextcord.Embed
        """
        if current is None:
            if self.current is None:
                raise EndOfQueueError('No track is currently playing')
            current = self.current

        # Construct Spotify URL if it exists
        track = self._queue_mgr.current
        uri = current.uri
        if track.spotify_id is not None:
            uri = f'https://open.spotify.com/track/{track.spotify_id}'

        # Get track duration
        duration_ms = track.duration
        if track.lavalink_track is not None:
            duration_ms = track.lavalink_track.length

        # Build track duration string
        duration = ''
        if duration_ms is not None:
            duration = human_readable_time(duration_ms)

        # Display complete artists if available
        artist = track.artist if track.author is None else track.author
        if artist is None:
            artist = 'Unknown artist'

        # Display type of track
        is_stream = False
        if track.lavalink_track is not None:
            is_stream = track.lavalink_track.stream

        # Build footer
        footer = f'Track {self._queue_mgr.current_shuffled_index + 1} of {self.queue_size}'
        if self._queue_mgr.is_shuffling:
            footer += ' 🔀'
        if self._queue_mgr.is_looping_one:
            footer += ' 🔂'
        if self._queue_mgr.is_looping_all:
            footer += ' 🔁'
        footer += f' • Volume {self.volume}%'

        imperfect_msg = ':warning: Playing the [**closest match**]({})'
        embed = CustomEmbed(
            title='Now streaming' if is_stream else 'Now playing',
            description=[
                f'[**{track.title}**]({uri})',
                artist,
                duration if not is_stream else '',
                f'\nrequested by <@{track.requester}>',
                imperfect_msg.format(current.uri) if track.is_imperfect else ''
            ],
            footer=footer,
            color=Colour.teal(),
            thumbnail_url=track.artwork
        )
        return embed.get()

    async def on_load_failed(self, failed_source: 'Track'):
        """
        Called when a track fails to load.
        Sends an error message to the status channel
        and skips to the next track in queue.

        :param failed_track: The track that failed to load. Must be an instance of mafic.Track.
        """
        # Get current track and its index
        failed_track = self._queue_mgr.current
        index = self._queue_mgr.current_shuffled_index + 1
        queue_size = self._queue_mgr.size

        # Send error embed
        embed = CustomEmbed(
            color=Colour.red(),
            title=':warning:｜Failed to load track',
            description=[
                'This could be due to a temporary issue with the source,',
                'a bot outage, or the track may be unavailable for playback.',
                'You can try playing the track again later.'
            ],
            fields=[
                ['Track', f'`{failed_track.title}`\n{failed_track.artist}'],
                ['Position in queue', f'{index} of {queue_size}'],
                ['Playback source', f'`{failed_source.title}`\n{failed_source.author}'],
                ['Playback URL', f'[{failed_source.source}]({failed_source.uri})'],
            ],
            footer='Skipping to next track...',
        )
        await self.status_channel.send(embed=embed.get())

        # Skip to next track
        await self.skip()

    async def pause(self, pause: bool = True):
        """
        Pauses the player and stores the time at which playback was paused.

        The timestamp is necessary because Lavalink 4.0.0 (beta) does not
        properly resume tracks when they are paused for an extended period,
        causing the track to skip to the next one in the queue after a few
        seconds of resumed playback.

        :param pause: Whether to pause or resume playback.
        """
        await super().pause(pause=pause)

        # Store pause timestamp
        self._pause_ts = int(time())

    async def play_impl(self, query: str, requester: int) -> str:
        """
        Adds an item to the player queue and begins playback if necessary.

        :param query: The query to play.
        :param requester: The ID of the user who requested the track.
        :return: A string containing the name of the track that was added.
        """
        # Get results for query
        try:
            new_tracks = await parse_query(
                self.node,
                self._bot.spotify,
                query,
                requester
            )
        except JockeyException:
            raise
        except SpotifyNoResultsError as err:
            raise JockeyError(err.args[0]) from err
        except Exception as exc:
            if self.playing:
                raise JockeyException(str(exc)) from exc
            raise JockeyError(str(exc)) from exc

        # Add new tracks to queue
        old_size = self._queue_mgr.size
        self._queue_mgr.extend(new_tracks)

        # Get info for first track
        first = new_tracks[0]
        first_name = f'**{first.title}**\n{first.artist}' if first.title is not None else query

        # Are we beginning a new queue or is the player idle?
        if not self.playing:
            # We are! Play the first new track.
            old_index = self._queue_mgr.current_index
            self._queue_mgr.current_index = old_size

            try:
                await self._play(new_tracks[0])
            except (JockeyError, PlayerNotConnected) as err:
                # Remove enqueued tracks
                for _ in range(old_size, self._queue_mgr.size):
                    self._queue_mgr.remove(old_size)

                # Restore old index
                self._queue_mgr.current_index = old_index

                raise JockeyError(f'Failed to play "{first.title}"') from err

        # Send embed
        return first_name if len(new_tracks) == 1 else f'{len(new_tracks)} item(s)'

    async def remove(self, index: int) -> Tuple[str | None, str | None]:
        """
        Removes a track from the queue.
        """
        # Remove track from queue
        removed_track = self._queue_mgr.remove(index)

        # Return removed track details
        return removed_track.title, removed_track.artist

    async def resume(self):
        """
        Resumes the player from a paused state.

        If the player was paused for an extended period, the current track
        will be re-enqueued and played from the last position to work around
        a bug in Lavalink 4.0.0 (beta).
        """
        # Check if we were paused for too long or if reenqueuing is disabled
        assert self._bot.config is not None
        if not self._bot.config.reenqueue_paused or (
            self._pause_ts is None or int(time()) - self._pause_ts < UNPAUSE_THRESHOLD):
            await super().resume()
            return

        # We were paused for too long, re-enqueue the current track
        # and play from a little bit before the last position
        last_pos = max(self.position - 10, 0)
        self._pause_ts = None
        self._logger.debug('Unpaused beyond %d sec threshold, re-enqueueing', UNPAUSE_THRESHOLD)
        await self._play(self._queue_mgr.current, last_pos)

    async def set_volume(self, volume: int, /):
        """
        Sets the player volume.
        """
        await super().set_volume(volume)
        self.volume = volume

    async def skip(self, *, forward: bool = True, index: int = -1, auto: bool = True):
        """
        Skips the current track and plays the next one in the queue.

        :param forward: Whether to skip forward or backward.
        :param index: The index of the track to skip to.
        :param auto: Whether this is an automatic skip, i.e. not part of a user's command.
            This is True when the player skips to the next track automatically,
            such as when the current track ends.
        """
        # It takes a while for the player to skip,
        # so let's remove the player controls while we wait
        # to prevent the user from spamming them.
        await self._edit_np_controls(show_controls=False)

        try:
            played = await self.play_bump()
            if played:
                return
        except JockeyException as err:
            self._logger.error("Error attempting to play bump, skipping: %s", err)

        # If index is specified, use that instead
        if index != -1:
            try:
                await self._enqueue(index, auto=auto)
            except JockeyError:
                await self._edit_np_controls(show_controls=True)
                await self.status_channel.send(embed=create_error_embed(
                    f'Unable to skip to index {index}'
                ))
                raise

            return

        # Is this autoskipping?
        if auto:
            # Check if we're looping the current track
            if self._queue_mgr.is_looping_one:
                # Re-enqueue the current track
                try:
                    await self._enqueue(self._queue_mgr.current_index, auto=auto)
                except JockeyError as err:
                    await self._edit_np_controls(show_controls=True)
                    await self.status_channel.send(embed=create_error_embed(
                        f'Unable to loop track: {err}'
                    ))

                return

        # Try to enqueue the next playable track
        delta = 1 if forward else -1
        while True:
            # Get next index
            try:
                next_i = self._queue_mgr.calc_next_index(delta=delta)
            except EndOfQueueError:
                # We've reached the end of the queue and looping is disabled
                return

            # Get details of next track for logging
            next_track = self._queue_mgr.queue[next_i]
            next_title = next_track.title if next_track.title is not None else 'Unknown track'
            next_artist = next_track.artist if next_track.artist is not None else 'Unknown artist'

            # Try to enqueue the next track
            try:
                await self._enqueue(next_i, auto=auto)
            except JockeyError as err:
                await self._edit_np_controls(show_controls=True)
                delta += 1 if forward else -1

                await self.status_channel.send(embed=CustomEmbed(
                    color=Colour.red(),
                    title=':warning:｜Failed to skip to track',
                    description='It might be unavailable temporarily '
                        'or restricted to specific regions.\n',
                    fields=[
                        ['Track', f'`{next_title}`\n{next_artist}'],
                        ['Position in queue', f'{next_i + 1} of {self.queue_size}'],
                        ['Error', f'```{err}```']
                    ],
                    footer='Skipping to next track...' if auto else None
                ).get())
            else:
                break

    async def update_now_playing(self):
        """
        Update the existing Now Playing view with current information.
        """
        # Get now playing message
        np_msg = await self._get_now_playing()
        if np_msg is None:
            return

        # Edit message
        try:
            await np_msg.edit(embed=self.now_playing())
        except (HTTPException, Forbidden) as exc:
            # Ignore 404
            if not isinstance(exc, NotFound):
                self._logger.warning(
                    'Failed to edit now playing message for %s: %s',
                    self.guild.name,
                    exc
                )

    async def play_bump(self) -> bool:
        """
        Check and attempt to play a bump if it's been long enough.
        :return: A boolean denoting whether a bump was played or not.
        """

        enabled = self._db.get_bumps_enabled(self.guild.id)
        if not enabled:
            self._logger.debug("Bumps are not enabled in this guild, returning...")
            return False

        interval = self._db.get_bump_interval(self.guild.id) * 60
        last_bump = self._db.get_last_bump(self.guild.id)

        if last_bump == 0:
            self._logger.debug('Last bump is zero, initializing and skipping...')
            self._db.set_last_bump(self.guild.id)
            return False

        if int(time()) - last_bump < interval:
            self._logger.debug('Hasn\'t been long enough to play a bump.')
            return False

        bump = self._db.get_random_bump(self.guild.id)
        if bump is None:
            self._logger.debug('Guild has no bumps.')
            return False

        requester = self._bot.user.id if self._bot.user is not None else self.guild.me.id

        try:
            tracks = await parse_query(self.node, self._bot.spotify, bump.url, requester)
        except (JockeyException, SpotifyNoResultsError) as err:
            self._logger.error('Error parsing bump tracks: %s', err)
            return False

        if len(tracks) == 0:
            self._logger.error('Unable to parse bump URL into track.')
            return False

        await self._play(tracks[0])
        self._db.set_last_bump(self.guild.id)
        return True
