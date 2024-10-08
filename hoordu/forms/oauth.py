from typing import Any, TypeVar

from .fields import *
from ..dynamic import Dynamic

__all__ = [
    'OAuthForm'
]

class OAuthForm:
    def __init__(self, label: str, url: str):
        self.label: str = label
        self.url: str = url
        self.entries: list[str] = []
        self._entries: Dynamic = Dynamic()
    
    def __getitem__(self, key: str) -> str:
        return self._entries[key]
    
    def clear(self) -> None:
        self._entries = Dynamic()
    
    def fill(self, values) -> None:
        self._entries.update(values)
    
    def validate(self) -> bool:
        return len(self._entries) > 0
    
    @property
    def value(self) -> Dynamic:
        return self._entries
