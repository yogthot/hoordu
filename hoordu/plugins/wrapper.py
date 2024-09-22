import abc
from enum import Enum
from typing import Any, Optional, ClassVar, Protocol, Type, TypeVar, Generic
from collections.abc import AsyncIterator, AsyncIterable, Iterable

from sqlalchemy import select

from hoordu.http.download import save_response

from ..dynamic import Dynamic
from ..forms import *
from ..logging import *
from ..models import *
from ..util import *
from .base import *

from datetime import datetime, timezone
import pathlib
import logging
import os
import contextlib
import yarl
import aiohttp

__all__ = [
    'PluginWrapper'
]


class PluginWrapper:
    def __init__(self,
        session,
        plugin_class: Type[PluginBase]
    ):
        self.session = session
        self.plugin_class: Type[PluginBase] = plugin_class
        self.log: logging.Logger = logging.getLogger(f'hoordu.{self.plugin_class.source}')
        
        self.source: Source
        self.plugin: Plugin
        self.instance: PluginBase
        self.http: aiohttp.ClientSession
    
    async def get_source(self, session) -> Source:
        stream = await session.stream(
                select(Source) \
                    .where(Source.name == self.plugin_class.source))
        row = await stream.one()
        return row.Source
    
    async def get_plugin(self, session) -> Plugin:
        stream = await session.stream(
                select(Plugin) \
                    .where(Plugin.name == self.plugin_class.id))
        row = await stream.one()
        return row.Plugin
    
    async def _get_post(self, original_id: Optional[str]) -> tuple[bool, RemotePost]:
        post = None
        
        if original_id is not None:
            post = await self.session.select(RemotePost) \
                .where(
                    RemotePost.source == self.source,
                    RemotePost.original_id == original_id
                ).one_or_none()
        
        if post is not None:
            return True, post
            
        else:
            post = RemotePost(
                source=self.source,
                original_id=original_id
            )
            
            self.session.add(post)
            await self.session.flush()
            
            return False, post
    
    async def _get_tag(self, category: TagCategory, tagstr: str) -> RemoteTag:
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
    
    async def __aenter__(self):
         self.__context = self.context()
         return await self.__context.__aenter__()
    async def __aexit__(self, *args):
         return await self.__context.__aexit__(*args)
    
    @contextlib.asynccontextmanager
    async def context(self):
        self.source = await self.get_source(self.session)
        self.plugin = await self.get_plugin(self.session)
        self.config = Dynamic.from_json(self.source.config)
        
        self.http = aiohttp.ClientSession()
        self.instance = self.plugin_class()
        self.instance.log = self.log
        self.instance.config = Dynamic.from_json(self.plugin.config)
        
        async with self.http:
            self.instance.http = self.http
            await self.instance.setup()
            yield self
    
    async def _convert_post(self,
        remote_post: RemotePost,
        post_details: PostDetails
    ) -> RemotePost:
        
        if post_details._omit_id:
            remote_post.original_id = None
        
        self.log.info(f'getting post from: {post_details.url}')
        self.log.info(f'creating post: {self.source.name}:{remote_post.original_id}')
        self.log.info(f'local id: {remote_post.id}')
        
        remote_post.url = post_details.url
        remote_post.comment = post_details.comment
        remote_post.type = post_details.type or PostType.set
        remote_post.post_time = post_details.post_time
        remote_post.metadata_ = post_details.metadata
        
        for category, tag in post_details.tags:
            tag = await self._get_tag(category, tag)
            await remote_post.add_tag(tag)
        
        for url in post_details.related:
            await remote_post.add_related_url(url)
        
        available = {f.order: f for f in post_details.files}
        present = set(file.remote_order for file in await remote_post.awaitable_attrs.files)
        
        for order in set(available.keys()) - present:
            file = File(remote=remote_post, remote_order=order)
            self.session.add(file)
            await self.session.flush()
        
        # TODO check file_id and encode it in the metadata_, but also handle the cases where that does not exist (use order instead)
        for file in await remote_post.awaitable_attrs.files:
            f = available[file.remote_order]
            
            file.filename = f.filename
            if not file.present:
                orig = None
                is_move = False
                
                url = yarl.URL(f.url)
                match url.scheme:
                    case 'file':
                        self.log.info(f'copying file {file.remote_order}: {url.path}')
                        orig = url.path
                        is_move = False
                        
                    case 'http' | 'https':
                        self.log.info(f'downloading file {file.remote_order}: {f.url}')
                        async with self.http.get(f.url) as resp:
                            orig = await save_response(resp, suffix=f.filename)
                        is_move = True
                
                if orig is not None:
                    await self.session.import_file(file, orig=orig, thumb=None, move=is_move)
        
        remote_post.favorite = post_details.is_favorite
        remote_post.hidden = post_details.is_hidden
        remote_post.removed = post_details.is_removed
        
        self.session.add(remote_post)
        return remote_post
    
    async def parse_url(self, url: str) -> str | Dynamic | None:
        return await self.plugin_class.parse_url(url)
    
    async def download(self, post: RemotePost | str) -> RemotePost:
        if isinstance(post, RemotePost):
            remote_post = post
            post_id = post.original_id
        else:
            _, remote_post = await self._get_post(post)
            post_id = post
        
        if post_id is None:
            raise ValueError('original id cannot be null when downloading a post')
        
        post_details = await self.instance.download(post_id)
        return await self._convert_post(remote_post, post_details)
    
    async def probe_query(self,
        query: Dynamic
    ) -> Optional[SearchDetails]:
        return await self.instance.probe_query(query)
    
    async def subscribe(self,
        name: str,
        query: Dynamic
    ) -> Subscription:
        details = await self.probe_query(query)
        if details is None:
            raise Exception(f'Subscriptions are not supported for {self.instance.id}')
        
        subcription = Subscription(
            source=self.source,
            plugin=self.plugin,
            name=name,
            repr=details.identifier,
            options=query.to_json(),
            metadata_=details.to_json()
        )
        
        self.session.add(subcription)
        await self.session.flush()
        
        return subcription
    
    async def _iterate_query(self,
        is_head: bool,
        opt: Dynamic | Subscription
    ) -> AsyncIterator[RemotePost]:
        if isinstance(opt, Subscription):
            subscription = opt
            query = Dynamic.from_json(opt.options)
        else:
            subscription = None
            query = opt
        
        is_first = True
        first_id = None
        last_id = None
        
        begin_at = None
        end_at = None
        if subscription is not None:
            state: Dynamic = Dynamic.from_json(subscription.state)
            if not is_head:
                begin_at = state.get('tail_id')
            else:
                end_at = state.get('head_id')
        
        exc = False
        try:
            async for sort_index, post_id, post_data in self.instance.iterate_query(query, begin_at=begin_at):
                if end_at is not None and sort_index <= end_at:
                    break
                
                remote_post = None
                if post_id is not None:
                    exists, remote_post = await self._get_post(post_id)
                    post_details = await self.instance.download(post_id, post_data)
                    post = await self._convert_post(remote_post, post_details)
                    
                    if subscription is not None:
                        await subscription.add_post(remote_post, int(sort_index))
                        await self.session.commit()
                
                if is_first:
                    is_first = False
                    first_id = sort_index
                
                last_id = sort_index
                
                if remote_post is not None:
                    yield remote_post
            
        except:
            exc = True
            
        finally:
            if subscription is not None:
                state: Dynamic = Dynamic.from_json(subscription.state)
                
                if first_id is not None and (not state.contains('head_id') or (is_head and not exc)):
                    state.head_id = first_id
                    
                if last_id is not None and (not state.contains('tail_id') or not is_head):
                    state.tail_id = last_id
                
                subscription.state = state.to_json()
                subscription.updated_time = datetime.now(timezone.utc)
                self.session.add(subscription)
            
            await self.session.commit()
    
    def update(self, opt: Subscription | Dynamic) -> AsyncIterator[RemotePost]:
        return self._iterate_query(True, opt)
    
    def fetch(self, opt: Subscription | Dynamic) -> AsyncIterator[RemotePost]:
        return self._iterate_query(False, opt)

