from nextcord import Intents
from utils.config import config
from utils.blanco import BlancoBot
from utils.logger import create_logger


# Create bot instance
intents = Intents.default()
intents.members = True
client = BlancoBot(intents=intents)
client.init_config(config)


# Run client
if __name__ == '__main__':
    logger = create_logger('main')
    logger.info('Starting bot...')
    
    if not client.debug:
        client._bot_loop.start()
    client.run(config['bot']['discord_token'])
