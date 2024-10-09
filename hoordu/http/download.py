import asyncio
import os
from typing import Optional
import aiohttp
import yarl

from pathlib import Path
from tempfile import mkstemp
from .rfc6266 import safe_filename as safe_rfc6266_filename
from ..util import wrap_async

async def save_response(
    r: aiohttp.ClientResponse,
    url: Optional[str] = None,
    destination: Optional[str | os.PathLike] = None,
    suffix: Optional[str] = None,
) -> os.PathLike:
    final_url = str(r.url)
    
    if final_url is None:
        final_url = url
    
    # not sure why this was added but it's here for a reason?
    if isinstance(final_url, bytes):
        final_url = final_url.decode('utf-8')
    
    if destination and not str(destination).endswith('/'):
        path = destination
        file = open(destination, 'w+b')
        
    else:
        if suffix is None:
            content_disposition = r.headers.get('content-disposition')
            attachment_filename = None
            if content_disposition is not None:
                attachment_filename = safe_rfc6266_filename(content_disposition)
                
            if attachment_filename is not None:
                suffix = attachment_filename
                
            elif final_url is not None:
                suffix = Path(yarl.URL(final_url).path).name
                
            else:
                suffix = ''
        
        suffix = suffix.replace('/', '_')
        
        if destination:
            if not suffix:
                fd, path = mkstemp(dir=destination)
                file = os.fdopen(fd, 'w+b')
                
            else:
                path = Path(destination) / suffix
                file = open(path, 'w+b')
            
        else:
            fd, path = mkstemp(suffix=suffix)
            file = os.fdopen(fd, 'w+b')
    
    with file as f:
        write = wrap_async(f.write)
        async for data in r.content.iter_chunked(1024):
            await write(data)
    
    return Path(path)

