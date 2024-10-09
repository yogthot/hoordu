import json
import os
from pathlib import Path
from typing import Any, Union

import importlib
import importlib.util
import importlib.machinery

class GenericEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, set):
            return list(o)
        
        return super().default(o)

class Dynamic(dict):
    def __getattr__(self, name: str) -> Any:
        if name in self:
            val = self[name]
            if isinstance(val, dict):
                val = Dynamic(val)
            return val
        else:
            raise AttributeError
    
    def __setattr__(self, name: str, value: Any):
        self[name] = value
    
    def contains(self, *keys: str) -> bool:
        return all(self.get(key) is not None for key in keys)
    
    def contains_path(self, *path: str) -> bool:
        cur = self
        for sect in path:
            cur = cur.get(sect)
            if cur is None:
                return False
        
        return True
    
    def get_path(self, *path: str, default: Any = None) -> Any:
        cur = self
        for sect in path:
            cur = cur.get(sect)
            if cur is None:
                return None
        
        return cur
    
    def to_json(self) -> str:
        return json.dumps(self, separators=(',', ':'), cls=GenericEncoder)
    
    def to_file(self, filename: str | os.PathLike) -> None:
        with open(filename, 'w+') as json_file:
            json.dump(self, json_file)
    
    @classmethod
    def from_module(cls, filename: str | os.PathLike) -> Any:
        module_name = '_hoordu_config.' + Path(filename).name.split('.')[0]
        module = importlib.machinery.SourceFileLoader(module_name, str(filename)).load_module()
        
        return cls((k, getattr(module, k)) for k in dir(module) if not k.startswith('_'))
    
    @classmethod
    def from_json(cls, json_string: str | bytes | None) -> Any:
        if json_string is None:
            return cls()
        
        return json.loads(json_string, object_hook=cls)
    
    @classmethod
    def from_file(cls, filename: str | os.PathLike) -> Any:
        with open(filename) as json_file:
            s = json.load(json_file, object_hook=cls)
        
        if not isinstance(s, cls):
            raise ValueError('json file is not an object')
        
        return s
