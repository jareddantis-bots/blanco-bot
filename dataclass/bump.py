"""
Dataclass for guild bumps.
"""
from dataclasses import dataclass


@dataclass
class Bump:
    """
    Dataclass for guild bumps.
    """

    idx: int
    guild_id: int
    url: str
    title: str
    author: str
