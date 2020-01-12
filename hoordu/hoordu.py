from .config import get_logger
from . import models
from .util import *

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import shutil
import pathlib

class hoordu(object):
    def __init__(self, config):
        self.config = config
        self.logger = get_logger('hoordu', self.config.get('logto'))
        self.engine = create_engine(self.config.database, echo=self.config.get('debug', False))
        self._Session = sessionmaker(bind=self.engine)
        self.session = self._Session()
        
        self.filespath = '{}/files'.format(self.config.base_path)
        self.thumbspath = '{}/thumbs'.format(self.config.base_path)
    
    def create_all(self):
        models.Base.metadata.create_all(self.engine)
    
    def register_service(self, name):
        service = self.session.query(models.Service).filter(models.Service.name==name).one_or_none()
        
        if service is not None:
            return service
            
        else:
            service = models.Service(name=name, version=0)
            self.add(service)
            self.flush()
            return service
    
    def add(self, *args):
        return self.session.add_all(args)
    
    def flush(self):
        return self.session.flush()
    
    def commit(self):
        return self.session.commit()
    
    """
    # not sure if this is a good idea
    def save(self, *args):
        session = self._Session()
        session.add_all(args)
        return session.commit()
    """
    
    def import_file(self, post, src, thumb=None, order=None, move=False):
        hash = md5(src)
        mime = mime_from_file(src)
        ext = ''.join(pathlib.Path(src).suffixes)[1:]
        
        flags = models.FileFlags.none
        if thumb is None:
            flags = flags | models.FileFlags.thumb_present
        
        file = models.File(remote=post, remote_order=order, hash=hash, mime=mime, ext=ext, flags=flags)
        
        # I'd rather not do this, but we need the id for the filename
        self.add(file)
        self.flush()
        
        dst, tdst = self._get_file_paths(file)
        
        mvfun = shutil.move if move else shutil.copy
        
        pathlib.Path(dst).parent.mkdir(parents=True, exist_ok=True)
        mvfun(src, dst)
        if thumb is not None:
            pathlib.Path(tdst).parent.mkdir(parents=True, exist_ok=True)
            mvfun(thumb, tdst)
    
    def _file_slot(self, file):
        return file.id // self.config.files_slot_size
    
    def _get_file_paths(self, file):
        file_slot = self._file_slot(file)
        
        if file.ext is not None:
            filepath = '{}/{}/{}.{}'.format(self.filespath, file_slot, file.id, file.ext)
        else:
            filepath = '{}/{}/{}'.format(self.filespath, file_slot, file.id)
        
        thumbpath = '{}/{}/{}.jpg'.format(self.thumbspath, file_slot, file.id)
        
        return filepath, thumbpath

