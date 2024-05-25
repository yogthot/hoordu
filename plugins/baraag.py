import os
import re
from datetime import datetime, timezone
from tempfile import mkstemp
import shutil
from urllib.parse import urlparse, parse_qs
import functools
from collections import OrderedDict
import dateutil.parser

import aiohttp
import contextlib
import asyncio
from bs4 import BeautifulSoup

import hoordu
from hoordu.models import *
from hoordu.plugins import *
from hoordu.forms import *


POST_FORMAT = 'https://baraag.net/@{user}/{post_id}'
POST_REGEXP = [
    re.compile(r'^https?:\/\/baraag\.net\/@(?P<user>[^\/]+)\/(?P<post_id>\d+)(?:\/.*)?(?:\?.*)?$', flags=re.IGNORECASE),
]
TIMELINE_REGEXP = re.compile(r'^https?:\/\/baraag\.net\/@(?P<user>[^\/]+)(?:\/.*)?(?:\?.*)?$', flags=re.IGNORECASE)

PAGE_LIMIT = 30


class BaraagClient:
    def __init__(self, token):
        self.token = token
        
        self.headers = {
            'Authorization': f'Bearer {token}'
        }
        
        self.http = aiohttp.ClientSession(headers=self.headers)
    
    async def __aenter__(self) -> 'BaraagClient':
        await self.http.__aenter__()
        return self
    
    async def __aexit__(self, *args):
        return await self.http.__aexit__(*args)
    
    async def _request(self, *args, **kwargs):
        async with self.http.get(*args, **kwargs) as resp:
            resp.raise_for_status()
            return hoordu.Dynamic.from_json(await resp.text())
    
    async def get_user(self, handle):
        query = {
            'acct': handle,
        }
        
        return await self._request('https://baraag.net/api/v1/accounts/lookup', params=query)
    
    async def get_post(self, post_id):
        return await self._request(f'https://baraag.net/api/v1/statuses/{post_id}')
    
    async def get_timeline(self, user_id, max_id=None, since_id=None):
        query = {
            #'exclude_replies': True,
            'only_media': 'true',
            'limit': '40',
        }
        if max_id is not None:
            query['max_id'] = max_id
        if since_id is not None:
            query['since_id'] = since_id
        
        return await self._request(f'https://baraag.net/api/v1/accounts/{user_id}/statuses', params=query)


class BaraagIterator(IteratorBase['Baraag']):
    def __init__(self, plugin, subscription=None, options=None):
        super().__init__(plugin, subscription=subscription, options=options)
        
        self.api = plugin.api
        
        self.options.user_id = self.options.get('user_id')
        
        self.first_id = None
        self.state.head_id = self.state.get('head_id')
        self.state.tail_id = self.state.get('tail_id')
    
    def __repr__(self):
        return '{}:{}'.format(self.options.method, self.options.user_id)
    
    async def init(self):
        if self.options.user_id is None:
            user = await self.api.get_user(self.options.user)
            
            self.options.user_id = user.id
            
            if self.subscription is not None:
                self.subscription.options = self.options.to_json()
                self.session.add(self.subscription)
    
    def reconfigure(self, direction=FetchDirection.newer, num_posts=None):
        if direction == FetchDirection.newer:
            if self.state.tail_id is None:
                direction = FetchDirection.older
            else:
                num_posts = None
        
        super().reconfigure(direction=direction, num_posts=num_posts)
    
    async def _feed_iterator(self):
        max_id = None if self.direction == FetchDirection.newer else self.state.tail_id
        
        total = 0
        while True:
            self.log.info('getting next page')
            posts = await self.api.get_timeline(self.options.user_id, max_id=max_id)
            
            if len(posts) == 0:
                return
            
            for post in posts:
                yield int(post.id), post
                max_id = post.id
                
                total +=1
                if self.num_posts is not None and total >= self.num_posts:
                    return
    
    def _validate_method(self, post):
        is_reblog = False
        reblog = post.get('reblog')
        if reblog is not None:
            is_reblog = True
            post = reblog
        
        media_list = post.get('media_attachments')
        
        has_files = (
            media_list is not None and
            len(media_list) > 0
        )
        
        if self.options.method == 'reposts':
            return has_files and is_reblog
            
        elif self.options.method == 'posts':
            return has_files and not is_reblog
    
    async def generator(self):
        is_first = True
        
        async for sort_index, post in self._feed_iterator():
            if is_first:
                if self.state.head_id is None or self.direction == FetchDirection.newer:
                    self.first_id = sort_index
                
                is_first = False
            
            if self.direction == FetchDirection.newer and sort_index <= self.state.head_id:
                break
            
            if self._validate_method(post):
                remote_post = await self.plugin._to_remote_post(post, preview=self.subscription is None)
                yield remote_post
                
                if self.subscription is not None:
                    await self.subscription.add_post(remote_post, sort_index)
                
                await self.session.commit()
            
            if self.direction == FetchDirection.older:
                self.state.tail_id = sort_index
        
        if self.first_id is not None:
            self.state.head_id = self.first_id
            self.first_id = None
        
        if self.subscription is not None:
            self.subscription.state = self.state.to_json()
            self.session.add(self.subscription)
        
        await self.session.commit()


