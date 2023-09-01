from collections.abc import Callable, Awaitable
from typing import Type
import contextlib
import pathlib
import shutil
import os
import stat

from sqlalchemy import select

from .config import *
from .models import *
from .models.sql import SqlStatement
from .util import *
from .plugins import *
from .http.requests import DefaultRequestManager, Response


class HoorduSession:
    def __init__(self, hoordu):
        self.hoordu: hoordu = hoordu
        self.raw = hoordu._sessionmaker()
        self.priority = hoordu._sessionmaker()
        self._plugins: dict[str, PluginBase] = {}
        
        self.requests: DefaultRequestManager = DefaultRequestManager()
        self.requests.headers['User-Agent'] = self.hoordu.useragent
        
        self._callbacks: list[tuple[Callable[['HoorduSession', bool], Awaitable], bool, bool]] = []
        self._stack: contextlib.AsyncExitStack | None = None
    
    async def __aenter__(self):
        async with contextlib.AsyncExitStack() as stack:
            await stack.enter_async_context(self.requests)
            await stack.enter_async_context(self.raw)
            await stack.enter_async_context(self.priority)
            self._stack = stack.pop_all()
        return self
    
    async def __aexit__(self, exc_type, exc, tb):
        try:
            await self.priority.commit()
            
            if exc is None:
                await self.commit()
                
            else:
                await self.rollback()
        
        finally:
            await self._stack.__aexit__(exc_type, exc, tb)
            self._stack = None
        
        return False
    
    async def plugin(self, plugin_id: str | Type[PluginBase]) -> PluginBase:
        if not isinstance(plugin_id, str) and issubclass(plugin_id, PluginBase):
            # when passing a plugin class, Plugin_cls is that class and plugin_id is its id
            plugin_id = plugin_id.id
        
        plugin = self._plugins.get(plugin_id)
        if plugin is not None:
            return plugin
        
        # load plugin if it wasn't loaded before
        Plugin = await self.hoordu.load_plugin(plugin_id)
        
        plugin = await self._stack.enter_async_context(Plugin(self))
        self._plugins[plugin_id] = plugin
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
    
    
    async def download(self, *args, **kwargs) -> tuple[str, Response]:
        return await self.requests.download(*args, **kwargs)
    
    async def request(self, *args, **kwargs) -> Response:
        return await self.requests.request(*args, **kwargs)
    
    
    async def import_file(self,
        file: File,
        orig: str = None,
        thumb: str = None,
        move: bool = False
    ) -> None:
        mvfun = wrap_async(shutil.move if move else shutil.copy)
        
        if orig is not None:
            file.hash = await md5(orig)
            file.mime = await mime_from_file(orig)
            suffixes = pathlib.Path(orig).suffixes
            if len(suffixes):
                file.ext = suffixes[-1][1:20]
            else:
                file.ext = None
        
        if thumb is not None:
            suffixes = pathlib.Path(thumb).suffixes
            if len(suffixes):
                file.thumb_ext = suffixes[-1][1:20]
            else:
                file.thumb_ext = None
        
        dst, tdst = self.hoordu.get_file_paths(file)
        
        if orig is not None:
            await mkpath(pathlib.Path(dst).parent)
            await mvfun(orig, dst)
            os.chmod(dst, self.hoordu.config.settings.perms)
            file.present = True
            self.add(file)
        
        if thumb is not None:
            await mkpath(pathlib.Path(tdst).parent)
            await mvfun(thumb, tdst)
            os.chmod(tdst, self.hoordu.config.settings.perms)
            file.thumb_present = True
            self.add(file)
