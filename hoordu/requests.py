import os
import urllib3
import shutil
from urllib.parse import urlencode, urlparse
from tempfile import TemporaryFile
from pathlib import Path
import functools
from tempfile import mkstemp
from .rfc6266 import safe_filename as safe_rfc6266_filename

class HTTPError(Exception):
    def __init__(self, status, response, message):
        super().__init__(message)
        self.status = status
        self.response = response

class Response:
    def __init__(self, url=None, status=0, reason=None, headers=[], data=None):
        self.url = url
        self.status_code = status
        self.status_reason = reason
        self.headers = headers
        self.data = data

class DefaultRequestManager:
    def __init__(self):
        self._http = urllib3.PoolManager()
        self.headers = {
            'Accept-Encoding': 'gzip, deflate, br'
        }
    
    def _request(self, url, *, method='GET', query=None, headers={}, cookies=None, fields=None, body=None, preload_content=True):
        if query is not None:
            parsed = urlparse(url)
            
            query = urlencode(query)
            if parsed.query:
                query = parsed.query + '&' + query
            
            url = parsed._replace(query=query).geturl()
        
        kwargs = {
            'preload_content': preload_content,
            'headers': dict(self.headers),
        }
        
        kwargs['headers'].update(headers)
        
        if cookies is not None:
            kwargs['headers']['Cookie'] = '; '.join(['{}={}'.format(*i) for i in cookies.items()])
        
        if fields is not None:
            kwargs['fields'] = fields
        
        if body is not None:
            kwargs['body'] = body
        
        return self._http.request(method, url, **kwargs)
    
    def request(self, url, **kwargs):
        r = self._request(url, **kwargs)
        return Response(
            url=r.geturl(),
            status=r.status,
            reason=r.reason,
            headers=list(r.headers.items()),
            data=r.data
        )
    
    def download(self, url, dst_path=None, suffix=None, **kwargs):
        with self._request(url, preload_content=False, **kwargs) as r:
            if r.status == 200:
                if dst_path:
                    path = dst_path
                    file = open(dst_path, 'w+b')
                    
                else:
                    if suffix is None:
                        content_disposition = r.headers.get('content-disposition', None)
                        attachment_filename = None
                        if content_disposition is not None:
                            attachment_filename = safe_rfc6266_filename(content_disposition)
                            
                        if attachment_filename is not None:
                            suffix = attachment_filename
                            
                        else:
                            suffix = ''.join(Path(urlparse(url).path).suffixes)
                            if not suffix.startswith('.'):
                                suffix = ''
                    
                    fd, path = mkstemp(suffix=suffix)
                    file = os.fdopen(fd, 'w+b')
                
                
                r.read = functools.partial(r.read, decode_content=True)
                
                with file as f:
                    shutil.copyfileobj(r, f)
                
                return path, Response(
                    url=r.geturl(),
                    status=r.status,
                    reason=r.reason,
                    headers=list(r.headers.items()),
                    data=None
                )
                
            else:
                raise HTTPError(r.status, r, f'{r.status} while downloading: {url}')
