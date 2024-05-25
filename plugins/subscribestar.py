import os
import re
from datetime import datetime, timezone
from tempfile import mkstemp
import shutil
from urllib import parse as urlparse
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
from hoordu.plugins.helpers import parse_href


POST_FORMAT = 'https://subscribestar.adult/posts/{post_id}'
POST_REGEXP = [
    re.compile(r'^https?:\/\/subscribestar\.adult\/posts\/(?P<post_id>\d+)(?:\/.*)?(?:\?.*)?$', flags=re.IGNORECASE),
]
USER_REGEXP = re.compile(r'^https?:\/\/subscribestar\.adult\/(?P<user>[^\/]+)(?:\/.*)?(?:\?.*)?$', flags=re.IGNORECASE)


class SubStarIterator(IteratorBase['SubStar']):
    def __init__(self, plugin, subscription=None, options=None):
        super().__init__(plugin, subscription=subscription, options=options)
        
        self.http = plugin.http
        
        self.options.user_id = self.options.get('user_id')
        
        self.first_id = None
        self.state.head_id = self.state.get('head_id')
        self.state.tail_id = self.state.get('tail_id')
        self.state.page_end_order = self.state.get('page_end_order')
    
    def __repr__(self):
        return self.options.user
    
    async def init(self):
        if self.options.user_id is None:
            url = f'https://subscribestar.adult/{self.options.user}'
            async with self.http.get(url) as response:
                response.raise_for_status()
                page_html = BeautifulSoup(await response.text(), 'html.parser')
            
            # TODO what if there isn't a full page of content yet?
            posts_href = page_html.select('.posts-more')[0].attrs['href']
            p = urlparse.urlparse(posts_href)
            query = urlparse.parse_qs(p.query)
            
            self.options.user_id = query['star_id'][0]
            
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
        total = 0
        next_page = None
        main_url = f'https://subscribestar.adult/{self.options.user}'
        
        if self.direction == FetchDirection.older:
            if self.state.page_end_order == -1:
                return
            
            if self.state.page_end_order is not None:
                next_page = f'https://subscribestar.adult/posts?page_end_order_position={self.state.page_end_order}&star_id={self.options.user_id}'
        
        while True:
            self.log.info('getting next page')
            
            if next_page is None:
                async with self.http.get(main_url) as response:
                    response.raise_for_status()
                    page_html = BeautifulSoup(await response.text(), 'html.parser')
                    posts_html = page_html.select('.posts')[0]
                
            else:
                timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
                next_page += f'&_={timestamp}'
                async with self.http.get(next_page) as response:
                    response.raise_for_status()
                    json_response = hoordu.Dynamic.from_json(await response.text())
                    page_html = BeautifulSoup(json_response.html, 'html.parser')
                    posts_html = page_html
            
            next_page_sel = page_html.select('.posts-more')
            if len(next_page_sel) != 0:
                next_href = next_page_sel[0].attrs['href']
                next_page = parse_href(main_url, next_href)
                
            else:
                next_href = None
                next_page = None
            
            posts = page_html.select('.post')
            
            if len(posts) == 0:
                return
            
            for post in posts:
                if self.num_posts is not None and total >= self.num_posts:
                    return
                
                post_id = int(post.attrs['data-id'])
                yield post_id, post
                
                total +=1
            
            if next_page is not None:
                if self.direction == FetchDirection.older:
                    p = urlparse.urlparse(next_page)
                    query = urlparse.parse_qs(p.query)
                    # but what if we didn't get to the end of the page?
                    self.state.page_end_order = query['page_end_order_position'][0]
                
            else:
                self.state.page_end_order = -1
                return
    
    async def generator(self):
        is_first = True
        
        async for sort_index, post in self._feed_iterator():
            if is_first:
                if self.state.head_id is None or self.direction == FetchDirection.newer:
                    self.first_id = sort_index
                
                is_first = False
            
            if self.direction == FetchDirection.newer and sort_index <= self.state.head_id:
                break
            
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