class Baraag(SimplePlugin):
    name = 'baraag'
    version = 1
    iterator = BaraagIterator
    
    @classmethod
    def config_form(cls):
        return Form('{} config'.format(cls.name),
            ('token', Input('Bearer Token', [validators.required])),
        )
    
    @classmethod
    async def setup(cls, session, parameters=None):
        plugin = await cls.get_plugin(session)
        
        # check if everything is ready to use
        config = hoordu.Dynamic.from_json(plugin.config)
        
        # use values from the parameters if they were passed
        if parameters is not None:
            config.update(parameters)
            
            plugin.config = config.to_json()
            session.add(plugin)
        
        if not config.contains('token'):
            # but if they're still None, the api can't be used
            return False, cls.config_form()
            
        else:
            # the config contains every required property
            return True, None
    
    @classmethod
    async def update(cls, session):
        plugin = await cls.get_plugin(session)
        
        if plugin.version < cls.version:
            # update anything if needed
            
            # if anything was updated, then the db entry should be updated as well
            plugin.version = cls.version
            session.add(plugin)
    
    @classmethod
    async def parse_url(cls, url):
        if url.isdigit():
            return url
        
        for regexp in POST_REGEXP:
            match = regexp.match(url)
            if match:
                return match.group('post_id')
        
        match = TIMELINE_REGEXP.match(url)
        if match:
            user = match.group('user')
            method = 'posts'
            
            return hoordu.Dynamic({
                'user': user,
                'method': method
            })
        
        return None
    
    @contextlib.asynccontextmanager
    async def context(self):
        async with super().context():
            async with BaraagClient(self.config.token) as api:
                self.api: BaraagClient = api
                yield self
    
    async def _download_file(self, url, filename=None):
        path, resp = await self.session.download(url, suffix=filename)
        return path
    
    async def _to_remote_post(self, post, remote_post=None, preview=False):
        reblog = post.get('reblog')
        if reblog is not None and len(post.media_attachments) == 0:
            self.log.info(f'downloading reblog: {post.id}')
            post = reblog
        
        original_id = post.id
        user = post.account.acct
        text = post.content if post.spoiler_text is None else f'{post.spoiler_text}\n{post.content}'
        post_time = dateutil.parser.isoparse(post.created_at).replace(tzinfo=None)
        
        
        text_html = BeautifulSoup(text, 'html.parser')
        
        for p in text_html.find_all('p'):
            p.replace_with(p.text + '\n')
        
        for br in text_html.find_all('br'):
            br.replace_with('\n')
        
        text = text_html.text
        
        
        if remote_post is None:
            remote_post = await self._get_post(original_id)
        
        remote_post.url = POST_FORMAT.format(user=user, post_id=original_id)
        remote_post.comment = text
        remote_post.type = PostType.set
        remote_post.post_time = post_time
        remote_post.metadata_ = hoordu.Dynamic({'user': user}).to_json()
        self.session.add(remote_post)
        
        self.log.info(f'downloading post: {remote_post.original_id}')
        self.log.info(f'local id: {remote_post.id}')
        
        user_tag = await self._get_tag(TagCategory.artist, user)
        await remote_post.add_tag(user_tag)
        
        if post.sensitive or post.spoiler_text:
            nsfw_tag = await self._get_tag(TagCategory.meta, 'nsfw')
            await remote_post.add_tag(nsfw_tag)
        
        hashtags = post.get('tags')
        if hashtags is not None:
            for hashtag in hashtags:
                tag = await self._get_tag(TagCategory.general, hashtag.name)
                await remote_post.add_tag(tag)
        
        reblog = post.get('reblog')
        if reblog is not None:
            await remote_post.add_related_url(POST_FORMAT.format(user=reblog.account.acct, post_id=reblog.id))
        
        self.session.add(remote_post)
        
        files = post.media_attachments
        if len(files) > 0:
            current_files = {file.metadata_: file for file in await remote_post.awaitable_attrs.files}
            
            order = 0
            for rfile in files:
                rfile_id = rfile.id
                file = current_files.get(rfile_id)
                
                if file is None:
                    file = File(remote=remote_post, metadata_=rfile_id, remote_order=order)
                    self.session.add(file)
                    await self.session.flush()
                    
                elif file.remote_order != order:
                    file.remote_order = order
                    self.session.add(file)
                
                need_orig = not file.present and not preview
                need_thumb = not file.thumb_present and rfile.preview_url is not None
                
                if need_thumb or need_orig:
                    self.log.info(f'downloading file: {file.remote_order}')
                    
                    orig = await self._download_file(rfile.url) if need_orig else None
                    thumb = None
                    try:
                        if need_thumb:
                            thumb = await self._download_file(rfile.preview_url)
                    except:
                        self.log.exception('error while downloading thumbnail')
                    
                    await self.session.import_file(file, orig=orig, thumb=thumb, move=True)
                
                order += 1
        
        return remote_post
    
    async def download(self, id=None, remote_post=None, preview=False):
        if id is None and remote_post is None:
            raise ValueError('either id or remote_post must be passed')
        
        if remote_post is not None:
            id = remote_post.original_id
        
        post = await self.api.get_post(id)
        
        return await self._to_remote_post(post, remote_post=remote_post, preview=preview)
    
    def search_form(self):
        return Form('{} search'.format(self.name),
            ('method', ChoiceInput('method', [
                    ('posts', 'posts'),
                    ('reposts', 'reposts'),
                ], [validators.required()])),
            ('user', Input('screen name', [validators.required()]))
        )
    
    async def get_search_details(self, options):
        user = await self.api.get_user(options.user)
        options.user_id = user.id
        
        related_urls = {}
        
        thumb_url = user.avatar
        
        desc_html = BeautifulSoup(user.note, 'html.parser')
        
        for p in desc_html.find_all('p'):
            p.replace_with(p.text + '\n')
        
        for br in desc_html.find_all('br'):
            br.replace_with('\n')
        
        return SearchDetails(
            hint=user.username,
            title=user.display_name if user.display_name else user.username,
            description=desc_html.text,
            thumbnail_url=thumb_url,
            related_urls=related_urls
        )

Plugin = Baraag


