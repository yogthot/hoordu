from .config import *
from .models import *
from .util import *
from .plugins import *

import pathlib
import shutil

class HoorduSession:
    def __init__(self, hoordu):
        self.hoordu = hoordu
        self.raw = hoordu._Session()
        self.priority = hoordu._Session()
        self._plugins = {}
        
        self._callbacks = []
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc, tb):
        self.priority.commit()
        
        if exc is None:
            try:
                self.commit()
                
            except:
                self.rollback()
            
        else:
            self.rollback()
    
    def plugin(self, plugin_id):
        Plugin_cls = plugin_id
        if not isinstance(plugin_id, str) and issubclass(plugin_id, PluginBase):
            # when passing a plugin class, Plugin_cls is that class and plugin_id is its id
            plugin_id = plugin_id.id
        
        plugin = self._plugins.get(plugin_id)
        if plugin is not None:
            return plugin
        
        # load plugin if it wasn't loaded before
        Plugin = self.hoordu.load_plugin(Plugin_cls)
        
        plugin = Plugin(self)
        self._plugins[plugin_id] = plugin
        return plugin
    
    def callback(self, callback, on_commit=False, on_rollback=False):
        self._callbacks.append((callback, on_commit, on_rollback))
    
    def add(self, *args):
        return self.raw.add_all(args)
    
    def flush(self):
        return self.raw.flush()
    
    def delete(self, instance):
        def delete_file(sess, is_commit):
            files = self.hoordu.get_file_paths(instance)
            for f in files:
                path = pathlib.Path(f)
                path.unlink(missing_ok=True)
        
        if isinstance(instance, File):
            self.callback(delete_file, on_commit=True)
        
        return self.raw.delete(instance)
    
    def commit(self):
        res = self.raw.commit()
        
        for callback, on_commit, _ in self._callbacks:
            if on_commit:
                try:
                    callback(self, True)
                    
                except Exception:
                    self.hoordu.log.exception('callback error during commit')
        
        self._callbacks.clear()
        
        return res
    
    def rollback(self):
        res = self.raw.rollback()
        
        for callback, _, on_rollback in self._callbacks:
            if on_rollback:
                try:
                    callback(self, False)
                    
                except Exception:
                    self.hoordu.log.exception('callback error during rollback')
        
        self._callbacks.clear()
        
        return res
    
    def query(self, *args, **kwargs):
        return self.raw.query(*args, **kwargs)
    
    
    def download(self, url, dst_path=None, suffix=None, **kwargs):
        return self.hoordu.requests.download(url, dst_path=dst_path, suffix=suffix, **kwargs)
    
    
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
        
        dst, tdst = self.hoordu.get_file_paths(file)
        
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
