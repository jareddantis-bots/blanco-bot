"""
Database migrations module for Blanco.
Handles automatic adjustment of the SQLite database schema
across updates of the bot.
"""

from importlib import import_module
from os import listdir, path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logging import Logger
    from sqlite3 import Connection


def run_migrations(logger: 'Logger', con: 'Connection'):
    """
    Run all migrations on Blanco's database.

    :param con: The Connection instance to the SQLite database.
    """
    for file in sorted(listdir(path.dirname(__file__))):
        if file != path.basename(__file__) and file.endswith('.py'):
            logger.info(f'Running migration: {file}')
            migration = import_module(f'database.migrations.{file[:-3]}')
            migration.run(con)
