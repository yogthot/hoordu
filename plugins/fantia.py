import re
import dateutil.parser
from bs4 import BeautifulSoup

from hoordu.dynamic import Dynamic
from hoordu.models import *
from hoordu.plugins import *
from hoordu.forms import *
from hoordu.plugins.helpers import parse_href

POST_FORMAT = 'https://fantia.jp/posts/{post_id}'
CONTENT_FORMAT = 'https://fantia.jp/posts/{post_id}#post-content-id-{content_id}'
POST_REGEXP = re.compile(r'^https?:\/\/fantia\.jp\/posts\/(?P<post_id>\d+)(?:\?.*)?(?:#.*)?$', flags=re.IGNORECASE)
FANCLUB_REGEXP = re.compile(r'^https?:\/\/fantia\.jp\/fanclubs\/(?P<fanclub_id>\d+)(?:\/.*)?(?:\?.*)?(?:#.*)?$', flags=re.IGNORECASE)
FILENAME_REGEXP = re.compile(r'^[a-z0-9]+-(?P<filename>.+)$')

POST_GET_URL = 'https://fantia.jp/api/v1/posts/{post_id}'
FANCLUB_URL = 'https://fantia.jp/fanclubs/{fanclub_id}'
FANCLUB_GET_URL = 'https://fantia.jp/api/v1/fanclubs/{fanclub_id}'


