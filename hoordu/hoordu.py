from typing import Type

from . import models
from .config import *
from .session import HoorduSession
from .plugins import *
from .plugins.filesystem import Filesystem
from . import _version

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import packaging.version

import logging

class hoordu:
    def __init__(self, config: HoorduConfig):
        self.version: packaging.version.Version = packaging.version.parse(_version.__version__)
        self.useragent: str = f'{_version.__fulltitle__}/{_version.__version__}'
        
        self.config: HoorduConfig = config
        self.settings: Dynamic = config.settings
        
        self.engine = create_async_engine(self.settings.database, echo=self.settings.get('debug', False))
        self._sessionmaker = sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )
        self._session: HoorduSession = HoorduSession(self)
        
        # global initializer
        configure_logger('hoordu', self.settings.get('log_file'))
        
        self.log: logging.Logger = logging.getLogger('hoordu.hoordu')
        
        self._plugins: dict[str, Type[PluginBase]] = dict()
        self._plugins_ready: dict[str, bool] = dict()
        
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
    
    def _file_bucket(self, file: File) -> int:
        return file.id // self.settings.files_bucket_size
    
    def _get_plugin(self,
        identifier: str | Type[PluginBase]
    ) -> Type[PluginBase] | None:
        if not isinstance(identifier, str) and issubclass(identifier, PluginBase):
            return identifier
            
        else:
            return self._plugins.get(identifier)
    
    def _is_plugins_ready(self, identifier: str | Type[PluginBase]) -> bool:
        if not isinstance(identifier, str) and issubclass(identifier, PluginBase):
            identifier = identifier.id
        
        return self._plugins_ready.get(identifier, False)
    
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

    def _is_plugin_supported(self, version: str) -> bool:
        version = packaging.version.parse(version)
        # same major, greater or equal to current
        return version.major == self.version.major and self.version >= version
    
    async def _setup_plugin(self,
        Plugin_cls: Type[PluginBase],
        parameters: Dynamic = None
    ) -> tuple[bool, Form | None]:
        if not self._is_plugin_supported(Plugin_cls.required_hoordu):
            raise ValueError(f'plugin {Plugin_cls.id} is unsupported')
        
        async with self._session as session:
            # create source
            source = await session.select(Source) \
                    .where(Source.name == Plugin_cls.name) \
                    .one_or_none()
            
            source_exists = source is not None
            if not source_exists:
                source = Source(name=Plugin_cls.name)
                session.add(source)
                await session.flush()
            
            # create plugin
            plugin = await session.select(Plugin) \
                    .where(Plugin.name == Plugin_cls.id) \
                    .one_or_none()
            
            if plugin is None:
                plugin = Plugin(name=Plugin_cls.id, version=0, source=source)
                session.add(plugin)
                await session.flush()
            
            # preferred plugin
            if not source_exists:
                source.preferred_plugin = plugin
                session.add(source)
                await session.flush()
            
            await Plugin_cls.update(session)
            success, form = await Plugin_cls.setup(session, parameters=parameters)
            await session.commit()
        
            if success:
                if Plugin_cls.id not in self._plugins:
                    self._plugins[Plugin_cls.id] = Plugin_cls
                
                self._plugins_ready[Plugin_cls.id] = True
            
            return success, form
    
    async def parse_url(self, url: str) -> list[tuple[Type[SimplePlugin], str | Dynamic]]:
        plugins = []
        
        for identifier, Plugin_cls in self._plugins.items():
            if issubclass(Plugin_cls, SimplePlugin):
                options = await Plugin_cls.parse_url(url)
                if options is not None:
                    plugins.append((Plugin_cls, options))
        
        return plugins
    
    async def setup_plugin(self,
        identifier: str | Type[PluginBase],
        parameters: Optional[Dynamic] = None
    ) -> tuple[bool, Form | None]:
        Plugin_cls = self._get_plugin(identifier)
        if Plugin_cls is not None:
            return await self._setup_plugin(Plugin_cls, parameters)
        
        # check for new plugins
        ctors, errors = self.config.load_plugins()
        self._plugins.update(ctors)
        
        Plugin_cls = self._get_plugin(identifier)
        if Plugin_cls is not None:
            return await self._setup_plugin(Plugin_cls, parameters)
        
        # check if this plugin failed to load
        exc = errors.get(identifier)
        if exc is not None:
            raise ValueError(f'plugin {identifier} failed to load') from exc
        
        raise ValueError(f'plugin {identifier} does not exist')
    
    async def load_plugin(self, identifier: str | Type[PluginBase]) -> Type[PluginBase]:
        if not self._is_plugins_ready(identifier):
            success, _ = await self.setup_plugin(identifier)
            if not success:
                raise ValueError(f'plugin {identifier} needs to be setup before use')
        
        return self._get_plugin(identifier)
    
    def session(self) -> HoorduSession:
        return HoorduSession(self)
