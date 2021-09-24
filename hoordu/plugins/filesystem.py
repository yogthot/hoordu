import os
import re
import json
from datetime import datetime
from tempfile import mkstemp
import shutil
from urllib.parse import urlparse
import functools
import urllib3

import hoordu
from hoordu.models import *
from hoordu.plugins import *
from hoordu.forms import *

import pathlib
from datetime import datetime
from natsort import natsorted

def _ordered_walk(path):
    for p in natsorted(path.iterdir(), key=lambda x: (not x.is_file(), x.name.lower())):
        yield p
        
        if p.is_dir():
            yield from _ordered_walk(p)
        

class Filesystem(PluginBase):
    name = 'filesystem'
    version = 1
    
    iterator = None
    
    @classmethod
    def config_form(cls):
        return None
    
    @classmethod
    def setup(cls, session, parameters=None):
        return True, None
    
    #def __init__(self, session):
    #    super().__init__(session)
    
    def parse_url(self, url):
        if url.startswith('/'):
            return url
        
    def download(self, url=None, remote_post=None, preview=False):
        if remote_post is not None:
            return remote_post
        
        path = pathlib.Path(url).resolve()
        create_time = datetime.fromtimestamp(path.stat().st_ctime)
        
        remote_post = RemotePost(
            source=self.source,
            original_id=None,
            url='file://{}'.format(url),
            type=PostType.set,
            post_time=create_time
        )
        self.session.add(remote_post)
            
        if path.is_file():
            filename = path.name
            
            file = File(remote=remote_post, remote_order=0, filename=filename)
            self.session.add(file)
            self.session.flush()
            
            self.session.import_file(file, orig=url, move=False)
            
            return remote_post
        
        elif path.is_dir():
            order = 0
            for p in _ordered_walk(path):
                if p.is_file():
                    filename = str(p.relative_to(path))
                    
                    file = File(remote=remote_post, remote_order=order, filename=filename)
                    self.session.add(file)
                    self.session.flush()
                    
                    self.session.import_file(file, orig=str(p), move=False)
                    order += 1
            
            return remote_post
            
        else:
            raise APIError('unsupported')

