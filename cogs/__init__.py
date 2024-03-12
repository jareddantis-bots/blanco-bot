"""
Cogs extension for Blanco, which takes care of loading all the cogs
and therefore all of the commands.
"""

from typing import TYPE_CHECKING
from .debug import DebugCog
from .player import PlayerCog
from .bumps import BumpCog
if TYPE_CHECKING:
    from utils.blanco import BlancoBot


def setup(bot: 'BlancoBot'):
    """
    Setup function for the cogs extension.
    """
    # Add cogs
    bot.add_cog(DebugCog(bot))
    bot.add_cog(PlayerCog(bot))
    bot.add_cog(BumpCog(bot))
