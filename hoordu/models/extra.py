from typing import Optional, Iterator

from enum import IntEnum

from ..config import Dynamic


class BlockType(IntEnum):
    text = 1
    file = 2


class BlogBlock(dict):
    @property
    def type(self) -> str:
        return self['t']
    @type.setter
    def type(self, t) -> None:
        self['t'] = t
    
    @property
    def value(self) -> str:
        return self['v']
    @value.setter
    def value(self, v) -> None:
        self['v'] = v


class BlogComment:
    def __init__(self, json: Optional[str] = None):
        self._comment: Dynamic
        if json is not None:
            self._comment = Dynamic.from_json(json)
            self._comment.blocks = [BlogBlock(b) for b in self._comment.blocks]
        else:
            self._comment = Dynamic()
            self._comment.blocks = []
        
        self.blocks: list[BlogBlock] = self._comment.blocks
    
    def to_json(self) -> str:
        # could compress the blocks here (concat text blocks)
        return self._comment.to_json()
    
    def append_text(self, text: str) -> None:
        self.blocks.append(BlogBlock({'t': BlockType.text, 'v': text}))
    
    def append_file(self, metadata: str) -> None:
        self.blocks.append(BlogBlock({'t': BlockType.file, 'v': metadata}))
    
    def __getitem__(self, idx: int) -> BlogBlock:
        return self._comment.blocks[idx]
    
    def __iter__(self) -> Iterator[BlogBlock]:
        return iter(self._comment.blocks)

