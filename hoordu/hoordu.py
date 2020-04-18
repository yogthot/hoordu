from . import models
from .util import *
from .core import core

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

class hoordu(object):
    def __init__(self, config):
        self.config = config
        
        self.engine = create_engine(self.config.database, echo=self.config.get('debug', False))
        self._Session = sessionmaker(bind=self.engine)
        
        self.cores = {}
        self.core = self._core()
        self.logger = self.core.logger
        
        self.plugins = {}
    
    def _core(self, name='hoordu'):
        c = self.cores.get(name)
        if c is not None:
            return c
        else:
            c = core(name, self.config, self._Session())
            self.cores[name] = c
            return c
    
    def create_all(self):
        self.logger.info('creating all relations in the database')
        models.Base.metadata.create_all(self.engine)
    
    def init_plugin(self, Plugin, parameters):
        name = Plugin.name
        
        plugin = self.plugins.get(name)
        if plugin is not None:
            return True, plugin
        
        core = self._core(name)
        success, plugin = Plugin.init(core, parameters=parameters)
        
        if success:
            self.plugins[name] = plugin
        
        return success, plugin
    
