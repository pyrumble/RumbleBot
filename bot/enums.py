from enum import Enum

class SearchType(Enum):
    Track = "Track"
    Album = "Album"
    Playlist = "Playlist"
    Artist = "Artist (Top songs)"
    def __init__(self, *args, **kwargs):
        super().__init__()
        self._name_ = self._value_

class RotationSpeed(Enum):
    Low = 1
    Medium = 2
    High = 3

class SourceEmoji(Enum):
    SPOTIFY = "<:spotify:1287932350981865535>"
    DEEZER = "<:deezer:1305533450811478099>"
    SOUNDCLOUD = "<:soundcloud:1287932414060003388>"
    APPLEMUSIC = "<:applemusic:1289428488478003211>"
    YOUTUBE = "<:youtube:1370532640020496434>"
    HTTP = "<:rumblebot:1358562728402358543>"

__all__ = [
    "SearchType",
    "SourceEmoji",
    "RotationSpeed",
]
