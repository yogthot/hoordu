from .config import *
from .models import *
from .util import *

import pathlib
import shutil

class HoorduSession:
    def __init__(self, hrd):
        self.hrd = hrd
        self.raw = hrd._Session()
        self._plugins = {}
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc, tb):
        if exc is None:
            self.commit()
            
        else:
            self.rollback()
    
    def plugin(self, plugin_id):
        plugin = self._plugins.get(plugin_id)
        if plugin is not None:
            return plugin
        
        # load plugin if it wasn't loaded before
        Plugin = self.hrd.load_plugin(plugin_id)
        
        plugin = Plugin(self)
        self._plugins[plugin_id] = plugin
        return plugin
    
    def add(self, *args):
        return self.raw.add_all(args)
    
    def flush(self):
        return self.raw.flush()
    
    def commit(self):
        return self.raw.commit()
    
    def rollback(self):
        return self.raw.rollback()
    
    def query(self, *args, **kwargs):
        return self.raw.query(*args, **kwargs)
    
    
    def download(self, url, dst_path=None, suffix=None, **kwargs):
        return self.hrd.requests.download(url, dst_path=dst_path, suffix=suffix, **kwargs)
    
    
    def _file_bucket(self, file):
        return file.id // self.hrd.settings.files_bucket_size
    
    def get_file_paths(self, file):
        file_bucket = self._file_bucket(file)
        
        if file.ext:
            filepath = '{}/{}/{}.{}'.format(self.hrd.filespath, file_bucket, file.id, file.ext)
        else:
            filepath = '{}/{}/{}'.format(self.hrd.filespath, file_bucket, file.id)
        
        if file.thumb_ext:
            thumbpath = '{}/{}/{}.{}'.format(self.hrd.thumbspath, file_bucket, file.id, file.thumb_ext)
        else:
            thumbpath = '{}/{}/{}'.format(self.hrd.thumbspath, file_bucket, file.id)
        
        return filepath, thumbpath
    
    def import_file(self, file, orig=None, thumb=None, move=False):
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
        
        dst, tdst = self.get_file_paths(file)
        
        if orig is not None:
            pathlib.Path(dst).parent.mkdir(parents=True, exist_ok=True)
            mvfun(orig, dst)
            file.present = True
            self.add(file)
        
        if thumb is not None:
            pathlib.Path(tdst).parent.mkdir(parents=True, exist_ok=True)
            mvfun(thumb, tdst)
            file.thumb_present = True
            self.add(file)
