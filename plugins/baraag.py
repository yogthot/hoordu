import re
import dateutil.parser

from bs4 import BeautifulSoup

from hoordu.dynamic import Dynamic
from hoordu.plugins import *
from hoordu.models.common import *
from hoordu.forms import *


POST_FORMAT = 'https://baraag.net/@{user}/{post_id}'
POST_REGEXP = [
    re.compile(r'^https?:\/\/baraag\.net\/@(?P<user>[^\/]+)\/(?P<post_id>\d+)(?:\/.*)?(?:\?.*)?$', flags=re.IGNORECASE),
]
TIMELINE_REGEXP = re.compile(r'^https?:\/\/baraag\.net\/@(?P<user>[^\/]+)(?:\/.*)?(?:\?.*)?$', flags=re.IGNORECASE)


class Baraag(PluginBase):
    source = 'baraag'
    
    @classmethod
    def config_form(cls):
        return Form(f'{cls.source} config',
            ('token', Input('Bearer Token', [validators.required()])),
        )
    
    @classmethod
    def search_form(cls):
        return Form(f'{cls.source} search',
            ('method', ChoiceInput('method', [
                    ('posts', 'posts'),
                    ('reposts', 'reposts'),
                ], [validators.required()])),
            ('user', Input('screen name', [validators.required()]))
        )
    
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
            
            return Dynamic({
                'user': user,
                'method': method
            })
        
        return None
    
    async def setup(self):
        self.http.headers.update({
            'Authorization': f'Bearer {self.config.token}'
        })
    
    def _check_reblog(self, post_data):
        reblog = post_data.get('reblog')
        if reblog is not None and len(post_data.media_attachments) == 0:
            post_data = reblog
        
        return post_data
    
    async def download(self, post_id, post_data=None):
        if post_data is None:
            resp = await self.http.get(f'https://baraag.net/api/v1/statuses/{post_id}')
            resp.raise_for_status()
            post_data = Dynamic.from_json(await resp.text())
        
        post_data = self._check_reblog(post_data)
        
        user = post_data.account.acct
        text = post_data.content if post_data.spoiler_text is None else f'{post_data.spoiler_text}\n{post_data.content}'
        text_html = BeautifulSoup(text, 'html.parser')
        
        for p in text_html.find_all('p'):
            p.replace_with(p.text + '\n')
        
        for br in text_html.find_all('br'):
            br.replace_with('\n')
        
        text = text_html.text
        
        post = PostDetails()
        post.url = POST_FORMAT.format(user=user, post_id=post_data.id)
        post.comment = text
        post.post_time = post_time = dateutil.parser.isoparse(post_data.created_at).replace(tzinfo=None)
        
        post.metadata = Dynamic({'user': user}).to_json()
        
        post.tags.append((TagCategory.artist, user))
        
        if post_data.sensitive or post_data.spoiler_text:
            post.tags.append((TagCategory.meta, 'nsfw'))
        
        hashtags = post_data.get('tags', [])
        for hashtag in hashtags:
            post.tags.append((TagCategory.general, hashtag.name))
        
        quoted = post_data.get('reblog')
        if quoted is not None:
            post.related.append(POST_FORMAT.format(user=quoted.account.acct, post_id=quoted.id))
        
        post.files = [
            FileDetails(
                url=f.url,
                order=i + 1,
                identifier=f.id
            )
            for i, f in enumerate(post_data.media_attachments)
        ]
        
        return post
    
    async def probe_query(self, query):
        request = {
            'acct': query.user
        }
        
        resp = await self.http.get('https://baraag.net/api/v1/accounts/lookup', params=request)
        resp.raise_for_status()
        user = Dynamic.from_json(await resp.text())
        
        query.user_id = user.id
        
        related_urls = []
        
        thumb_url = user.avatar
        
        desc_html = BeautifulSoup(user.note, 'html.parser')
        
        for p in desc_html.find_all('p'):
            p.replace_with(p.text + '\n')
        
        for br in desc_html.find_all('br'):
            br.replace_with('\n')
        
        return SearchDetails(
            identifier=f'{query.method}:{query.user_id}',
            hint=user.username,
            title=user.display_name if user.display_name else user.username,
            description=desc_html.text,
            thumbnail_url=thumb_url,
            related_urls=related_urls
        )
    
    def _validate_method(self, method, post_data):
        is_reblog = False
        reblog = post_data.get('reblog')
        if reblog is not None and len(post_data.media_attachments) == 0:
            is_reblog = True
            post_data = reblog
        
        media_list = post_data.get('media_attachments')
        
        has_files = (
            media_list is not None and
            len(media_list) > 0
        )
        
        if method == 'reposts':
            return has_files and is_reblog
            
        elif method == 'posts':
            return has_files and not is_reblog
    
    async def iterate_query(self, query, begin_at=None):
        if 'user_id' not in query:
            await self.probe_query(query)
        
        until_id = None
        if begin_at is not None:
            until_id = begin_at
        
        while True:
            self.log.info('getting next page')
            request = {
                #'exclude_replies': True,
                'limit': '40',
            }
            if until_id is not None:
                request['max_id'] = str(until_id)
            if query.method != 'reposts':
                request['only_media'] = 'true'
            
            resp = await self.http.get(f'https://baraag.net/api/v1/accounts/{query.user_id}/statuses', params=request)
            resp.raise_for_status()
            posts = Dynamic.from_json(await resp.text())
            
            if len(posts) == 0:
                return
            
            self.log.info(f'page date: {posts[0].created_at}')
            
            for post in posts:
                sort_index = int(post.id)
                if self._validate_method(query.method, post):
                    post = self._check_reblog(post)
                    yield sort_index, post.id, post
                    until_id = post.id
                    
                else:
                    yield sort_index, None, None

Plugin = Baraag

