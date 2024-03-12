"""
BumpCog: Cog for guild bumps.
"""

from typing import TYPE_CHECKING

from nextcord import (Color, Permissions, Interaction, SlashOption, slash_command)
from nextcord.ext.commands import Cog

from dataclass.bump import Bump

from utils.url import check_url
from utils.embeds import CustomEmbed, create_error_embed, create_success_embed
from utils.logger import create_logger
from utils.paginator import Paginator, list_chunks

if TYPE_CHECKING:
    from utils.blanco import BlancoBot


class BumpCog(Cog):
    """
    Cog for guild bumps.
    """
    def __init__(self, bot: 'BlancoBot'):
        """
        Constructor for BumpCog.
        """
        self._bot = bot
        self._logger = create_logger(self.__class__.__name__)
        self._logger.info('Loaded BumpCog')

    @slash_command(
            name='bump',
            dm_permission=False,
            default_member_permissions=Permissions(manage_guild=True)
    )
    async def bump(self, itx: Interaction):
        """
        Base slash command for bumps.
        """


    @bump.subcommand(name='toggle', description='Toggle the playback of bumps.')
    async def bump_toggle(
        self,
        itx: Interaction,
        toggle: bool = SlashOption(
            name='toggle',
            description='Turn bumps on or off?',
            required=False
        )
    ):
        """
        Subcommand for toggling bumps.
        """
        if itx.guild is None:
            raise RuntimeError('[bump::toggle] itx.guild is None')

        if toggle is None:
            enabled = self._bot.database.get_bumps_enabled(itx.guild.id)
            status = "Bump playback is currently enabled." if enabled \
                else "Bump playback is currently disabled."
            return await itx.response.send_message(
                embed=create_success_embed(
                    title="Bumps status",
                    body=status,
                )
            )

        self._bot.database.set_bumps_enabled(itx.guild.id, toggle)
        status = "Bump playback has been enabled." if toggle \
            else "Bump playback has been disabled."
        return await itx.response.send_message(
            embed=create_success_embed(
                title="Bumps toggled",
                body=status,
            )
        )

    @bump.subcommand(name='add', description='Add a bump.')
    async def bump_add(
        self,
        itx: Interaction,
        title: str = SlashOption(name='title', description='Title of bump.', required=True),
        author: str = SlashOption(name='author', description='Author of bump.', required=True),
        url: str = SlashOption(name='url', description='URL to add.', required=True),
    ):
        """
        Subcommand for adding a bump.
        """
        if itx.guild is None:
            raise RuntimeError('[bump::add] itx.guild is None')

        if len(title) > 32 or len(author) > 32:
            return await itx.response.send_message(
                embed=create_error_embed(
                    message='Titles/authors cannot exceed 32 characters in length.'
                )
            )

        if not check_url(url):
            return await itx.response.send_message(
                embed=create_error_embed(
                    message='The given URL is not valid.'
                )
            )

        bump = self._bot.database.get_bump_by_url(itx.guild.id, url)
        if bump is not None:
            return await itx.response.send_message(
                embed=create_error_embed(
                    message='A bump with the given URL already exists.'
                )
            )

        self._bot.database.set_bump(itx.guild.id, url, title, author)
        return await itx.response.send_message(
            embed=create_success_embed(
                title='Bump added',
                body='Bump has been successfully added to the database.'
            )
        )

    @bump.subcommand(name='remove', description='Remove a bump.')
    async def bump_remove(
        self,
        itx: Interaction,
        idx: int = SlashOption(name='index', description='Index of bump.', required=True)
    ):
        """
        Subcommand for removing a bump.
        """
        if itx.guild is None:
            raise RuntimeError('[bump::remove] itx.guild is None')

        bump = self._bot.database.get_bump(itx.guild.id, idx)
        if bump is None:
            return await itx.response.send_message(
                embed=create_error_embed(
                    message='There is no bump at that index for this guild.'
                )
            )

        self._bot.database.delete_bump(itx.guild.id, idx)
        return await itx.response.send_message(
            embed=create_success_embed(
                title='Bump removed',
                body='Bump has successfully been removed from the database.'
            )
        )

    @bump.subcommand(name='list', description='List every bump.')
    async def bump_list(
        self,
        itx: Interaction,
    ):
        """
        Subcommand for listing bumps.
        """
        if itx.guild is None:
            raise RuntimeError('[bump::list] itx.guild is None')
        await itx.response.defer()

        bumps = self._bot.database.get_bumps(itx.guild.id)
        if bumps is None:
            return await itx.response.send_message(
                embed=create_error_embed(
                    message='This guild has no bumps.'
                )
            )

        pages = []
        count = 1
        for _, chunk in enumerate(list_chunks(bumps)):
            chunk_bumps = []

            bump: Bump
            for bump in chunk:
                line = f'{bump.idx} :: [{bump.title}]({bump.url}) by {bump.author}'
                chunk_bumps.append(line)
                count += 1

            embed = CustomEmbed(
                title=f'Bumps for {itx.guild.name}',
                description='\n'.join(chunk_bumps),
                color=Color.lighter_gray()
            )
            pages.append(embed.get())

        paginator = Paginator(itx)
        return await paginator.run(pages)

    @bump.subcommand(name='interval', description='Set or get the bump interval.')
    async def bump_interval(
        self,
        itx: Interaction,
        interval: int = SlashOption(
            name='interval',
            description='The new interval bumps will play at',
            required=False,
            min_value=1,
            max_value=60
        )
    ):
        """
        Subcommand for changing/checking the bump interval.
        """

        if itx.guild is None:
            raise RuntimeError('[bump::interval] itx.guild is None')

        if interval is None:
            curr_interval = self._bot.database.get_bump_interval(itx.guild.id)
            return await itx.response.send_message(
                embed=create_success_embed(
                    title='Current Interval',
                    body=f'A bump will play once at least every {curr_interval} minute(s).'
                )
            )

        self._bot.database.set_bump_interval(itx.guild.id, interval)
        return await itx.response.send_message(
            embed=create_success_embed(
                title='Interval Changed',
                body=f'The bump interval has been set to {interval} minute(s).'
            )
        )
