class EndOfQueueError(Exception):
    def __init__(self, reason):
        self.message = reason
        super().__init__(self.message)


class JockeyStartError(Exception):
    pass


class JockeyDeprecatedError(Exception):
    pass


class LavalinkInvalidIdentifierError(Exception):
    def __init__(self, url, reason=None):
        self.message = f'Error encountered while processing "{url}": `{reason}`'
        super().__init__(self.message)


class LavalinkSearchError(Exception):
    def __init__(self, query, reason=None):
        self.message = f'Could not search for "{query}" on YouTube. Reason: {reason}'
        super().__init__(self.message)


class SpotifyInvalidURLError(Exception):
    def __init__(self, url):
        self.message = "Invalid Spotify link or URI: {}".format(url)
        super().__init__(self.message)


class SpotifyNoResultsError(Exception):
    pass


class VoiceCommandError(Exception):
    def __init__(self, reason):
        self.message = reason
        super().__init__(self.message)
