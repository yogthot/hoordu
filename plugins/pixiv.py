import re
import dateutil.parser
from urllib.parse import unquote
from xml.sax.saxutils import unescape

from bs4 import BeautifulSoup

from hoordu.models import *
from hoordu.plugins import *
from hoordu.forms import *
from hoordu.dynamic import Dynamic
from hoordu.plugins.helpers import parse_href

POST_FORMAT = 'https://www.pixiv.net/artworks/{post_id}'
FANBOX_URL_FORMAT = 'https://www.pixiv.net/fanbox/creator/{user_id}'
POST_REGEXP = [
    re.compile(r'^(?P<post_id>\d+)_p\d+\.[a-zA-Z0-9]+$'),
    re.compile(r'^https?:\/\/(?:www\.)?pixiv\.net\/(?:[a-zA-Z]{2}\/)?artworks\/(?P<post_id>\d+)(?:\?.*)?(?:#.*)?$', flags=re.IGNORECASE)
]
USER_REGEXP = [
    re.compile(r'^https?:\/\/(?:www\.)?pixiv\.net\/(?:[a-zA-Z]{2}\/)?users\/(?P<user_id>\d+)(?:\/illustration|\/manga)?(?:\?.*)?(?:#.*)?$', flags=re.IGNORECASE)
]
BOOKMARKS_REGEXP = [
    re.compile(r'^https?:\/\/(?:www\.)?pixiv\.net\/(?:[a-zA-Z]{2}\/)?users\/(?P<user_id>\d+)\/bookmarks\/artworks(?:\?.*)?(?:#.*)?$', flags=re.IGNORECASE)
]
REDIRECT_REGEXP = re.compile(r'^https?:\/\/(?:www\.)?pixiv\.net\/jump\.php\?(?P<url>.*)$', flags=re.IGNORECASE)

USER_URL = 'https://www.pixiv.net/en/users/{user_id}'
USER_API_URL = 'https://www.pixiv.net/ajax/user/{user_id}?full=1&lang=ja'
POST_GET_URL = 'https://www.pixiv.net/ajax/illust/{post_id}'
POST_PAGES_URL = 'https://www.pixiv.net/ajax/illust/{post_id}/pages'
POST_UGOIRA_URL = 'https://www.pixiv.net/ajax/illust/{post_id}/ugoira_meta'
USER_POSTS_URL = 'https://www.pixiv.net/ajax/user/{user_id}/profile/all'
USER_BOOKMARKS_URL = 'https://www.pixiv.net/ajax/user/{user_id}/illusts/bookmarks'
BOOKMARKS_LIMIT = 48

