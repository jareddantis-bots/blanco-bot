"""
Database module for Blanco. Interfaces with the bot's SQLite database.
"""

import sqlite3 as sql
from typing import List, Optional
import time

from dataclass.oauth import LastfmAuth, OAuth
from dataclass.bump import Bump
from utils.logger import create_logger

from .migrations import run_migrations


class Database:
    """
    Class for handling connections to the bot's SQLite DB.
    """

    def __init__(self, db_filename: str):
        self._con = sql.connect(db_filename, check_same_thread=False)
        self._cur = self._con.cursor()
        self._logger = create_logger(self.__class__.__name__)

        # Run migrations
        self._logger.info('Connected to database %s, running migrations...', db_filename)
        run_migrations(self._logger, self._con)

    def init_guild(self, guild_id: int):
        """
        Initialize a guild in the database if it hasn't been yet.
        """
        self._cur.execute(f'INSERT OR IGNORE INTO player_settings (guild_id) VALUES ({guild_id})')
        self._con.commit()

    def get_volume(self, guild_id: int) -> int:
        """
        Get the volume for a guild.
        """
        self._cur.execute(f'SELECT volume FROM player_settings WHERE guild_id = {guild_id}')
        return self._cur.fetchone()[0]

    def set_volume(self, guild_id: int, volume: int):
        """
        Set the volume for a guild.
        """
        self._cur.execute(
            f'UPDATE player_settings SET volume = {volume} WHERE guild_id = {guild_id}'
        )
        self._con.commit()

    def get_loop(self, guild_id: int) -> bool:
        """
        Get the loop setting for a guild.
        """
        self._cur.execute(f'SELECT loop FROM player_settings WHERE guild_id = {guild_id}')
        return self._cur.fetchone()[0] == 1

    def set_loop(self, guild_id: int, loop: bool):
        """
        Set the loop setting for a guild.
        """
        self._cur.execute(
            f'UPDATE player_settings SET loop = {int(loop)} WHERE guild_id = {guild_id}'
        )
        self._con.commit()

    def get_loop_all(self, guild_id: int) -> bool:
        """
        Get the whole-queue loop setting for a guild.
        """
        self._cur.execute(f'SELECT loop_all FROM player_settings WHERE guild_id = {guild_id}')
        return self._cur.fetchone()[0] == 1

    def set_loop_all(self, guild_id: int, loop: bool):
        """
        Set the whole-queue loop setting for a guild.
        """
        self._cur.execute(
            f'UPDATE player_settings SET loop_all = {int(loop)} WHERE guild_id = {guild_id}'
        )
        self._con.commit()

    def get_now_playing(self, guild_id: int) -> int:
        """
        Get the last now playing message ID for a guild.
        """
        self._cur.execute(
            f'SELECT last_np_msg FROM player_settings WHERE guild_id = {guild_id}'
        )
        return self._cur.fetchone()[0]

    def set_now_playing(self, guild_id: int, msg_id: int):
        """
        Set the last now playing message ID for a guild.
        """
        self._cur.execute(
            f'UPDATE player_settings SET last_np_msg = {msg_id} WHERE guild_id = {guild_id}'
        )
        self._con.commit()

    def get_status_channel(self, guild_id: int) -> int:
        """
        Get the status channel for a guild.
        """
        self._cur.execute(
            f'SELECT status_channel FROM player_settings WHERE guild_id = {guild_id}'
        )
        return self._cur.fetchone()[0]

    def set_status_channel(self, guild_id: int, channel_id: int):
        """
        Set the status channel for a guild.
        """
        self._cur.execute(
            f'UPDATE player_settings SET status_channel = {channel_id} WHERE guild_id = {guild_id}'
        )
        self._con.commit()

    def set_last_bump(self, guild_id: int):
        """
        Set the last bump for a guild.
        """
        seconds = int(time.time())
        self._cur.execute(
            f'UPDATE player_settings SET last_bump = {seconds} WHERE guild_id = {guild_id}'
        )
        self._con.commit()

    def get_last_bump(self, guild_id: int) -> int:
        """
        Get the last bump for a guild.
        """
        self._cur.execute(f'SELECT last_bump FROM player_settings WHERE guild_id = {guild_id}')
        return self._cur.fetchone()[0]

    def set_bumps_enabled(self, guild_id: int, enabled: bool):
        """
        Set whether bumps are enabled for a guild.
        """
        self._cur.execute(
            f'UPDATE player_settings SET bumps_enabled = {int(enabled)} WHERE guild_id = {guild_id}'
        )
        self._con.commit()

    def get_bumps_enabled(self, guild_id: int) -> bool:
        """
        Get whether bumps are enabled for a guild.
        """
        self._cur.execute(
            f'SELECT bumps_enabled FROM player_settings WHERE guild_id = {guild_id}'
        )
        return self._cur.fetchone()[0] == 1

    def set_bump_interval(self, guild_id: int, interval: int):
        """
        Set the bump interval for a guild.
        """
        self._cur.execute(
            f'UPDATE player_settings SET bump_interval = {interval} WHERE guild_id = {guild_id}'
        )
        self._con.commit()

    def get_bump_interval(self, guild_id: int) -> int:
        """
        Get the bump interval for a guild.
        """
        self._cur.execute(
            f'SELECT bump_interval FROM player_settings WHERE guild_id = {guild_id}'
        )
        return self._cur.fetchone()[0]

    def get_session_id(self, node_id: str) -> str:
        """
        Get the session ID for a Lavalink node.
        """
        self._cur.execute(f'SELECT session_id FROM lavalink WHERE node_id = "{node_id}"')
        return self._cur.fetchone()[0]

    def set_session_id(self, node_id: str, session_id: str):
        """
        Set the session ID for a Lavalink node.
        """
        self._cur.execute(
            f'''INSERT OR REPLACE INTO lavalink (
                node_id,
                session_id
            ) VALUES ("{node_id}", "{session_id}")'''
        )
        self._con.commit()

    def set_oauth(self, provider: str, credentials: OAuth):
        """
        Save OAuth2 data for a user.

        :param provider: The provider to save the data for. Can be either 'discord' or 'spotify'.
        :param credentials: The OAuth2 credentials to save.
        """
        self._cur.execute(f'''
            INSERT OR REPLACE INTO {provider}_oauth (
                user_id,
                username,
                access_token,
                refresh_token,
                expires_at
            ) VALUES (
                {credentials.user_id},
                "{credentials.username}",
                "{credentials.access_token}",
                "{credentials.refresh_token}",
                {credentials.expires_at}
            )
        ''')
        self._con.commit()

    def get_oauth(self, provider: str, user_id: int) -> Optional[OAuth]:
        """
        Get OAuth2 data for a user from the database.

        :param provider: The provider to get credentials for. Can be either 'discord' or 'spotify'.
        :param user_id: The user ID to get credentials for
        """
        self._cur.execute(f'SELECT * FROM {provider}_oauth WHERE user_id = {user_id}')
        row = self._cur.fetchone()
        if row is None:
            return None
        return OAuth(
            user_id=row[0],
            username=row[1],
            access_token=row[2],
            refresh_token=row[3],
            expires_at=row[4]
        )

    def set_lastfm_credentials(self, credentials: LastfmAuth):
        """
        Save Last.fm credentials for a user.
        """
        self._cur.execute(f'''
            INSERT OR REPLACE INTO lastfm_oauth (
                user_id,
                username,
                session_key
            ) VALUES (
                {credentials.user_id},
                "{credentials.username}",
                "{credentials.session_key}"
            )
        ''')
        self._con.commit()

    def get_lastfm_credentials(self, user_id: int) -> Optional[LastfmAuth]:
        """
        Get Last.fm credentials for a user.
        """
        self._cur.execute(
            f'SELECT * FROM lastfm_oauth WHERE user_id = {user_id}'
        )
        row = self._cur.fetchone()
        if row is None:
            return None
        return LastfmAuth(*row)

    def delete_oauth(self, provider: str, user_id: int):
        """
        Delete OAuth2 data for a user from the database.
        """
        self._cur.execute(f'DELETE FROM {provider}_oauth WHERE user_id = {user_id}')
        self._con.commit()

    def set_spotify_scopes(self, user_id: int, scopes: List[str]):
        """
        Set the Spotify scopes for a user.
        """
        self._cur.execute(f'''
            UPDATE spotify_oauth SET scopes = "{",".join(scopes)}" WHERE user_id = {user_id}
        ''')
        self._con.commit()

    def get_spotify_scopes(self, user_id: int) -> List[str]:
        """
        Get the Spotify scopes for a user.
        """
        self._cur.execute(f'SELECT scopes FROM spotify_oauth WHERE user_id = {user_id}')
        return self._cur.fetchone()[0].split(',')

    def set_bump(self, guild_id: int, url: str, title: str, author: str):
        """
        Set a bump for a guild.
        """
        self._cur.execute(f'SELECT MAX(idx) FROM bumps WHERE guild_id = {guild_id}')
        idx = self._cur.fetchone()[0]
        if idx is None:
            idx = 0
        idx += 1
        self._cur.execute(f'''
            INSERT INTO bumps (
                guild_id,
                idx,
                url,
                title,
                author
            ) VALUES (
                {guild_id},
                {idx},
                "{url}",
                "{title}",
                "{author}"
            )
            '''
        )
        self._con.commit()

    def get_bumps(self, guild_id: int) -> Optional[List[Bump]]:
        """
        Get every bump for a guild.
        """
        self._cur.execute(f'''SELECT idx, guild_id, url, title, author
            FROM bumps WHERE guild_id = {guild_id}''')
        rows = self._cur.fetchall()
        if len(rows) == 0:
            return None

        return [
            Bump(
                idx=row[0],
                guild_id=row[1],
                url=row[2],
                title=row[3],
                author=row[4]
            )
            for row in rows
        ]

    def get_bump(self, guild_id: int, idx: int) -> Optional[Bump]:
        """
        Get a guild bump by its index.
        """
        self._cur.execute(
            f'''SELECT idx, guild_id, url, title, author FROM bumps 
            WHERE guild_id = {guild_id} AND idx = {idx}
            '''
        )
        row = self._cur.fetchone()
        if row is None:
            return None
        return Bump(
            idx=row[0],
            guild_id=row[1],
            url=row[2],
            title=row[3],
            author=row[4]
        )

    def get_bump_by_url(self, guild_id: int, url: str) -> Optional[Bump]:
        """
        Get a guild bump by its URL.
        """
        self._cur.execute(
            f'''SELECT idx, guild_id, url, title, author FROM bumps
            WHERE guild_id = {guild_id} AND url = "{url}"
            '''
        )
        row = self._cur.fetchone()
        if row is None:
            return None
        return Bump(
            idx=row[0],
            guild_id=row[1],
            url=row[2],
            title=row[3],
            author=row[4]
        )

    def get_random_bump(self, guild_id: int) -> Optional[Bump]:
        """
        Get a random guild bump.
        """
        self._cur.execute(
            f'''SELECT idx, guild_id, url, title, author FROM bumps WHERE
            guild_id = {guild_id} ORDER BY RANDOM() LIMIT 1
            '''
        )
        row = self._cur.fetchone()
        if row is None:
            return None
        return Bump(
            idx=row[0],
            guild_id=row[1],
            url=row[2],
            title=row[3],
            author=row[4]
        )

    def delete_bump(self, guild_id: int, idx: int):
        """
        Delete a guild bump by its index.
        """
        self._cur.execute(f'DELETE FROM bumps WHERE guild_id = {guild_id} AND idx = {idx}')
        self._con.commit()
