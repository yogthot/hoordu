from ..config import *
from ..models import *
from ..util import *

import pathlib
import shutil
import logging

class plugin_core:
    def __init__(self, name, hrd, session):
        self.name = name
        self.hrd = hrd
        self.session = session
        
        log_file = template_format(self.hrd.config.get('log_file'), name=self.name)
        self.logger = get_logger(self.name, log_file, self.hrd.config.get('log_level', logging.WARNING))
        
        self._init_source()
        self.config = Settings.from_json(self.source.config)
    
    def _init_source(self):
        self.source = self.session.query(Source).filter(Source.name == self.name).one_or_none()
        
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
    
    def get_remote_tag(self, **kwargs):
        tag = self.session.query(RemoteTag).filter_by(**kwargs).one_or_none()
        
        if tag is None:
            tag = RemoteTag(**kwargs)
            self.session.add(tag)
        
        return tag
    
    def import_file(self, file, orig=None, thumb=None, move=False):
        self.logger.info('importing file: %s, from remote post: %s', file.id, file.remote_id)
        self.logger.debug('file: %s', orig)
        self.logger.debug('thumb: %s', thumb)
        mvfun = shutil.move if move else shutil.copy
        
        if orig is not None:
            file.hash = md5(orig)
            file.mime = mime_from_file(orig)
            file.ext = ''.join(pathlib.Path(orig).suffixes)[1:]
        
        if thumb is not None:
            file.thumb_ext = ''.join(pathlib.Path(thumb).suffixes)[1:]
        
        dst, tdst = self.hrd.get_file_paths(file)
        
        if orig is not None:
            self.logger.info('importing original file, move: %r', move)
            pathlib.Path(dst).parent.mkdir(parents=True, exist_ok=True)
            mvfun(orig, dst)
            file.present = True
        
        if thumb is not None:
            self.logger.info('importing thumbnail, move: %r', move)
            pathlib.Path(tdst).parent.mkdir(parents=True, exist_ok=True)
            mvfun(thumb, tdst)
            file.thumb_present = True