class SubStar(SimplePlugin):
    name = 'subscribe-star'
    version = 1
    iterator = SubStarIterator
    
    @classmethod
    def config_form(cls):
        return Form('{} config'.format(cls.name),
            ('personalization_id', Input('_personalization_id cookie', [validators.required])),
            ('subscribestar_session', Input('_subscribestar_session cookie', [validators.required])),
            ('auth_tracker_code', Input('auth_tracker_code cookie', [validators.required])),
            ('cf_clearance', Input('cf_clearance cookie', [validators.required])),
            ('two_factor_auth_token', Input('two_factor_auth_token cookie', [validators.required])),
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
        
        if not config.contains('personalization_id', 'subscribestar_session', 'auth_tracker_code', 'cf_clearance', 'two_factor_auth_token'):
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
        
        match = USER_REGEXP.match(url)
        if match:
            user = match.group('user')
            return hoordu.Dynamic({
                'user': user
            })
        
        return None
    
    @contextlib.asynccontextmanager
    async def context(self):
        async with super().context():
            self._headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:80.0) Gecko/20100101 Firefox/100.0',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1',
            }
            self.cookies = {
                '_personalization_id': self.config.personalization_id,
                '_subscribestar_session': self.config.subscribestar_session,
                'auth_tracker_code': self.config.auth_tracker_code,
                'cf_clearance': self.config.cf_clearance,
                'two_factor_auth_token': self.config.two_factor_auth_token,
                
                '18_plus_agreement_generic': 'true',
                'cookies_accepted': 'true',
            }
            
            async with aiohttp.ClientSession(headers=self._headers, cookies=self.cookies) as http:
                self.http: aiohttp.ClientSession = http
                yield self
    
    async def _download_file(self, url, filename=None):
        # cookies and headers
        path, resp = await self.session.download(url, suffix=filename)
        return path
    
    def _parse_text(self, el):
        # could even convert to MD or something similar
        for p in el.find_all('p'):
            p.replace_with(p.text + '\n')
        
        for br in el.find_all('br'):
            br.replace_with('\n')
        
        return el.text
    
    def _get_text(self, html, selector):
        elements = html.select(selector)
        if not elements:
            return None
        
        return '\n'.join(self._parse_text(e) for e in elements)
    
    async def _hidden_to_remote_post(self, post_html, remote_post=None, preview=False):
        original_id = post_html.attrs['data-id']
        if not original_id:
            raise APIError('no id found')
        
        title = self._get_text(post_html, '.post-title h2')
        text = None
        post_date = self._get_text(post_html, '.post-date')
        if post_date is None:
            post_date = self._get_text(post_html, '.section-subtitle')
        
        post_time = dateutil.parser.parse(post_date).replace(tzinfo=None)
        
        user_els = post_html.select('.post-avatar')
        if not user_els:
            user_els = post_html.select('.star_link')
            
        user = user_els[0].attrs['href'].lstrip('/')
        
        
        if remote_post is None:
            remote_post = await self._get_post(original_id)
        
        remote_post.url = POST_FORMAT.format(user=user, post_id=original_id)
        remote_post.title = title
        remote_post.comment = text
        remote_post.type = PostType.set
        remote_post.post_time = post_time
        self.session.add(remote_post)
        
        self.log.info(f'downloading post: {remote_post.original_id}')
        self.log.info(f'local id: {remote_post.id}')
        
        user_tag = await self._get_tag(TagCategory.artist, user)
        await remote_post.add_tag(user_tag)
        
        tags = post_html.select('.post-tag')
        if tags:
            for tag_element in tags:
                tagname = tag_element.text.replace(' ', '_')
                tag = await self._get_tag(TagCategory.general, tagname)
                await remote_post.add_tag(tag)
        
        self.session.add(remote_post)
        
        return remote_post
    
    async def _to_remote_post(self, post_html, remote_post=None, preview=False):
        post_id_el = post_html.select('[data-post_id]')
        is_accessible = len(post_id_el) > 0
        
        if not is_accessible:
            return await self._hidden_to_remote_post(post_html, remote_post, preview)
        
        original_id = post_html.select('[data-post_id]')[0].attrs['data-post_id']
        title = self._get_text(post_html, '.post-content > h1:first-child')
        text = self._get_text(post_html, '.post-content > :not(h1:first-child)')
        post_date = self._get_text(post_html, '.post-date')
        if post_date is None:
            post_date = self._get_text(post_html, '.section-subtitle')
        
        post_time = dateutil.parser.parse(post_date).replace(tzinfo=None)
        
        user_els = post_html.select('.post-avatar')
        if not user_els:
            user_els = post_html.select('.star_link')
            
        user = user_els[0].attrs['href'].lstrip('/')
        
        
        if remote_post is None:
            remote_post = await self._get_post(original_id)
        
        remote_post.url = POST_FORMAT.format(user=user, post_id=original_id)
        remote_post.title = title
        remote_post.comment = text
        remote_post.type = PostType.set
        remote_post.post_time = post_time
        self.session.add(remote_post)
        
        self.log.info(f'downloading post: {remote_post.original_id}')
        self.log.info(f'local id: {remote_post.id}')
        
        user_tag = await self._get_tag(TagCategory.artist, user)
        await remote_post.add_tag(user_tag)
        
        tags = post_html.select('.post-tag')
        if tags:
            for tag_element in tags:
                tagname = tag_element.text.replace(' ', '_')
                tag = await self._get_tag(TagCategory.general, tagname)
                await remote_post.add_tag(tag)
        
        self.session.add(remote_post)
        
        current_files = {file.metadata_: file for file in await remote_post.awaitable_attrs.files}
        
        gallery = []
        gallery_els = post_html.select('[data-gallery]')
        if gallery_els:
            gallery = hoordu.Dynamic.from_json(gallery_els[0].attrs['data-gallery'])
        
        if len(gallery) > 0:
            
            order = 0
            for rfile in gallery:
                rfile_id = str(rfile.id)
                file = current_files.get(rfile_id)
                
                filename = rfile.original_filename
                
                if file is None:
                    file = File(remote=remote_post, metadata_=rfile_id, remote_order=order, filename=filename)
                    self.session.add(file)
                    await self.session.flush()
                    
                elif file.remote_order != order:
                    file.remote_order = order
                    self.session.add(file)
                
                need_orig = not file.present and not preview
                #need_thumb = not file.thumb_present and rfile.preview_url is not None
                
                if need_orig: # or need_thumb:
                    self.log.info(f'downloading file: {file.remote_order}')
                    
                    orig = await self._download_file(rfile.url, filename=filename) if need_orig else None
                    await self.session.import_file(file, orig=orig, move=True)
                
                order += 1
        
        docs = post_html.select('.uploads-docs .doc_preview')
        if len(docs) > 0:
            order = 10000
            for doc in docs:
                doc_id = str(doc.attrs['data-upload-id'])
                anchor = doc.select('a')[0]
                
                file = current_files.get(doc_id)
                url = parse_href(remote_post.url, anchor.attrs['href'])
                filename = self._get_text(anchor, '.doc_preview-title')
                
                if file is None:
                    file = File(remote=remote_post, metadata_=doc_id, remote_order=order, filename=filename)
                    self.session.add(file)
                    await self.session.flush()
                    
                elif file.remote_order != order:
                    file.remote_order = order
                    self.session.add(file)
                
                if not file.present and not preview:
                    self.log.info(f'downloading file: {file.remote_order}')
                    
                    orig = await self._download_file(url, filename=filename) if need_orig else None
                    await self.session.import_file(file, orig=orig, move=True)
                
                order += 1
        
        return remote_post
    
    async def download(self, id=None, remote_post=None, preview=False):
        if id is None and remote_post is None:
            raise ValueError('either id or remote_post must be passed')
        
        if remote_post is not None:
            id = remote_post.original_id
        
        url = POST_FORMAT.format(post_id=id)
        
        async with self.http.get(url) as response:
            response.raise_for_status()
            post = BeautifulSoup(await response.text(), 'html.parser')
        
        #self.log.debug(post)
        
        return await self._to_remote_post(post, remote_post=remote_post, preview=preview)
    
    def search_form(self):
        return Form('{} search'.format(self.name),
            ('user', Input('username', [validators.required()]))
        )
    
    async def get_search_details(self, options):
        return SearchDetails(
            hint=options.user,
            title=options.user
        )

Plugin = SubStar


