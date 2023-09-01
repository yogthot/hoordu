
from functools import wraps
from sqlalchemy.dialects import postgresql

def _result(fun):
    @wraps(fun)
    async def wrapped(self, *args, **kwargs):
        result = await self._session.stream_scalars(self._statement)
        result_fun = getattr(result, fun.__name__)
        return await result_fun()
    
    return wrapped

class SqlStatement:
    def __init__(self, session, statement):
        self._session = session
        self._statement = statement
    
    def _clone(self, statement=None):
        if statement is not None:
            return self.__class__(self._session, statement)
        else:
            return self.__class__(self._session, self._statement)
    
    def __getattr__(self, attr):
        fun = getattr(self._statement, attr)
        if not callable(fun):
            return fun
        
        @wraps(fun)
        def wrapper(*args, **kwargs):
            statement = fun(*args, **kwargs)
            return self._clone(statement)
        
        return wrapper
    
    def execute(self):
        return self._session.execute(self._statement)
    
    
    async def stream(self):
        return await self._session.stream_scalars(self._statement)
    
    
    @_result
    async def all(self): ...
    
    @_result
    async def first(self): ...
    @_result
    async def one_or_none(self): ...
    @_result
    async def one(self): ...
    
    def __str__(self):
        return str(self._statement.compile(dialect=postgresql.dialect()))