class Pixiv(PluginBase):
    source = 'pixiv'
    
    @classmethod
    def config_form(cls):
        return Form(f'{cls.source} config',
            ('PHPSESSID', Input('PHPSESSID cookie', [validators.required()]))
        )
    
    @classmethod
    def search_form(cls):
        return Form(f'{cls.source} search',
            ('method', ChoiceInput('method', [
                    ('illusts', 'illustrations'),
                    ('bookmarks', 'bookmarks')
                ], [validators.required()])),
            ('user_id', Input('user id', [validators.required()]))
        )
    
    @classmethod
    async def parse_url(cls, url):
        if url.isdigit():
            return url
        
        for regexp in POST_REGEXP:
            match = regexp.match(url)
            if match:
                return match.group('post_id')
        
        for regexp in USER_REGEXP:
            match = regexp.match(url)
            if match:
                return Dynamic({
                    'method': 'illusts',
                    'user_id': match.group('user_id')
                })
        
        for regexp in BOOKMARKS_REGEXP:
            match = regexp.match(url)
            if match:
                return Dynamic({
                    'method': 'bookmarks',
                    'user_id': match.group('user_id')
                })
        
        return None
    
    async def init(self):
        self.http.headers.update({
            'Referer': 'https://www.pixiv.net/'
        })
        self.http.cookie_jar.update_cookies({
            'PHPSESSID': self.config.PHPSESSID
        })
    
    async def download(self, post_id, post_data=None):
        if post_data is None:
            async with self.http.get(POST_GET_URL.format(post_id=post_id)) as resp:
                resp.raise_for_status()
                post_resp = Dynamic.from_json(await resp.text())
        
            if post_resp.error is True:
                self.log.error('pixiv api error: %s', post_resp.message)
                raise APIError(post_resp.message)
            
            post_data = post_resp.body
        
        post = PostDetails()
        
        post.url = POST_FORMAT.format(post_id=post_id)
        post.title = post_data.title
        post.type = PostType.collection if post_data.illustType == 1 else PostType.set
        post.post_time = dateutil.parser.parse(post_data.createDate)
        
        post.extensions = {
            'user_name': post_data.userName,
            'user_handle': post_data.userAccount,
            'user_url': f'https://www.pixiv.net/users/{post_data.userId}',
            'user_icon': next((p.profileImageUrl for p in post_data.userIllusts.values() if p and 'profileImageUrl' in p), None),
        }
        
        # there is no visual difference in multiple whitespace (or newlines for that matter)
        # unless inside <pre>, but that's too hard to deal with :(
        description = re.sub(r'\s+', ' ', post_data.description)
        comment_html = BeautifulSoup(description, 'html.parser')
        
        page_url = POST_FORMAT.format(post_id=post_id)
        for a in comment_html.select('a'):
            url = parse_href(page_url, a['href'])
            match = REDIRECT_REGEXP.match(url)
            if match:
                url = unquote(match.group('url'))
                post.related.append(url)
                
            else:
                post.related.append(url)
            
            a.replace_with(url)
        
        for br in comment_html.find_all('br'):
            br.replace_with('\n')
        
        post.comment = comment_html.text
        
        if post_data.likeData:
            post.is_favorite = True
        
        post.tags.append(TagDetails(
            category=TagCategory.artist,
            tag=post_data.userId,
            metadata={'name': post_data.userName, 'account': post_data.userAccount}
        ))
        
        for tag in post_data.tags.tags:
            metadata = {}
            if tag.contains('romaji'):
                metadata['romaji'] = tag.romaji
            
            post.tags.append(TagDetails(
                category=TagCategory.general,
                tag=tag.tag,
                metadata=metadata
            ))
        
        if post_data.xRestrict >= 1:
            post.tags.append(TagDetails(
                category=TagCategory.meta,
                tag='nsfw',
            ))
            
        if post_data.xRestrict >= 2:
            post.tags.append(TagDetails(
                category=TagCategory.meta,
                tag='extreme',
            ))
        
        if post_data.isOriginal:
            post.tags.append(TagDetails(
                category=TagCategory.copyright,
                tag='original',
            ))
        
        if post_data.illustType == 2:
            # ugoira
            async with self.http.get(POST_UGOIRA_URL.format(post_id=post_id)) as resp:
                resp.raise_for_status()
                ugoira_meta = Dynamic.from_json(await resp.text()).body
            
            post.files.append(FileDetails(
                url=ugoira_meta.originalSrc,
                order=0,
                metadata=Dynamic({'frames': ugoira_meta.frames}).to_json()
            ))
            
        elif post_data.pageCount == 1:
            # single file
            post.files.append(FileDetails(
                url=post_data.urls.original,
                order=0
            ))
            
        else:
            async with self.http.get(POST_PAGES_URL.format(post_id=post_id)) as resp:
                resp.raise_for_status()
                pages = Dynamic.from_json(await resp.text()).body
            
            for order, page in enumerate(pages):
                post.files.append(FileDetails(
                    url=page.urls.original,
                    order=order
                ))
        
        return post
    
    async def probe_query(self, query):
        async with self.http.get(USER_API_URL.format(user_id=query.user_id)) as resp:
            resp.raise_for_status()
            user = Dynamic.from_json(await resp.text()).body
        
        related_urls = set()
        if user.webpage:
            related_urls.add(user.webpage)
        
        # it's [] when it's empty
        if isinstance(user.social, dict):
            related_urls.update(s.url for s in user.social.values())
        
        comment_html = BeautifulSoup(user.commentHtml, 'html.parser')
        related_urls.update(a.text for a in comment_html.select('a'))
        
        async with self.http.get(FANBOX_URL_FORMAT.format(user_id=query.user_id), allow_redirects=False) as creator_response:
            if creator_response.status // 100 == 3:
                related_urls.add(creator_response.headers['Location'])
        
        return SearchDetails(
            identifier=f'{query.method}:{query.user_id}',
            hint=user.name,
            title=user.name,
            description=user.comment,
            thumbnail_url=user.imageBig,
            related_urls=list(related_urls)
        )
    
    async def iterate_user(self, query, state, begin_at=None):
        async with self.http.get(USER_POSTS_URL.format(user_id=query.user_id)) as resp:
            resp.raise_for_status()
            user_info = Dynamic.from_json(await resp.text())
        
        if user_info.error is True:
            raise APIError(user_info.message)
        
        body = user_info.body
        
        posts = []
        for bucket in ('illusts', 'manga'):
            # these are [] when empty
            if isinstance(body[bucket], dict):
                posts.extend([int(id) for id in body[bucket].keys()])
        
        posts = sorted([pid for pid in posts if begin_at is None or pid < begin_at], reverse=True)
        
        for post_id in posts:
            sort_index = int(post_id)
            yield sort_index, str(post_id), None
    
    async def iterate_bookmarks(self, query, state, begin_at=None):
        first_time = 'offset' in state
        offset = state.get('offset', 0) if begin_at is not None else 0
        
        while True:
            params = {
                'tag': '',
                'offset': str(offset),
                'limit': BOOKMARKS_LIMIT,
                'rest': 'show'
            }
            
            self.log.info('getting next page')
            async with self.http.get(USER_BOOKMARKS_URL.format(user_id=query.user_id), params=params) as resp:
                resp.raise_for_status()
                bookmarks_resp = Dynamic.from_json(await resp.text())
                
                if bookmarks_resp.error is True:
                    raise APIError(bookmarks_resp.message)
                
                bookmarks = bookmarks_resp.body.works
                
                if len(bookmarks) == 0:
                    return
                
                for bookmark in bookmarks:
                    bookmark_id = int(bookmark.bookmarkData.id)
                    post_id = bookmark.id
                    
                    async with self.http.get(POST_GET_URL.format(post_id=post_id)) as resp:
                        # skip this post if 404 (deleted bookmarks)
                        was_deleted = (resp.status == 404)
                        
                        if not was_deleted:
                            resp.raise_for_status()
                            post_resp = Dynamic.from_json(await resp.text())
                            
                            if post_resp.error is True:
                                raise APIError(post_resp.message)
                            
                            yield bookmark_id, str(post_id), post_resp.body
                        
                        if first_time or begin_at is not None:
                            state['offset'] += 1
                
                # offset for the next page
                offset += len(bookmarks)
    
    def iterate_query(self, query, state, begin_at=None):
        if query.method == 'illusts':
            return self.iterate_user(query, state, begin_at)
            
        elif query.method == 'bookmarks':
            return self.iterate_bookmarks(query, state, begin_at)
            
        else:
            raise Exception(f'unsupported method: {query.method}')

Plugin = Pixiv
