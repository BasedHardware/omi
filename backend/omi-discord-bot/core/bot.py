from discord.ext import commands
import discord

#bot_configs = BotConfigs()

import logging
from rich.logging import RichHandler

logging.basicConfig(format='::: %(message)s', handlers=[RichHandler()])
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class OmiDiscordBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        description = '''Omi Discord bot '''
        super().__init__(command_prefix=commands.when_mentioned_or('$'), intents=intents, description=description)

    async def setup_hook(self) -> None:
        pass

    async def on_ready(self):
        logger.info(f'Logged in as {self.user}')
        logger.info('------')
        logger.info('------')