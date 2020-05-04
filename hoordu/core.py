from .config import get_logger
from . import models
from .util import *

from string import Template
import pathlib
import shutil
import logging

def _template_format(format, **kwargs):
    if format is not None:
        return Template(format).substitute(kwargs)

class core(object):
    def __init__(self, name, config, session):
        self.name = name
        self.config = config
        self.session = session
        
        log_file = _template_format(self.config.get('log_file'), name=self.name)
        self.logger = get_logger(name, log_file, self.config.get('log_level', logging.WARNING))
        
        self.filespath = '{}/files'.format(self.config.base_path)
        self.thumbspath = '{}/thumbs'.format(self.config.base_path)
    
    def add(self, *args):
        return self.session.add_all(args)
    
    def flush(self):
        return self.session.flush()
    
    def commit(self):
        return self.session.commit()
    
    def rollback(self):
        return self.session.rollback()
    
    def register_source(self, name):
        self.logger.info('registering source: %s', name)
        source = self.session.query(models.Source).filter(models.Source.name == name).one_or_none()
        
        if source is not None:
            self.logger.info('source already exists: %s', name)
            return source
            
        else:
            source = models.Source(name=name, version=0)
            self.add(source)
            self.flush()
            self.logger.info('registered source: %s', name)
            return source
    
    def get_tag(self, **kwargs):
        tag = self.session.query(models.Tag).filter_by(**kwargs).one_or_none()
        
        if tag is None:
            tag = models.Tag(**kwargs)
            self.session.add(tag)
        
        return tag
    
    def get_remote_tag(self, **kwargs):
        tag = self.session.query(models.RemoteTag).filter_by(**kwargs).one_or_none()
        
        if tag is None:
            tag = models.RemoteTag(**kwargs)
            self.session.add(tag)
        
        return tag
    
    def import_file(self, file, orig=None, thumb=None, move=False):
        self.logger.info('importing file: %s, of post: %s', file.id, file.remote_id)
        self.logger.debug('file: %s', orig)
        self.logger.debug('thumb: %s', thumb)
        mvfun = shutil.move if move else shutil.copy
        
        if orig is not None:
            file.hash = md5(orig)
            file.mime = mime_from_file(orig)
            file.ext = ''.join(pathlib.Path(orig).suffixes)[1:]
        
        if thumb is not None:
            file.thumb_ext = ''.join(pathlib.Path(thumb).suffixes)[1:]
        
        dst, tdst = self._get_file_paths(file)
        
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
    
    def _file_bucket(self, file):
        return file.id // self.config.files_bucket_size
    
    def _get_file_paths(self, file):
        file_bucket = self._file_bucket(file)
        
        if file.ext:
            filepath = '{}/{}/{}.{}'.format(self.filespath, file_bucket, file.id, file.ext)
        else:
            filepath = '{}/{}/{}'.format(self.filespath, file_bucket, file.id)
        
        if file.thumb_ext:
            thumbpath = '{}/{}/{}.{}'.format(self.thumbspath, file_bucket, file.id, file.thumb_ext)
        else:
            thumbpath = '{}/{}/{}'.format(self.thumbspath, file_bucket, file.id)
        
        return filepath, thumbpath
    
    # not needed yet
    #def delete_file(self, file):
    #    self.logger.info('deleting file: %s, of post: %s', file.id, file.local_id)
    #    filepath, thumbpath = self._get_file_paths(file)
    #    
    #    self.session.delete(file)
    #    self.commit()
    #    
    #    pathlib.Path(filepath).unlink()
    #    pathlib.Path(thumbpath).unlink()