from . import *

import pathlib
from datetime import datetime
from natsort import natsorted
from typing import Optional, Any, Iterable

def _ordered_walk(path: pathlib.Path) -> Iterable[pathlib.Path]:
    for p in natsorted(path.iterdir(), key=lambda x: (not x.is_file(), x.name.lower())):
        yield p
        
        if p.is_dir():
            yield from _ordered_walk(p)
        

class Filesystem(PluginBase):
    id = 'filesystem'
    source = 'filesystem'
    
    @classmethod
    async def parse_url(cls, url: str):
        if url.startswith('/'):
            return url

    async def download(self, post_id: str, post_data: Any=None):
        path = pathlib.Path(post_id).resolve()
        create_time = datetime.fromtimestamp(path.stat().st_ctime)
        
        post = PostDetails(
            _omit_id=True,
            url=f'file://{path}',
            post_time=create_time
        )
        
        if path.is_file():
            filename = path.name
            post.files.append(FileDetails(order=0, url=f'file://${path}', filename=filename))
            return post
            
        elif path.is_dir():
            order = 0
            for p in _ordered_walk(path):
                if p.is_file():
                    filename = str(p.relative_to(path))
                    post.files.append(FileDetails(order=order, url=f'file://${p}', filename=filename))
                    order += 1
            
            return post
            
        else:
            raise APIError('unsupported')

