from . import models
from .util import *
from .manager import manager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

class hoordu(object):
    def __init__(self, config):
        self.config = config
        
        self.engine = create_engine(self.config.database, echo=self.config.get('debug', False))
        self._Session = sessionmaker(bind=self.engine)
        
        self.managers = {}
        self.manager = self.get_manager()
        
        self.logger = self.manager.logger
    
    def create_all(self):
        self.logger.info('creating all relations in the database')
        models.Base.metadata.create_all(self.engine)
    
    def get_manager(self, name='hoordu'):
        mgr = self.managers.get(name)
        if mgr is not None:
            return mgr
        else:
            mgr = manager(name, self.config, self._Session())
            self.managers[name] = mgr
            return mgr
