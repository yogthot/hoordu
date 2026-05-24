import re
import dateutil.parser
import itertools
import httpx

from bs4 import BeautifulSoup

from hoordu.dynamic import Dynamic
from hoordu.plugins import *
from hoordu.models.common import *
from hoordu.forms import *

CREATOR_URL_REGEXP = re.compile(r'https?:\/\/(?P<creator>[^\.]+)\.fanbox\.cc\/', flags=re.IGNORECASE)

POST_FORMAT = 'https://fanbox.cc/@{creator}/posts/{post_id}'
POST_REGEXP = [
    re.compile(r'^https?:\/\/(?P<creator>[^\.]+)\.fanbox\.cc\/posts\/(?P<post_id>\d+)(?:\?.*)?(?:#.*)?$', flags=re.IGNORECASE),
    re.compile(r'^https?:\/\/(?:www\.)?fanbox\.cc\/@(?P<creator>[^\/]*)\/posts\/(?P<post_id>\d+)(?:\?.*)?(?:#.*)?$', flags=re.IGNORECASE)
]
CREATOR_REGEXP = [
    re.compile(r'^https?:\/\/(?:www\.)?fanbox\.cc\/@(?P<creator>[^\/]+)(?:\/.*)?(?:\?.*)?(?:#.*)?$', flags=re.IGNORECASE),
    re.compile(r'^https?:\/\/(?P<creator>[^\.]+)\.fanbox\.cc(?:\/.*)?(?:\?.*)?(?:#.*)?$', flags=re.IGNORECASE),
]

POST_EMBED_INFO_URL = 'https://api.fanbox.cc/post.get?postId={related_post_id}'


