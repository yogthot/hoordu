import re
import itertools
from bs4 import BeautifulSoup

from hoordu.models import *
from hoordu.plugins import *
from hoordu.forms import *
from hoordu.dynamic import Dynamic
from hoordu.plugins.helpers import parse_href


PRODUCT_FORMAT = 'https://{account_code}.gumroad.com/l/{product_code}'
PRODUCT_REGEXP = [
    re.compile(r'^https?:\/\/(?P<account_code>[^\.]+)\.gumroad\.com\/l\/(?P<product_code>[^\/\?]+)(?:\?.*)?$', flags=re.IGNORECASE),
]


class Gumroad(PluginBase):
    source = 'gumroad'
    
    @classmethod
    def config_form(cls):
        return Form(f'{cls.source} config',
            ('gumroad_guid', Input('_gumroad_guid cookie', [validators.required()])),
            ('gumroad_app_session', Input('_gumroad_app_session cookie', [validators.required()])),
        )
    
    async def init(self):
        self.http.cookie_jar.update_cookies({
            '_gumroad_guid': self.config.gumroad_guid,
            '_gumroad_app_session': self.config.gumroad_app_session,
        })
    
    @classmethod
    async def parse_url(cls, url):
        for regexp in PRODUCT_REGEXP:
            match = regexp.match(url)
            if match:
                return match.group('account_code') + '.' + match.group('product_code')
        
        return None
    
    async def download(self, post_id, post_data=None):
        account_code, product_code = post_id.split('.')
        main_url = PRODUCT_FORMAT.format(account_code=account_code, product_code=product_code)
        
        async with self.http.get(main_url) as response:
            response.raise_for_status()
            doc = BeautifulSoup(await response.text(), 'html.parser')
        
        post_json = doc.select('script[data-component-name="ProductPage"]')[0].text
        post_data = Dynamic.from_json(post_json)
        
        post = PostDetails()
        post.title = post_data.product.name
        post.url = main_url
        post.type = PostType.set
        post.metadata = {'creator': account_code}
        
        comment_html = BeautifulSoup(post_data.product.description_html, 'html.parser')
        
        for a in comment_html.select('a'):
            url = parse_href(main_url, a['href'])
            
            post.related.append(url)
            a.replace_with(url)
        
        for br in comment_html.find_all('br'):
            br.replace_with('\n')
        
        for para in comment_html.find_all('p'):
            para.replace_with(para.text + '\n')
        
        post.comment = comment_html.text
        
        post.tags.append(TagDetails(
            category=TagCategory.artist,
            tag=account_code,
            metadata={'name': post_data.product.seller.name}
        ))
        
        
        if post_data.purchase is not None:
            # download files
            content_url = parse_href(main_url, post_data.purchase.content_url)
            async with self.http.get(content_url) as response:
                response.raise_for_status()
                doc = BeautifulSoup(await response.text(), 'html.parser')
            
            content_json = doc.select('script[data-component-name="DownloadPageWithContent"]')[0].text
            content: Dynamic = Dynamic.from_json(content_json)
            
            for item, order in zip(content.content.content_items, itertools.count(1)):
                if item.type == 'file':
                    post.files.append(FileDetails(
                        url=parse_href(content_url, item.download_url),
                        filename=f'{item.file_name}.{item.extension.lower()}',
                        order=order,
                        identifier=item.id,
                    ))
        
        return post

Plugin = Gumroad
