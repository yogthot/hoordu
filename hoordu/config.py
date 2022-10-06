import os
import re
import json
from pathlib import Path

import importlib
import importlib.util
import importlib.machinery

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
        return json.dumps(self, separators=(',', ':'))
    
    def to_file(self, filename):
        with open(filename, 'w+') as json_file:
            json.dump(self, json_file)
    
    @classmethod
    def from_module(cls, filename):
        module_name = '_hoordu_config.' + Path(filename).name.split('.')[0]
        module = importlib.machinery.SourceFileLoader(module_name, filename).load_module()
        
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
    PLUGIN_FILE_REGEX = re.compile('^(?P<plugin_id>[^\.]+)\.py$', re.IGNORECASE)
    
    def __init__(self, home):
        self.home = Path(home)
        self.settings = Dynamic.from_module(str(self.home / 'hoordu.conf'))
        
        self.plugins = {}
        self._plugin_path = (self.home / 'plugins').resolve()
        self._plugin_package = '_hoordu_plugin'
        
        self._load_init()
    
    def _load_init(self):
        init_file = self._plugin_path / '__init__.py'
        
        if not init_file.exists():
            init_file.touch()
        
        importlib.machinery.SourceFileLoader(self._plugin_package, str(init_file)).load_module()
    
    def load_plugin(self, plugin_id):
        module = importlib.import_module(f'{self._plugin_package}.{plugin_id}')
        return module.Plugin
    
    def load_plugins(self):
        errors = {}
        
        for script in self._plugin_path.iterdir():
            match = self.PLUGIN_FILE_REGEX.match(script.name)
            if not match:
                continue
            
            plugin_id = match.group('plugin_id')
            if plugin_id in self.plugins:
                continue
            
            # load new valid plugins
            try:
                module = importlib.import_module(f'{self._plugin_package}.{plugin_id}')
                Plugin = module.Plugin
                
                Plugin.id = plugin_id
                self.plugins[Plugin.id] = Plugin
                
            except Exception as e:
                errors[plugin_id] = e
        
        return self.plugins, errors

def load_config():
    paths = []
    env_path = os.environ.get('HOORDU_HOME', None)
    
    if env_path is not None:
        paths.append(Path(env_path).expanduser().resolve())
    
    paths.extend([
        Path('~/.config/hoordu').expanduser().resolve(),
        Path('/etc/hoordu').resolve(),
    ])
    
    for path in paths:
        try:
            return HoorduConfig(path)
        except FileNotFoundError:
            pass
    
    raise FileNotFoundError('no configuration file found')

