import abc
from enum import Enum
from typing import Any, Optional, ClassVar, Protocol, Type, TypeVar, Generic, Union
from collections.abc import AsyncIterator, AsyncIterable, Iterable

from dataclasses import dataclass, field
from sqlalchemy import select

from ..dynamic import Dynamic
from ..forms import *
from ..logging import *
from ..models import *
from ..util import *

from datetime import datetime
import pathlib
import logging
import os
import contextlib
import yarl
import aiohttp


__all__ = [
    'APIError',
    'RateLimitError',
    
    'FileDetails',
    'PostDetails',
    'SearchDetails',
    
    'PluginBase',
]

class APIError(Exception):
    pass


class RateLimitError(APIError):
    pass


@dataclass
class FileDetails:
    url: str
    order: int = 0
    filename: Optional[str] = None
    file_id: Optional[str] = None


@dataclass
class PostDetails:
    url: Optional[str] = None
    title: Optional[str] = None
    comment: Optional[str] = None
    metadata: Optional[str] = None
    post_time: Optional[datetime] = None
    tags: list[tuple[TagCategory, str]] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    files: list[FileDetails] = field(default_factory=list)
    
    is_favorite: bool = False
    is_hidden: bool = False
    is_removed: bool = False
    
    omit_post_id: bool = False


@dataclass
class SearchDetails:
    identifier: str
    hint: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    related_urls: Optional[list[str]] = field(default_factory=list)
    
    def to_json(self):
        d = Dynamic({
            'title': self.title,
            'description': self.description,
            'related_urls': self.related_urls,
        })
        return d.to_json()


class PluginBase:
    # reserved
    id: ClassVar[str]
    log: logging.Logger
    config: Any
    
    http: aiohttp.ClientSession
    
    # to be set by plugin developer
    source: ClassVar[str]
    
    @classmethod
    def config_form(cls) -> Optional[Form]:
        """
        Returns a form for the configuration of the values by the plugin.
        """
        
        return None
        
    @classmethod
    async def parse_url(cls, url: str) -> str | Dynamic | None:
        """
        Checks if an url can be downloaded by this plugin.
        
        Returns the remote id if the url corresponds to a single post,
        a Dynamic object that can be passed to search if the url
        corresponds to multiple posts, or None if this plugin can't
        download or create a search using this url.
        """
        
        return None
    
    async def setup(self) -> bool:
        """
        Tries to initialize a plugin from existing configuration or new configuration
        passed in `parameters`.
        
        If the plugin initializes successfully, this should return a tuple of
        True and the plugin object.
        Otherwise, it should return a tuple of False and a form for any missing values
        required (e.g.: oauth tokens).
        """
        
        return True
    
    @classmethod
    def search_form(cls) -> Optional[Form]:
        """
        Returns the form or a list of forms used for searches and subscriptions.
        (e.g.: user id, a search string, or advanced options available on the website)
        """

        return None
    
    @abc.abstractmethod
    async def download(self,
        post_id: str,
        post_data: Optional[Any] = None
    ) -> PostDetails:
        """
        Creates or updates a RemotePost entry along with all the associated Files,
        and downloads all files and thumbnails that aren't present yet.
        
        If remote_post is passed, its original_id will be used and it will be
        updated in place.
        
        If preview is set to True, then only the thumbnails are downloaded.
        
        Returns the downloaded RemotePost object.
        """
        pass
    
    async def probe_query(self, query: Dynamic) -> Optional[SearchDetails]:
        """
        Returns a SearchDetails object with extra details about the search that would
        be performed by this set of options (e.g.: user timeline).
        May return None if no specific information is found (e.g.: global searches).
        """
        
        return None
    
    @abc.abstractmethod
    def iterate_query(self, query: Dynamic, begin_at: Optional[int]=None) -> AsyncIterator[tuple[int, Union[str, None], Any]]:
        """
        Returns a SearchDetails object with extra details about the search that would
        be performed by this set of options (e.g.: user timeline).
        May return None if no specific information is found (e.g.: global searches).
        """
        pass

