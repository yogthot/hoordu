from . import models
from .util import *
from .config import get_logger
from .plugins import PluginCore
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
        self.session = self._Session()
        
        self.requests = DefaultRequestManager()
        self.requests.headers['User-Agent'] = '{}/{}'.format(_version.__fulltitle__, _version.__version__)
        
        name = 'hoordu'
        log_file = template_format(self.settings.get('log_file'), name=name)
        self.logger = get_logger(name, log_file, self.settings.get('log_level', logging.WARNING))
        
        self.plugin_cores = {}
        self._plugin_ctors = {}
        self._plugins = {}
        
        self.filespath = '{}/files'.format(self.settings.base_path)
        self.thumbspath = '{}/thumbs'.format(self.settings.base_path)
    
    def create_all(self):
        self.logger.info('creating all relations in the database')
        models.Base.metadata.create_all(self.engine)
    
    def add(self, *args):
        return self.session.add_all(args)
    
    def flush(self):
        return self.session.flush()
    
    def commit(self):
        return self.session.commit()
    
    def rollback(self):
        return self.session.rollback()
    
    def _get_plugin_core(self, name):
        c = self.plugin_cores.get(name)
        if c is not None:
            return c
        else:
            session = self._Session()
            c = PluginCore(name, self, session)
            
            self.plugin_cores[name] = c
            return c
    
    def _init_plugin(self, Plugin, parameters=None):
        name = Plugin.name
        
        plugin = self._plugins.get(name)
        if plugin is not None:
            return True, plugin
        
        if not self._is_plugin_supported(Plugin.required_hoordu):
            raise ValueError('plugin {} is unsupported'.format(Plugin.name))
        
        core = self._get_plugin_core(name)
        Plugin.update(core)
        success, plugin = Plugin.init(core, parameters=parameters)
        
        if success:
            core.commit()
            self._plugins[name] = plugin
        
        return success, plugin
    
    def _is_plugin_supported(self, version):
        version = packaging.version.parse(version)
        # same major, lesser or equal to current
        return version.major == self.version.major and self.version >= version
    
    def load_plugins(self):
        self._plugin_ctors.update(self.config.load_plugins())
        for Plugin in self._plugin_ctors.values():
            if self._is_plugin_supported(Plugin.required_hoordu):
                self._init_plugin(Plugin)
        
        return self.plugins
    
    def load_plugin(self, name, parameters=None):
        plugin = self._plugins.get(name)
        if plugin is not None:
            return True, plugin
        
        Plugin = self._plugin_ctors.get(name)
        if Plugin is not None:
            return self._init_plugin(Plugin, parameters)
        
        # try to search for new plugins, then try initializing it again
        self._plugin_ctors.update(self.config.load_plugins())
        
        Plugin = self._plugin_ctors.get(name)
        if Plugin is not None:
            return self._init_plugin(Plugin, parameters)
        
        raise ValueError('plugin {} does not exist'.format(name))
    
    @property
    def plugins(self):
        return dict(self._plugins)
    
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
