from ..config import *
from ..models import *
from ..util import *

import pathlib
import shutil
import logging

from lru import LRU

class PluginCore:
    def __init__(self, name, hrd, session):
        self.name = name
        self._hrd = hrd
        self.session = session
        
        log_file = template_format(self._hrd.settings.get('log_file'), name=self.name)
        self.logger = get_logger(self.name, log_file, self._hrd.settings.get('log_level', logging.WARNING))
        
        self._init_source()
        self.config = Dynamic.from_json(self.source.config)
        
        # (category, tag) -> RemoteTag
        self._tag_cache = LRU(100)
    
    def _init_source(self):
        self.source = self.session.query(Source) \
                .filter(Source.name == self.name) \
                .one_or_none()
        
        if self.source is None:
            self.source = Source(name=self.name, version=0)
            self.add(self.source)
            self.flush()
            self.logger.info('registered source: %s', self.name)
    
    def add(self, *args):
        return self.session.add_all(args)
    
    def flush(self):
        return self.session.flush()
    
    def commit(self):
        return self.session.commit()
    
    def rollback(self):
        return self.session.rollback()
    
    def get_remote_tag(self, category, tagstr):
        tag = self._tag_cache.get((category, tagstr))
        
        if tag is None:
            tag = self.session.query(RemoteTag) \
                    .filter(RemoteTag.source==self.source, RemoteTag.category==category, RemoteTag.tag==tagstr) \
                    .one_or_none()
            
            if tag is None:
                tag = RemoteTag(source=self.source, category=category, tag=tagstr)
                self.session.add(tag)
            
            self._tag_cache[category, tagstr] = tag
        
        return tag
    
    def download(self, url, dst_path=None, suffix=None, **kwargs):
        self.logger.debug('downloading %s', url)
        return self._hrd.requests.download(url, dst_path=dst_path, suffix=suffix, **kwargs)
    
    def import_file(self, file, orig=None, thumb=None, move=False):
        self.logger.info('importing file: %s, from remote post: %s', file.id, file.remote_id)
        self.logger.debug('file: %s', orig)
        self.logger.debug('thumb: %s', thumb)
        mvfun = shutil.move if move else shutil.copy
        
        if orig is not None:
            file.hash = md5(orig)
            file.mime = mime_from_file(orig)
            suffixes = pathlib.Path(orig).suffixes
            if len(suffixes):
                file.ext = suffixes[-1][1:]
            else:
                file.ext = None
        
        if thumb is not None:
            suffixes = pathlib.Path(thumb).suffixes
            if len(suffixes):
                file.thumb_ext = suffixes[-1][1:]
            else:
                file.thumb_ext = None
        
        dst, tdst = self._hrd.get_file_paths(file)
        
        if orig is not None:
            self.logger.info('importing original file, move: %r', move)
            pathlib.Path(dst).parent.mkdir(parents=True, exist_ok=True)
            mvfun(orig, dst)
            file.present = True
            self.session.add(file)
        
        if thumb is not None:
            self.logger.info('importing thumbnail, move: %r', move)
            pathlib.Path(tdst).parent.mkdir(parents=True, exist_ok=True)
            mvfun(thumb, tdst)
            file.thumb_present = True
            self.session.add(file)
