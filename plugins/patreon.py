import re
import dateutil.parser
import itertools

from bs4 import BeautifulSoup
from collections import OrderedDict

import hoordu
from hoordu.models import *
from hoordu.plugins import *
from hoordu.forms import *
from hoordu.plugins.helpers import parse_href
from hoordu.dynamic import Dynamic


POST_FORMAT = 'https://www.patreon.com/posts/{post_id}'
POST_REGEXP = re.compile(r'^https?:\/\/(?:www\.)?patreon\.com\/posts\/(:?[^\?#\/]*-)?(?P<post_id>\d+)(?:\?.*)?(?:#.*)?$', flags=re.IGNORECASE)

CREATOR_REGEXP = re.compile(r'^https?:\/\/(?:www\.)?patreon\.com\/(?P<vanity>[^\/]+)(?:\/.*)?(?:\?.*)?(?:#.*)?$', flags=re.IGNORECASE)


class IncludedMap(OrderedDict):
    def __init__(self, included_raw):
        super().__init__()
        for include in included_raw:
            self[(include.type, include.id)] = include
    
    def __getitem__(self, key):
        if isinstance(key, tuple):
            return super().__getitem__(key)
            
        else:
            return super().__getitem__((key.type, key.id))


class Patreon(PluginBase):
    source = 'patreon'
    
    @classmethod
    def config_form(cls):
        return Form(f'{cls.source} config',
            ('session_id', Input('session_id cookie', [validators.required()]))
        )
    
    @classmethod
    def search_form(cls):
        return Form(f'{cls.source} search',
            ('creator', Input('creator vanity', [validators.required()]))
        )
    
    async def setup(self):
        self.http.headers.update({
            'Origin': 'https://www.patreon.com/',
            'Referer': 'https://www.patreon.com/',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/109.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'same-origin',
            'TE': 'trailers',
        })
        self.http._cookie_jar.update_cookies({
            'session_id': self.config.session_id
        })
    
    @classmethod
    async def parse_url(cls, url):
        if url.isdigit():
            return url
        
        match = POST_REGEXP.match(url)
        if match:
            return match.group('post_id')
        
        match = CREATOR_REGEXP.match(url)
        if match:
            return Dynamic({
                'vanity': match.group('vanity')
            })
        
        return None
    
    async def download(self, post_id, post_data=None):
        if post_data is None:
            params = {
                'include': 'attachments,audio,images,media,user,user_defined_tags',
                'json-api-use-default-includes': 'false',
                'json-api-version': '1.0'
            }
            
            async with self.http.get(f'https://www.patreon.com/api/posts/{post_id}', params=params) as response:
                response.raise_for_status()
                json = Dynamic.from_json(await response.text())
            
            post_obj = json.data
            included = IncludedMap(json.included)
            
        else:
            post_obj, included = post_data
        
        
        post_attr = post_obj.attributes
        post_id = post_obj.id
        
        user = included[post_obj.relationships.user.data]
        user_id = user.id
        user_vanity = user.attributes.vanity
        
        
        post = PostDetails()
        post.url = POST_FORMAT.format(post_id=post_id)
        post.title = post_attr.title
        post.type = PostType.collection
        post.post_time = dateutil.parser.parse(post_attr.published_at)
        
        # parse post content
        urls = []
        content_images = []
        if post_attr.get('content') is not None:
            content = re.sub(r'\s+', ' ', post_attr.content)
            comment_html = BeautifulSoup(content, 'html.parser')
            
            page_url = POST_FORMAT.format(post_id=post_id)
            for a in comment_html.select('a'):
                if 'href' in a:
                    url = parse_href(page_url, a['href'])
                    urls.append(url)
                else:
                    url = a.text
                
                a.replace_with(url)
            
            for img in comment_html.find_all('img'):
                content_images.append(img['data-media-id'])
            
            for br in comment_html.find_all('br'):
                br.replace_with('\n')
            
            for p in comment_html.find_all('p'):
                p.replace_with(f'{p.text}\n')
            
            post.comment = comment_html.text
            
        elif post_attr.get('teaser_text') is not None and not post.comment:
            post.comment = post_attr.teaser_text
        
        if post_attr.current_user_has_liked is True:
            post.is_favorite = True
        
        
        post.tags.append(TagDetails(
            category=TagCategory.artist,
            tag=user_id,
            metadata={'vanity': user_vanity}
        ))
        
        tags = post_obj.relationships.user_defined_tags.data or []
        for tag in tags:
            name = tag.id.split(';', 1)[1]
            
            post.tags.append(TagDetails(
                category=TagCategory.general,
                tag=name
            ))
        
        for url in urls:
            post.related.append(url)
        
        embed = post_attr.get('embed')
        if embed is not None:
            post.related.append(embed.url)
        
        images = post_obj.relationships.images.data or []
        try:
            attachments = post_obj.relationships.attachments.data or []
        except Exception:
            attachments = []
        
        try:
            media = post_obj.relationships.media.data or []
        except Exception:
            media = []
        
        media = [x for x in media if x.id in content_images]
        
        audio = []
        audio_data = post_obj.relationships.audio.data
        if audio_data is not None:
            audio = [audio_data]
        
        # remove duplicates
        #all_content = images + audio + attachments + media
        #filtered_content = [Dynamic(x) for x in list(set(tuple(d.items()) for d in all_content))]
        
        for data, order in zip(itertools.chain(images, audio, attachments, media), itertools.count(1)):
            attributes = included[data].attributes
            
            filename = None
            url = None
            
            if data.type == 'attachment':
                filename = attributes.name
                url = attributes.url
                
            elif data.type == 'media':
                # skip not ready images for now
                if attributes.state != 'ready':
                    continue
                
                # skip embeded image, url has been saved instead
                if post_attr.post_type == 'link' and attributes.owner_relationship == 'main':
                    continue
                
                url = attributes.image_urls.original
                
                filename = attributes.file_name
                
            else:
                self.log.warning(f'could not get filename or url for type: {data.type}')
            
            if filename is not None and '/' in filename:
                filename = None
            
            if url is None:
                raise Exception('could not detect file url properly')
            
            post.files.append(FileDetails(
                url=url,
                order=order,
                identifier=f'{data.type}-{data.id}',
                filename=filename
            ))
            
            orig_url = None
            thumb_url = None
        
        return post
    
    async def probe_query(self, query):
        params = {
            'filter[vanity]': query.vanity,
            'json-api-use-default-includes': 'true',
            'json-api-version': '1.0'
        }
        
        async with self.http.get('https://www.patreon.com/api/users', params=params) as response:
            response.raise_for_status()
            creator_resp = Dynamic.from_json(await response.text())
        
        creator = creator_resp.data.attributes
        
        query.creator_id = creator_resp.data.id
        
        for incl in creator_resp.included:
            if incl.type == 'campaign':
                query.campaign_id = incl.id
                break
        
        related_urls = list()
        for social in creator.social_connections.values():
            if social is not None and social.url is not None:
                related_urls.append(social.url)
        
        return SearchDetails(
            identifier=f'posts:{query.creator_id}',
            hint=creator.vanity,
            title=creator.full_name,
            description=creator.about,
            thumbnail_url=creator.image_url,
            related_urls=related_urls
        )
    
    async def iterate_query(self, query, state, begin_at=None):
        cursor = None
        
        while True:
            params = {
                'include': 'attachments,audio,images,media,user,user_defined_tags',
                'filter[campaign_id]': query.campaign_id,
                # what does this do?
                'filter[contains_exclusive_posts]': 'true',
                'filter[is_draft]': 'false',
                'sort': '-published_at',
                'json-api-use-default-includes': 'false',
                'json-api-version': '1.0',
            }
            if cursor is not None:
                params['page[cursor]'] = cursor
            
            self.log.info('getting next page')
            async with self.http.get('https://www.patreon.com/api/posts', params=params) as response:
                response.raise_for_status()
                page = Dynamic.from_json(await response.text())
            
            includes = IncludedMap(page.included)
            
            if cursor is None and len(page.data) > 0:
                self.first_timestamp = page.data[0].attributes.published_at
            
            for post in page.data:
                sort_index = int(post.id)
                
                if post.attributes.current_user_can_view:
                    yield sort_index, post.id, (post, includes)
                    
                else:
                    yield sort_index, None, None
            
            cursors = page.meta.pagination.get('cursors')
            if cursors is None:
                return
            
            cursor = cursors.next
            if cursor is None:
                return

Plugin = Patreon
