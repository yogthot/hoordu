
from .fields import *
from ..config import Dynamic

__all__ = [
    'Form',
    'Section'
]

class Form:
    def __init__(self, label, *entries):
        self.label = label
        self.entries = [self._parse_entry(entry) for entry in entries]
        self._entries = {entry.id: entry for entry in self.entries if entry.id}
    
    @staticmethod
    def _parse_entry(entry):
        if isinstance(entry, tuple):
            id, entry = entry
            if not id.startswith('_'):
                entry.id = id
        return entry
    
    def __getitem__(self, key):
        return self._entries[key]
    
    def clear(self):
        for entry in self.entries:
            entry.clear()
    
    def fill(self, values):
        for id, value in values.items():
            try: self._entries[id].fill(value)
            except KeyError: pass
    
    def validate(self):
        return all([entry.validate() for entry in self.entries])
    
    @property
    def errors(self):
        return {entry.id: entry.errors for entry in self.entries if entry.errors}
    
    @property
    def value(self):
        return Dynamic({entry.id: entry.value for entry in self.entries if hasattr(entry, 'value')})

class Section(Form):
    def __init__(self, label, *entries, id=None):
        super().__init__(label, *entries)
        self.id = id
