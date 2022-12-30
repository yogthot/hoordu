import abc
from typing import Optional, ClassVar, Protocol, TypeVar, Generic
from collections.abc import AsyncIterator, AsyncIterable, Iterable

from .common import *
from ..dynamic import Dynamic
from ..forms import *
from ..logging import *
from ..models import *
from ..util import *

import pathlib
import logging
import os
import contextlib

P = TypeVar('P')


class APIError(Exception):
    pass

class SearchDetails:
    def __init__(self,
        hint: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        related_urls: Optional[set[str]] = None
    ):
        self.hint: Optional[str] = hint
        self.title: Optional[str] = title
        self.description: Optional[str] = description
        self.thumbnail_url: Optional[str] = thumbnail_url
        self.related_urls: set[str]
        if related_urls is not None:
            self.related_urls = set(related_urls)
        else:
            self.related_urls = set()


class IteratorBase(AsyncIterable[RemotePost], Generic[P]):
    def __init__(self,
        plugin: P,
        subscription: Optional[Subscription] = None,
        options: Optional[Dynamic] = None
    ):
        self.plugin: P = plugin
        self.session = plugin.session
        self.log = plugin.log
        self.subscription: Optional[Subscription] = subscription
        self.options: Dynamic
        self.state: Dynamic
        
        if self.subscription is not None:
            self.options = Dynamic.from_json(self.subscription.options)
            self.state = Dynamic.from_json(self.subscription.state)
        else:
            self.options = options
            self.state = Dynamic()

        self.direction: FetchDirection = FetchDirection.newer
        self.num_posts: int | None = None
    
    def __aiter__(self) -> AsyncIterator[RemotePost, None]:
        self.__iterator: AsyncIterator[RemotePost] = self.generator()
        return self
    
    async def __anext__(self) -> RemotePost:
        return await anext(self.__iterator)

    def __repr__(self):
        raise NotImplementedError
    
    async def init(self) -> None:
        """
        Override this method to implement any startup IO task related
        to this specific subscription that doesn't need to execute
        on every fetch call.
        """
        
        pass
    
    def reconfigure(self,
        direction: FetchDirection = FetchDirection.newer,
        num_posts: Optional[int] = None
    ) -> None:
        """
        Sets direction and tentative number of posts to iterate through
        at a time
        """
        
        self.direction = direction
        self.num_posts = num_posts
    
    @abc.abstractmethod
    def generator(self) -> AsyncIterator[RemotePost]:
        """
        Iterates through around `self.num_posts` newer or older posts from this
        search or subscription depending on the direction.
        This method may auto-commit by default.
        """
        ...

class IteratorConstructor(Protocol):
    def __call__(self,
        plugin: 'SimplePlugin',
        subscription: Optional[Subscription] = None,
        options: Optional[Dynamic] = None
    ) -> IteratorBase:
        ...


class PluginBase:
    id: ClassVar[str] = None # reserved
    
    name: ClassVar[str] = None
    version: ClassVar[int] = 0
    required_hoordu: ClassVar[str] = '0.0.0'
    
    @classmethod
    async def get_source(cls, session) -> Source:
        stream = await session.stream(
                select(Source) \
                    .where(Source.name == cls.name))
        row = await stream.one()
        return row.Source
    
    @classmethod
    async def get_plugin(cls, session) -> Plugin:
        stream = await session.stream(
                select(Plugin) \
                    .where(Plugin.name == cls.id))
        row = await stream.one()
        return row.Plugin
    
    @classmethod
    def config_form(cls) -> Optional[Form]:
        """
        Returns a form for the configuration of the values by the plugin.
        """
        
        return None
    
    @classmethod
    async def setup(cls,
        session,
        parameters: Optional[Dynamic] = None
    ) -> tuple[bool, Form | None]:
        """
        Tries to initialize a plugin from existing configuration or new configuration
        passed in `parameters`.
        
        If the plugin initializes successfully, this should return a tuple of
        True and the plugin object.
        Otherwise, it should return a tuple of False and a form for any missing values
        required (e.g.: oauth tokens).
        """
        
        return True, None
    
    @classmethod
    async def update(cls, session) -> None:
        """
        Updates the database objects related to this plugin/source, if needed.
        """
        
        pass
    
    def __init__(self, session):
        # TODO session type: need to fix imports
        self.session = session
        self.log = logging.getLogger(f'hoordu.{self.name}')
        
        self.source: Source
        self.plugin: Plugin
        self.config: Dynamic
    
    async def __aenter__(self):
         self.__context = self.context()
         return await self.__context.__aenter__()
    async def __aexit__(self, *args):
         return await self.__context.__aexit__(*args)
    
    @contextlib.asynccontextmanager
    async def context(self):
        try:
            self.source = await self.get_source(self.session)
            self.plugin = await self.get_plugin(self.session)
            self.config = Dynamic.from_json(self.plugin.config)
            yield self
        finally:
            pass

