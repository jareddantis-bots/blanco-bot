from dataclass.custom_embed import CustomEmbed
from dataclass.queue_item import QueueItem
from itertools import islice
from lavalink.models import DefaultPlayer
from nextcord import Color, Embed, Interaction
from typing import Any, Coroutine, List, Optional, TYPE_CHECKING
from .exceptions import SpotifyInvalidURLError
from .lavalink_client import *
from .spotify_client import Spotify
from .string_util import human_readable_time
from .url import *
import asyncio
if TYPE_CHECKING:
    from dataclass.lavalink_result import LavalinkResult
    from dataclass.spotify_track import SpotifyTrack


def create_error_embed(message: str) -> Embed:
    embed = CustomEmbed(
        color=Color.red(),
        title=':x:｜Error processing command',
        description=message
    )
    return embed.get()


def create_success_embed(title: str = None, body: str = None) -> Embed:
    if body is None:
        body = title
        title = 'Success'
    
    embed = CustomEmbed(
        color=Color.green(),
        title=f':white_check_mark:｜{title}',
        description=body
    )
    return embed.get()


def create_now_playing_embed(track: QueueItem, real_uri: Optional[str] = '') -> Embed:
    # Construct Spotify URL if it exists
    uri = real_uri
    if track.spotify_id is not None:
        uri = f'https://open.spotify.com/track/{track.spotify_id}'
    
    # Get track duration
    duration = None
    if track.duration != 0:
        h, m, s = human_readable_time(track.duration)
        duration = f'{s} sec'
        if m > 0:
            duration = f'{m} min {duration}'
        if h > 0:
            duration = f'{h} hr {duration}'

    try:
        is_stream = track.lavalink_track.stream
    except:
        is_stream = False
    embed = CustomEmbed(
        title='Now streaming' if is_stream else 'Now playing',
        description=[
            f'[**{track.title}**]({uri})',
            f'{track.artist}',
            duration if not is_stream else None,
            f'\nrequested by <@{track.requester}>',
            f'\n:warning: Could not find a perfect match for this Spotify track.\nPlaying the closest match instead: {real_uri}' if track.is_imperfect else None
        ],
        color=Color.teal(),
        thumbnail_url=track.artwork,
        timestamp_now=True
    )
    return embed.get()


def list_chunks(data: List[Any]) -> List[Any]:
    for i in range(0, len(data), 10):
        yield islice(data, i, i + 10)


def manual_await(coro: Coroutine) -> Any:
    """
    Await a coroutine, but don't raise an exception if it fails.
    """
    try:
        task = asyncio.create_task(coro)
        return asyncio.get_event_loop().run_until_complete(task)
    except Exception:
        return None


async def parse_query(itx: Interaction, player: DefaultPlayer, spotify: Spotify, query: str) -> List[QueueItem]:
    query_is_url = check_url(query)
    if query_is_url:
        if check_spotify_url(query):
            # Query is a Spotify URL.
            return await parse_spotify_query(itx, spotify, query)
        elif check_youtube_url(query):
            # Query is a YouTube URL.
            return await parse_youtube_query(itx, player, query)
        elif check_youtube_playlist_url(query):
            # Query is a YouTube playlist URL.
            return await parse_youtube_playlist(itx, player, query)
        elif check_sc_url(query):
            # Query is a SoundCloud URL.
            return await parse_sc_query(itx, player, query)
    
    try:
        if query_is_url:
            # Try to get track details directly from URL
            _, results = await get_tracks(player, query)
        else:
            # Play the first matching track on YouTube
            results = await get_youtube_matches(player, query, automatic=False)
        
        result: LavalinkResult = results[0]
    except IndexError:
        embed = create_error_embed(message=f'No results found for "`{query}`": `{e}`')
        await itx.followup.send(embed=embed)
        return []
    except Exception as e:
        embed = create_error_embed(message=f'Could not load track: `{e}`')
        await itx.followup.send(embed=embed)
        return []
    else:
        return [QueueItem(
            title=result.title,
            artist=result.author,
            requester=itx.user.id,
            duration=result.duration_ms,
            url=result.url,
            lavalink_track=result.lavalink_track
        )]


async def parse_sc_query(itx: Interaction, player: DefaultPlayer, query: str) -> List[QueueItem]:
    # Get entity type
    entity_type = get_sctype_from_url(query)

    try:
        # Get results with Lavalink
        set_name, tracks = await get_tracks(player, query)
    except:
        raise LavalinkInvalidIdentifierError(f'Entity {query} is private, nonexistent, or has no stream URL')
    else:
        if not entity_type:
            embed = CustomEmbed(
                color=Color.orange(),
                header=f'Enqueueing SoundCloud set',
                title=set_name,
                description=[
                    f'{len(tracks)} track(s)',
                    query
                ],
                footer='This might take a while, please wait...'
            )
            await itx.channel.send(embed=embed.get())

        return [QueueItem(
            requester=itx.user.id,
            title=track.title,
            artist=track.author,
            duration=track.duration_ms,
            url=track.url,
            lavalink_track=track.lavalink_track
        ) for track in tracks]


