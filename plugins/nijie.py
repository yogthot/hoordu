import re
import itertools
import dateutil.parser
import httpx

from bs4 import BeautifulSoup

import hoordu
from hoordu.models import *
from hoordu.plugins import *
from hoordu.forms import *
from hoordu.plugins.helpers import parse_href

POST_URL = ['nijie.info/view.php', 'www.nijie.info/view.php']
USER_URL = [
    'nijie.info/members.php',
    'nijie.info/members_illust.php',
    'nijie.info/members_dojin.php',
]

class Nijie(PluginBase):
    source = 'nijie'
    
    @classmethod
    def config_form(cls):
        return Form(f'{cls.source} config',
            ('NIJIEIJIEID', Input('NIJIEIJIEID cookie', [validators.required()])),
            ('nijie_tok', Input('nijie_tok cookie', [validators.required()])),
        )
    
    @classmethod
    def search_form(cls):
        return Form(f'{cls.source} search',
            ('user_id', Input('user id', [validators.required()]))
        )
    
    async def init(self):
        self.http.cookies.update({
            'NIJIEIJIEID': self.config.NIJIEIJIEID,
            'nijie_tok': self.config.nijie_tok,
        })
    
    @classmethod
    async def parse_url(cls, url):
        if url.isdigit():
            return url
        
        parsed = httpx.URL(url)
        part = parsed.host + parsed.path
        
        if part in POST_URL:
            return parsed.query['id']
        
        if part in USER_URL:
            return hoordu.Dynamic({
                'user_id': parsed.query['id']
            })
        
        return None
    
    async def download(self, post_id, post_data=None):
        post_url = str(httpx.URL('https://nijie.info/view.php').copy_add_param('id', post_id))
        
        if post_data is None:
            response = await self.http.get(post_url)
            response.raise_for_status()
            post_data = BeautifulSoup(response.text, 'html.parser')
        
        post_files = post_data.select("#gallery .mozamoza")
        user_id = post_files[0]['user_id']
        if not isinstance(user_id, str):
            raise APIError('failed to find user id')
        
        user_name = list(post_data.select("#pro .name")[0].children)[2]
        
        timestamp = post_data.select("#view-honbun span")[0].text.split('：', 1)[-1]
        
        post = PostDetails()
        post.url = post_url
        post.title = post_data.select('.illust_title')[0].text
        post.type = PostType.set
        post.post_time = dateutil.parser.parse(timestamp)
        
        comment_html = post_data.select('#illust_text')[0]
        
        urls = []
        page_url = f'https://nijie.info/view.php?id={post_id}'
        for a in comment_html.select('a'):
            url = parse_href(page_url, a['href'])
            urls.append(url)
            
            a.replace_with(url)
        
        for br in comment_html.find_all('br'):
            br.replace_with('\n')
        
        for para in comment_html.find_all('p'):
            para.replace_with(para.text + '\n')
        
        post.comment = comment_html.text
        
        post.tags.append(TagDetails(
            category=TagCategory.artist,
            tag=user_id,
            metadata={'name': user_name}
        ))
        
        tags = post_data.select('#view-tag li.tag a')
        for tag in tags:
            post.tags.append(TagDetails(
                category=TagCategory.general,
                tag=tag.text
            ))
        
        for url in urls:
            post.related.append(url)
        
        # files
        response = await self.http.get('https://nijie.info/view_popup.php', params={'id': post_id})
        response.raise_for_status()
        popup = BeautifulSoup(response.text, 'html.parser')
        
        files = popup.select('#img_window a > *:not(.view_filter)')
        if len(files) != len(post_files):
            raise APIError(f'inconsistent files, please review the scraper ({len(files)}, {len(post_files)})')
        
        for file, order in zip(files, itertools.count(1)):
            tag = file.name.lower()
            if tag not in ('img', 'video'):
                raise APIError(f'unknown file type: {tag}')
            
            orig_url = parse_href(page_url, file['src'])
            
            post.files.append(FileDetails(
                url=orig_url,
                order=order
            ))
        
        return post
    
    async def probe_query(self, query):
        response = await self.http.get('https://nijie.info/members.php', params={'id': query.user_id})
        response.raise_for_status()
        html = BeautifulSoup(response.text, 'html.parser')
        
        user_name = list(html.select("#pro .name")[0].children)[2]
        thumbnail_url = html.select("#pro img")[0]['src'].replace("__rs_cs150x150/", "")
        
        
        desc_html = html.select('#prof-l')[0]
        
        urls = list()
        for a in desc_html.select('a'):
            url = a.text
            urls.append(url)
            
            a.replace_with(url)
        
        for dt in desc_html.find_all('dt'):
            dt.replace_with(dt.text + ' | ')
        
        for dd in desc_html.find_all('dd'):
            dd.replace_with(dd.text + '\n')
        
        return SearchDetails(
            identifier=f'user:{query.user_id}',
            hint=user_name.text,
            title=user_name.text,
            description=desc_html.text,
            thumbnail_url=thumbnail_url,
            related_urls=urls
        )
    
    async def iterate_query(self, query, state, begin_at=None):
        page_id = 1 if begin_at is None else state.get('page_id', 1)
        
        try:
            while True:
                # ?p={page_id (1 indexed)}&id={user_id}
                params = {
                    'p': page_id,
                    'id': query.user_id,
                }
                response = await self.http.get('https://nijie.info/members_illust.php', params=params)
                response.raise_for_status()
                html = BeautifulSoup(response.text, 'html.parser')
                
                post_urls = [e['href'] for e in html.select('#members_dlsite_left .picture a')]
                post_ids = [int(httpx.URL(url).params['id']) for url in post_urls]
                
                if len(post_ids) == 0:
                    # empty page, stopping
                    return
                
                for post_id in post_ids:
                    yield post_id, str(post_id), None
                
                page_id += 1
            
        finally:
            if begin_at is not None or 'page_id' not in state:
                state['page_id'] = page_id

Plugin = Nijie
