import re
import dateutil.parser
import json
import httpx
from datetime import datetime

from hoordu.dynamic import Dynamic
from hoordu.models import *
from hoordu.plugins import *
from hoordu.forms import *
from hoordu.plugins.helpers import parse_jwt


# TODO https://docs.bsky.app/docs/category/http-reference

# TODO get uris dynamically
POST_FORMAT = 'https://bsky.app/profile/{user}/post/{post_id}'
POST_REGEXP = [
    re.compile(r'^https?:\/\/bsky\.app\/profile\/(?P<user>[^\/]+)\/post\/(?P<post_id>[a-z0-9]+)(?:\/.*)?(?:\?.*)?$', flags=re.IGNORECASE),
]
TIMELINE_REGEXP = re.compile(r'^https?:\/\/(x|twitter)\.com\/(?P<user>[^\/]+)(?:\/(?P<type>[^\/]+)?)?(?:\?.*)?$', flags=re.IGNORECASE)

PAGE_LIMIT = 40


class Bsky(PluginBase):
    source = 'bsky'
    
    @classmethod
    def config_form(cls):
        return Form(f'{cls.source} config',
            ('username', Input('username (including .bsky.social)', [validators.required()])),
            ('password', Input('password', [validators.required()])),
        )
    
    @classmethod
    async def setup(cls, config, parameters=None):
        if parameters is not None:
            config.update(parameters)
        
        headers = {
            'Origin': 'https://bsky.app'
        }
        
        if not config.contains('username', 'password'):
            return False, cls.config_form()
            
        elif not config.contains('refresh_token'):
            if '.' not in config.username:
                config.username = config.username + '.bsky.social'
            
            data = {
                'identifier': config.username,
                'password': config.password
            }
            
            async with httpx.AsyncClient(http2=True, follow_redirects=True) as http:
                domain = config.username.split('.', 1)[1]
                resp = await http.post(f'https://{domain}/xrpc/com.atproto.server.createSession', json=data, headers=headers)
                resp.raise_for_status()
                tokens = Dynamic.from_json(resp.text)
            
            config.access_token = tokens['accessJwt']
            config.refresh_token = tokens['refreshJwt']
            
            return True, None
            
        else:
            return True, None
    
    @classmethod
    def search_form(cls):
        return Form(f'{cls.source} search',
            ('method', ChoiceInput('method', [
                    ('posts', 'posts'),
                    ('reposts', 'reposts'),
                ], [validators.required()])),
            ('user', Input('username', [validators.required()]))
        )
    
    @classmethod
    async def parse_url(cls, url):
        if url.isdigit():
            return url
        
        for regexp in POST_REGEXP:
            match = regexp.match(url)
            if match:
                username = match.group('user')
                post_id = match.group('post_id')
                return f'{username}/{post_id}'
        """
        match = TIMELINE_REGEXP.match(url)
        if match:
            user = match.group('user')
            method = match.group('type')
            
            #if method != 'likes':
            #    method = 'tweets'
            method = 'tweets'
            
            return Dynamic({
                'user': user,
                'method': method
            })
        """
        return None
    
    async def init(self):
        self.http.headers.update({
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Origin': 'https://bsky.app',
            'Referer': 'https://bsky.app/',
            'Authorization': f'Bearer {self.config.access_token}',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache'
        })
    
    def _get_domain(self, did):
        if did.startswith('did:web:'):
            return did[8:]
            
        else:
            raise Exception(f'unknown did: {did}')
    
    async def _login(self):
        
        data = {
            'identifier': config.username,
            'password': config.password
        }
        
        async with httpx.AsyncClient(http2=True, follow_redirects=True) as http:
            domain = self.config.username.split('.', 1)[1]
            resp = await http.post(f'https://{domain}/xrpc/com.atproto.server.createSession', json=data)
            resp.raise_for_status()
            tokens = Dynamic.from_json(resp.text)
        
        self.config.access_token = tokens['accessJwt']
        self.config.refresh_token = tokens['refreshJwt']
        self.http.headers.update({
            'Authorization': f'Bearer {self.config.access_token}',
        })
    
    async def _refresh_token(self):
        self.log.info('refreshing token')
        headers = {'Authorization': f'Bearer {self.config.refresh_token}'}
        domain = self.config.username.split('.', 1)[1]
        resp = await self.http.post(f'https://{domain}/xrpc/com.atproto.server.refreshSession', headers=headers)
        if resp.status_code == 400:
            error = Dynamic.from_json(resp.text)
            #if error.error == 'ExpiredToken':
            #    self._login()
            #    return
        
        resp.raise_for_status()
        
        tokens = Dynamic.from_json(resp.text)
        
        self.config.access_token = tokens['accessJwt']
        self.config.refresh_token = tokens['refreshJwt']
        self.http.headers.update({
            'Authorization': f'Bearer {self.config.access_token}',
        })
    
    async def _request(self, method, endpoint, *args, **kwargs):
        token = parse_jwt(self.config.access_token)
        
        # TODO now or utcnow?
        if datetime.fromtimestamp(token['exp']) < datetime.utcnow():
            await self._refresh_token()
        
        domain = self._get_domain(token['aud']) if 'aud' in token else 'bsky.app'
        url = f'https://{domain}/xrpc/{endpoint}'
        return await self.http.request(method, url, *args, **kwargs)
    
    async def download(self, post_id, post_data=None):
        username, pid = post_id.split('/')
        
        if post_data is None:
            params = {
                'uri': f'at://{username}/app.bsky.feed.post/{pid}',
                'depth': '10'
            }
            resp = await self._request('GET', 'app.bsky.feed.getPostThread', params=params)
            resp.raise_for_status()
            thread = Dynamic.from_json(resp.text).thread
            
            post_data = thread.post
        
        user = post_data.author.handle
        user_id = post_data.author.did
        text = post_data.record.text
        post_time = dateutil.parser.parse(post_data.record.createdAt)
        
        post = PostDetails()
        
        post.url = POST_FORMAT.format(user=user, post_id=pid)
        post.comment = text
        post.type = PostType.set
        post.post_time = post_time
        post.metadata = {'user': user}
        
        post.extensions = {
            'user_name': post_data.author.displayName,
            'user_handle': user,
            'user_url': f'https://bsky.app/profile/{user}',
            'user_icon': post_data.author.avatar,
        }
        
        post.tags.append(TagDetails(
            category=TagCategory.artist,
            tag=user_id,
            metadata={'user': user}
        ))
        
        facets = post_data.record.get('facets')
        if facets is not None:
            for facet in facets:
                for feature in facet.features:
                    if feature['$type'] == 'app.bsky.richtext.facet#link':
                        post.related.append(feature.uri)
                        
                    elif feature['$type'] == 'app.bsky.richtext.facet#mention':
                        pass
                        
                    elif feature['$type'] == 'app.bsky.richtext.facet#tag':
                        post.tags.append(TagDetails(
                            category=TagCategory.general,
                            tag=feature.tag
                        ))
                        
                    else:
                        raise Exception(f'unknown facet: {feature['$type']}')
        
        labels = post_data.record.get_path('labels', 'values')
        if labels is not None:
            for label in labels:
                post.tags.append(TagDetails(
                    category=TagCategory.meta,
                    tag=label.val
                ))
        
        order = 1
        # TODO calculate the domain dynamically
        media_base = 'https://bsky.social'
        
        embed = post_data.record.get('embed')
        if embed is not None:
            if 'images' in embed:
                for image_embed in embed.images:
                    media = image_embed.image
                    media_cid = media['cid'] if 'cid' in media else media['ref']['$link']
                    post.files.append(FileDetails(
                        url=f'{media_base}/xrpc/com.atproto.sync.getBlob?did={user_id}&cid={media_cid}',
                        filename=f'{media_cid}.{media.mimeType.split('/')[-1]}',
                        order=order
                    ))
                    order += 1
                
            elif 'video' in embed:
                media = embed.video
                media_cid = media['cid'] if 'cid' in media else media['ref']['$link']
                post.files.append(FileDetails(
                    url=f'{media_base}/xrpc/com.atproto.sync.getBlob?did={user_id}&cid={media_cid}',
                    filename=f'{media_cid}.{media.mimeType.split('/')[-1]}',
                    order=order,
                    metadata=Dynamic({'presentation': embed.get('presentation')}).to_json()
                ))
                order += 1
                
            else:
                raise NotImplementedError(f'new embed type found: {embed}')
        
        return post
    
    async def probe_query(self, query):
        pass
    
    async def iterate_query(self, query, state, begin_at=None):
        pass
    
Plugin = Bsky

