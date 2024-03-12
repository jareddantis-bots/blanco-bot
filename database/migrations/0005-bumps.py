"""
Create tables for guild bumps and alter player_settings where needed.
"""

# pylint: disable=invalid-name

from sqlite3 import OperationalError
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlite3 import Connection


def run(con: 'Connection'):
    """
    Run the migration.
    """
    cur = con.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS bumps (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            idx INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            url TEXT NOT NULL,

            UNIQUE(guild_id, idx)
        )
    ''')

    con.commit()

    try:
        cur.execute('''
            ALTER TABLE player_settings ADD COLUMN bump_interval INTEGER NOT NULL DEFAULT 20
        ''')

        con.commit()
    except OperationalError:
        pass

    try:
        cur.execute('''
            ALTER TABLE player_settings ADD COLUMN last_bump INTEGER NOT NULL DEFAULT 0
        ''')

        con.commit()
    except OperationalError:
        pass

    try:
        cur.execute('''
            ALTER TABLE player_settings ADD COLUMN bumps_enabled INTEGER NOT NULL DEFAULT 0
        ''')

        con.commit()
    except OperationalError:
        pass
