import os
from pathlib import Path
import logging

import importlib.util
from importlib.machinery import SourceFileLoader

class _config_module(object):
    def __init__(self, filename=None):
        if filename is not None:
            self.__name = Path(filename).name
            module_name = self.__name.split('.')[0]
            # force the file to be loaded as source
            loader = SourceFileLoader(module_name, filename)
            spec = importlib.util.spec_from_loader(module_name, loader)
            self.__module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.__module)
            
        else:
            self.__module = object()
    
    def __getattr__(self, name):
        try:
            return getattr(self.__module, name)
        except AttributeError:
            raise AttributeError('config {} has no attribute {}'.format(repr(self.__name), repr(name)))
    
    def get(self, name, default=None):
        return getattr(self.__module, name, default)


def load_config(filename=None, env=None):
    if filename is not None:
        path = filename
        
    elif env is not None:
        envpath = os.environ.get(env, None)
        if envpath is not None:
            path = envpath
    
    else:
        raise TypeError('both filename and env are None')
    
    return _config_module(path)


def get_logger(name, filename=None, level=logging.WARNING):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter('[%(asctime)s] %(name)s | %(levelname)s | %(message)s', '%Y-%m-%d %H:%M:%S')
    
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    
    logger.addHandler(console)
    
    if filename is not None:
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        
        file = logging.FileHandler(filename)
        file.setLevel(level)
        file.setFormatter(formatter)
        
        logger.addHandler(file)
    
    return logger


