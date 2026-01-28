from typing import Type

from . import models
from .models import *
from .config import *
from .dynamic import Dynamic
from .session import HoorduSession
from .plugins import *
from .forms import *
from .logging import *
from .plugins.filesystem import Filesystem
from . import _version

import packaging.version
from typing import Optional

import logging

__all__ = [
    'hoordu',
    'load_config'
]

class hoordu:
    def __init__(self, config: HoorduConfig):
        self.version: packaging.version.Version = packaging.version.parse(_version.__version__)
        self.useragent: str = f'{_version.__fulltitle__}/{_version.__version__}'
        
        self.config: HoorduConfig = config
        self.settings: Dynamic = config.settings
        
        useragent = self.settings.get('useragent')
        if useragent is not None:
            self.useragent = useragent
        
        # global initializer
        configure_logger('hoordu', self.settings.get('log_file'))
        self.log: logging.Logger = logging.getLogger('hoordu.hoordu')
        
        self._session: HoorduSession = HoorduSession(self)
        
        self._plugins: dict[str, Type[PluginBase]] = dict()
        
        self.filespath: str = '{}/files'.format(self.settings.base_path)
        self.thumbspath: str = '{}/thumbs'.format(self.settings.base_path)
        
        self._plugins[Filesystem.id] = Filesystem
        
        # load plugin classes
        ctors, errors = self.config.load_plugins()
        self._plugins.update(ctors)
    
    @staticmethod
    async def create_all(config: HoorduConfig) -> None:
        log = logging.getLogger('hoordu.hoordu')
        log.info('creating all relations in the database')
        
        settings = config.settings
        engine = create_async_engine(settings.database, echo=settings.get('debug', False))
        async with engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        
        await engine.dispose()
    
    def _file_bucket(self, file: File) -> int:
        return file.id // self.settings.files_bucket_size
    
    def get_file_paths(self, file: File) -> tuple[str, str]:
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
    
    async def _create_plugin(self,
        plugin_class: Type[PluginBase],
        parameters: Optional[Dynamic] = None
    ) -> tuple[bool, Form | None]:
        async with self._session as session:
            # create source
            source = await session.select(Source) \
                    .where(Source.name == plugin_class.source) \
                    .one_or_none()
            
            source_exists = source is not None
            if not source_exists:
                source = Source(name=plugin_class.source)
                session.add(source)
                await session.flush()
            
            # create plugin
            plugin = await session.select(Plugin) \
                    .where(Plugin.name == plugin_class.id) \
                    .one_or_none()
            
            if plugin is None:
                plugin = Plugin(name=plugin_class.id, version=0, source=source)
                session.add(plugin)
                await session.flush()
            
            # preferred plugin
            if not source_exists:
                source.preferred_plugin = plugin
                session.add(source)
                await session.flush()
            
            config = Dynamic.from_json(plugin.config)
            
            success, form = await plugin_class.setup(config, parameters)
            
            plugin.config = config.to_json()
            session.add(plugin)
            await session.commit()
        
            if success:
                if plugin_class.id not in self._plugins:
                    self._plugins[plugin_class.id] = plugin_class
            
            return success, form
    
    async def parse_url(self, url: str) -> list[tuple[Type[PluginBase], str | Dynamic]]:
        plugins = []
        
        for identifier, plugin_class in self._plugins.items():
            options = await plugin_class.parse_url(url)
            if options is not None:
                plugins.append((plugin_class, options))
        
        return plugins
    
    async def setup_plugin(self,
        identifier: str | Type[PluginBase],
        parameters: Optional[Dynamic] = None
    ) -> tuple[bool, Form | None]:
        if isinstance(identifier, str):
            plugin_class = self._plugins.get(identifier)
            plugin_id = identifier
            
            if plugin_class is None:
                ctors, errors = self.config.load_plugins()
                self._plugins.update(ctors)
                
                # check if this plugin failed to load
                exc = errors.get(identifier)
                if exc is not None:
                    raise ValueError(f'plugin {plugin_id} failed to load') from exc
                
                plugin_class = self._plugins.get(identifier)
                
                if plugin_class is None:
                    raise ValueError(f'plugin {plugin_id} does not exist')
            
        else:
            plugin_class = identifier
            plugin_id = plugin_class.id
        
        return await self._create_plugin(plugin_class, parameters)
    
    async def load_plugin(self, identifier: str | Type[PluginBase]) -> Type[PluginBase]:
        if isinstance(identifier, str):
            plugin = self._plugins.get(identifier)
            plugin_id = identifier
        else:
            plugin = identifier
            plugin_id = plugin.id
        
        if plugin is None:
            raise ValueError(f'plugin {plugin_id} does not exist')
        
        success, _ = await self.setup_plugin(identifier)
        if not success:
            raise ValueError(f'plugin {plugin_id} needs to be setup before use')
        
        return plugin
    
    async def reload_plugins(self):
        ctors, errors = self.config.load_plugins()
        self._plugins.update(ctors)
        for plugin_class in self._plugins.values():
            await self._create_plugin(plugin_class)
    
    def session(self) -> HoorduSession:
        return HoorduSession(self)