class Fanbox(PluginBase):
    source = 'fanbox'
    
    @classmethod
    def config_form(cls):
        return Form(f'{cls.source} config',
            ('FANBOXSESSID', Input('FANBOXSESSID cookie', [validators.required()]))
        )
    
    @classmethod
    def search_form(cls):
        return Form('{self.source} search',
            ('creator', Input('creator', [validators.required()]))
        )
    
    async def init(self):
        self.http.headers.update({
            'Origin': 'https://www.fanbox.cc',
            'Referer': 'https://www.fanbox.cc/',
            'Alt-Used': 'api.fanbox.cc',
        })
        self.http.cookies.update({
            'FANBOXSESSID': self.config.FANBOXSESSID,
        })
    
    @classmethod
    async def parse_url(cls, url):
        if url.isdigit():
            return url
        
        for regexp in POST_REGEXP:
            match = regexp.match(url)
            if match:
                return match.group('post_id')
        
        for regexp in CREATOR_REGEXP:
            match = regexp.match(url)
            if match:
                return Dynamic({
                    'creator': match.group('creator')
                })
        
        return None
    
    async def download(self, post_id, post_data=None):
        response = await self.http.get(f'https://api.fanbox.cc/post.info?postId={post_id}')
        response.raise_for_status()
        post_data = Dynamic.from_json(response.text).body
        
        if post_data.isRestricted:
            self.log.warning('inaccessible post %s', post_id)
        
        main_id = post_data.id
        creator_id = post_data.user.userId
        creator_slug = post_data.creatorId
        creator_name = post_data.user.name
        
        post = PostDetails()
        post.type = PostType.collection
        post.url = POST_FORMAT.format(creator=creator_slug, post_id=main_id)
        post.title = post_data.title
        post.post_time = dateutil.parser.parse(post_data.publishedDatetime)
        
        if post_data.feeRequired != 0:
            post.metadata['price'] = post_data.feeRequired
        
        if post_data.isLiked is True:
            post.is_favorite = True
        
        post.tags.append(TagDetails(TagCategory.artist, creator_id, metadata={'name': creator_name, 'slug': creator_slug}))
        
        for tag in post_data.tags:
            post.tags.append(TagDetails(TagCategory.general, tag))
        
        if post_data.hasAdultContent is True:
            post.tags.append(TagDetails(TagCategory.meta, 'nsfw'))
        
        if not post_data.isRestricted:
            if post_data.type == 'image':
                post.comment = post_data.body.text
                
                for image, order in zip(post_data.body.images, itertools.count(1)):
                    post.files.append(FileDetails(
                        url=image.originalUrl,
                        order=order,
                        identifier=f'i-{image.id}'
                    ))
                
            elif post_data.type == 'file':
                post.comment = post_data.body.text
                
                for rfile, order in zip(post_data.body.files, itertools.count(1)):
                    post.files.append(FileDetails(
                        url=rfile.url,
                        filename=f'{rfile.name}.{rfile.extension}',
                        order=order,
                        identifier=f'f-{rfile.id}'
                    ))
                
            elif post_data.type == 'article':
                imagemap = post_data.body.get('imageMap')
                filemap = post_data.body.get('fileMap')
                embedmap = post_data.body.get('embedMap')
                urlembedmap = post_data.body.get('urlEmbedMap')
                
                order = 1
                
                blog = []
                for block in post_data.body.blocks:
                    if block.type in ('p', 'header'):
                        links = block.get('links')
                        if links is not None:
                            for link in links:
                                url = link.url
                                post.related.append(url)
                        
                        blog.append({
                            'type': 'text',
                            'content': block.text + '\n'
                        })
                        
                    elif block.type == 'image':
                        file_id = f'i-{block.imageId}'
                        post.files.append(FileDetails(
                            url=imagemap[block.imageId].originalUrl,
                            identifier=file_id,
                            order=order
                        ))
                        order += 1
                        
                        blog.append({
                            'type': 'file',
                            'metadata': file_id
                        })
                        
                    elif block.type == 'file':
                        file_id = f'f-{block.fileId}'
                        post.files.append(FileDetails(
                            url=filemap[block.fileId].url,
                            filename=f'{filemap[block.fileId].name}.{filemap[block.fileId].extension}',
                            identifier=file_id,
                            order=order,
                        ))
                        order += 1
                        
                        blog.append({
                            'type': 'file',
                            'metadata': file_id
                        })
                        
                    elif block.type == 'embed':
                        embed = embedmap[block.embedId]
                        
                        url = None
                        if embed.serviceProvider == 'fanbox':
                            related_post_id = embed.contentId.split('/')[-1]
                            
                            response = await self.http.get(POST_EMBED_INFO_URL.format(related_post_id=related_post_id))
                            response.raise_for_status()
                            related_post_body = Dynamic.from_json(response.text).body
                            
                            url = POST_FORMAT.format(creator=related_post_body.creatorId, post_id=related_post_id)
                            
                        elif embed.serviceProvider == 'google_forms':
                            url = 'https://docs.google.com/forms/d/e/{}/viewform'.format(embed.contentId)
                            
                        elif embed.serviceProvider == 'twitter':
                            url = 'https://x.com/i/web/status/{}'.format(embed.contentId)
                            
                        else:
                            self.log.warning('unknown embed service provider: %s', str(embed.serviceProvider))
                        
                        if url:
                            post.related.append(url)
                            
                            blog.append({
                                'type': 'text',
                                'content': url + '\n'
                            })
                        
                    elif block.type == 'url_embed':
                        urlembed = urlembedmap[block.urlEmbedId]
                        
                        url = None
                        if urlembed.type == 'fanbox.post':
                            related_post_id = urlembed.postInfo.id
                            related_creator_id = urlembed.postInfo.creatorId
                            url = POST_FORMAT.format(creator=related_creator_id, post_id=related_post_id)
                            
                        elif urlembed.type in ('html', 'html.card'):
                            embed_html = BeautifulSoup(urlembed.html, 'html.parser')
                            iframes = embed_html.select('iframe')
                            if len(iframes) >= 1:
                                src = iframes[0]['src']
                                if isinstance(src, str):
                                    url = src
                                else:
                                    url = src[0]
                            else:
                                self.log.warning('no iframe found on html/card embed: %s', str(urlembed.html))
                            
                        else:
                            self.log.warning('unknown url_embed type: %s', str(urlembed.type))
                        
                        if url:
                            post.related.append(url)
                            
                            blog.append({
                                'type': 'text',
                                'content': url + '\n'
                            })
                        
                    else:
                        self.log.warning('unknown blog block: %s', str(block.type))
                
                post.comment = Dynamic({'comment': blog}).to_json()
                post.type = PostType.blog
                
            elif post_data.type == 'text':
                post.comment = post_data.body.text
                post.type = PostType.set
                
            else:
                raise NotImplementedError('unknown post type: {}'.format(post.type))
        
        async def unwind_framely(url):
            if 'cdn.iframe.ly' in url:
                resp = await self.http.get(url)
                try:
                    resp.raise_for_status()
                    url = re.search(r'"linkUri":"([^"]*)"', resp.text).group(1)
                except:
                    pass
            
            return url
        
        post.related = [await unwind_framely(url) for url in post.related]
        
        return post
    
    async def probe_query(self, query):
        pixiv_id = query.get('pixiv_id')
        
        if pixiv_id:
            response = await self.http.get(f'https://www.pixiv.net/fanbox/creator/{pixiv_id}', follow_redirects=False)
            creator_url = response.headers['Location']
            
            creator_id = CREATOR_URL_REGEXP.match(creator_url).group('creator')
            
        else:
            creator_id = query.creator
        
        response = await self.http.get(f'https://api.fanbox.cc/creator.get?creatorId={creator_id}')
        response.raise_for_status()
        creator = Dynamic.from_json(response.text).body
        
        query.creator = creator_id
        query.pixiv_id = creator.user.userId
        
        related_urls = creator.profileLinks
        related_urls.append(f'https://www.pixiv.net/en/users/{query.pixiv_id}')
        
        return SearchDetails(
            identifier=f'posts:{query.pixiv_id}',
            hint=creator.creatorId,
            title=creator.user.name,
            description=creator.description,
            thumbnail_url=creator.user.iconUrl,
            related_urls=creator.profileLinks
        )
    
    async def iterate_query(self, query, state, begin_at=None):
        await self.probe_query(query)
        
        pinned_post = None
        
        page_params = {
            'creatorId': query.creator
        }
        response = await self.http.get('https://api.fanbox.cc/post.paginateCreator', params=page_params)
        response.raise_for_status()
        pages = Dynamic.from_json(response.text).body
        
        if begin_at is None:
            page_id = 0
        else:
            page_map = [int(httpx.URL(page).params['maxId']) for page in pages]
            page_id = next((i for i, p in enumerate(page_map) if p < begin_at), len(page_map))
            page_id = max(page_id - 1, 0)
        
        while True:
            if page_id >= len(pages):
                return
            
            response = await self.http.get(pages[page_id])
            response.raise_for_status()
            posts = Dynamic.from_json(response.text).body
            
            for post in posts:
                if post.isPinned:
                    if pinned_post is not None:
                        raise Exception('more than 1 pinned post detected')
                    
                    pinned_post = post
                    continue
                
                sort_index = int(post.id)
                
                if pinned_post is not None and sort_index < int(pinned_post.id):
                    yield int(pinned_post.id), pinned_post.id, None
                    pinned_post = None
                
                yield sort_index, post.id, None
            
            page_id += 1

Plugin = Fanbox