async def parse_spotify_query(itx: Interaction, spotify: Spotify, query: str) -> List[QueueItem]:
    # Generally for Spotify tracks, we pick the YouTube result with
    # the same artist and title, and the closest duration to the Spotify track.
    try:
        sp_type, sp_id = get_spinfo_from_url(query, valid_types=['track', 'album', 'playlist'])
    except SpotifyInvalidURLError:
        embed = CustomEmbed(
            color=Color.red(),
            title=':x:｜Can only play tracks, albums, and playlists from Spotify.'
        )
        await itx.followup.send(embed=embed.get())
        return []
    else:
        # Get artwork for Spotify album/playlist
        sp_art = ''
        if sp_type == 'album':
            sp_art = spotify.get_album_art(sp_id)
        elif sp_type == 'playlist':
            sp_art = spotify.get_playlist_cover(sp_id, default='')

    new_tracks = []
    track_queue: List['SpotifyTrack']
    if sp_type == 'track':
        # Get track details from Spotify
        track_queue = [spotify.get_track(sp_id)]
    else:
        # Get playlist or album tracks from Spotify
        list_name, list_author, track_queue = spotify.get_tracks(sp_type, sp_id)

    if len(track_queue) < 1:
        # No tracks.
        embed = CustomEmbed(
            color=Color.red(),
            title=':x:｜Playlist or album is empty.'
        )
        await itx.followup.send(embed=embed.get())
        return []

    # At least one track.
    # Send embed if the list is longer than 1 track.
    if len(track_queue) > 1:
        embed = CustomEmbed(
            color=Color.green(),
            header=f'Enqueued Spotify {sp_type}',
            title=list_name,
            description=[
                f'by **{list_author}**',
                f'{len(track_queue)} track(s)',
                f'https://open.spotify.com/{sp_type}/{sp_id}'
            ],
            thumbnail_url=sp_art
        )
        await itx.channel.send(embed=embed.get())

    for track in track_queue:
        new_tracks.append(QueueItem(
            requester=itx.user.id,
            title=track.title,
            artist=track.artist,
            spotify_id=track.spotify_id,
            duration=track.duration_ms,
            artwork=track.artwork,
            isrc=track.isrc
        ))
    
    return new_tracks


async def parse_youtube_playlist(itx: Interaction, player: DefaultPlayer, query: str) -> List[QueueItem]:
    try:
        # Get playlist tracks from YouTube
        playlist_id = get_ytlistid_from_url(query)
        playlist_name, tracks = await get_tracks(player, playlist_id)
    except:
        # No tracks.
        raise LavalinkInvalidIdentifierError(f'Playlist {playlist_id} is empty, private, or nonexistent')
    else:
        embed = CustomEmbed(
            color=Color.dark_red(),
            header=f'Enqueueing YouTube playlist',
            title=playlist_name,
            description=[
                f'{len(tracks)} track(s)',
                f'https://youtube.com/playlist?list={playlist_id}'
            ],
            footer='This might take a while, please wait...'
        )
        await itx.channel.send(embed=embed.get())

        return [QueueItem(
            requester=itx.user.id,
            title=track.title,
            artist=track.author,
            duration=track.duration_ms,
            url=track.url,
            lavalink_track=track.lavalink_track
        ) for track in tracks]


async def parse_youtube_query(itx: Interaction, player: DefaultPlayer, query: str) -> List[QueueItem]:
    # Is it a video?
    try:
        video_id = get_ytid_from_url(query)

        # It is a video!
        # Is it part of a playlist?
        if check_contains_ytlistid(query):
            # Extract the playlist ID from the URL
            playlist_id = get_ytlistid_from_url(query, force_extract=True)
            embed = CustomEmbed(
                color=Color.yellow(),
                title=':information_source:｜This YouTube video is part of a playlist',
                description=[
                    'To play the playlist, use the playlist URL instead:',
                    f'`/play https://youtube.com/playlist?list={playlist_id}`'
                ]
            )
            await itx.channel.send(embed=embed.get())

        # Let us get the video's details.
        _, video = await get_tracks(player, video_id)
        return [QueueItem(
            title=video[0].title,
            artist=video[0].author,
            requester=itx.user.id,
            duration=video[0].duration_ms,
            url=video[0].url,
            lavalink_track=video[0].lavalink_track
        )]
    except LavalinkInvalidIdentifierError:
        embed = CustomEmbed(
            color=Color.red(),
            title=':x:｜Error enqueueing YouTube video',
            description='The video has either been deleted, or made private, or never existed.'
        )
        await itx.followup.send(embed=embed.get())
        return []
    except:
        embed = CustomEmbed(
            color=Color.red(),
            title=':x:｜YouTube URL is invalid',
            description=f'Only YouTube video and playlist URLs are supported.'
        )
        await itx.followup.send(embed=embed.get())
        return []
