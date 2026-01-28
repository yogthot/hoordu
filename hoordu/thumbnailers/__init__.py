import tempfile
from typing import Optional
import mimetypes
import functools
import re
import os.path

from .common import *
from .unzip import Unzip


# always jpeg
MAX_SIZE = 500


mimetypes.init()


thumbnailers = {}

def register(match):
    if isinstance(match, str):
        rexp = re.compile(match)
    else:
        rexp = match
    
    def dec(f):
        thumbnailers[rexp] = f
        return f
    return dec


@register(r'image\/.*')
@register('application/pdf')
async def magick_thumbnail(src: str, dst: str):
    await async_exec(
        'magick',
        f'{src}[0]',
        '-resize', f'{MAX_SIZE}x{MAX_SIZE}>',
        '-quality', f'85',
        dst
    )
    return True

@register(r'video\/.*')
async def ffmpeg_thumbnail(src: str, dst: str):
    await async_exec(
        'ffmpeg',
        '-i', src,
        '-vf', f'scale=w={MAX_SIZE}:h={MAX_SIZE}:force_original_aspect_ratio=decrease',
        '-frames:v', '1',
        '-q:v', '2',
        '-y',
        dst
    )
    return True

@register('application/zip')
@register('application/x-rar')
@register('application/x-7z-compressed')
async def zip_thumbnail(src: str, dst: str):
    zip = Unzip(src)
    files = await zip.list()
    
    for file in files:
        ext = os.path.splitext(file['path'])[1].decode()
        mime_type = mimetypes.types_map.get(ext, None)
        if mime_type is None:
            continue
        
        for rexp, thumbnailer in thumbnailers.items():
            if rexp.fullmatch(mime_type):
                if thumbnailer != zip_thumbnail:
                    break
        else:
            continue
        
        with tempfile.TemporaryDirectory() as dir:
            filename = file['path']
            tmpdst = f'{dir}/{filename.split(b'/')[-1]}'
            await zip.extract(filename, tmpdst)
            return await thumbnailer(tmpdst, dst)
    
    return False


async def generate_thumbnail(src: str, dst: str, mime_type: str) -> bool:
    for rexp, thumbnailer in thumbnailers.items():
        if rexp.fullmatch(mime_type):
            return await thumbnailer(src, dst)
    
    return False
