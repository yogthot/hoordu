import os
from pathlib import Path
import json
import logging

import importlib.util
from importlib.machinery import SourceFileLoader


class Dynamic(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError
    
    def __setattr__(self, name, value):
        self[name] = value
    
    def contains(self, *keys):
        return set(keys).issubset(self)
    
    def defined(self, *keys):
        return all(self.get(key) is not None for key in keys)
    
    def to_json(self):
        return json.dumps(self)
    
    def to_file(self, filename):
        with open(filename) as json_file:
            return json.dump(self)
    
    @classmethod
    def from_module(cls, filename):
        module_name = '_config.' + Path(filename).name.split('.')[0]
        # force the file to be loaded as source code
        loader = SourceFileLoader(module_name, filename)
        spec = importlib.util.spec_from_loader(module_name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        
        return cls((k, getattr(module, k)) for k in dir(module) if not k.startswith('_'))
    
    @classmethod
    def from_json(cls, json_string):
        if json_string is None:
            return cls()
        
        s = json.loads(json_string, object_hook=cls)
        
        if not isinstance(s, cls):
            raise ValueError('json string is not an object')
        
        return s
    
    @classmethod
    def from_file(cls, filename):
        with open(filename) as json_file:
            s = json.load(json_file, object_hook=cls)
        
        if not isinstance(s, cls):
            raise ValueError('json string is not an object')
        
        return s


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