class Fantia(PluginBase):
    source = 'fantia'
    
    @classmethod
    def config_form(cls):
        return Form(f'{cls.source} config',
            ('session_id', Input('_session_id cookie', [validators.required()]))
        )
    
    @classmethod
    def search_form(cls):
        return Form(f'{cls.source} search',
            ('creator_id', Input('fanclub id', [validators.required()]))
        )
    
    @classmethod
    async def parse_url(cls, url):
        if url.isdigit():
            return url
        
        match = POST_REGEXP.match(url)
        if match:
            return match.group('post_id')
        
        match = FANCLUB_REGEXP.match(url)
        if match:
            return Dynamic({
                'creator_id': match.group('fanclub_id')
            })
        
        return None
    
    async def init(self):
        self.http.headers.update({
            'Origin': 'https://fantia.jp/',
            'Referer': 'https://fantia.jp/'
        })
        self.http.cookie_jar.update_cookies({
            '_session_id': self.config.session_id
        })
    
    async def _get_csrf_token(self, post_id):
        async with self.http.get(POST_FORMAT.format(post_id=post_id)) as response:
            response.raise_for_status()
            html = BeautifulSoup(await response.text(), 'html.parser')
            meta_tag = html.select('meta[name="csrf-token"]')[0]
            return str(meta_tag['content'])
    
    async def _content_to_post(self, post_data, content_data):
        creator_id = str(post_data.fanclub.id)
        creator_name = post_data.fanclub.user.name
        # possible timezone issues?
        post_time = dateutil.parser.parse(post_data.posted_at)
        
        post = PostDetails()
        
        post.url = CONTENT_FORMAT.format(post_id=post_data.id, content_id=content_data.id)
        post.title = content_data.title
        post.comment = content_data.comment
        post.type = PostType.collection
        post.post_time = post_time
        
        if content_data.plan is not None:
            post.metadata['price'] = content_data.plan.price
        
        if post_data.liked is True:
            post.is_favorite = True
        
        post.tags.append(TagDetails(
            category=TagCategory.artist,
            tag=creator_id,
            metadata={'name': creator_name}
        ))
        
        for tag in post_data.tags:
            post.tags.append(TagDetails(
                category=TagCategory.general,
                tag=tag.name
            ))
        
        if post_data.rating == 'adult':
            post.tags.append(TagDetails(
                category=TagCategory.meta,
                tag='nsfw'
            ))
        
        if content_data.category == 'file':
            post.files.append(FileDetails(
                url=parse_href(post.url, content_data.download_uri),
                filename=content_data.filename,
                order=0
            ))
            
        elif content_data.category == 'photo_gallery':
            for order, photo in enumerate(content_data.post_content_photos):
                post.files.append(FileDetails(
                    url=parse_href(post.url, photo.url.original),
                    identifier=str(photo.id),
                    order=order
                ))
            
        elif content_data.category == 'text':
            # there are no files to save
            post.type = PostType.set
            
        elif content_data.category == 'blog':
            sections = Dynamic.from_json(content_data.comment).ops
            blog = []
            order = 0
            for section in sections:
                insert = section.insert
                if isinstance(insert, str):
                    blog.append({
                        'type': 'text',
                        'content': insert
                    })
                    
                elif isinstance(insert, dict):
                    fantiaImage = insert.get('fantiaImage')
                    image = insert.get('image')
                    if fantiaImage is not None:
                        photo_id = str(fantiaImage.id)
                        
                        post.files.append(FileDetails(
                            url=parse_href(post.url, fantiaImage.original_url),
                            identifier=photo_id,
                            order=order
                        ))
                        
                        blog.append({
                            'type': 'file',
                            'metadata': photo_id
                        })
                        
                        order += 1
                        
                    elif image is not None:
                        # not sure what this does tbh
                        image_id = '0:' + re.split(r'[\/.]', image)[-2]
                        post.files.append(FileDetails(
                            url=parse_href(post.url, image),
                            identifier=image_id,
                            order=order
                        ))
                        
                        blog.append({
                            'type': 'file',
                            'metadata': image_id
                        })
                        
                        order += 1
                        
                    else:
                        self.log.warning(f'unknown blog insert: {str(insert)}')
            
            post.comment = Dynamic({'comment': blog}).to_json()
            post.type = PostType.blog
            
        elif content_data.category == 'product':
            post.related.append(parse_href(post.url, content_data.product.uri))
            
        else:
            raise NotImplementedError('unknown content category: {}'.format(content_data.category))
        
        return post
    
    async def download(self, post_id, post_data=None):
        csrf = await self._get_csrf_token(post_id)
        headers = {
            'X-CSRF-Token': csrf,
            'X-Requested-With': 'XMLHttpRequest'
        }
        
        if post_data is None:
            async with self.http.get(POST_GET_URL.format(post_id=post_id), headers=headers) as response:
                response.raise_for_status()
                post_data = Dynamic.from_json(await response.text()).post
        
        id_parts = post_id.split('-')
        if len(id_parts) == 2:
            content_id = int(id_parts[1])
            
            content = next((c for c in post_data.post_contents if c.id == content_id), None)
            
            if content is not None and content.visible_status == 'visible':
                return await self._content_to_post(post_data, content)
            
            if content is not None:
                raise Exception('content not found')
            else:
                # maybe we could try getting something out of it
                raise Exception('content is not accessible')
        
        post = PostDetails()
        
        creator_id = str(post_data.fanclub.id)
        creator_name = post_data.fanclub.user.name
        # possible timezone issues?
        post_time = dateutil.parser.parse(post_data.posted_at)
        
        post.url = POST_FORMAT.format(post_id=post_id)
        post.title = post_data.title
        post.comment = post_data.comment
        post.type = PostType.collection
        post.post_time = post_time
        
        if post_data.liked is True:
            post.is_favorite = True
        
        post.tags.append(TagDetails(
            category=TagCategory.artist,
            tag=creator_id,
            metadata={'name': creator_name}
        ))
        
        for tag in post_data.tags:
            post.tags.append(TagDetails(
                category=TagCategory.general,
                tag=tag.name
            ))
        
        if post_data.rating == 'adult':
            post.tags.append(TagDetails(
                category=TagCategory.meta,
                tag='nsfw'
            ))
        
        post.files.append(FileDetails(
            url=parse_href(post.url, post_data.thumb.original),
            order=0
        ))
        
        # convert the post contents to posts as well
        for content in post_data.post_contents:
            if content.visible_status == 'visible':
                content_post = await self._content_to_post(post_data, content)
                # TODO need to pass the new post id to each related post
                post.related.append((f'{post_id}-{content.id}', content_post))
        
        return post
    
    async def probe_query(self, query):
        async with self.http.get(FANCLUB_URL.format(fanclub_id=query.creator_id)) as html_response:
            html_response.raise_for_status()
            html = BeautifulSoup(await html_response.text(), 'html.parser')
        
        async with self.http.get(FANCLUB_GET_URL.format(fanclub_id=query.creator_id)) as response:
            response.raise_for_status()
            fanclub = Dynamic.from_json(await response.text()).fanclub
        
        related_urls = {str(x['href']) for x in html.select('main .btns:not(.share-btns) a')}
        
        return SearchDetails(
            identifier=f'posts:{query.creator_id}',
            hint=fanclub.user.name,
            title=fanclub.name,
            description=fanclub.comment,
            thumbnail_url=fanclub.icon.main,
            related_urls=list(related_urls)
        )
    
    async def iterate_query(self, query, state, begin_at=None):
        post_id = begin_at
        if post_id is None:
            async with self.http.get(FANCLUB_GET_URL.format(fanclub_id=query.creator_id)) as response:
                response.raise_for_status()
                fanclub = Dynamic.from_json(await response.text()).fanclub
            
            if not fanclub.recent_posts:
                return
            
            # begin at first post
            post_id = fanclub.recent_posts[0].id
        
        while True:
            headers = {
                'X-CSRF-Token': await self._get_csrf_token(post_id),
                'X-Requested-With': 'XMLHttpRequest',
            }
            
            async with self.http.get(POST_GET_URL.format(post_id=post_id), headers=headers) as response:
                was_deleted = (response.status == 404)
                if was_deleted:
                    raise Exception('post was deleted...')
                response.raise_for_status()
                post = Dynamic.from_json(await response.text()).post
            
            # the wrapper will automatically skip the begin_at post if not None
            
            sort_index = int(post.id)
            yield sort_index, str(post.id), post
            
            next_post = post.links.previous
            if next_post is None:
                break
            
            post_id = next_post.id

Plugin = Fantia
