from .config import load_config, get_logger
from . import models

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import shutil
from hashlib import md5 as _md5
import pathlib

# handle both python-magic libraries
import magic
if hasattr(magic, 'open'):
    __magic = magic.open(magic.MAGIC_MIME_TYPE)
    __magic.load()
    mime_from_file = __magic.file
else:
    mime_from_file = lambda path: magic.from_file(path, mime=True)
# /

def md5(fname):
    hash = _md5()
    with open(fname, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash.update(chunk)
    return hash.digest()

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
    
    def register_service(self, name, version):
        service = self.session.query(models.Service).filter(models.Service.name==name).one_or_none()
        
        if service is not None:
            old_version = service.version
            
            if service.version != version:
                # update version
                service.version = version
                self.flush()
            
            return service, old_version
            
        else:
            service = models.Service(name=name, version=version)
            self.add(service)
            self.flush()
            return service, 0
    
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
        # ...unless we use some kind of uuid
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

