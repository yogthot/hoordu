__all__ = [
    'wrap_async',
    'mime_from_file',
    'md5',
    'mkpath',
    'template_format',
    'save_data_uri'
]

import os
import asyncio
import functools
import pathlib
from collections.abc import Awaitable, Callable
from hashlib import md5 as _md5
from string import Template
import re
import mimetypes
import base64
from tempfile import mkstemp
from typing import Any, TypeVar, ParamSpec


DATAURI_REGEX = re.compile('^data:(?P<mime>[^\/;,]+\/[^;,]+)(?P<parameters>;[^;,]+)+,(?P<content>.*)$')


# handle both python-magic libraries
import magic
if hasattr(magic, 'open'):
    __magic = magic.open(magic.MAGIC_MIME_TYPE)
    __magic.load()
    mime_from_file_sync = __magic.file
else:
    mime_from_file_sync = lambda path: magic.from_file(path, mime=True)
# /

def md5_sync(filename: str | bytes | os.PathLike) -> bytes:
    digest = _md5()
    with open(filename, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            digest.update(chunk)
    return digest.digest()

def mkpath_sync(path: str | bytes | os.PathLike) -> None:
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)


P = ParamSpec('P')
R = TypeVar('R')
def wrap_async(func: Callable[P, R]) -> Callable[P, Awaitable[R]]:
    @functools.wraps(func)
    async def run_async(*args: P.args, **kwargs: P.kwargs) -> R:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))

    return run_async


mime_from_file = wrap_async(mime_from_file_sync)
md5 = wrap_async(md5_sync)
mkpath = wrap_async(mkpath_sync)


def template_format(format: str, **kwargs: Any):
    if format is not None:
        return Template(format).substitute(kwargs)

def save_data_uri(data_uri: str):
    match = DATAURI_REGEX.match(data_uri)
    mime = match.group('mime')
    if mime is None:
        mime = 'text/plain'
        ext = 'txt'
        
    else:
        ext = mimetypes.guess_extension(mime, strict=False)
        if ext is None:
            ext = mime.split('/')[-1]
    
    content = match.group('content')
    
    parameters = match.group('parameters')
    if parameters:
        parameters = [p for p in parameters.split(';') if p]
        if parameters[-1] == 'base64':
            content = base64.b64decode(content)
    
    
    fd, path = mkstemp(suffix=f'.{ext}')
    with os.fdopen(fd, 'w+b') as file:
        file.write(content)
    
    return path

