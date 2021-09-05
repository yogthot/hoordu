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
        with open(filename, 'w+') as json_file:
            json.dump(self, json_file)
    
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

class HoorduConfig:
    def __init__(self, home):
        self.home = Path(home)
        self.settings = Dynamic.from_module(str(self.home / 'hoordu.conf'))
        # path -> plugin
        self._plugins = {}
    
    def _load_module(self, path):
        module_name = '_hoordu_plugin.' + path.name.split('.')[0]
        spec = importlib.util.spec_from_file_location(module_name, str(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    
    def load_plugins(self):
        plugin_scripts = [p.resolve() for p in (self.home / 'plugins').glob('*.py')]
        errors = {}
        for script in plugin_scripts:
            if script not in self._plugins:
                try:
                    Plugin = self._load_module(script).Plugin
                    self._plugins[script] = Plugin
                except Exception as e:
                    errors[script] = e
        
        return {p.name: p for p in self._plugins.values()}, errors


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

def load_config():
    paths = []
    env_path = os.environ.get('HOORDU_HOME', None)
    
    if env_path is not None:
        paths.append(env_path)
    
    paths.extend([
        Path('~/.config/hoordu').expanduser().resolve(),
        Path('/etc/hoordu').resolve(),
    ])
    
    for path in paths:
        try:
            return HoorduConfig(path)
        except Exception:
            pass
    
    raise FileNotFoundError('no configuration file found')

