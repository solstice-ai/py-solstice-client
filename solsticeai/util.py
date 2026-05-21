from datetime import datetime
from typing import Optional, Union

import pandas as pd


def parse_to_timestamp(timestamp: Optional[Union[int, float, datetime, pd.Timestamp]]) -> int:
    if isinstance(timestamp, (int, float)):
        return round(timestamp)

    if isinstance(timestamp, pd.Timestamp):
        if timestamp.tz is None:
            raise ValueError(f"Pandas timestamp '{timestamp}' was provided without timezone.")
        return round(timestamp.timestamp())

    if isinstance(timestamp, datetime):
        if timestamp.tzinfo is None:
            raise ValueError(f"Datetime '{timestamp}' was provided without timezone.")
        return round(timestamp.timestamp())

    raise ValueError(f"Invalid timestamp provided: '{timestamp}' (type: {type(timestamp)})")


def clean_url(url: str) -> str:
    # first remove any double //, then re-add the "//" after http or https
    return url.replace("//", "/").replace("http:/", "http://").replace("https:/", "https://")


class DebugObject:
    # extracted from github.com/ilfrich/python-basic-utils (pip: pbu)
    def __init__(self, debug=False, logger=None):
        self._debug = debug
        self._logger = logger

    def debug_log(self, *kwargs):
        if self._debug:
            if self._logger is not None:
                msg = " ".join([str(x) for x in kwargs])
                self._logger.info(msg)
            else:
                print(f"[{self.__class__.__name__}]", *kwargs)
