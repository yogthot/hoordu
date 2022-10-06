
from enum import IntEnum, IntFlag, auto

from ..config import Dynamic


class BlockType(IntEnum):
    text = 1
    file = 2

class BlogBlock(dict):
    @property
    def type(self):
        return self['t']
    @type.setter
    def type(self, t):
        self['t'] = t
    
    @property
    def value(self):
        return self['v']
    @value.setter
    def value(self, v):
        self['v'] = v

class BlogComment:
    def __init__(self, json=None):
        if json is not None:
            self._comment = Dynamic.from_json(json)
            self._comment.blocks = [BlogBlock(b) for b in self._comment.blocks]
        else:
            self._comment = Dynamic()
            self._comment.blocks = []
        
        self.blocks = self._comment.blocks
    
    def to_json(self):
        # could compress the blocks here (concat text blocks)
        return self._comment.to_json()
    
    def append_text(self, text):
        self.blocks.append(BlogBlock({'t': BlockType.text, 'v': text}))
    
    def append_file(self, metadata):
        self.blocks.append(BlogBlock({'t': BlockType.file, 'v': metadata}))
    
    def __getitem__(self, idx):
        return self._comment.blocks[idx]
    
    def __iter__(self):
        return iter(self._comment.blocks)

