import asyncio
import os
from collections.abc import Iterable
from typing import Optional
import contextlib

import aiohttp
from urllib.parse import urlencode, urlparse
from pathlib import Path
from tempfile import mkstemp
from .rfc6266 import safe_filename as safe_rfc6266_filename
from ..util import wrap_async


class HTTPError(Exception):
    def __init__(self, status, response, message):
        super().__init__(message)
        self.status = status
        self.response = response

class Response:
    def __init__(self,
        url: str = None,
        status: int = 0,
        reason: str = None,
        headers: Optional[list[tuple[str, str]]] = None,
        data: bytes = None
    ):
        self.url: str = url
        self.status_code: int = status
        self.status_reason: str = reason
        if headers is None: headers = list()
        self.headers: list[tuple[str, str]] = headers
        self.data: bytes = data

class DefaultRequestManager:
    def __init__(self):
        self._http: aiohttp.ClientSession
        self.headers: dict[str, str] = {}
        self._stack: contextlib.AsyncExitStack | None = None
    
    async def __aenter__(self):
        async with contextlib.AsyncExitStack() as stack:
            self._http = await stack.enter_async_context(aiohttp.ClientSession())
            self._stack = stack.pop_all()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._stack.__aexit__(exc_type, exc_val, exc_tb)
        self._stack = None
        await asyncio.sleep(0.250)
        return False
    
    def _request(self,
        url: str,
        *,
        method: str='GET',
        query:Optional[Iterable[tuple[str, str]]] = None,
        headers: Optional[Iterable[tuple[str, str]]] = None,
        cookies: Optional[Iterable[tuple[str, str]]] = None,
        fields: Optional[Iterable[tuple[str, str]]] = None,
        data: Optional[bytes | str] = None
    ):
        if query is not None:
            url_parts = urlparse(url)
            
            query = urlencode([t for t in query])
            if url_parts.query:
                query = url_parts.query + '&' + query
            
            url = url_parts._replace(query=query).geturl()
        
        kwargs = {
            'headers': dict(self.headers),
        }

        if headers is not None:
            kwargs['headers'].update(headers)
        
        if cookies is not None:
            # TODO fix this
            if hasattr(cookies, 'items'): cookies = cookies.items()
            kwargs['headers']['Cookie'] = '; '.join([f'{name}={val}' for name, val in cookies])
        
        # TODO this might need to be a dict?
        if fields is not None:
            kwargs['data'] = fields
            
        elif data is not None:
            kwargs['data'] = data
        
        self._http.cookie_jar.clear()
        return self._http.request(method, url, **kwargs)
    
    async def request(self, url: str, **kwargs) -> Response:
        async with self._request(url, **kwargs) as r:
            return Response(
                url=str(r.url),
                status=r.status,
                reason=r.reason,
                headers=[(k, v) for k, v in r.headers.items()],
                data=await r.read()
            )
    
    async def download(self,
        url: str,
        destination: Optional[str | os.PathLike] = None,
        suffix: Optional[str] = None,
        **kwargs
    ) -> tuple[str, Response]:
        if destination:
            dst_path = Path(destination)
        else:
            dst_path = None
        
        async with self._request(url, **kwargs) as r:
            if r.status != 200:
                raise HTTPError(r.status, r, f'{r.status} while downloading: {url}')
            
            final_url = str(r.url)

            if final_url is None:
                final_url = url

            if isinstance(final_url, bytes):
                final_url = final_url.decode('utf-8')

            if destination and not str(destination).endswith('/'):
                path = dst_path
                file = open(dst_path, 'w+b')
                
            else:
                if suffix is None:
                    content_disposition = r.headers.get('content-disposition')
                    attachment_filename = None
                    if content_disposition is not None:
                        attachment_filename = safe_rfc6266_filename(content_disposition)
                        
                    if attachment_filename is not None:
                        suffix = attachment_filename
                        
                    else:
                        suffix = Path(urlparse(final_url).path).name
                
                suffix = suffix.replace('/', '_')
                
                if dst_path:
                    if not suffix:
                        fd, path = mkstemp(dir=dst_path)
                        file = os.fdopen(fd, 'w+b')
                        
                    else:
                        path = dst_path / suffix
                        file = open(path, 'w+b')
                    
                else:
                    fd, path = mkstemp(suffix=suffix)
                    file = os.fdopen(fd, 'w+b')
            
            with file as f:
                write = wrap_async(f.write)
                async for data in r.content.iter_chunked(1024):
                    await write(data)
            
            return Path(path), Response(
                url=final_url,
                status=r.status,
                reason=r.reason,
                headers=[(k, v) for k, v in r.headers.items()],
                data=None
            )

