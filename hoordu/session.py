from collections.abc import Callable, Awaitable
from typing import Coroutine, Type
import contextlib
import pathlib
import shutil
import os
from typing import Optional
import logging

from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from .config import *
from .models import *
from .models.sql import SqlStatement
from .util import *
from .plugins import *
from .plugins.wrapper import PluginWrapper
from .thumbnailers import generate_thumbnail


class HoorduSession:
    def __init__(self, hoordu):
        self.hoordu = hoordu
        self.log: logging.Logger = hoordu.log
        
        self.engine = create_async_engine(self.hoordu.settings.database,
            echo=self.hoordu.settings.get('debug', False),
            #isolation_level='AUTOCOMMIT' # TODO find a better way to do this
        )
        self._sessionmaker = sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )
        
        self.raw = self._sessionmaker()
        self.priority = self._sessionmaker()
        self._plugins: dict[str, PluginWrapper] = {}
        
        self._callbacks: list[tuple[Callable[['HoorduSession', bool], Awaitable], bool, bool]] = []
        self._stack: contextlib.AsyncExitStack = contextlib.AsyncExitStack()
    
    async def __aenter__(self):
        async with contextlib.AsyncExitStack() as stack:
            await stack.enter_async_context(self.raw)
            await stack.enter_async_context(self.priority)
            self._stack = stack.pop_all()
        return self
    
    async def __aexit__(self, exc_type, exc, tb):
        try:
            #await self.priority.commit()
            
            if exc is None:
                await self.commit()
                
            else:
                await self.rollback()
        
        finally:
            await self._stack.__aexit__(exc_type, exc, tb)
            await self.engine.dispose()
            self._stack = contextlib.AsyncExitStack()
        
        return False
    
    async def plugin(self, plugin_id: str | Type[PluginBase]) -> PluginWrapper:
        plugin_name: str
        if isinstance(plugin_id, str):
            plugin_name = plugin_id
        else:
            plugin_name = plugin_id.id
        
        plugin = self._plugins.get(plugin_name)
        if plugin is not None:
            return plugin
        
        # load plugin if it wasn't loaded before
        Plugin = await self.hoordu.load_plugin(plugin_id)
        
        plugin = await self._stack.enter_async_context(PluginWrapper(self, Plugin))
        self._plugins[plugin_name] = plugin
        return plugin
    
    def callback(self,
        callback: Callable[['HoorduSession', bool], Awaitable],
        on_commit: bool = False,
        on_rollback: bool = False
    ):
        self._callbacks.append((callback, on_commit, on_rollback))
    
    def add(self, *args: Base) -> None:
        return self.raw.add_all(args)
    
    async def flush(self) -> None:
        await self.raw.flush()
    
    async def refresh(self, *args, **kwargs) -> None:
        return await self.raw.refresh(*args, **kwargs)
    
    async def delete(self, instance: Base) -> None:
        def delete_file(sess, is_commit):
            files = self.hoordu.get_file_paths(instance)
            for f in files:
                path = pathlib.Path(f)
                path.unlink(missing_ok=True)
        
        if isinstance(instance, File):
            self.callback(wrap_async(delete_file), on_commit=True)
        
        await self.raw.delete(instance)
    
    async def commit(self):
        await self.raw.commit()
        
        for callback, on_commit, _ in self._callbacks:
            if on_commit:
                try:
                    await callback(self, True)
                    
                except Exception:
                    self.hoordu.log.exception('callback error during commit')
        
        self._callbacks.clear()
    
    async def rollback(self) -> None:
        await self.raw.rollback()
        
        for callback, _, on_rollback in self._callbacks:
            if on_rollback:
                try:
                    await callback(self, False)
                    
                except Exception:
                    self.hoordu.log.exception('callback error during rollback')
        
        self._callbacks.clear()
    
    def stream(self, *args, **kwargs):
        return self.raw.stream(*args, **kwargs)
    
    def stream_scalars(self, *args, **kwargs):
        return self.raw.stream_scalars(*args, **kwargs)
    
    def execute(self, *args, **kwargs):
        return self.raw.execute(*args, **kwargs)
    
    def select(self, *args, **kwargs):
        return SqlStatement(self.raw, select(*args, **kwargs))
    
    
    async def import_file(self,
        file: File,
        path: str,
        move: bool = False
    ) -> None:
        mvfun: Callable[[str, str], Awaitable[None]] = wrap_async(shutil.move if move else shutil.copy)
        
        file.hash = await md5(path)
        file.mime = await mime_from_file(path)
        suffixes = pathlib.Path(path).suffixes
        if len(suffixes):
            file.ext = suffixes[-1][1:20]
        else:
            file.ext = None
        
        file.thumb_ext = 'jpg'
        
        dst, tdst = self.hoordu.get_file_paths(file)
        
        await mkpath(pathlib.Path(dst).parent)
        await mvfun(path, dst)
        os.chmod(dst, self.hoordu.config.settings.perms)
        file.present = True
        
        await mkpath(pathlib.Path(tdst).parent)
        has_thumbnail = False
        try:
            has_thumbnail = await generate_thumbnail(dst, tdst, file.mime)
            
        except Exception as e:
            self.log.exception('failed to generate a thumbnail')
            pass
        
        if has_thumbnail:
            os.chmod(tdst, self.hoordu.config.settings.perms)
            file.thumb_present = True
            
        else:
            file.thumb_ext = None
        
        self.add(file)
        await self.commit()
