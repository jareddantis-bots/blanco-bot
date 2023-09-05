from dataclass.oauth import OAuth
from typing import List, Optional
from utils.logger import create_logger
from .migrations import run_migrations
import sqlite3 as sql


class Database:
    """
    Class for handling connections to the bot's SQLite DB.
    """

    def __init__(self, db_filename: str):
        self._con = sql.connect(db_filename)
        self._cur = self._con.cursor()
        self._logger = create_logger(self.__class__.__name__)
        self._logger.info(f'Connected to database: {db_filename}')

        # Run migrations
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
        self._cur.execute(f'UPDATE player_settings SET volume = {volume} WHERE guild_id = {guild_id}')
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
        self._cur.execute(f'UPDATE player_settings SET loop = {int(loop)} WHERE guild_id = {guild_id}')
        self._con.commit()
    
    def get_now_playing(self, guild_id: int) -> int:
        """
        Get the last now playing message ID for a guild.
        """
        self._cur.execute(f'SELECT last_np_msg FROM player_settings WHERE guild_id = {guild_id}')
        return self._cur.fetchone()[0]
    
    def set_now_playing(self, guild_id: int, msg_id: int):
        """
        Set the last now playing message ID for a guild.
        """
        self._cur.execute(f'UPDATE player_settings SET last_np_msg = {msg_id} WHERE guild_id = {guild_id}')
        self._con.commit()
    
    def get_status_channel(self, guild_id: int) -> int:
        """
        Get the status channel for a guild.
        """
        self._cur.execute(f'SELECT status_channel FROM player_settings WHERE guild_id = {guild_id}')
        return self._cur.fetchone()[0]
    
    def set_status_channel(self, guild_id: int, channel_id: int):
        """
        Set the status channel for a guild.
        """
        self._cur.execute(f'UPDATE player_settings SET status_channel = {channel_id} WHERE guild_id = {guild_id}')
        self._con.commit()
    
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
        self._cur.execute(f'INSERT OR REPLACE INTO lavalink (node_id, session_id) VALUES ("{node_id}", "{session_id}")')
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
        return OAuth(*row)
    
    def set_spotify_scopes(self, user_id: int, scopes: List[str]):
        """
        Set the Spotify scopes for a user.
        """
        self._cur.execute(f'UPDATE spotify_oauth SET scopes = "{",".join(scopes)}" WHERE user_id = {user_id}')
        self._con.commit()

    def get_spotify_scopes(self, user_id: int) -> List[str]:
        """
        Get the Spotify scopes for a user.
        """
        self._cur.execute(f'SELECT scopes FROM spotify_oauth WHERE user_id = {user_id}')
        return self._cur.fetchone()[0].split(',')
