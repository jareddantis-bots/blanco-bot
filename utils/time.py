"""
Utility methods for converting between human and machine readable time formats.
"""

from math import floor
from typing import Tuple, Union


def get_time_components(msec: Union[int, float]) -> Tuple[int, int, int]:
    """
    Decompose milliseconds into a tuple of hours, minutes, and seconds.
    """
    minute, sec = divmod(msec / 1000, 60)
    hour, minute = divmod(minute, 60)
    return floor(hour), floor(minute), floor(sec)


def human_readable_time(msec: Union[int, float]) -> str:
    """
    Turn milliseconds into a human readable time string.
    """
    hour, minute, sec = get_time_components(msec)
    string = ''
    if hour > 0:
        string += f'{hour} hr'
    if minute > 0:
        string += f' {minute} min'
    if sec > 0:
        string += f' {sec} sec'

    return string.strip()


def machine_readable_time(colon_delimited_time: str) -> int:
    """
    Parse colon delimited time (e.g. "1:30:00") into milliseconds.
    """
    time_segments = colon_delimited_time.split(':')
    sec = int(time_segments[-1])
    minute = int(time_segments[-2])
    hour = int(time_segments[0]) if len(time_segments) == 3 else 0
    return hour * 3600000 + minute * 60000 + sec * 1000
