import abc
from enum import Enum
from typing import Any, Optional, ClassVar, Protocol, Type, TypeVar, Generic, Union
from collections.abc import AsyncGenerator, AsyncIterable, Iterable

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
    'TagDetails',
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
    order: Optional[int] = None
    filename: Optional[str] = None
    identifier: Optional[str] = None
    metadata: Optional[str] = None


@dataclass
class TagDetails:
    category: TagCategory
    tag: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PostDetails:
    type: Optional[PostType] = None
    url: Optional[str] = None
    title: Optional[str] = None
    comment: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    post_time: Optional[datetime] = None
    tags: list[TagDetails] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    files: list[FileDetails] = field(default_factory=list)
    
    is_favorite: bool = False
    is_hidden: bool = False
    is_removed: bool = False
    
    # hack until I find a better way to do this
    _omit_id: bool = False


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
        The plugin can only be instantiated if the form validates.
        """
        
        return None
    
    @classmethod
    def search_form(cls) -> Optional[Form]:
        """
        Returns the form or a list of forms used for searches and subscriptions.
        (e.g.: user id, a search string, advanced options available on the backend)
        """

        return None
    
    # TODO generalize this with some kinda pattern matching? or a dictionary at the class level?
    @classmethod
    async def parse_url(cls, url: str) -> str | Dynamic | None:
        """
        Checks if an url can be downloaded by this plugin.
        
        Returns the remote id if the url corresponds to a single post,
        a Dynamic object that can be passed to search if the url
        corresponds to multiple posts, or None otherwise.
        """
        
        return None
    
    async def setup(self) -> None:
        """
        Called right after everything is ready to use but before any other method is called.
        Use this to add headers or cookies to the http client, or do any other initial setup.
        """
        pass
    
    @abc.abstractmethod
    async def download(self,
        post_id: str,
        post_data: Optional[Any] = None
    ) -> PostDetails:
        """
        Fetches a PostDetails object from the backend.
        
        post_data contains any data that may have been yielded during
        the iteration of a query, but is unused for direct downloads.
        """
        pass
    
    async def probe_query(self, query: Dynamic) -> Optional[SearchDetails]:
        """
        Returns a SearchDetails object with extra details about the search that would
        be performed by this query.
        It's advisable to implement this even it only to return the identifier and hint,
        so creating subscriptions can be automated.
        """
        
        return None
    
    @abc.abstractmethod
    def iterate_query(self, query: Dynamic, state: dict[str, Any], begin_at: Optional[int]=None) -> AsyncGenerator[tuple[int, Union[str, None], Any]]:
        """
        Iterates a given query.
        begin_at will be set to the last returned sort index when attempting to load more
        posts from the end of the query.
        If begin_at is None, the iteration should start at the beginning.
        `yield` throws GeneratorExit when the iteration should stop.
        
        The yielded tuple should be:
        - sort index: a number to help sort posts in a timeline (newer posts should be higher than old posts)
        - post id: identifier that will be passed to the download method (can be None to update the sort index)
        - post data: will be passed as is to the download method when downloading this post
        """
        pass

