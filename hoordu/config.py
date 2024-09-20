import os
import re
import json
from pathlib import Path
from typing import Type, Optional

import importlib
import importlib.util
import importlib.machinery

from .dynamic import Dynamic
from .plugins import PluginBase

__all__ = [
    'HoorduConfig',
    'load_config'
]

class HoorduConfig:
    PLUGIN_FILE_REGEX = re.compile('^(?P<plugin_id>[^\.]+)\.py$', re.IGNORECASE)
    
    def __init__(self, home):
        self.home: Path = Path(home)
        self.settings: Dynamic = Dynamic.from_module(str(self.home / 'hoordu.conf'))
        
        self.plugins: dict[str, Type[PluginBase]] = dict()
        self._plugin_path: Path = (self.home / 'plugins').resolve()
        self._plugin_package: str = '_hoordu_plugin'
        
        self._load_init()
    
    def _load_init(self) -> None:
        init_file = self._plugin_path / '__init__.py'
        
        if not init_file.exists():
            init_file.parent.mkdir(parents=True, exist_ok=True)
            init_file.touch()
        
        importlib.machinery.SourceFileLoader(self._plugin_package, str(init_file)).load_module()
    
    def load_plugin(self, plugin_id: str) -> Type[PluginBase]:
        module = importlib.import_module(f'{self._plugin_package}.{plugin_id}')
        return module.Plugin
    
    def load_plugins(self) -> tuple[dict[str, Type[PluginBase]], dict[str, Exception]]:
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

def load_config() -> HoorduConfig:
    paths = []
    env_path = os.environ.get('HOORDU_HOME', None)
    
    if env_path is not None:
        paths.append(Path(env_path).expanduser().resolve())
    
    xdg_config_home = os.environ.get('XDG_CONFIG_HOME', None)
    if xdg_config_home is not None:
        user_config_path = Path(xdg_config_home)
    else:
        user_config_path = Path('~/.config').expanduser().resolve()
    
    paths.extend([
        user_config_path / 'hoordu',
        Path('/etc/hoordu').resolve(),
    ])
    
    for path in paths:
        try:
            return HoorduConfig(path)
        except FileNotFoundError:
            pass
    
    raise FileNotFoundError('no configuration file found')

