from . import models
from .util import *
from .config import get_logger
from .plugins import plugin_core

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import logging

class hoordu:
    def __init__(self, config):
        self.config = config
        
        self.engine = create_engine(self.config.database, echo=self.config.get('debug', False))
        self._Session = sessionmaker(bind=self.engine)
        
        self.session = self._Session()
        
        name = 'hoordu'
        log_file = template_format(self.config.get('log_file'), name=name)
        self.logger = get_logger(name, log_file, self.config.get('log_level', logging.WARNING))
        
        self.plugin_cores = {}
        self.plugins = {}
        
        self.filespath = '{}/files'.format(self.config.base_path)
        self.thumbspath = '{}/thumbs'.format(self.config.base_path)
    
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
            c = plugin_core(name, self, session)
            
            self.plugin_cores[name] = c
            return c
    
    def init_plugin(self, Plugin, parameters):
        name = Plugin.name
        
        plugin = self.plugins.get(name)
        if plugin is not None:
            return True, plugin
        
        core = self._get_plugin_core(name)
        success, plugin = Plugin.init(core, parameters=parameters)
        
        if success:
            self.plugins[name] = plugin
        
        return success, plugin
    
    def _file_bucket(self, file):
        return file.id // self.config.files_bucket_size
    
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
