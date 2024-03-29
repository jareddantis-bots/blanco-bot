"""
This file is used to run the webserver without running the bot,
along with spawning the TailwindCSS compiler. This is useful for
development, as it allows you to see changes to the webserver
without having to restart the bot.
"""

import asyncio
import threading
from subprocess import run

from database import Database
from server.main import run_app
from utils.config import config


def run_tailwind():
    """
    Run the TailwindCSS compiler.
    """
    run(
        ' '.join([
            'tailwindcss',
            '-i',
            './server/static/css/base.css',
            '-o',
            './server/static/css/main.css',
            '--watch'
        ]),
        check=False,
        shell=True
    )


if __name__ == '__main__':
    thread = threading.Thread(target=run_tailwind)
    thread.start()

    db = Database(config.db_file)
    loop = asyncio.get_event_loop()
    loop.create_task(run_app(db, config))
    loop.run_forever()
