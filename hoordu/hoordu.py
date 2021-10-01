from . import models
from .util import *
from .models import *
from .config import get_logger
from .session import HoorduSession
from .plugins import *
from .plugins.filesystem import Filesystem
from .requests import DefaultRequestManager
from . import _version

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import packaging.version

import logging

class hoordu:
    def __init__(self, config):
        self.version = packaging.version.parse(_version.__version__)
        
        self.config = config
        self.settings = config.settings
        
        self.engine = create_engine(self.settings.database, echo=self.settings.get('debug', False))
        self._Session = sessionmaker(bind=self.engine)
        self._session = HoorduSession(self)
        
        self.requests = DefaultRequestManager()
        self.requests.headers['User-Agent'] = '{}/{}'.format(_version.__fulltitle__, _version.__version__)
        
        name = 'hoordu'
        log_file = template_format(self.settings.get('log_file'), name=name)
        self.log = get_logger(name, log_file, self.settings.get('log_level', logging.WARNING))
        
        self._plugins = {} # id -> Plugin
        self._plugins_ready = {} # id -> bool
        
        self.filespath = '{}/files'.format(self.settings.base_path)
        self.thumbspath = '{}/thumbs'.format(self.settings.base_path)
        
        # load built-in plugins
        self._setup_plugin(Filesystem)
        
        # load plugin classes
        ctors, errors = self.config.load_plugins()
        self._plugins.update(ctors)
    
    def create_all(self):
        self.logger.info('creating all relations in the database')
        models.Base.metadata.create_all(self.engine)
    
    def _file_bucket(self, file):
        return file.id // self.settings.files_bucket_size
    
    def get_file_paths(self, file):
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
    
    
    def _is_plugin_supported(self, version):
        version = packaging.version.parse(version)
        # same major, greater or equal to current
        return version.major == self.version.major and self.version >= version
    
    def _setup_plugin(self, Plugin, parameters=None):
        id = Plugin.id
        
        ready = self._plugins_ready.get(id, False)
        if ready:
            return True, None
        
        if not self._is_plugin_supported(Plugin.required_hoordu):
            raise ValueError('plugin {} is unsupported'.format(id))
        
        with self._session:
            source_exists = self._session.query(
                    self._session.query(Source) \
                            .filter(Source.name == Plugin.name) \
                            .exists()
                    ).scalar()
            
            if not source_exists:
                self._session.add(Source(name=Plugin.name, version=0))
                self._session.flush()
            
            Plugin.update(self._session)
            success, form = Plugin.setup(self._session, parameters=parameters)
        
            if success:
                if Plugin.id not in self._plugins:
                    self._plugins[Plugin.id] = Plugin
                
                self._plugins_ready[id] = True
            
            return success, form
    
    def parse_url(self, url, plugin_id=None):
        if plugin_id is None:
            for id, Plugin in self._plugins.items():
                if issubclass(Plugin, SimplePluginBase):
                    options = Plugin.parse_url(url)
                    if options is not None:
                        return id, options
            
        else:
            Plugin = self._plugins[plugin_id]
            options = Plugin.parse_url(url)
            if options is not None:
                return plugin_id, options
        
        return None, None
    
    def setup_plugin(self, id, parameters=None):
        Plugin = self._plugins.get(id)
        if Plugin is not None:
            return self._setup_plugin(Plugin, parameters)
        
        # check for new plugins
        ctors, errors = self.config.load_plugins()
        self._plugins.update(ctors)
        
        Plugin = self._plugins.get(id)
        if Plugin is not None:
            return self._setup_plugin(Plugin, parameters)
        
        # check if this plugin failed to load
        exc = errors.get(id)
        if exc is not None:
            raise ValueError(f'plugin {id} failed to load') from exc
        
        raise ValueError(f'plugin {id} does not exist')
    
    def load_plugin(self, id):
        if not self._plugins_ready.get(id, False):
            if not self.setup_plugin(id)[0]:
                raise ValueError(f'plugin {id} needs to be setup before use')
        
        return self._plugins[id]
    
    def session(self):
        return HoorduSession(self)
