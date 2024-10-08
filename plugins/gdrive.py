import re
import dateutil.parser
from natsort import natsorted

from hoordu.dynamic import Dynamic
from hoordu.oauth.client import OAuth
from hoordu.plugins import *
from hoordu.models.common import *
from hoordu.forms import *


AUTH_URL = 'https://accounts.google.com/o/oauth2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
REDIRECT_URL = 'http://127.0.0.1:8941/gdrive'
SCOPES = 'https://www.googleapis.com/auth/drive.readonly'

GDRIVE_ENDPOINT = 'https://www.googleapis.com/drive/v3'
PAGE_LIMIT = 100

FOLDER_FORMAT = 'https://drive.google.com/drive/folders/{file_id}'
FILE_FORMAT = 'https://drive.google.com/file/d/{file_id}'
FILE_REGEXP = [
    re.compile(r'^https?:\/\/drive\.google\.com\/drive\/(u\/\d+\/)?folders\/(?P<file_id>[^\/\?]+)(?:\/.*)?(?:\?.*)?$', flags=re.IGNORECASE),
    re.compile(r'^https?:\/\/drive\.google\.com\/file\/d\/(?P<file_id>[^\/\?]+)(?:\/.*)?(?:\?.*)?$', flags=re.IGNORECASE)
]

LINK_MIMETYPE = 'application/vnd.google-apps.shortcut'
DIR_MIMETYPE = 'application/vnd.google-apps.folder'

FILE_URL_FORMAT = GDRIVE_ENDPOINT + '/files/{node_id}?alt=media'


class GDrive(PluginBase):
    source = 'gdrive'
    
    @classmethod
    def config_form(cls):
        return Form(f'{cls.source} config',
            ('client_id', Input('client id', [validators.required()])),
            ('client_secret', Input('client secret', [validators.required()])),
            ('access_token', Input('access token')),
            ('refresh_token', Input('refresh token'))
        )
    
    @classmethod
    async def setup(cls, config, parameters=None):
        if parameters is not None:
            config.update(parameters)
        
        if not config.contains('client_id', 'client_secret'):
            return False, cls.config_form()
        
        else:
            oauth = OAuth(**{
                'auth_endpoint': AUTH_URL,
                'token_endpoint': TOKEN_URL,
                'redirect_uri': REDIRECT_URL,
                'scopes': SCOPES,
                'client_id': config.client_id,
                'client_secret': config.client_secret
            })
            
            if not config.contains('access_token', 'refresh_token'):
                code = None
                if parameters is not None:
                    code = parameters.get('code')
                
                
                if code is None:
                    url, _, _ = oauth.auth_url(extra_args={'access_type': 'offline'})
                    
                    return False, OAuthForm('google authentication', url)
                    
                else:
                    response = await oauth.get_access_token(code)
                    config.access_token = response['access_token']
                    config.refresh_token = response['refresh_token']
                    
                    return True, None
                
            else:
                # maybe check if refreshing is needed
                tokens = await oauth.refresh_access_token(config.refresh_token)
                
                config.access_token = tokens['access_token']
                config.refresh_token = tokens.get('refresh_token', config.refresh_token)
                
                return True, None
    
    async def init(self):
        self.http.headers.update({
            'Authorization': f'Bearer {self.config.access_token}'
        })
    
    @classmethod
    async def parse_url(cls, url):
        for regexp in FILE_REGEXP:
            match = regexp.match(url)
            if match:
                return match.group('file_id')
        
        return None
    
    async def _ordered_walk(self, node, base_path=''):
        page_token = None
        nodes = []
        while True:
            args = {
                'q': f"'{node.id}' in parents",
                'fields': 'nextPageToken, files(id, name, mimeType, createdTime, thumbnailLink, shortcutDetails)',
                'pageSize': PAGE_LIMIT
            }
            
            if page_token is not None:
                args['pageToken'] = page_token
            
            async with self.http.get(f'{GDRIVE_ENDPOINT}/files', params=args) as response:
                response.raise_for_status()
                body = Dynamic.from_json(await response.text())
            
            for node in body.files:
                if node.mimeType == LINK_MIMETYPE:
                    node.id = node.shortcutDetails.targetId
                    node.mimeType = node.shortcutDetails.targetMimeType
                
                nodes.append(node)
            
            page_token = body.get('nextPageToken')
            
            if page_token is None:
                break
        
        # do this separately so it can be sorted properly
        for node in natsorted(nodes, key=lambda n: (n.mimeType == DIR_MIMETYPE, n.name.lower())):
            path = base_path + node.name
            if node.mimeType != DIR_MIMETYPE:
                yield path, node
            
            else:
                async for n in self._ordered_walk(node, base_path=path + '/'):
                    yield n
    
    async def download(self, post_id, post_data=None):
        args = {
            'fields': 'id, name, mimeType, createdTime, thumbnailLink, shortcutDetails'
        }
        async with self.http.get(f'{GDRIVE_ENDPOINT}/files/{post_id}', params=args) as response:
            response.raise_for_status()
            node = Dynamic.from_json(await response.text())
        
        url = None
        if node.mimeType == DIR_MIMETYPE:
            url = FOLDER_FORMAT.format(file_id=node.id)
            
        else:
            url = FILE_FORMAT.format(file_id=node.id)
        
        created_time = dateutil.parser.parse(node.createdTime)
        
        post = PostDetails()
        post.title = node.name
        post.url = url
        post.type = PostType.set
        post.post_time = created_time
        
        if node.mimeType != DIR_MIMETYPE:
            post.files.append(FileDetails(
                url=FILE_URL_FORMAT.format(node_id=node.id),
                filename=node.name,
                order=1
            ))
            
        else:
            order = 0
            async for path, cnode in self._ordered_walk(node):
                order += 1
                
                post.files.append(FileDetails(
                    url=FILE_URL_FORMAT.format(node_id=cnode.id),
                    filename=path,
                    order=order,
                    identifier=cnode.id
                ))
        
        return post

Plugin = GDrive
