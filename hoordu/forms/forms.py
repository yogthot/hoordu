from typing import Any, TypeVar

from .fields import *
from ..dynamic import Dynamic

__all__ = [
    'Form',
    'OAuthForm',
    'Section',
]

Entry = TypeVar('Entry', FormEntry, 'Section')

class Form:
    def __init__(self,
        label: str,
        *entries: Entry | tuple[str, Entry]
    ):
        self.label: str = label
        self.entries: list[Entry] = [self._parse_entry(entry) for entry in entries]
        self._entries: dict[str, Entry] = {entry.id: entry for entry in self.entries if entry.id}
    
    @staticmethod
    def _parse_entry(entry: Entry | tuple[str, Entry]) -> Entry:
        if isinstance(entry, tuple):
            identifier, entry = entry
            if not identifier.startswith('_'):
                entry.id = identifier
        return entry
    
    def __getitem__(self, key: str) -> Entry:
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

# this acts as a FormEntry as well, what do
class Section(Form):
    def __init__(self,
        label: str,
        *entries: Entry,
        identifier: str = None
    ):
        super().__init__(label, *entries)
        self.id: str = identifier
