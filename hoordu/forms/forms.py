from typing import Any, TypeVar

from .fields import *
from ..dynamic import Dynamic

__all__ = [
    'Form'
]


class Form:
    def __init__(self,
        label: str,
        *entries: FormEntry | tuple[str, FormEntry]
    ):
        self.label: str = label
        self.entries: list[FormEntry] = [self._parse_entry(entry) for entry in entries]
        self._entries: dict[str, FormEntry] = {entry.id: entry for entry in self.entries if entry.id}
    
    @staticmethod
    def _parse_entry(entry: FormEntry | tuple[str, FormEntry]) -> FormEntry:
        if isinstance(entry, tuple):
            identifier, entry = entry
            if not identifier.startswith('_'):
                entry.id = identifier
        return entry
    
    def __getitem__(self, key: str) -> FormEntry:
        return self._entries[key]
    
    def clear(self) -> None:
        for entry in self.entries:
            entry.clear()
    
    def fill(self, values: dict[str, Any]) -> None:
        for identifier, value in values.items():
            try: self._entries[identifier].fill(value)
            except KeyError: pass
    
    def validate(self) -> bool:
        return all([entry.validate() for entry in self.entries])
    
    @property
    def errors(self) -> dict[str, list[str]]:
        return {entry.id: entry.errors for entry in self.entries if entry.errors}
    
    @property
    def value(self) -> Dynamic:
        return Dynamic({entry.id: entry.value for entry in self.entries if hasattr(entry, 'value')})

