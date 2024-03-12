"""
Paginator class for sending embeds with controls to change pages.

Based on https://github.com/toxicrecker/DiscordUtils/blob/master/DiscordUtils/Pagination.py
but with support for custom home page and adapted for Interaction responses.
"""

from asyncio import sleep
from itertools import islice
from typing import TYPE_CHECKING, Callable, List, Optional, Any, Generator

from nextcord import Embed, Forbidden, HTTPException, Interaction

from views.paginator import PaginatorView

if TYPE_CHECKING:
    from nextcord import Message


def list_chunks(data: List[Any]) -> Generator[List[Any], Any, Any]:
    """
    Yield 10-element chunks of a list. Used for pagination.
    """
    for i in range(0, len(data), 10):
        yield list(islice(data, i, i + 10))


class Paginator:
    """
    Paginator class for sending embeds with controls to change pages.
    """
    def __init__(self, itx: Interaction):
        self.current = 0
        self.embeds = []
        self.home = 0
        self.itx = itx
        self.msg: Optional['Message'] = None
        self.original_timeout = 0
        self.timeout = 0

    async def run(
        self,
        embeds: List[Embed],
        start: int = 0,
        timeout: int = 0,
        callback: Optional[Callable[[int], None]] = None
    ):
        """
        Sends the given embeds and adds controls to change pages if there's more than one.
        """
        # If there's only one page, just send it as is
        if len(embeds) == 1:
            msg = await self.itx.followup.send(embed=embeds[0], wait=True)
            if callback is not None:
                callback(msg.id)
            return

        timeout = timeout if timeout > 0 else 60
        self.original_timeout = timeout
        self.timeout = timeout

        # Add footer and timestamp to every embed
        for i, embed in enumerate(embeds):
            embed.timestamp = self.itx.created_at
            embed.set_footer(text=f'Page {i + 1} of {len(embeds)}')

        # Send initial embed and call callback with message ID
        self.home = start
        self.current = start
        self.embeds = embeds
        msg = await self.itx.followup.send(
            embed=self.embeds[start],
            view=PaginatorView(self),
            wait=True
        )
        self.msg = await msg.channel.fetch_message(msg.id)
        if callback is not None:
            callback(msg.id)

        # Remove controls if inactive for more than timeout amount
        while True:
            await sleep(1)
            self.timeout -= 1
            if self.timeout <= 0:
                return await self.msg.edit(view=None)

    async def _switch_page(self, new_page: int) -> Optional['Message']:
        self.current = new_page
        if self.msg is not None:
            try:
                msg = await self.msg.edit(embed=self.embeds[self.current])
            except (Forbidden, HTTPException):
                return None

            self.timeout = self.original_timeout
            return msg

    async def first_page(self):
        """
        Switches to the first page.
        """
        await self._switch_page(0)

    async def previous_page(self):
        """
        Switches to the previous page.
        """
        await self._switch_page(self.current - 1)

    async def home_page(self):
        """
        Switches to the home page, which is the first page by default,
        but can be changed with the `start` parameter in `Paginator.run()`.
        """
        await self._switch_page(self.home)

    async def next_page(self):
        """
        Switches to the next page.
        """
        await self._switch_page(self.current + 1)

    async def last_page(self):
        """
        Switches to the last page.
        """
        await self._switch_page(len(self.embeds) - 1)
