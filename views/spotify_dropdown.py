from nextcord import SelectOption
from nextcord.ui import Select, View
from typing import Dict, TYPE_CHECKING
if TYPE_CHECKING:
    from cogs.player import PlayerCog
    from nextcord import Interaction
    from utils.blanco import BlancoBot


class SpotifyDropdown(Select):
    def __init__(self, bot: 'BlancoBot', playlists: Dict[str, str], user_id: int):
        self._cog: 'PlayerCog' = bot.get_cog('PlayerCog') # type: ignore
        self._user_id = user_id
        
        options = [
            SelectOption(label=playlist_name, value=playlist_id)
            for playlist_id, playlist_name in playlists.items()
        ]
        super().__init__(
            placeholder='Select a playlist...',
            options=options,
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: 'Interaction'):
        # Ignore if the user isn't the one who invoked the command
        if not interaction.user or interaction.user.id != self._user_id:
            return
        
        # Edit message
        if interaction.message:
            await interaction.message.edit(
                content=':hourglass: Loading...',
                embed=None,
                view=None
            )
        
        # Call the `/play` command with the playlist URL
        playlist_url = f'https://open.spotify.com/playlist/{self.values[0]}'
        await self._cog.play(interaction, query=playlist_url)

        # Delete message
        if interaction.message:
            await interaction.message.delete()


class SpotifyDropdownView(View):
    def __init__(self, bot: 'BlancoBot', playlists: Dict[str, str], user_id: int):
        super().__init__(timeout=None)

        self.add_item(SpotifyDropdown(bot, playlists, user_id))