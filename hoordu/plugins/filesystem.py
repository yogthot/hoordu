from . import *

import pathlib
from datetime import datetime
from natsort import natsorted

def _ordered_walk(path: pathlib.Path):
    for p in natsorted(path.iterdir(), key=lambda x: (not x.is_file(), x.name.lower())):
        yield p
        
        if p.is_dir():
            yield from _ordered_walk(p)
        

class Filesystem(SimplePlugin):
    id = 'filesystem'
    name = 'filesystem'
    version = 1
    
    iterator = None
    
    @classmethod
    async def setup(cls, session, parameters=None):
        return True, None
    
    @classmethod
    async def parse_url(cls, url):
        if url.startswith('/'):
            return url

    async def download(self, url=None, remote_post=None, preview=False):
        if remote_post is not None:
            return remote_post
        
        path = pathlib.Path(url).resolve()
        create_time = datetime.fromtimestamp(path.stat().st_ctime)
        
        remote_post = RemotePost(
            source=self.source,
            original_id=None,
            url=f'file://{path}',
            type=PostType.set,
            post_time=create_time
        )
        self.session.add(remote_post)
        
        if path.is_file():
            filename = path.name
            
            file = File(remote=remote_post, remote_order=0, filename=filename)
            self.session.add(file)
            await self.session.flush()
            
            await self.session.import_file(file, orig=str(path), move=False)
            
            return remote_post
        
        elif path.is_dir():
            order = 0
            for p in _ordered_walk(path):
                if p.is_file():
                    filename = str(p.relative_to(path))
                    
                    file = File(remote=remote_post, remote_order=order, filename=filename)
                    self.session.add(file)
                    await self.session.flush()
                    
                    await self.session.import_file(file, orig=str(p), move=False)
                    order += 1
            
            return remote_post
            
        else:
            raise APIError('unsupported')

