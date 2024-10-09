import re
from datetime import datetime, timezone
from tempfile import mkstemp
import functools
import dateutil.parser
import yarl

from bs4 import BeautifulSoup

from hoordu.models import *
from hoordu.plugins import *
from hoordu.forms import *
from hoordu.dynamic import Dynamic
from hoordu.plugins.helpers import parse_href


POST_REGEXP = [
    re.compile(r'^https?:\/\/subscribestar\.adult\/posts\/(?P<post_id>\d+)(?:\/.*)?(?:\?.*)?$', flags=re.IGNORECASE),
]
USER_REGEXP = re.compile(r'^https?:\/\/subscribestar\.adult\/(?P<user>[^\/]+)(?:\/.*)?(?:\?.*)?$', flags=re.IGNORECASE)


class SubStar(PluginBase):
    source = 'subscribe-star'
    
    @classmethod
    def config_form(cls):
        return Form(f'{cls.source} config',
            ('personalization_id', Input('_personalization_id cookie', [validators.required()])),
            ('subscribestar_session', Input('_subscribestar_session cookie', [validators.required()])),
            ('auth_tracker_code', Input('auth_tracker_code cookie', [validators.required()])),
            ('cf_clearance', Input('cf_clearance cookie', [validators.required()])),
            ('two_factor_auth_token', Input('two_factor_auth_token cookie', [validators.required()])),
        )
    
    @classmethod
    def search_form(cls):
        return Form(f'{cls.source} search',
            ('user', Input('username', [validators.required()]))
        )
    
    async def init(self):
        self.http.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        })
        self.http.cookie_jar.update_cookies({
            '_personalization_id': self.config.personalization_id,
            '_subscribestar_session': self.config.subscribestar_session,
            'auth_tracker_code': self.config.auth_tracker_code,
            'cf_clearance': self.config.cf_clearance,
            'two_factor_auth_token': self.config.two_factor_auth_token,
            
            '18_plus_agreement_generic': 'true',
            'cookies_accepted': 'true',
        })
    
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
            return Dynamic({
                'user': user
            })
        
        return None
    
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
    
    def _convert_hidden_post(self, url, post_data):
        post = PostDetails()
        
        original_id = post_data.attrs['data-id']
        if not original_id:
            raise APIError('post_id not found in the page')
        
        post.url = url
        post.title = self._get_text(post_data, '.post-title h2')
        post.comment = None
        post.type = PostType.set
        
        post_date = self._get_text(post_data, '.post-date')
        if post_date is None:
            post_date = self._get_text(post_data, '.section-subtitle')
        
        post.post_time = dateutil.parser.parse(post_date).replace(tzinfo=None)
        
        user_els = post_data.select('.post-avatar')
        if not user_els:
            user_els = post_data.select('.star_link')
            
        user = user_els[0].attrs['href'].lstrip('/')
        
        post.tags.append(TagDetails(
            category=TagCategory.artist,
            tag=user
        ))
        
        tags = post_data.select('.post-tag')
        if tags:
            for tag_element in tags:
                tagname = tag_element.text.replace(' ', '_')
                post.tags.append(TagDetails(
                    category=TagCategory.general,
                    tag=tagname
                ))
        
        return post
    
    def _convert_post(self, url, post_data):
        post = PostDetails()
        
        post.url = url
        post.title = self._get_text(post_data, '.post-content > h1:first-child')
        post.comment = self._get_text(post_data, '.post-content > :not(h1:first-child)')
        post.type = PostType.set
        
        post_date = self._get_text(post_data, '.post-date')
        if post_date is None:
            post_date = self._get_text(post_data, '.section-subtitle')
        
        if post_date is None:
            post_date = self._get_text(post_data, '.section-title .star_link-types')
        
        print(post_date)
        
        post.post_time = dateutil.parser.parse(post_date).replace(tzinfo=None)
        
        user_els = post_data.select('.post-avatar')
        if not user_els:
            user_els = post_data.select('.star_link')
            
        user = user_els[0].attrs['href'].lstrip('/')
        
        post.tags.append(TagDetails(
            category=TagCategory.artist,
            tag=user
        ))
        
        tags = post_data.select('.post-tag')
        if tags:
            for tag_element in tags:
                tagname = tag_element.text.replace(' ', '_')
                post.tags.append(TagDetails(
                    category=TagCategory.general,
                    tag=tagname
                ))
        
        gallery = []
        gallery_els = post_data.select('[data-gallery]')
        if gallery_els:
            gallery = Dynamic.from_json(gallery_els[0].attrs['data-gallery'])
        
        if len(gallery) > 0:
            order = 0
            for rfile in gallery:
                post.files.append(FileDetails(
                    url=parse_href(url, rfile.url),
                    filename=rfile.original_filename,
                    identifier=str(rfile.id),
                    order=order
                ))
                
                order += 1
        
        docs = post_data.select('.uploads-docs .doc_preview')
        if len(docs) > 0:
            order = 10000
            for doc in docs:
                anchor = doc.select('a')[0]
                
                post.files.append(FileDetails(
                    url=parse_href(url, anchor.attrs['href']),
                    filename=self._get_text(anchor, '.doc_preview-title'),
                    identifier=str(doc.attrs['data-upload-id']),
                    order=order
                ))
                
                order += 1
        
        return post
    
    async def download(self, post_id, post_data=None):
        url = f'https://subscribestar.adult/posts/{post_id}'
        
        if post_data is None:
            async with self.http.get(url) as response:
                response.raise_for_status()
                post_data = BeautifulSoup(await response.text(), 'html.parser')
        
        post_id_el = post_data.select('[data-post_id]')
        is_accessible = len(post_id_el) > 0
        
        if is_accessible:
            return self._convert_post(url, post_data)
            
        else:
            return self._convert_hidden_post(url, post_data)
    
    async def probe_query(self, query):
        if query.user_id is None:
            url = f'https://subscribestar.adult/{query.user}'
            async with self.http.get(url) as response:
                response.raise_for_status()
                page_html = BeautifulSoup(await response.text(), 'html.parser')
            
            posts_href = page_html.select('.posts-more')[0].attrs['href']
            query.user_id = yarl.URL(posts_href).query['star_id']
        
        return SearchDetails(
            identifier=query.user,
            hint=query.user,
            title=query.user
        )
    
    async def iterate_query(self, query, state, begin_at=None):
        main_url = f'https://subscribestar.adult/{query.user}'
        next_page = None
        
        if begin_at is not None:
            page_end_order = state.get('page_end_order')
            if page_end_order == -1:
                return
                
            else:
                next_page = f'https://subscribestar.adult/posts?page_end_order_position={page_end_order}&star_id={query.user_id}'
        
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
                    json_response = Dynamic.from_json(await response.text())
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
                post_id = post.attrs['data-id']
                yield int(post_id), post_id, post
            
            if next_page is not None:
                if begin_at is not None or 'page_end_order' not in state:
                    state['page_end_order'] = yarl.URL(next_page).query['page_end_order_position']
                
            else:
                state['page_end_order'] = -1
                return

# TODO test this whole thing

Plugin = SubStar