class SimplePlugin(PluginBase):
    iterator: Optional[IteratorConstructor] = None
    
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
    
    async def _get_tag(self, category: TagCategory, tagstr: str) -> RemoteTag | None:
        tag = await self.session.select(RemoteTag) \
                .where(
                    RemoteTag.source == self.source,
                    RemoteTag.category == category,
                    RemoteTag.tag == tagstr
                ).one_or_none()
        
        if tag is None:
            tag = RemoteTag(source=self.source, category=category, tag=tagstr)
            self.session.add(tag)
        
        return tag
    
    async def _get_post(self, original_id: str) -> RemotePost:
        post = await self.session.select(RemotePost) \
            .where(
                RemotePost.source == self.source,
                RemotePost.original_id == original_id
            ).one_or_none()
        
        if post is None:
            post = RemotePost(
                source=self.source,
                original_id=original_id
            )
            
            self.session.add(post)
            await self.session.flush()
        
        return post
    
    async def download(self,
        id: Optional[str] = None,
        remote_post: Optional[RemotePost] = None,
        preview: bool = False
    ) -> RemotePost:
        """
        Creates or updates a RemotePost entry along with all the associated Files,
        and downloads all files and thumbnails that aren't present yet.
        
        If remote_post is passed, its original_id will be used and it will be
        updated in place.
        
        If preview is set to True, then only the thumbnails are downloaded.
        
        Returns the downloaded RemotePost object.
        """
        
        raise NotImplementedError
    
    def search_form(self) -> Optional[Form]:
        """
        Returns the form or a list of forms used for searches and subscriptions.
        (e.g.: user id, a search string, or advanced options available on the website)
        """
        
        return None
    
    async def get_search_details(self, options: Dynamic) -> Optional[SearchDetails]:
        """
        Returns a SearchDetails object with extra details about the search that would
        be performed by this set of options (e.g.: user timeline).
        May return None if no specific information is found (e.g.: global searches).
        """
        
        return None
    
    async def search(self, options: Dynamic) -> IteratorBase:
        """
        Creates a temporary search for a given set of search options.
        
        Returns a post iterator object.
        """
        
        if self.iterator is None:
            raise NotImplementedError
        
        iterator = self.iterator(self, options=options)
        await iterator.init()
        iterator.reconfigure(direction=FetchDirection.older, num_posts=None)
        return iterator
    
    async def subscribe(self,
        name: str,
        options: Optional[Dynamic] = None,
        iterator: Optional[IteratorBase] = None
    ) -> IteratorBase:
        """
        Creates a Subscription entry for the given search options identified by the given name,
        should not get any posts from the post source.
        """
        
        if iterator is None:
            iterator = self.iterator(self, options=options)
        
        await iterator.init()
        
        sub = Subscription(
            source=self.source,
            plugin=self.plugin,
            name=name,
            repr=repr(iterator),
            options=iterator.options.to_json(),
            state=iterator.state.to_json()
        )
        
        self.session.add(sub)
        await self.session.flush()
        
        iterator.subscription = sub
        
        return iterator
    
    async def create_iterator(self,
        subscription: Subscription,
        direction: FetchDirection = FetchDirection.newer,
        num_posts: Optional[int] = None
    ) -> IteratorBase:
        """
        Gets the post iterator for a specific subscription.
        
        Returns a post iterator object.
        """
        
        if self.iterator is None:
            raise NotImplementedError
        
        iterator = self.iterator(self, subscription=subscription)
        await iterator.init()
        iterator.reconfigure(direction=direction, num_posts=num_posts)
        return iterator


class ReverseSearchEntry:
    def __init__(self, session, title: str, thumbnail_url: str, sources: Iterable[str]):
        self.session = session
        self.title = title
        self.thumbnail_url = thumbnail_url
        self.thumbnail_path = None
        self.sources = list(sources)
    
    async def _download(self) -> None:
        path, response = self.session.download(self.thumbnail_url)
        self.thumbnail_path = path
        self.session.callback(self._delete, on_commit=True, on_rollback=True)
    
    async def _delete(self, session, is_commit: bool) -> None:
        pathlib.Path(self.thumbnail_path).unlink()
        self.thumbnail_path = None

class ReverseSearchPlugin(PluginBase):
    async def _make_result(self, title: str, thumbnail_url: str, sources: Iterable[str]):
        result = ReverseSearchEntry(self.session, title, thumbnail_url, sources)
        await result._download()
        return result
    
    @abc.abstractmethod
    def reverse_search(self,
        path: Optional[str | os.PathLike] = None,
        url: Optional[str] = None
    ) -> AsyncIterator[ReverseSearchEntry]:
        """
        Returns an async generator of ReverseSearchEntry objects.
        """
        ...
    
