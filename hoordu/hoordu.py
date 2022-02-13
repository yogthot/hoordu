from . import models
from .util import *
from .models import *
from .logging import configure_logger
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
        
        # global initializer
        configure_logger('hoordu', self.settings.get('log_file'))
        
        self.log = logging.getLogger('hoordu.hoordu')
        
        self._plugins = {} # id -> Plugin_cls
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
    
    def _setup_plugin(self, Plugin_cls, parameters=None):
        id = Plugin_cls.id
        
        ready = self._plugins_ready.get(id, False)
        if ready:
            return True, None
        
        if not self._is_plugin_supported(Plugin_cls.required_hoordu):
            raise ValueError('plugin {} is unsupported'.format(id))
        
        with self._session:
            # create source
            source = self._session.query(Source) \
                    .filter(Source.name == Plugin_cls.name) \
                    .one_or_none()
            
            source_exists = source is not None
            if not source_exists:
                source = Source(name=Plugin_cls.name)
                self._session.add(source)
                self._session.flush()
            
            # create plugin
            plugin = self._session.query(Plugin) \
                    .filter(Plugin.name == Plugin_cls.id) \
                    .one_or_none()
            
            if plugin is None:
                p = Plugin(name=Plugin_cls.id, version=0, source=source)
                self._session.add(p)
                self._session.flush()
            
            # preferred plugin
            if not source_exists:
                source.preferred_plugin = p
                self._session.add(source)
                self._session.flush()
            
            Plugin_cls.update(self._session)
            success, form = Plugin_cls.setup(self._session, parameters=parameters)
        
            if success:
                if Plugin_cls.id not in self._plugins:
                    self._plugins[Plugin_cls.id] = Plugin_cls
                
                self._plugins_ready[id] = True
            
            return success, form
    
    def parse_url(self, url, plugin_id=None):
        if plugin_id is None:
            for id, Plugin_cls in self._plugins.items():
                if issubclass(Plugin_cls, SimplePluginBase):
                    options = Plugin_cls.parse_url(url)
                    if options is not None:
                        return id, options
            
        else:
            Plugin_cls = self._plugins[plugin_id]
            options = Plugin_cls.parse_url(url)
            if options is not None:
                return plugin_id, options
        
        return None, None
    
    def setup_plugin(self, id, parameters=None):
        Plugin_cls = self._plugins.get(id)
        if Plugin_cls is not None:
            return self._setup_plugin(Plugin_cls, parameters)
        
        # check for new plugins
        ctors, errors = self.config.load_plugins()
        self._plugins.update(ctors)
        
        Plugin_cls = self._plugins.get(id)
        if Plugin_cls is not None:
            return self._setup_plugin(Plugin_cls, parameters)
        
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
